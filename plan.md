# AI 助教分步生成与变更记录方案

## Summary

基于当前仓库结构，这次按技术文档分 13 个实现步骤推进，不一次性大改。每一步都做到“可落地、可回看、可继续”，并维护一个总记录文件 `docs/ai_tutor_build_log.md`，持续追加本步修改文件、完成功能、验证结果、遗留事项。

数据库部分按你选定的方式执行：同时补 `ORM + 建表 SQL`。这样代码能直接接入，数据库也有单独落库依据。

## Key Changes

### 1. 先建立“可持续开发”的记录机制
- 新增 `docs/ai_tutor_build_log.md` 作为唯一过程日志。
- 固定日志模板：
  - `Step 标题`
  - `目标`
  - `修改文件`
  - `实现功能`
  - `接口/数据结构变化`
  - `验证结果`
  - `未完成/下一步`
- 每次代码生成后都只追加，不覆盖历史。

### 2. 后端按文档顺序拆成独立能力层
- Step 1: 在 `models/orm_models.py` 新增 4 个 ORM 模型：
  - `AiTutorSession`
  - `AiTutorEvent`
  - `AiTutorMemorySummary`
  - `AiTutorMessage`
- Step 2: 新增 `services/ai_context_store.py`
  - Redis 优先，失败自动降级内存字典
  - 支持 snapshot / events / diagnosis / cooldown
- Step 3: 新增 `services/ai_session_service.py`、`services/ai_context_service.py`
  - 负责 session 创建、touch、事件入库、快照保存、上下文拼装
- Step 4: 新增 `services/ai_rule_service.py`
  - 实现三门课一期规则
  - 输出统一诊断码、下一步建议、提示语
- Step 5: 新增 `services/ai_knowledge_service.py` 与 `docs/ai_knowledge/`
  - 只接一期需要的步骤说明和卡点说明
- Step 6: 改 `services/ai_tutor_service.py`、`routes/ai_tutor.py`
  - `/ai/ask` 保留旧调用
  - 新增结构化返回：`answer / diagnosis / next_step / tips / context_used / source / mode`
- Step 7: 新增 `routes/ai_context.py`，并在 `app.py` 注册
  - `POST /ai/context/event`
  - `POST /ai/context/snapshot`
  - `POST /ai/context/delete_memory`
  - `GET /ai/context/debug/<session_id>`
- 同步新增 SQL 文件，建议命名为 `docs/sql/ai_tutor_context_tables.sql`
  - 仅新增表，不修改现有表结构

### 3. 前端先铺通用桥，再接三门课
- Step 8: 新增 `static/js/ai_context_tracker.js`、`static/js/ai_course_bridge.js`
  - 统一 session_id、事件上报、snapshot 上报、主动提示桥接
- Step 9: 改 `templates/base.html`
  - 悬浮助教请求体附带当前页面 `context`
  - 支持展示结构化的 `next_step` 和 `tips`
- Step 10: 接 `emotion_computing`
  - 改 `templates/emotion_computing.html`
  - 改 `static/js/emotion_computing.js`
  - 接入文档定义的 P0 事件、snapshot、`selected_toy`
- Step 11: 接 `face_emotion`
  - 改 `templates/face_emotion.html`
  - 改 `static/js/face_emotion.js`
  - 新增本地推导 `consecutive_no_face_count`
- Step 12: 接 `ecobottle`
  - 改 `templates/ecobottle.html`
  - 改 `static/js/ecobottle.js`
  - 接入 P0 事件、snapshot，并清理写死 `G01`
- Step 13: 完成主动提示能力
  - 后端补动作提示生成
  - 前端仅允许高亮按钮、切换 tab，不做侵入式弹窗

### 4. 关键接口与类型约束
- `/ai/ask` 继续接受旧格式：
  - `{"question": "..."}`
- 新格式追加字段，不替换旧字段：
  - `prefer_llm`
  - `context.session_id/page/course/step_code/snapshot`
- `context_used` 统一包含：
  - 页面
  - step_code
  - recent_events
  - rule_hits
  - knowledge_refs
- session 粒度按文档执行：
  - 共享主体是 `group_id`
  - 当前课程会话用 `session_id`

## Test Plan

- 数据层
  - ORM 模型可初始化，字段与文档一致
  - SQL 文件可独立执行建表
- `/ai/ask`
  - 旧请求只传 `question` 仍返回成功
  - 新请求传 `context` 时返回结构化字段
- `/ai/context/*`
  - event 可写入缓存与数据库
  - snapshot 可更新 session 最新状态
  - debug 接口仅在 debug 模式开放
- `emotion_computing`
  - 已有表情结果、未录音时，问“下一步怎么做”应引导录音
- `face_emotion`
  - 连续 3 次无人脸时，问“为什么没结果”应提示调整站位
- `ecobottle`
  - `data_count < 3` 且训练时，应明确提示数据不足
  - 预测完成后问“下一步是什么”应引导控制或报告
- 过程日志
  - 每完成一个步骤，`docs/ai_tutor_build_log.md` 必须追加本步改动清单与功能说明

## Assumptions

- 主技术文档以根目录 [ai_tutor_technical_design.md](/d:/codeC/VsCodeP/eduplatform/ai_tutor_technical_design.md:1) 为准，`docs/` 下同名文件只作为指针说明。
- 记录文件默认新建为 [docs/ai_tutor_build_log.md](/d:/codeC/VsCodeP/eduplatform/docs/ai_tutor_build_log.md:1)。
- 数据库没有现成迁移体系，因此采用“ORM 落地 + 独立 SQL 文件”双交付。
- 一期不引入向量库，不接入教师后台，不改现有课程主业务流程，只做外挂式增强。
- 实施时严格按 Step 1 到 Step 13 顺序推进；每一步完成后先更新总日志，再进入下一步。
