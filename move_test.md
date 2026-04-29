# AI Tutor 测试副本部署清单

这份文档按你已经选好的方案来写：

1. 数据库方案：`C`
2. Web 端口：`5001`
3. 启动方式：`A`，直接 `python run.py`
4. 配置方式：`A`，直接改测试目录里的 `config.py`
5. 数据库数据：`B`，导入正式库数据到测试库
6. LLM：`A`，测试环境启用
7. MySQL 端口：`A`，不改，继续用现有 MySQL 实例

也就是说，你的测试环境最终会是：

- 正式项目目录：`/www/eduplatform`
- 测试项目目录：`/www/eduplatform_test`
- 正式数据库：`maogang`
- 测试数据库：`maogang_test`
- 测试 Web 端口：`5001`

---

## 0. 现在唯一还要你现场确认的两个点

这两个点我现在不能替你确定，部署前你要先看一眼：

### 0.1 目标服务器真实 MySQL 端口是多少

当前仓库里的 [config.py](/d:/codeC/VsCodeP/eduplatform/config.py:14) 默认写的是：

```python
mysql+pymysql://root@127.0.0.1:3307/maogang?charset=utf8mb4
```

但你真实服务器未必是 `3307`，也可能是 `3306`。

所以你要先确认：

1. 正式环境当前实际连接的是 `3306` 还是 `3307`
2. 正式环境是不是靠环境变量覆盖了 `SQLALCHEMY_DATABASE_URI`

### 0.2 `run.py` 启动时是不是可以直接用 `PORT=5001`

当前 [run.py](/d:/codeC/VsCodeP/eduplatform/run.py:25) 会读环境变量 `PORT`：

```python
port = int(os.environ.get('PORT', 5000))
```

所以理论上你可以这样启动测试副本：

```bash
PORT=5001 python run.py
```

如果服务器是 Linux，这样通常没问题。

---

## 1. 不要做的事

不要复制这些到测试副本：

- `.local_mysql/`
- `__pycache__/`
- `*.pyc`
- `*.pid`
- `*.err`
- 本地日志

不要让测试副本直接连正式库 `maogang`。

不要占用正式项目的 Web 端口。

---

## 2. 先复制一份项目目录

假设正式项目目录是：

```bash
/www/eduplatform
```

先复制：

```bash
cp -r /www/eduplatform /www/eduplatform_test
```

复制后检查：

```bash
ls /www/eduplatform_test
```

成功标志：

1. `eduplatform_test` 目录存在
2. 里面有 `app.py`、`run.py`、`templates/`、`services/`、`routes/`

---

## 3. 进入测试目录

```bash
cd /www/eduplatform_test
pwd
```

你应该看到：

```bash
/www/eduplatform_test
```

---

## 4. 创建测试数据库

先进入 MySQL：

```bash
mysql -u root -p
```

执行：

```sql
CREATE DATABASE maogang_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SHOW DATABASES;
```

成功标志：

1. `SHOW DATABASES` 里能看到 `maogang_test`

如果已经存在，可以执行：

```sql
SHOW DATABASES LIKE 'maogang_test';
```

---

## 5. 把正式数据库导入测试数据库

你已经选的是“导一份正式数据”，所以按这个做。

### 5.1 导出正式库

```bash
mysqldump -u root -p maogang > /tmp/maogang.sql
```

成功标志：

1. `/tmp/maogang.sql` 文件生成成功

检查：

```bash
ls -lh /tmp/maogang.sql
```

### 5.2 导入到测试库

```bash
mysql -u root -p maogang_test < /tmp/maogang.sql
```

成功标志：

1. 命令执行没有报错

### 5.3 简单检查测试库里是不是有数据

进入 MySQL：

```bash
mysql -u root -p
```

执行：

```sql
USE maogang_test;
SHOW TABLES;
```

如果你知道正式业务里一定有某张表，比如 `users` 或 `groups`，可以继续查：

```sql
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM groups;
```

---

## 6. 在测试库里执行 AI Tutor 新表 SQL

回到测试项目目录：

```bash
cd /www/eduplatform_test
```

执行：

```bash
mysql -u root -p maogang_test < docs/sql/ai_tutor_context_tables.sql
```

然后检查：

```bash
mysql -u root -p
```

执行：

```sql
USE maogang_test;
SHOW TABLES LIKE 'ai_tutor_sessions';
SHOW TABLES LIKE 'ai_tutor_events';
SHOW TABLES LIKE 'ai_tutor_memory_summaries';
SHOW TABLES LIKE 'ai_tutor_messages';
```

成功标志：

1. 4 张表都能查到

---

## 7. 修改测试目录里的 config.py

你已经选了“直接改测试目录配置文件”，所以只改：

```bash
/www/eduplatform_test/config.py
```

不要改正式目录的 `config.py`。

### 7.1 重点要改的配置

#### 数据库连接

把库名从：

```text
maogang
```

改成：

```text
maogang_test
```

端口要按你服务器真实情况来定：

如果正式服务器用的是 `3306`，就写：

```python
mysql+pymysql://用户名:密码@127.0.0.1:3306/maogang_test?charset=utf8mb4
```

如果正式服务器用的是 `3307`，就写：

```python
mysql+pymysql://用户名:密码@127.0.0.1:3307/maogang_test?charset=utf8mb4
```

#### LLM 配置

确认这三个在测试环境里也能用：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`

如果你准备用正式那套 key 测试，就保持测试目录里可用即可。

### 7.2 改完后自己检查一下

检查思路：

1. 正式目录还连 `maogang`
2. 测试目录改成连 `maogang_test`

---

## 8. 安装测试环境依赖

进入测试项目目录：

```bash
cd /www/eduplatform_test
```

如果共用现有虚拟环境：

```bash
source venv/bin/activate
```

然后执行：

```bash
pip install -r requirements.txt
pip install flask_sqlalchemy pymysql httpx
```

成功标志：

1. 没有安装错误

---

## 9. 检查测试目录里的 AI Tutor 文件是否完整

在测试目录执行：

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

再检查知识库：

```bash
find docs/ai_knowledge -type f
```

成功标志：

1. 所有关键文件都存在
2. `docs/ai_knowledge/` 下面有一批 `.md` 文件

---

## 10. 做 Python 语法检查

在测试目录执行：

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

1. 没有语法错误

---

## 11. 用 5001 启动测试副本

你已经选的是 `python run.py`，当前项目也支持环境变量 `PORT`。

所以在测试目录执行：

```bash
cd /www/eduplatform_test
source venv/bin/activate
PORT=5001 python run.py
```

成功标志：

1. 终端打印启动信息
2. 日志里能看到类似 `http://127.0.0.1:5001`

如果你是远程服务器，要确认防火墙允许访问 `5001`。

访问地址通常是：

```text
http://服务器IP:5001
```

---

## 12. 验证测试副本是否真的连的是测试库

这是你最关心的安全点。

验证方法有 3 个：

### 方法 1：看 config.py

确认测试目录的数据库名是：

```text
maogang_test
```

### 方法 2：做一次测试写入

进入测试页面后操作 AI tutor，让它产生事件、会话、消息。

然后进 MySQL 执行：

```sql
USE maogang_test;
SELECT COUNT(*) FROM ai_tutor_sessions;
SELECT COUNT(*) FROM ai_tutor_events;
SELECT COUNT(*) FROM ai_tutor_messages;
```

如果这些表里出现数据，说明测试副本确实写到了测试库。

### 方法 3：确认正式库没变化

再切回正式库执行：

```sql
USE maogang;
SELECT COUNT(*) FROM ai_tutor_sessions;
SELECT COUNT(*) FROM ai_tutor_events;
SELECT COUNT(*) FROM ai_tutor_messages;
```

如果正式库这些数据没有被你刚才测试影响，就说明隔离成功。

---

## 13. 测试顺序

按下面顺序测，最稳。

### 13.1 先测登录

打开：

```text
http://服务器IP:5001
```

确认能登录。

### 13.2 测试 `/ai/llm_probe`

登录后访问：

```text
/ai/llm_probe
```

成功标志：

1. 返回成功 JSON，或者至少不是 404/500

### 13.3 测试普通提问

打开悬浮小助手，先问：

```text
什么是人工智能？
```

### 13.4 测试上下文增强

进入以下任一页面：

1. `emotion_computing`
2. `face_emotion`
3. `ecobottle`

先做一些操作，再问：

```text
我下一步该做什么？
```

成功标志：

1. 回答能结合你刚才的页面状态

---

## 14. 如果测试环境启动失败，先查这几个地方

### 14.1 数据库连接错误

优先检查：

1. `config.py` 里测试库名是不是 `maogang_test`
2. MySQL 端口到底是 `3306` 还是 `3307`
3. 用户名密码对不对

### 14.2 5001 打不开

优先检查：

1. `PORT=5001 python run.py` 是否真的启动成功
2. 防火墙是否放行 `5001`
3. 服务器安全组是否允许 `5001`

### 14.3 LLM 不工作

优先检查：

1. `LLM_API_KEY`
2. `LLM_BASE_URL`
3. `LLM_MODEL`
4. `/ai/llm_probe`

---

## 15. 最后的执行摘要

你现在这套测试方案，正确的执行路径就是：

1. 复制 `/www/eduplatform` 到 `/www/eduplatform_test`
2. 新建 `maogang_test`
3. 把正式库数据导入 `maogang_test`
4. 在 `maogang_test` 上执行 `docs/sql/ai_tutor_context_tables.sql`
5. 只改测试目录的 `config.py`
6. 把数据库改成 `maogang_test`
7. 用 `PORT=5001 python run.py` 启动测试副本
8. 打开 `http://服务器IP:5001` 测试

这样即使你把测试副本改坏了，也不会直接影响正式目录和正式数据库。
