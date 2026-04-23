"""
AI 代码编辑器路由
提供代码执行、模板管理、代码提交等 API
"""

import os
import re
import json
import uuid
import time
import subprocess
import threading
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session, current_app, Response

from config import Config

# 导入登录验证装饰器
from routes.auth import login_required

editor_bp = Blueprint('editor', __name__, url_prefix='/editor')

# 存储当前正在运行的进程（进程ID -> Process对象）
_running_processes = {}
_running_lock = threading.Lock()

# 静态黑名单：文件创建/删除由运行时沙箱限制在「小组工作目录」内，故不再禁止 os.makedirs 等
EDITOR_FORBIDDEN = [
    'os.system', 'subprocess.', 'os.popen', 'pty.',
    'eval(', 'exec(',
    'shutil.rmtree', 'shutil.move', 'shutil.copy', 'shutil.copytree',
    '__import__', '__builtins__["__import__"]', "__builtins__['__import__']",
    'requests.', 'urllib', 'socket.',
    'pickle.load', 'torch.load',
    'sys.exit', 'sys.path.remove', 'sys.modules.pop',
    'ctypes.', 'fcntl.', 'resource.',
    'threading.', 'multiprocessing.',
]


def _editor_forbidden_error(code: str):
    """若命中黑名单返回错误文案，否则返回 None。"""
    for kw in EDITOR_FORBIDDEN:
        if kw in code:
            return f'安全限制：禁止使用 "{kw}"'
    return None


def _safe_group_id():
    """与 save_code 一致：从 session 取小组标识并净化为目录名。"""
    gid = session.get('group_id', session.get('user_id', 'G01'))
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(gid))


def _ensure_group_workspace() -> str:
    """
    返回当前登录用户对应小组的沙箱工作目录（绝对路径），不存在则创建。
    输入/输出：无参数；返回 str 绝对路径。
    """
    root = os.path.abspath(Config.EDITOR_WORKSPACE_ROOT)
    ws = os.path.join(root, _safe_group_id())
    os.makedirs(ws, exist_ok=True)
    return ws


def _get_python_cmd():
    """
    获取代码执行用的 Python 解释器路径。
    优先级：环境变量 EDITOR_PYTHON_CMD > 当前 Flask 进程的 Python > 'python'
    """
    env_val = os.environ.get('EDITOR_PYTHON_CMD', '').strip()
    if env_val:
        return env_val
    try:
        import sys as _sys
        if _sys.executable and os.path.isfile(_sys.executable):
            return _sys.executable
    except Exception:
        pass
    return 'python'

# ── 页面路由 ────────────────────────────────────────────────────────────────

@editor_bp.route('/editor')
@login_required
def index():
    """编辑器主页面"""
    course = request.args.get('course', 'face')
    return render_template('editor.html', course=course)


# ── 代码执行 ─────────────────────────────────────────────────────────────────

@editor_bp.route('/run', methods=['POST'])
@login_required
def run_code():
    """
    执行用户提交的 Python 代码
    在独立子进程中运行，设置资源限制（CPU时间、内存）
    """
    data = request.get_json()
    code = data.get('code', '')
    filename = data.get('filename', 'untitled.py')

    if not code.strip():
        return jsonify({'error': '代码不能为空'})

    fb = _editor_forbidden_error(code)
    if fb:
        return jsonify({
            'error': fb,
            'errors': [{'severity': 'error', 'message': fb}],
        })

    # 清理语法错误（静态检查）
    errors = []
    try:
        compile(code, filename, 'exec')
    except SyntaxError as e:
        errors.append({
            'severity': 'error',
            'message': e.msg,
            'file': filename,
            'line': e.lineno or 1
        })
        return jsonify({'error': f'语法错误: {e.msg}', 'errors': errors})

    # 生成临时文件
    job_id = str(uuid.uuid4())[:8]
    tmp_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'editor', job_id)
    os.makedirs(tmp_dir, exist_ok=True)

    script_path = os.path.join(tmp_dir, filename)
    output_path = os.path.join(tmp_dir, 'output.json')
    workspace_root = _ensure_group_workspace()

    # 包装代码：沙箱路径限制 + 捕获 stdout，输出 JSON 结果
    wrapped_code = _wrap_code(code, output_path, tmp_dir, workspace_root)
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(wrapped_code)

    # 在子进程中执行（超时60秒；cwd=小组目录，相对路径写入均落在此目录）
    python_cmd = _get_python_cmd()
    try:
        proc = subprocess.Popen(
            [python_cmd, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace_root,
            text=True,
            env={
                **os.environ,
                'PYTHONDONTWRITEBYTECODE': '1',
                'EDITOR_WORKSPACE': workspace_root,
            },
        )

        with _running_lock:
            _running_processes[job_id] = proc

        try:
            stdout, stderr = proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            _cleanup(job_id, tmp_dir)
            return jsonify({
                'error': '执行超时（300秒），请优化代码或减少数据量',
                'errors': [{'severity': 'error', 'message': '执行超时'}]
            })
        finally:
            with _running_lock:
                _running_processes.pop(job_id, None)

        _cleanup(job_id, tmp_dir)

        # 解析输出结果
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)
                return jsonify({
                    'stdout': result_data.get('stdout', ''),
                    'result': result_data.get('result', {}),
                    'errors': []
                })
            except (json.JSONDecodeError, ValueError):
                pass

        # 回退：返回原始输出
        output_text = stdout
        if stderr:
            stderr_lines = stderr.split('\n')
            syntax_errors = []
            for line in stderr_lines:
                m = re.match(r'  File "(.*?)", line (\d+), in (.*?)\s*(.*)', line)
                if m:
                    syntax_errors.append({
                        'severity': 'error',
                        'message': line,
                        'file': m.group(1),
                        'line': int(m.group(2))
                    })

            if syntax_errors:
                return jsonify({
                    'error': '运行时错误',
                    'traceback': stderr,
                    'errors': syntax_errors
                })

            # 普通 stderr
            output_text += '\n' + stderr

        return jsonify({
            'stdout': output_text,
            'result': _extract_metrics_from_stdout(output_text),
            'errors': []
        })

    except FileNotFoundError:
        _cleanup(job_id, tmp_dir)
        python_cmd = _get_python_cmd()
        return jsonify({'error': f'Python 解释器未找到：「{python_cmd}」，请检查 config.py 中的 EDITOR_PYTHON_CMD 配置', 'errors': []})
    except Exception as e:
        _cleanup(job_id, tmp_dir)
        return jsonify({'error': f'执行异常: {str(e)}', 'errors': []})


@editor_bp.route('/run-stream', methods=['POST'])
def run_code_stream():
    """
    流式执行：yield 实时 stdout 行，前端可边执行边显示训练日志。
    请求体同 /run，返回 data: text/event-stream 流。
    """
    import queue

    data = request.get_json()
    code = data.get('code', '')
    filename = data.get('filename', 'untitled.py')

    if not code.strip():
        return jsonify({'error': '代码不能为空'}), 400

    fb = _editor_forbidden_error(code)
    if fb:
        return jsonify({'error': fb}), 400

    try:
        compile(code, filename, 'exec')
    except SyntaxError as e:
        return jsonify({'error': f'语法错误: {e.msg}'}), 400

    job_id = str(uuid.uuid4())[:8]
    tmp_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'editor', job_id)
    os.makedirs(tmp_dir, exist_ok=True)

    script_path = os.path.join(tmp_dir, filename)
    output_path = os.path.join(tmp_dir, 'output.json')
    workspace_root = _ensure_group_workspace()

    wrapped_code = _wrap_code(code, output_path, tmp_dir, workspace_root)
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(wrapped_code)

    python_cmd = _get_python_cmd()
    try:
        proc = subprocess.Popen(
            [python_cmd, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace_root,
            text=True,
            bufsize=1,  # 行缓冲
            env={
                **os.environ,
                'PYTHONDONTWRITEBYTECODE': '1',
                'EDITOR_WORKSPACE': workspace_root,
            },
        )
    except FileNotFoundError:
        _cleanup(job_id, tmp_dir)
        return 'event: error\ndata: Python解释器未找到\n\n', 500

    def generate():
        """实时读取子进程 stdout，每行 yield SSE 事件。"""
        try:
            for line in proc.stdout:
                # 跳过流式标记行本身（仅作为触发器，不输出给前端）
                if '\x00STREAM\x00' in line:
                    continue
                yield f'data: {line}'
            proc.stdout.close()
        except Exception:
            pass

        # 读取剩余 stderr
        stderr = ''
        try:
            stderr = proc.stderr.read()
            proc.stderr.close()
        except Exception:
            pass
        exitcode = proc.wait()

        # 读取完整 output.json
        result = {}
        stdout_all = ''
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)
                stdout_all = result_data.get('stdout', '')
                result = result_data.get('result', {})
            except Exception:
                pass

        import urllib.parse
        stdout_enc = urllib.parse.quote(stdout_all)
        yield f'event: done\ndata: {stdout_enc}\n\n'
        if stderr or exitcode != 0:
            err_enc = urllib.parse.quote(stderr)
            yield f'event: error\ndata: {err_enc}\n\n'

        _cleanup(job_id, tmp_dir)

    return Response(generate(), mimetype='text/event-stream')


def _wrap_code(code, output_path, tmp_dir, workspace_root):
    """将用户代码包装为可实时流式输出的脚本。

    策略：每 50 行 print 输出一次 stream 标记 + 当前缓冲区内容，
    使前端可以边执行边显示训练进度/日志。执行完毕后再写 output.json 收尾。
    """
    import json

    code_json_src = repr(json.dumps(code, ensure_ascii=False))
    out_path_src  = repr(os.path.abspath(output_path))
    sandbox = _sandbox_prologue(os.path.abspath(workspace_root), os.path.abspath(tmp_dir))

    # 流式输出标记（前端按此截取实时日志）
    STREAM_MARK = '\x00STREAM\x00'

    return '# -*- coding: utf-8 -*-\n' + sandbox + f'''
import sys, json, io

class _FlushWriter(io.TextIOBase):
    """实时写入+刷新，每次写入后自动 flush，使子进程 stdout 立即可见。"""
    def __init__(self, underlying):
        super().__init__()
        self._buf = io.StringIO()
        self._under = underlying
    def write(self, s):
        self._buf.write(s)
        self._under.write(s)
        self._under.flush()
        return len(s)
    def flush(self):
        self._under.flush()
    def getvalue(self):
        return self._buf.getvalue()

_old_stdout = sys.stdout
sys.stdout  = _FlushWriter(sys.stdout)

_exec_globals = {{}}
_stream_count = 0

def _maybe_stream():
    global _stream_count
    _stream_count += 1
    if _stream_count % 50 == 0:           # 每 50 次 write 调用输出一次 stream
        sys.stdout.write('\\n' + STREAM_MARK + sys.stdout.getvalue() + STREAM_MARK + '\\n')
        sys.stdout.flush()

try:
    _user_code = json.loads({code_json_src})

    # 注入 _maybe_stream 到 sys.stdout.write 链路上
    _orig_write = sys.stdout.write
    def _patched_write(s):
        r = _orig_write(s)
        _maybe_stream()
        return r
    sys.stdout.write = _patched_write

    exec(_user_code, _exec_globals)

    sys.stdout = _old_stdout
    stdout_content = sys.stdout.getvalue() if hasattr(sys.stdout, 'getvalue') else ''

    result = {{}}
    for _k in ['accuracy', 'acc', 'f1', 'f1_score', 'rmse', 'mae', 'loss']:
        if _k in _exec_globals:
            try: result[_k] = float(_exec_globals[_k])
            except Exception: pass

    output_data = {{
        'stdout': stdout_content,
        'result': result
    }}

    with open({out_path_src}, 'w', encoding='utf-8') as _f:
        json.dump(output_data, _f, ensure_ascii=False)

    print('\\n[DONE]' + json.dumps({{'result': result}}))

except Exception as _e:
    import traceback
    sys.stdout = _old_stdout
    print('[执行错误] ' + type(_e).__name__ + ': ' + str(_e), file=sys.stderr)
    traceback.print_exc()
'''


def _sandbox_prologue(workspace_root: str, tmp_dir: str) -> str:
    """生成注入到子进程的路径沙箱代码（字符串）。"""
    ws = os.path.abspath(workspace_root)
    td = os.path.abspath(tmp_dir)
    return f'''
import os as _edb_os
import builtins as _edb_builtins

_edb_WS = {repr(ws)}
_edb_TMP = {repr(td)}


def _edb_fspath(p):
    try:
        return _edb_os.fspath(p)
    except Exception:
        return p


def _edb_allowed(p):
    if p is None:
        return False
    try:
        p = _edb_fspath(p)
        if not isinstance(p, str):
            return False
        ap = _edb_os.path.abspath(p)
    except Exception:
        return False
    for root in (_edb_WS, _edb_TMP):
        if not root:
            continue
        if ap == root or ap.startswith(root + _edb_os.sep):
            return True
    return False


_real_makedirs = _edb_os.makedirs


def _edb_makedirs(name, mode=0o777, exist_ok=False):
    if not _edb_allowed(name):
        raise PermissionError(
            "[编辑器沙箱] 只能在小组工作目录内创建文件夹。当前工作目录已是小组目录，请使用相对路径，"
            "例如 os.makedirs('models', exist_ok=True)，勿使用盘符根路径或 /models。工作目录: "
            + _edb_WS)
    return _real_makedirs(name, mode=mode, exist_ok=exist_ok)


_edb_os.makedirs = _edb_makedirs

_real_mkdir = _edb_os.mkdir


def _edb_mkdir(path, mode=0o777, exist_ok=False, *, dir_fd=None):
    """兼容 os.mkdir(path, mode) / os.mkdir(path) 调用形式。"""
    if dir_fd is not None:
        raise PermissionError("[编辑器沙箱] 不支持 dir_fd")
    if not _edb_allowed(path):
        raise PermissionError("[编辑器沙箱] 只能在小组工作目录内创建目录: " + _edb_WS)
    return _real_mkdir(path, mode)


_edb_os.mkdir = _edb_mkdir

_real_remove = _edb_os.remove


def _edb_remove(path, *, dir_fd=None):
    if dir_fd is not None:
        raise PermissionError("[编辑器沙箱] 不支持 dir_fd")
    if not _edb_allowed(path):
        raise PermissionError("[编辑器沙箱] 只能删除工作目录内的文件: " + _edb_WS)
    return _real_remove(path)


_edb_os.remove = _edb_remove
_edb_os.unlink = _edb_remove

_real_rmdir = _edb_os.rmdir


def _edb_rmdir(path, *, dir_fd=None):
    if dir_fd is not None:
        raise PermissionError("[编辑器沙箱] 不支持 dir_fd")
    if not _edb_allowed(path):
        raise PermissionError("[编辑器沙箱] 只能删除工作目录内的空目录: " + _edb_WS)
    return _real_rmdir(path)


_edb_os.rmdir = _edb_rmdir

_real_rename = _edb_os.rename


def _edb_rename(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
    if src_dir_fd is not None or dst_dir_fd is not None:
        raise PermissionError("[编辑器沙箱] 不支持 dir_fd")
    if not _edb_allowed(src) or not _edb_allowed(dst):
        raise PermissionError("[编辑器沙箱] 重命名仅限工作目录内: " + _edb_WS)
    return _real_rename(src, dst)


_edb_os.rename = _edb_rename

_real_replace = _edb_os.replace


def _edb_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
    if src_dir_fd is not None or dst_dir_fd is not None:
        raise PermissionError("[编辑器沙箱] 不支持 dir_fd")
    if not _edb_allowed(src) or not _edb_allowed(dst):
        raise PermissionError("[编辑器沙箱] 替换文件仅限工作目录内: " + _edb_WS)
    return _real_replace(src, dst)


_edb_os.replace = _edb_replace

_real_open = _edb_builtins.open


def _edb_is_write_mode(mode):
    if isinstance(mode, int):
        return bool(mode & (_edb_os.O_CREAT | _edb_os.O_TRUNC | _edb_os.O_APPEND
                            | _edb_os.O_WRONLY | _edb_os.O_RDWR))
    if not isinstance(mode, str):
        return True
    s = mode.lower().replace("b", "").replace("t", "")
    if s in ("r",):
        return False
    return True


def _edb_open(file, mode="r", *args, **kwargs):
    if isinstance(file, int):
        return _real_open(file, mode, *args, **kwargs)
    # 解析文件路径（支持 pathlib.Path）
    try:
        resolved = _edb_os.fspath(file)
    except Exception:
        resolved = file
    # devnull 相关路径放行（dill、TensorFlow 等第三方库会用到）
    devnull_names = (_edb_os.devnull, 'nul', '/dev/null')
    if resolved in devnull_names:
        return _real_open(file, mode, *args, **kwargs)
    # 写模式：必须落在小组工作目录或本次临时目录
    if _edb_is_write_mode(mode):
        if not _edb_allowed(file):
            raise PermissionError(
                "[编辑器沙箱] 写入文件仅限小组工作目录（及本次运行临时目录）。"
                "请使用相对路径保存模型/数据。工作目录: " + _edb_WS)
    return _real_open(file, mode, *args, **kwargs)


_edb_builtins.open = _edb_open
'''


def _extract_metrics_from_stdout(stdout):
    """从 stdout 中提取训练指标"""
    result = {}
    patterns = {
        'accuracy': r'验证集准确率[:：]\s*([0-9.]+)',
        'f1': r'F1[:：]\s*([0-9.]+)',
        'time': r'训练时间[:：]\s*([0-9.]+)s',
    }
    for key, pat in patterns.items():
        m = re.search(pat, stdout)
        if m:
            result[key] = float(m.group(1))
    return result


def _cleanup(job_id, tmp_dir):
    """清理临时文件"""
    try:
        import shutil
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


# ── 停止执行 ─────────────────────────────────────────────────────────────────

@editor_bp.route('/stop', methods=['POST'])
@login_required
def stop_code():
    """停止当前运行的代码"""
    with _running_lock:
        for job_id, proc in list(_running_processes.items()):
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            _running_processes.pop(job_id, None)
    return jsonify({'success': True, 'message': '已停止所有运行中的代码'})


# ── 代码保存 ─────────────────────────────────────────────────────────────────

@editor_bp.route('/save', methods=['POST'])
@login_required
def save_code():
    """保存用户代码到服务器"""
    data = request.get_json()
    code = data.get('code', '')
    filename = data.get('filename', 'untitled.py')
    course = data.get('course', 'face')
    template = data.get('template', 'unknown')

    # 获取小组ID（从session或默认）
    group_id = session.get('group_id', session.get('user_id', 'G01'))
    safe_group = re.sub(r'[^a-zA-Z0-9_]', '_', str(group_id))

    save_dir = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'editor_codes',
        safe_group, course, template
    )
    os.makedirs(save_dir, exist_ok=True)

    safe_filename = os.path.basename(filename)
    if not safe_filename.endswith('.py'):
        safe_filename += '.py'

    save_path = os.path.join(save_dir, safe_filename)
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(code)

    return jsonify({
        'success': True,
        'path': f'/data/editor_codes/{safe_group}/{course}/{template}/{safe_filename}'
    })


# ── 模型保存 ─────────────────────────────────────────────────────────────────

@editor_bp.route('/save_model', methods=['POST'])
@login_required
def save_model():
    """
    保存训练后的模型到自定义模型库

    Request JSON:
    {
        "course": "face",
        "model_name": "我的表情模型",
        "model_path": "models/face_cnn_model.h5",
        "accuracy": 0.8523,
        "framework": "tensorflow",
        "auto_submit": true
    }
    """
    data = request.get_json()
    course = data.get('course', 'face')
    model_name = data.get('model_name', '')
    model_path = data.get('model_path', '')
    accuracy = data.get('accuracy', 0)

    if not model_name or not model_path:
        return jsonify({'success': False, 'error': '模型名称和路径不能为空'})

    group_id = session.get('group_id', session.get('user_id', 'G01'))
    group_name = session.get('group_name', session.get('username', '未知小组'))

    # 验证模型文件存在
    workspace_root = _ensure_group_workspace()
    full_model_path = os.path.join(workspace_root, model_path)
    if not os.path.exists(full_model_path):
        return jsonify({'success': False, 'error': f'模型文件不存在: {model_path}'})

    # 计算相对路径
    relative_path = os.path.join(_safe_group_id(), model_path)

    # 注册到自定义模型库
    from services.custom_model_service import (
        register_model,
        get_model_by_name,
        update_model,
        submit_to_leaderboard
    )

    # 检查是否已存在同名模型
    existing = get_model_by_name(group_id, model_name, course)

    if existing:
        # 更新现有模型
        model = update_model(existing['id'], {
            'accuracy': accuracy,
            'model_path': relative_path
        })
        action = 'updated'
        message = f'模型 "{model_name}" 已更新'
    else:
        # 注册新模型
        model = register_model(
            group_id=group_id,
            group_name=group_name,
            course=course,
            model_name=model_name,
            model_path=relative_path,
            accuracy=accuracy,
            framework=data.get('framework', 'tensorflow'),
            model_type='classification'
        )
        action = 'registered'
        message = f'模型 "{model_name}" 已保存到模型库'

    # 自动提交到排行榜
    leaderboard_result = None
    if accuracy > 0.5 and data.get('auto_submit', True):
        try:
            leaderboard_result = submit_to_leaderboard(
                group_id=group_id,
                group_name=group_name,
                course=course,
                accuracy=accuracy,
                model_id=model['id'],
                model_name=model_name
            )
        except Exception as e:
            pass

    return jsonify({
        'success': True,
        'action': action,
        'message': message,
        'model': model,
        'leaderboard': leaderboard_result
    })


# ── 代码提交 ─────────────────────────────────────────────────────────────────

@editor_bp.route('/submit', methods=['POST'])
@login_required
def submit_code():
    """
    提交代码参与排行榜评分（同时自动保存模型）

    Request JSON:
    {
        "code": "...",
        "course": "face",
        "template": "face_cnn",
        "model_name": "可选的模型名称",
        "save_model": true
    }
    """
    data = request.get_json()
    code = data.get('code', '')
    course = data.get('course', 'face')
    template = data.get('template', 'unknown')
    save_model_flag = data.get('save_model', True)
    model_name = data.get('model_name', f'{template}_v1')

    if not code.strip():
        return jsonify({'success': False, 'error': '代码不能为空'})

    fb = _editor_forbidden_error(code)
    if fb:
        return jsonify({'success': False, 'error': fb})

    group_id = session.get('group_id', session.get('user_id', 'G01'))
    group_name = session.get('group_name', session.get('username', '匿名小组'))

    job_id = str(uuid.uuid4())[:8]
    tmp_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'editor', job_id)
    os.makedirs(tmp_dir, exist_ok=True)
    workspace_root = _ensure_group_workspace()

    script_path = os.path.join(tmp_dir, 'submit.py')
    output_path = os.path.join(tmp_dir, 'output.json')

    wrapped_code = _wrap_code(code, output_path, tmp_dir, workspace_root)
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(wrapped_code)

    stdout, stderr = '', ''
    try:
        python_cmd = _get_python_cmd()
        proc = subprocess.Popen(
            [python_cmd, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace_root,
            text=True,
            env={
                **os.environ,
                'PYTHONDONTWRITEBYTECODE': '1',
                'EDITOR_WORKSPACE': workspace_root,
            },
        )
        stdout, stderr = proc.communicate(timeout=120)
    except Exception:
        _cleanup(job_id, tmp_dir)
        import random
        accuracy = round(random.uniform(0.55, 0.85), 4)
        rank = 0
        return jsonify({
            'success': True,
            'accuracy': accuracy,
            'rank': rank,
            'message': f'代码已提交（模拟评分: {accuracy:.2%}）'
        })

    # 先读取 output.json，再清理临时目录
    accuracy = 0.0
    result_data = {}
    model_path = None

    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
            accuracy = result_data.get('result', {}).get('accuracy', 0.0)
            # 尝试从输出中提取模型路径
            model_path = result_data.get('model_path')
        except Exception:
            pass

    _cleanup(job_id, tmp_dir)

    if accuracy == 0.0:
        accuracy = _extract_accuracy_from_stdout(stdout)

    # 尝试从代码中提取模型保存路径
    if not model_path:
        model_path = _extract_model_path_from_code(code)

    if accuracy > 0:
        # ── 保存模型到自定义模型库 ────────────────────────────────────────────
        model_info = None
        if save_model_flag and model_path:
            try:
                from services.custom_model_service import (
                    register_model,
                    get_model_by_name,
                    submit_to_leaderboard
                )
                relative_path = os.path.join(_safe_group_id(), model_path)
                existing = get_model_by_name(group_id, model_name, course)

                if existing:
                    from services.custom_model_service import update_model
                    model_info = update_model(existing['id'], {
                        'accuracy': accuracy,
                        'model_path': relative_path
                    })
                else:
                    model_info = register_model(
                        group_id=group_id,
                        group_name=group_name,
                        course=course,
                        model_name=model_name,
                        model_path=relative_path,
                        accuracy=accuracy
                    )
            except Exception:
                pass

        # 提交到排行榜
        leaderboard_result = None
        try:
            from services.leaderboard_service import submit_score
            course_key = 'emotion_face' if course == 'face' else 'eco_prediction'
            leaderboard_result = submit_score(
                course=course_key,
                group_id=str(group_id),
                group_name=str(group_name),
                accuracy=accuracy,
                correct=int(accuracy * 50),
                total=50,
                time_cost_minutes=5,
                config={'model_id': model_info.get('id') if model_info else None}
            )
        except Exception:
            pass

        rank = leaderboard_result.get('rank', 0) if leaderboard_result else 0

        return jsonify({
            'success': True,
            'accuracy': accuracy,
            'rank': rank,
            'model': model_info,
            'leaderboard': leaderboard_result,
            'message': f'提交成功！准确率: {accuracy:.2%}' + (f'，排名第{rank}' if rank else '')
        })
    else:
        return jsonify({
            'success': False,
            'error': '未能从代码中提取准确率指标，请确保代码中有验证集准确率输出'
        })


def _extract_model_path_from_code(code: str) -> str:
    """从代码中提取模型保存路径"""
    patterns = [
        r'model\.save\(["\']([^"\']+)["\']\)',
        r'model\.save\(["\']([^"\']+)["\']\)',
        r'SAVE_PATH\s*=\s*["\']([^"\']+)["\']',
        r'save_path\s*=\s*["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        import re
        m = re.search(pattern, code)
        if m:
            path = m.group(1)
            # 提取相对于小组目录的路径
            if path.startswith('./'):
                path = path[2:]
            elif path.startswith('/'):
                parts = path.split('/')
                # 跳过小组ID
                for i, part in enumerate(parts):
                    if part in ('G01', 'G02', 'G03', group_id if 'group_id' in dir() else ''):
                        path = '/'.join(parts[i+1:])
                        break
            return path
    return None


def _extract_accuracy_from_stdout(stdout):
    """从 stdout 提取准确率"""
    patterns = [
        r'验证集准确率[:：]\s*([0-9.]+)',
        r'准确率[:：]\s*([0-9.]+)',
        r'Accuracy[:：]\s*([0-9.]+)',
        r'accuracy[:= ]+([0-9.]+)',
    ]
    for pat in patterns:
        m = re.search(pat, stdout, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if val > 1:
                val /= 100
            return val
    return 0.0


# ── 小组沙箱工作目录（供前端展示路径说明）──────────────────────────────────────

@editor_bp.route('/workspace', methods=['GET'])
@login_required
def editor_workspace():
    """返回当前用户小组的代码运行工作目录（绝对路径）。"""
    path = _ensure_group_workspace()
    return jsonify({
        'workspace_abs': path,
        'workspace_root': os.path.abspath(Config.EDITOR_WORKSPACE_ROOT),
        'group': _safe_group_id(),
        'env_name': 'EDITOR_WORKSPACE',
        'hint': '运行代码时进程工作目录即 workspace_abs；请用相对路径保存模型/数据，例如 models/face_cnn_model.h5',
    })


@editor_bp.route('/read_file', methods=['GET'])
@login_required
def read_file():
    """读取工作空间中单个文件的内容（供文件树双击打开）"""
    rel_path = request.args.get('path', '').strip()
    # 必须为相对路径，不能包含 .. 或绝对路径
    if not rel_path or '..' in rel_path or rel_path.startswith('/') or rel_path.startswith('\\'):
        return jsonify({'error': '无效路径'}), 400

    ws_root = os.path.abspath(_ensure_group_workspace())
    file_path = os.path.abspath(os.path.join(ws_root, rel_path))

    # 禁止读取 ws_root 之外的文件
    if not file_path.startswith(ws_root):
        return jsonify({'error': '禁止访问该路径'}), 403

    if not os.path.isfile(file_path):
        return jsonify({'error': '文件不存在'}), 404

    # 限制大小 10MB
    if os.path.getsize(file_path) > 10 * 1024 * 1024:
        return jsonify({'error': '文件过大'}), 413

    try:
        content = open(file_path, 'r', encoding='utf-8', errors='replace').read()
        return jsonify({'content': content, 'path': rel_path})
    except Exception as e:
        return jsonify({'error': f'读取失败: {e}'}), 500


@editor_bp.route('/workspace_tree', methods=['GET'])
@login_required
def workspace_tree():
    """
    返回小组工作空间的目录结构（供文件树组件使用）
    特别包含小组标注数据的目录
    """
    group_id = session.get('group_id', session.get('user_id', 'G01'))  # 原始编号，用于 data 目录
    group_safe_id = _safe_group_id()  # 净化后的 ID，仅用于 workspace 目录
    course = request.args.get('course', 'face')

    def build_tree(root_path, rel_prefix=''):
        """递归构建目录树"""
        items = []
        try:
            for item in os.listdir(root_path):
                if item.startswith('.') or item.startswith('_'):
                    continue
                item_path = os.path.join(root_path, item)
                rel_path = os.path.join(rel_prefix, item) if rel_prefix else item

                if os.path.isdir(item_path):
                    children = build_tree(item_path, rel_path)
                    items.append({
                        'name': item,
                        'type': 'folder',
                        'path': rel_path,
                        'children': children
                    })
                else:
                    # 获取文件大小
                    size = os.path.getsize(item_path)
                    items.append({
                        'name': item,
                        'type': 'file',
                        'path': rel_path,
                        'size': size
                    })
        except PermissionError:
            pass
        return items

    # 构建基础工作空间树（用净化后的 ID）
    workspace_root = _ensure_group_workspace()
    workspace_tree = build_tree(workspace_root)

    # 检查是否有标注数据目录（用原始编号）
    emotion_data_dir = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'emotion_data', group_id
    )
    group_has_data = os.path.exists(emotion_data_dir) and any(
        f.endswith('.jpg') for f in os.listdir(emotion_data_dir)
    )

    # 检查标注数据数量
    data_count = 0
    by_emotion = {}
    if group_has_data:
        for f in os.listdir(emotion_data_dir):
            if f.endswith('.jpg'):
                data_count += 1
                # 统计各情绪数量
                parts = f.replace('.jpg', '').split('_')
                for part in parts:
                    if part in ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']:
                        by_emotion[part] = by_emotion.get(part, 0) + 1

    return jsonify({
        'group_id': group_id,
        'course': course,
        'workspace': workspace_tree,
        'has_annotation_data': group_has_data,
        'annotation_count': data_count,
        'annotation_by_emotion': by_emotion,
        'workspace_path': workspace_root
    })


# ── 数据集信息 ─────────────────────────────────────────────────────────────────

@editor_bp.route('/sync_group_data', methods=['POST'])
@login_required
def sync_group_data():
    """
    将小组采集的标注数据同步到编辑器工作空间
    包括：复制图片、生成CSV标签文件
    """
    from services.emotion_labels_service import sync_images_to_editor_workspace, get_group_data_summary

    group_id = session.get('group_id', session.get('user_id', 'G01'))

    # 同步数据
    result = sync_images_to_editor_workspace(group_id)

    return jsonify(result)


@editor_bp.route('/sync_audio_data', methods=['POST'])
@login_required
def sync_audio_data():
    """
    将小组采集的音频数据同步到编辑器工作空间
    包括：复制音频文件、生成CSV标签文件
    """
    from services.audio_labels_service import sync_audios_to_editor_workspace, get_group_audio_data_summary

    group_id = session.get('group_id', session.get('user_id', 'G01'))

    # 同步数据
    result = sync_audios_to_editor_workspace(group_id)

    return jsonify(result)


@editor_bp.route('/audio_data_info', methods=['GET'])
@login_required
def audio_data_info():
    """获取小组音频数据的信息"""
    from services.audio_labels_service import get_group_audio_data_summary

    group_id = session.get('group_id', session.get('user_id', 'G01'))
    info = get_group_audio_data_summary(group_id)

    return jsonify(info)


@editor_bp.route('/group_data_info', methods=['GET'])
@login_required
def group_data_info():
    """获取小组标注数据的信息"""
    from services.emotion_labels_service import get_group_data_summary

    group_id = session.get('group_id', session.get('user_id', 'G01'))
    info = get_group_data_summary(group_id)

    return jsonify(info)


def _count_workspace_csv_data_rows(csv_path: str) -> int:
    """统计 CSV 数据行数（减去表头一行）；文件不存在或为空则返回 0。"""
    if not os.path.isfile(csv_path):
        return 0
    try:
        import csv
        with open(csv_path, 'r', encoding='utf-8', errors='replace', newline='') as fp:
            rows = list(csv.reader(fp))
        if not rows:
            return 0
        return max(0, len(rows) - 1)
    except Exception:
        return 0


def _count_face_training_images(images_dir: str) -> tuple:
    """
    统计 face/images 下常见图片数量，并汇总文件名中的情绪关键词。
    返回 (total, by_emotion_dict)
    """
    _IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    total = 0
    by_emotion = {}
    if not os.path.isdir(images_dir):
        return 0, by_emotion
    try:
        for fname in os.listdir(images_dir):
            if fname.startswith('.'):
                continue
            low = fname.lower()
            if not low.endswith(_IMAGE_EXT):
                continue
            total += 1
            base = low.rsplit('.', 1)[0]
            for p in base.replace('-', '_').split('_'):
                if p in ('angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral'):
                    by_emotion[p] = by_emotion.get(p, 0) + 1
    except OSError:
        pass
    return total, by_emotion


@editor_bp.route('/dataset_info', methods=['GET'])
@login_required
def dataset_info():
    """
    从当前小组沙箱根目录统计「训练数据」，与文件树一致。
    _ensure_group_workspace() 已是 .../editor_workspaces/{group}/，下面直接接 face/、eco/ 等。
    """
    course = request.args.get('course', 'face')
    ws_root = os.path.abspath(_ensure_group_workspace())
    total_images = 0
    total_labels = 0
    by_emotion = {}
    description = ''

    if course == 'face':
        images_dir = os.path.join(ws_root, 'face', 'images')
        csv_path = os.path.join(ws_root, 'face', 'train_labels.csv')
        total_images, by_emotion = _count_face_training_images(images_dir)
        total_labels = _count_workspace_csv_data_rows(csv_path)
        if total_images > 0:
            description = f'📸 工作空间 face/images 下共 {total_images} 张训练图片'
        else:
            description = '💡 点击上方「同步表情数据」将标注图片复制到工作空间'
    elif course == 'eco':
        sensor_csv = os.path.join(ws_root, 'data', 'eco', 'sensor_data.csv')
        total_labels = _count_workspace_csv_data_rows(sensor_csv)
        total_images = 0
        description = (
            f'📈 传感器数据 {total_labels} 行（./data/eco/sensor_data.csv）'
            if total_labels
            else '💡 请在生态瓶页面采集数据后导入到工作空间'
        )
    else:
        description = '💡 当前课程暂无训练数据统计'

    info = {
        'course': course,
        'train_samples': total_images,
        'train_labels': total_labels,
        'train_samples_unit': '张',
        'train_labels_unit': '行' if course == 'eco' else '条',
        'test_samples': 0,
        'description': description,
        'group_has_data': total_images > 0 or total_labels > 0,
        'group_data_summary': by_emotion,
        'workspace_path': ws_root,
    }

    return jsonify(info)

@editor_bp.route('/upload_dataset', methods=['POST'])
@login_required
def upload_dataset():
    """接收用户上传的数据集文件"""
    course = request.form.get('course', 'face')
    group_id = session.get('group_id', session.get('user_id', 'G01'))

    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'error': '未选择文件'})

    upload_dir = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'editor_uploads',
        str(group_id), course
    )
    os.makedirs(upload_dir, exist_ok=True)

    saved_count = 0
    for f in files:
        if f.filename:
            safe_name = os.path.basename(f.filename)
            save_path = os.path.join(upload_dir, safe_name)
            f.save(save_path)
            saved_count += 1

    return jsonify({
        'success': True,
        'count': saved_count,
        'message': f'成功上传 {saved_count} 个文件'
    })


# ═══════════════════════════════════════════════════════════════════════════
# 预处理数据同步 API
# ═══════════════════════════════════════════════════════════════════════════

@editor_bp.route('/sync_face_preprocessed', methods=['POST'])
@login_required
def sync_face_preprocessed():
    """
    将表情预处理后的数据同步到编辑器工作空间
    预处理数据来源：data/emotion_preprocessed/{group_id}/
    目标位置：data/editor_workspaces/{group_id}/face/preprocessed/
    """
    from services.emotion_labels_service import _safe_group_id

    group_id = session.get('group_id', session.get('user_id', 'G01'))
    safe_id = _safe_group_id(group_id)

    workspace_root = Config.EDITOR_WORKSPACE_ROOT
    source_dir = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'emotion_preprocessed', group_id
    )
    target_dir = os.path.join(workspace_root, safe_id, 'face', 'preprocessed', 'images')
    target_csv = os.path.join(workspace_root, safe_id, 'face', 'preprocessed', 'train_labels.csv')

    if not os.path.exists(source_dir):
        return jsonify({
            'success': False,
            'error': '预处理目录不存在，请先进行数据预处理'
        })

    os.makedirs(target_dir, exist_ok=True)

    copied = 0
    try:
        for f in os.listdir(source_dir):
            if f.endswith(('.jpg', '.png', '.jpeg')):
                import shutil
                shutil.copy2(
                    os.path.join(source_dir, f),
                    os.path.join(target_dir, f)
                )
                copied += 1

        # 复制CSV标签文件
        source_csv = os.path.join(source_dir, 'train_labels.csv')
        if os.path.exists(source_csv):
            import shutil
            shutil.copy2(source_csv, target_csv)

        return jsonify({
            'success': True,
            'images_copied': copied,
            'csv_generated': os.path.exists(target_csv),
            'target_dir': target_dir
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@editor_bp.route('/sync_audio_preprocessed', methods=['POST'])
@login_required
def sync_audio_preprocessed():
    """
    将音频预处理后的数据同步到编辑器工作空间
    预处理数据来源：data/audio_preprocessed/{group_id}/
    目标位置：data/editor_workspaces/{group_id}/audio/preprocessed/
    """
    from services.audio_labels_service import _safe_group_id

    group_id = session.get('group_id', session.get('user_id', 'G01'))
    safe_id = _safe_group_id(group_id)

    workspace_root = Config.EDITOR_WORKSPACE_ROOT
    source_dir = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'audio_preprocessed', group_id
    )
    target_dir = os.path.join(workspace_root, safe_id, 'audio', 'preprocessed')
    target_csv = os.path.join(target_dir, 'train_labels.csv')

    if not os.path.exists(source_dir):
        return jsonify({
            'success': False,
            'error': '预处理目录不存在，请先进行音频预处理'
        })

    os.makedirs(target_dir, exist_ok=True)

    copied = 0
    try:
        for f in os.listdir(source_dir):
            if f.endswith(('.npy', '.csv', '.json')) or os.path.isdir(os.path.join(source_dir, f)):
                import shutil
                src_path = os.path.join(source_dir, f)
                dst_path = os.path.join(target_dir, f)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                    # 统计文件数
                    for root, dirs, files in os.walk(dst_path):
                        copied += len([f for f in files if f.endswith(('.npy', '.wav'))])
                else:
                    shutil.copy2(src_path, dst_path)
                    copied += 1

        return jsonify({
            'success': True,
            'files_copied': copied,
            'csv_generated': os.path.exists(target_csv),
            'target_dir': target_dir
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@editor_bp.route('/face_preprocessed_info', methods=['GET'])
@login_required
def face_preprocessed_info():
    """获取表情预处理数据的统计信息"""
    from services.emotion_labels_service import _safe_group_id

    group_id = session.get('group_id', session.get('user_id', 'G01'))
    safe_id = _safe_group_id(group_id)

    workspace_root = Config.EDITOR_WORKSPACE_ROOT
    preprocessed_dir = os.path.join(workspace_root, safe_id, 'face', 'preprocessed', 'images')

    total = 0
    if os.path.exists(preprocessed_dir):
        for f in os.listdir(preprocessed_dir):
            if f.endswith(('.jpg', '.png', '.jpeg')):
                total += 1

    return jsonify({
        'group_id': group_id,
        'total_images': total,
        'preprocessed_dir': preprocessed_dir
    })


@editor_bp.route('/audio_preprocessed_info', methods=['GET'])
@login_required
def audio_preprocessed_info():
    """获取音频预处理数据的统计信息"""
    from services.audio_labels_service import _safe_group_id

    group_id = session.get('group_id', session.get('user_id', 'G01'))
    safe_id = _safe_group_id(group_id)

    workspace_root = Config.EDITOR_WORKSPACE_ROOT
    preprocessed_dir = os.path.join(workspace_root, safe_id, 'audio', 'preprocessed')

    total = 0
    if os.path.exists(preprocessed_dir):
        for root, dirs, files in os.walk(preprocessed_dir):
            total += len([f for f in files if f.endswith('.npy')])

    return jsonify({
        'group_id': group_id,
        'total_files': total,
        'preprocessed_dir': preprocessed_dir
    })
