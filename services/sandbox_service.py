"""
代码沙箱执行服务
在独立子进程中安全执行 Python 代码，设置资源限制
"""

import os
import sys
import uuid
import time
import json
import shutil
import subprocess
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# ── 全局进程管理 ────────────────────────────────────────────────────────────

_active_processes = {}
_process_lock = threading.Lock()

# 执行器：最多同时运行3个代码任务
_executor = ThreadPoolExecutor(max_workers=3)

# 超时配置（秒）
EXEC_TIMEOUT = 120  # 2分钟
MAX_OUTPUT_LINES = 2000


class ExecutionResult:
    """代码执行结果"""
    def __init__(self, success=True, stdout='', stderr='', error=None,
                 metrics=None, exit_code=0, duration=0.0):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.error = error
        self.metrics = metrics or {}
        self.exit_code = exit_code
        self.duration = duration

    def to_dict(self):
        return {
            'success': self.success,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'error': self.error,
            'result': self.metrics,
            'exit_code': self.exit_code,
            'duration': self.duration
        }

    @staticmethod
    def from_dict(d):
        return ExecutionResult(
            success=d.get('success', False),
            stdout=d.get('stdout', ''),
            stderr=d.get('stderr', ''),
            error=d.get('error'),
            metrics=d.get('result', {}),
            exit_code=d.get('exit_code', -1),
            duration=d.get('duration', 0.0)
        )


def run_code_async(code, filename='script.py', course='face',
                   job_id=None, callback=None):
    """
    异步执行代码，结果通过回调返回
    """
    if job_id is None:
        job_id = str(uuid.uuid4())[:8]

    future = _executor.submit(_execute_code, code, filename, course, job_id)
    future._job_id = job_id

    if callback:
        def on_done(f):
            result = f.result()
            callback(result)
        future.add_done_callback(on_done)

    return job_id


def _execute_code(code, filename, course, job_id):
    """
    在子进程中执行代码，返回 ExecutionResult
    """
    start_time = time.time()
    tmp_dir = None

    try:
        # ── 安全检查 ──────────────────────────────────────────────
        if not code or not code.strip():
            return ExecutionResult(
                success=False,
                error='代码不能为空',
                duration=time.time() - start_time
            )

        # 危险API黑名单（与 routes/editor.py 的 EDITOR_FORBIDDEN 对齐）
        # 文件类 API 若在 Web 路由中执行应配合路径沙箱；此处单独调用沙箱服务时仍禁止误用 shutil 等
        forbidden = [
            'os.system', 'subprocess.', 'os.popen', 'pty.',
            'eval(', 'exec(',
            'open("/', "open('/", "open(\"'", "open('\"",
            'shutil.rmtree', 'shutil.move', 'shutil.copy', 'shutil.copytree',
            '__import__', '__builtins__["__import__"]', "__builtins__['__import__']",
            'requests.', 'urllib', 'urllib2', 'urllib3', 'socket.',
            'pickle.load', 'torch.load',
            'sys.exit', 'sys.path.remove', 'sys.modules.pop',
            'ctypes.', 'fcntl.', 'resource.',
            'threading.', 'multiprocessing.',
        ]

        for kw in forbidden:
            if kw in code:
                return ExecutionResult(
                    success=False,
                    error=f'安全限制：禁止使用 "{kw}"',
                    duration=time.time() - start_time
                )

        # 静态语法检查
        try:
            compile(code, filename, 'exec')
        except SyntaxError as e:
            return ExecutionResult(
                success=False,
                error=f'语法错误: {e.msg} (第 {e.lineno} 行)',
                stderr=f'  File "{filename}", line {e.lineno}\n    {e.text}',
                duration=time.time() - start_time
            )

        # ── 创建临时执行环境 ────────────────────────────────────────
        tmp_dir = os.path.join(
            os.path.dirname(__file__), '..', 'data', 'editor', job_id
        )
        os.makedirs(tmp_dir, exist_ok=True)

        script_path = os.path.join(tmp_dir, filename)
        output_path = os.path.join(tmp_dir, 'result.json')

        # 包装代码：捕获输出和指标
        wrapped = _build_wrapper(code, output_path)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(wrapped)

        # ── 执行 ──────────────────────────────────────────────────
        proc = subprocess.Popen(
            [sys.executable or 'python', script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=tmp_dir,
            text=True,
            env={
                **os.environ,
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTHONUNBUFFERED': '1',
                'OMP_NUM_THREADS': '1',
                'MKL_NUM_THREADS': '1',
            }
        )

        with _process_lock:
            _active_processes[job_id] = proc

        try:
            stdout, stderr = proc.communicate(timeout=EXEC_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return ExecutionResult(
                success=False,
                error=f'执行超时（{EXEC_TIMEOUT}秒）',
                stderr=stderr,
                stdout=stdout,
                duration=time.time() - start_time
            )
        finally:
            with _process_lock:
                _active_processes.pop(job_id, None)

        # 限制输出行数
        stdout_lines = stdout.split('\n')
        if len(stdout_lines) > MAX_OUTPUT_LINES:
            stdout = '\n'.join(stdout_lines[:MAX_OUTPUT_LINES]) + \
                    f'\n... (输出已截断，共 {len(stdout_lines)} 行)'

        # ── 解析结果 ──────────────────────────────────────────────
        result_data = {}
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)
            except (json.JSONDecodeError, ValueError):
                pass

        stdout_from_wrap = result_data.get('stdout', '')
        metrics = result_data.get('result', {})
        error_from_wrap = result_data.get('error', '')

        if error_from_wrap:
            return ExecutionResult(
                success=False,
                error=error_from_wrap,
                stderr=stderr,
                stdout=stdout_from_wrap,
                metrics=metrics,
                exit_code=proc.returncode,
                duration=time.time() - start_time
            )

        return ExecutionResult(
            success=(proc.returncode == 0),
            stdout=stdout_from_wrap or stdout,
            stderr=stderr,
            metrics=metrics,
            exit_code=proc.returncode,
            duration=time.time() - start_time
        )

    except FileNotFoundError:
        return ExecutionResult(
            success=False,
            error='Python 解释器未找到，请联系系统管理员',
            duration=time.time() - start_time
        )
    except PermissionError:
        return ExecutionResult(
            success=False,
            error='权限不足，无法执行代码',
            duration=time.time() - start_time
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return ExecutionResult(
            success=False,
            error=f'执行异常: {type(e).__name__}: {e}',
            stderr=tb,
            duration=time.time() - start_time
        )
    finally:
        # 清理临时目录
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


def _build_wrapper(code, output_path):
    """构建包装代码，捕获 stdout/stderr 和训练指标

    使用 json.dumps 安全注入用户代码，避免三引号冲突。
    """
    import json
    code_json = json.dumps(code)
    output_json = json.dumps(output_path)
    return r'''
import sys
import json
import io

# 捕获 stdout
_stdout_buffer = io.StringIO()
_stderr_buffer = io.StringIO()
sys.stdout = _stdout_buffer
sys.stderr = _stderr_buffer

_result = {}
_error = ""
_exec_globals = {}
_exec_locals = {}

try:
    _user_code = json.loads(''' + code_json + r''')
    exec(_user_code, _exec_globals, _exec_locals)

    # 自动提取常见指标
    for _k in ['accuracy', 'acc', 'f1', 'f1_score', 'precision', 'recall',
                'loss', 'rmse', 'mae', 'train_time', 'time', 'score']:
        if _k in _exec_globals:
            try: _result[_k] = float(_exec_globals[_k])
            except: pass
        if _k in _exec_locals:
            try: _result[_k] = float(_exec_locals[_k])
            except: pass

except Exception as _e:
    import traceback
    _error = str(_e)
    sys.stderr = _stderr_buffer
    traceback.print_exc()

sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

_output_data = {
    "stdout": _stdout_buffer.getvalue(),
    "error": _error,
    "result": _result
}

try:
    with open(''' + output_json + r''', 'w', encoding='utf-8') as _f:
        json.dump(_output_data, _f, ensure_ascii=False)
except Exception:
    pass
'''


def stop_process(job_id):
    """停止指定任务"""
    with _process_lock:
        proc = _active_processes.get(job_id)
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            _active_processes.pop(job_id, None)
            return True
    return False


def stop_all():
    """停止所有运行中的任务"""
    with _process_lock:
        for job_id, proc in list(_active_processes.items()):
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        _active_processes.clear()


def get_active_jobs():
    """获取当前活跃的任务列表"""
    with _process_lock:
        return list(_active_processes.keys())


def list_pretrained_models():
    """
    列出预训练模型库中的可用模型
    返回: [{name, path, description, size}]
    """
    models_dir = os.path.join(os.path.dirname(__file__), '..', 'models', 'pretrained')
    models = []

    if not os.path.exists(models_dir):
        return models

    for root, dirs, files in os.walk(models_dir):
        for f in files:
            if f.endswith(('.h5', '.pth', '.pt', '.pkl', '.joblib', '.keras')):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, models_dir)
                size = os.path.getsize(full_path)
                size_str = _format_size(size)

                name = os.path.splitext(f)[0]
                category = os.path.basename(os.path.dirname(rel_path))

                models.append({
                    'name': name,
                    'file': f,
                    'path': f'/models/pretrained/{rel_path}',
                    'category': category,
                    'size': size_str,
                    'size_bytes': size
                })

    return models


def _format_size(size_bytes):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f'{size_bytes:.1f}{unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f}TB'
