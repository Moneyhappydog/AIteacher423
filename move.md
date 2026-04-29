# AI Tutor 迁移执行清单

这份文档用于把当前 AI Tutor 相关改动迁移到另一台已经在运行的服务器。

适用前提：

1. 目标服务器已经有这套项目。
2. 目标服务器已经连接真实 MySQL 数据库。
3. 你要迁移的是 AI Tutor 新功能，不是整套系统重装。

重要结论：

1. 不要复制 `.local_mysql/`、`.ibd`、`.pid`、`.err` 这些本地数据库文件。
2. 目标服务器如果已经有真实数据库，只需要在那个数据库里执行建表 SQL。
3. 这次迁移要同步：代码文件、前端模板和 JS、知识库 markdown、SQL。

---

## 1. 迁移前先确认

在目标服务器确认以下信息：

1. 项目目录路径
2. Python 虚拟环境路径
3. 数据库名称、用户名、密码
4. 服务启动方式

常见启动方式：

- `python run.py`
- `gunicorn`
- `supervisor`
- `systemctl`

---

## 2. 不要复制的内容

以下内容不要从本机复制到目标服务器：

- `.local_mysql/`
- `__pycache__/`
- `*.pyc`
- `*.pid`
- `*.err`
- 本地日志文件

原因：

1. 这些不是业务代码。
2. 这些是你本地开发机运行环境产物。
3. 目标服务器已经有自己的数据库和运行环境。

---

## 3. 先备份目标服务器

### 3.1 备份项目目录

进入目标服务器后执行：

```bash
cp -r /你的项目目录 /你的项目目录_backup_$(date +%Y%m%d_%H%M%S)
```

示例：

```bash
cp -r /www/eduplatform /www/eduplatform_backup_20260427_120000
```

### 3.2 如果目标服务器是 git 项目

```bash
cd /你的项目目录
git status
```

如果目标服务器已经有人改过代码，先确认这些修改是否需要保留。

---

## 4. 要同步的文件

### 4.1 新增文件

这些文件通常目标服务器旧版本里没有，需要新建：

```text
services/ai_context_store.py
services/ai_session_service.py
services/ai_context_service.py
services/ai_rule_service.py
services/ai_knowledge_service.py
routes/ai_context.py
static/js/ai_context_tracker.js
static/js/ai_course_bridge.js
docs/sql/ai_tutor_context_tables.sql
docs/ai_knowledge/  整个目录
```

### 4.2 覆盖已有文件

这些文件通常目标服务器已经有，需要用当前版本覆盖：

```text
models/orm_models.py
models/__init__.py
services/ai_tutor_service.py
routes/ai_tutor.py
app.py
templates/base.html
templates/emotion_computing.html
templates/face_emotion.html
templates/ecobottle.html
static/js/emotion_computing.js
static/js/face_emotion.js
static/js/ecobottle.js
```

---

## 5. 在目标服务器创建目录

进入项目目录：

```bash
cd /你的项目目录
```

如有必要，先创建目录：

```bash
mkdir -p docs/sql
mkdir -p docs/ai_knowledge
mkdir -p services
mkdir -p routes
mkdir -p static/js
mkdir -p templates
```

---

## 6. 上传文件

你可以用 `scp`、`WinSCP`、`FinalShell`、`VS Code Remote SSH` 上传。

### 6.1 先上传新增文件

上传这些：

```text
services/ai_context_store.py
services/ai_session_service.py
services/ai_context_service.py
services/ai_rule_service.py
services/ai_knowledge_service.py
routes/ai_context.py
static/js/ai_context_tracker.js
static/js/ai_course_bridge.js
docs/sql/ai_tutor_context_tables.sql
docs/ai_knowledge/...
```

### 6.2 再覆盖已有文件

上传这些：

```text
models/orm_models.py
models/__init__.py
services/ai_tutor_service.py
routes/ai_tutor.py
app.py
templates/base.html
templates/emotion_computing.html
templates/face_emotion.html
templates/ecobottle.html
static/js/emotion_computing.js
static/js/face_emotion.js
static/js/ecobottle.js
```

如果上传工具提示“是否覆盖”，选择覆盖。

---

## 7. 上传后检查文件是否到位

在目标服务器执行：

```bash
ls services/ai_context_store.py
ls services/ai_session_service.py
ls services/ai_context_service.py
ls services/ai_rule_service.py
ls services/ai_knowledge_service.py
ls routes/ai_context.py
ls static/js/ai_context_tracker.js
ls static/js/ai_course_bridge.js
ls docs/sql/ai_tutor_context_tables.sql
```

检查知识库文件：

```bash
find docs/ai_knowledge -type f
```

成功标志：

1. 上面的 `ls` 都能找到文件。
2. `find docs/ai_knowledge -type f` 能看到一批 `.md` 文件。

---

## 8. 不复制数据库文件，只执行建表 SQL

这一步最重要。

目标服务器已经有真实数据库，所以现在要做的是：

1. 保留原来的真实业务数据。
2. 只新增 AI Tutor 用到的 4 张表。

### 8.1 确认 SQL 文件存在

```bash
ls docs/sql/ai_tutor_context_tables.sql
```

### 8.2 执行建表 SQL

```bash
mysql -u 数据库用户名 -p 数据库名 < docs/sql/ai_tutor_context_tables.sql
```

示例：

```bash
mysql -u root -p maogang < docs/sql/ai_tutor_context_tables.sql
```

执行时会提示输入数据库密码。

### 8.3 进入 MySQL 检查表

```bash
mysql -u root -p
```

进入后执行：

```sql
USE maogang;
SHOW TABLES LIKE 'ai_tutor_sessions';
SHOW TABLES LIKE 'ai_tutor_events';
SHOW TABLES LIKE 'ai_tutor_memory_summaries';
SHOW TABLES LIKE 'ai_tutor_messages';
```

成功标志：

1. 以上 4 条 `SHOW TABLES` 都能查到结果。

---

## 9. 安装 Python 依赖

### 9.1 进入项目目录

```bash
cd /你的项目目录
```

### 9.2 激活虚拟环境

示例：

```bash
source venv/bin/activate
```

如果你的虚拟环境名字不是 `venv`，按实际路径来。

### 9.3 安装原项目依赖

```bash
pip install -r requirements.txt
```

### 9.4 补装关键依赖

```bash
pip install flask_sqlalchemy pymysql httpx
```

成功标志：

1. 没有安装报错。
2. `httpx`、`flask_sqlalchemy`、`pymysql` 都安装成功。

---

## 10. 检查配置

重点检查目标服务器上的配置，不要误用你本机配置。

### 10.1 检查数据库配置

确认项目连接的还是目标服务器自己的真实数据库。

### 10.2 检查 LLM 配置

确认这些配置存在并正确：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`

如果没配：

1. 小助手仍可能工作。
2. 但不会真正调用外部大模型。
3. 会更多走本地规则回答。

---

## 11. 检查 app.py 是否注册新蓝图

确认目标服务器里的 `app.py` 已经注册：

1. `ai_tutor_bp`
2. `ai_context_bp`

你要确认有类似逻辑：

```python
from routes.ai_context import ai_context_bp
app.register_blueprint(ai_context_bp)
```

成功标志：

1. `/ai/context/event` 不会 404
2. `/ai/context/snapshot` 不会 404

---

## 12. 做 Python 语法检查

在目标服务器执行：

```bash
python -m py_compile app.py
python -m py_compile routes/ai_tutor.py
python -m py_compile routes/ai_context.py
python -m py_compile services/ai_tutor_service.py
python -m py_compile services/ai_context_service.py
python -m py_compile services/ai_session_service.py
python -m py_compile services/ai_context_store.py
python -m py_compile services/ai_rule_service.py
python -m py_compile services/ai_knowledge_service.py
python -m py_compile models/orm_models.py
```

成功标志：

1. 命令执行不报语法错误。

---

## 13. 重启服务

按目标服务器原来的方式重启。

### 13.1 如果是直接启动 Flask

```bash
python run.py
```

### 13.2 如果是 gunicorn

示例：

```bash
pkill -f gunicorn
gunicorn wsgi:app -c gunicorn_config.py
```

### 13.3 如果是 supervisor

```bash
supervisorctl restart 你的服务名
```

### 13.4 如果是 systemd

```bash
systemctl restart 你的服务名
```

成功标志：

1. 服务正常启动。
2. 日志里没有明显导入错误、数据库错误。

---

## 14. 先验证后端核心接口

### 14.1 登录系统

因为很多接口是登录保护的。

### 14.2 测试 `/ai/llm_probe`

登录后访问：

```text
/ai/llm_probe
```

成功标志：

1. 接口返回成功 JSON，或者至少不是 404/500。

如果失败，重点检查：

1. `LLM_API_KEY`
2. `LLM_BASE_URL`
3. `LLM_MODEL`
4. 外网访问权限

### 14.3 测试 `/ai/ask`

打开悬浮小助手，先问一句：

```text
什么是人工智能？
```

成功标志：

1. 接口有返回。
2. 页面没有报错。

---

## 15. 再验证上下文链路

这一步是验证 AI Tutor 的核心能力。

### 15.1 进入一个接入页面

优先测试以下页面之一：

1. `emotion_computing`
2. `face_emotion`
3. `ecobottle`

### 15.2 先做页面操作

#### face_emotion

1. 选模型
2. 开摄像头
3. 等待识别结果

#### emotion_computing

1. 选 face model
2. 选 audio model
3. 开摄像头或录音
4. 等待融合结果

#### ecobottle

1. 切换 tab
2. 添加数据点
3. 尝试训练或预测

### 15.3 然后问小助手

示例问题：

```text
我下一步该做什么？
```

成功标志：

1. 回答能结合你刚才页面上的状态。
2. 不是纯固定答案。

这说明：

1. `event` 上报成功
2. `snapshot` 上报成功
3. `/ai/ask` 已拿到上下文
4. 规则、知识、LLM 链路基本正常

---

## 16. 如果出问题，按这里查

### 16.1 页面能打开，但问问题时报错

先看：

1. 后端日志
2. `/ai/ask` 返回内容

### 16.2 页面操作后上下文不生效

重点排查：

1. `/ai/context/event` 是否 404
2. `/ai/context/snapshot` 是否 404
3. 数据库表是否创建成功
4. `app.py` 是否注册 `ai_context_bp`

### 16.3 普通提问能回答，但不像大模型

重点排查：

1. `LLM_API_KEY`
2. `LLM_BASE_URL`
3. `LLM_MODEL`
4. `/ai/llm_probe`

### 16.4 数据库报错

重点排查：

1. SQL 是否执行成功
2. 当前项目连接的是不是你刚刚建表的那个数据库
3. 表是否存在

---

## 17. 最终核对清单

执行完后，逐项确认：

- 已备份目标服务器项目目录
- 未复制 `.local_mysql/` 和本地数据库文件
- 新增文件已上传
- 覆盖文件已上传
- `docs/ai_knowledge/` 已上传完整
- `docs/sql/ai_tutor_context_tables.sql` 已执行
- 4 张新表已创建成功
- 依赖安装完成
- LLM 配置已检查
- `app.py` 已注册新蓝图
- 服务已重启
- `/ai/llm_probe` 可访问
- `/ai/ask` 可正常回答
- 页面操作后再提问，回答能结合页面上下文

---

## 18. 迁移完成后的建议

如果这次迁移成功，建议你马上再做两件事：

1. 把目标服务器当前版本提交到 git，避免之后难以追踪。
2. 记录目标服务器的数据库建表时间和发布版本，方便后续排查。
