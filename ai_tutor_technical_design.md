# AI 助教上下文感知改造技术设计文档

## 1. 文档目标

本文档定义教学平台 AI 助教的一期、二期技术方案。目标是：

- 在不破坏现有课程主流程的前提下，让全站悬浮助教和 `/ai/ask` 具备“读取页面状态、读取最近操作、识别卡点、给出下一步指导”的能力。
- 保持现有 `/ai/ask` 调用方式向后兼容：老前端只传 `question` 仍然可用。
- 一期不强行引入向量 RAG，而是采用“页面状态 + 操作事件 + 规则诊断 + markdown 知识库 + LLM”的混合方案。
- 为二期向量检索、长期画像、教师后台保留扩展位。

本文档是后续分阶段编码的唯一技术基准。后续所有实现都必须以兼容初版为前提。

---

## 2. 设计范围与边界

### 2.1 一期必须完成

1. 统一增强 `/ai/ask`
2. 新增上下文采集链路
   - 事件上报
   - 页面快照上报
   - 会话管理
3. 三门课程接入
   - `emotion_computing`
   - `face_emotion`
   - `ecobottle`
4. 规则驱动的卡点检测
5. markdown 结构化知识库
6. 结构化回答结果
   - `answer`
   - `diagnosis`
   - `next_step`
   - `tips`
   - `context_used`
7. MySQL 持久化 + Redis 缓存 + 内存兜底
8. 主动提示
   - 仅在明显卡住时
   - 通过聊天框插入建议气泡
   - 不做侵入式弹窗

### 2.2 一期明确不做

- 向量数据库 / embedding / 真正向量 RAG
- 教师后台页面
- 长期画像参与主回答
- 复杂的多轮失败诊断
- `data_collect` / `model_import` / `model_eval` 页面接入
- 助教直接替学生执行操作

### 2.3 二期方向

- 向量 RAG
- 长期画像参与回答
- 教师分析后台
- 更复杂的卡点诊断
- 更多课程接入
- 主动提醒策略优化

---

## 3. 兼容性原则

### 3.1 数据库兼容

- 只允许新增表
- 不修改现有表结构
- 不改现有业务表字段含义

### 3.2 接口兼容

- `/ai/ask` 保持旧请求体可用
- `/ai/ask` 仅追加新字段，不替换旧字段
- 现有课程接口返回结构不得被破坏

### 3.3 前端兼容

- 不改课程页主流程函数的业务意图
- 课程页仅做外挂式增强：
  - 事件上报
  - 页面状态 provider
  - 轻量视觉引导

### 3.4 运行时兼容

- Redis 可用时优先使用 Redis
- Redis 不可用时必须自动降级到进程内内存缓存
- MySQL 始终是持久化真源

---

## 4. 当前代码基线

### 4.1 现有 AI 助教入口

- 后端路由：[routes/ai_tutor.py](/d:/codeC/VsCodeP/eduplatform/routes/ai_tutor.py:1)
- 服务层：[services/ai_tutor_service.py](/d:/codeC/VsCodeP/eduplatform/services/ai_tutor_service.py:1)
- 悬浮助教 UI：[templates/base.html](/d:/codeC/VsCodeP/eduplatform/templates/base.html:1)
- 独立助教页：[templates/ai_tutor.html](/d:/codeC/VsCodeP/eduplatform/templates/ai_tutor.html:1)

现状问题：

- 助教当前主要只接收问题文本
- `/ai/ask` 已支持 `context`，但悬浮助教未注入页面上下文
- 还没有统一的“操作事件流”和“页面快照”

### 4.2 当前已存在的课程交互入口

#### `emotion_computing`

- 页面模板：[templates/emotion_computing.html](/d:/codeC/VsCodeP/eduplatform/templates/emotion_computing.html:1)
- 前端逻辑：[static/js/emotion_computing.js](/d:/codeC/VsCodeP/eduplatform/static/js/emotion_computing.js:1)
- 后端路由：[routes/emotion_computing.py](/d:/codeC/VsCodeP/eduplatform/routes/emotion_computing.py:1)

#### `face_emotion`

- 页面模板：[templates/face_emotion.html](/d:/codeC/VsCodeP/eduplatform/templates/face_emotion.html:1)
- 前端逻辑：[static/js/face_emotion.js](/d:/codeC/VsCodeP/eduplatform/static/js/face_emotion.js:1)
- 后端路由：[routes/face_emotion.py](/d:/codeC/VsCodeP/eduplatform/routes/face_emotion.py:1)

#### `ecobottle`

- 页面模板：[templates/ecobottle.html](/d:/codeC/VsCodeP/eduplatform/templates/ecobottle.html:1)
- 前端逻辑：[static/js/ecobottle.js](/d:/codeC/VsCodeP/eduplatform/static/js/ecobottle.js:1)
- 后端路由：[routes/ecobottle.py](/d:/codeC/VsCodeP/eduplatform/routes/ecobottle.py:1)

### 4.3 当前必须修复的已知技术问题

- `static/js/ecobottle.js` 多处写死 `G01`，一期必须统一替换为真实 `group_id` 读取逻辑。[static/js/ecobottle.js](/d:/codeC/VsCodeP/eduplatform/static/js/ecobottle.js:117)
- `face_emotion` 当前没有现成的 `consecutive_no_face_count` 变量，一期必须新增本地推导状态，不能误认为是现成字段。[static/js/face_emotion.js](/d:/codeC/VsCodeP/eduplatform/static/js/face_emotion.js:146)
- `emotion_computing` 的“玩具反馈”是实际课程步骤，`selectToy` 必须进入事件字典。[static/js/emotion_computing.js](/d:/codeC/VsCodeP/eduplatform/static/js/emotion_computing.js:622)

---

## 5. 核心方案

一期不采用纯 RAG，而采用以下链路：

```text
课程页面
  -> 事件 tracker 上报关键操作
  -> context provider 维护页面快照
  -> 用户在悬浮助教或 /ai 页面提问
  -> /ai/ask 收到 question + context
  -> 读取 session / recent events / latest snapshot / rule diagnosis / markdown knowledge
  -> 规则优先生成下一步建议
  -> 必要时调用 LLM 组织自然语言
  -> 返回结构化结果
```

核心设计名词：

- 操作事件：学生做了什么
- 页面快照：学生当前在哪个状态
- 会话：当前课程这一轮操作上下文
- 规则诊断：是否卡住、缺哪一步
- 知识上下文：markdown 中的操作说明与错误处理

---

## 6. 数据模型设计

## 6.1 `ai_tutor_sessions`

用途：

- 记录当前课程会话
- 粒度为 `group_id + session_id`

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BigInteger PK | 主键 |
| session_id | String(64) unique | 前端生成会话 ID |
| group_id | Integer not null | 对应 `groups.user_id` |
| member_id | String(20) null | 可选 |
| page | String(50) not null | 如 `emotion_computing` |
| course | String(50) not null | 如 `emotion` / `face` / `ecobottle` |
| step_code | String(50) null | 当前步骤 |
| latest_snapshot | JSON null | 最近页面快照 |
| latest_diagnosis | JSON null | 最近规则诊断 |
| started_at | DateTime not null | 开始时间 |
| last_active_at | DateTime not null | 最近活跃时间 |
| ended_at | DateTime null | 结束时间 |
| is_active | Boolean default true | 是否活跃 |
| created_at | DateTime not null | 创建时间 |
| updated_at | DateTime not null | 更新时间 |

## 6.2 `ai_tutor_events`

用途：

- 完整事件流入库

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BigInteger PK | 主键 |
| session_id | String(64) index | 会话 ID |
| group_id | Integer not null | 小组 |
| member_id | String(20) null | 可选 |
| page | String(50) not null | 页面 |
| course | String(50) not null | 课程 |
| step_code | String(50) null | 当前步骤 |
| event_type | String(50) not null | 事件分类 |
| event_name | String(100) not null | 事件名 |
| payload | JSON null | 结构化数据 |
| summary_text | String(255) null | 压缩摘要 |
| dedupe_key | String(120) null | 去重键 |
| event_time | DateTime not null | 事件发生时间 |
| created_at | DateTime not null | 入库时间 |

## 6.3 `ai_tutor_memory_summaries`

用途：

- 存储最近 7 天长期画像摘要
- 一期只存不用

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BigInteger PK | 主键 |
| group_id | Integer not null | 小组 |
| summary_type | String(50) not null | `7d_profile` / `course_profile` |
| course | String(50) null | 可选课程 |
| summary_json | JSON not null | 结构化画像 |
| window_start | DateTime null | 起始窗口 |
| window_end | DateTime null | 结束窗口 |
| created_at | DateTime not null | 创建时间 |
| updated_at | DateTime not null | 更新时间 |

## 6.4 `ai_tutor_messages`

用途：

- 永久保存助教问答文本

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BigInteger PK | 主键 |
| session_id | String(64) index | 会话 ID |
| group_id | Integer not null | 小组 |
| role | String(20) not null | `user` / `assistant` / `system_hint` |
| user_question_text | Text null | 用户问题文本 |
| answer_text | Text null | 助教回答 |
| diagnosis | String(100) null | 诊断结果 |
| next_step | String(255) null | 下一步 |
| tips | JSON null | 提示列表 |
| context_used | JSON null | 依据上下文 |
| source | String(30) null | `rule` / `local` / `llm` / `hybrid` |
| created_at | DateTime not null | 创建时间 |

隐私要求：

- 不保存音视频原始内容
- 不保存图片 base64
- 操作事件只存结构化 payload
- 问答文本允许保存

---

## 7. Redis 与内存兜底

### 7.1 Redis 只做短期缓存

Redis 用于：

- 当前会话快照
- 最近事件列表
- 主动提示冷却
- 最近诊断结果

MySQL 始终是持久化真源。

### 7.2 Redis key 设计

| Key | 用途 |
|---|---|
| `ai:snapshot:{session_id}` | 当前快照 |
| `ai:events:{session_id}` | 最近事件列表 |
| `ai:diag:{session_id}` | 最近诊断 |
| `ai:cooldown:{session_id}:{rule}` | 主动提示冷却 |

### 7.3 降级顺序

1. Redis
2. 进程内内存字典
3. 必要时回查 MySQL

---

## 8. 接口设计

## 8.1 保持 `/ai/ask` 为统一入口

路由文件：

- [routes/ai_tutor.py](/d:/codeC/VsCodeP/eduplatform/routes/ai_tutor.py:1)

### 旧请求体

```json
{
  "question": "下一步怎么做？"
}
```

### 新请求体

```json
{
  "question": "下一步怎么做？",
  "prefer_llm": false,
  "context": {
    "session_id": "ec_20260423_xxx",
    "page": "emotion_computing",
    "course": "emotion",
    "step_code": "single_modal_result",
    "snapshot": {
      "face_model_id": 3,
      "audio_model_id": null,
      "fusion_strategy": "weighted_average",
      "face_weight": 0.6,
      "camera_started": true,
      "recording": false,
      "last_face_result": {"emotion": "happy"}
    }
  }
}
```

### `/ai/ask` 响应目标

必须保留旧字段，同时新增以下字段：

```json
{
  "success": true,
  "answer": "你已经完成了表情识别，下一步建议开始录音，让系统也读取声音情绪。",
  "source": "hybrid",
  "mode": "guide",
  "diagnosis": "emotion_missing_audio_input",
  "next_step": "点击开始录音，采集 3 到 5 秒声音",
  "tips": ["周围尽量安静一些"],
  "context_used": {
    "page": "emotion_computing",
    "step_code": "single_modal_result",
    "recent_events": [
      "selected face model 3",
      "camera started",
      "got face result happy"
    ],
    "rule_hits": ["emotion_missing_audio_input"],
    "knowledge_refs": [
      "emotion_computing/step_record_audio.md",
      "emotion_computing/stuck_missing_audio.md"
    ]
  }
}
```

## 8.2 新增 `POST /ai/context/event`

用途：

- 前端实时上报关键事件

请求体：

```json
{
  "session_id": "face_20260423_xxx",
  "page": "face_emotion",
  "course": "face",
  "step_code": "detecting",
  "event_type": "camera",
  "event_name": "camera_started",
  "payload": {
    "camera_status": "running"
  }
}
```

响应体：

```json
{
  "success": true,
  "event_id": 123
}
```

## 8.3 新增 `POST /ai/context/snapshot`

用途：

- 前端关键时刻刷新当前快照

## 8.4 新增 `POST /ai/context/delete_memory`

用途：

- 删除某个小组的会话、事件、摘要、消息
- 一期只做后端接口，不做前端入口

## 8.5 新增 `GET /ai/context/debug/<session_id>`

用途：

- 开发模式查看当前 session 的 snapshot / events / diagnosis
- 仅 debug 模式开放

---

## 9. 服务层拆分

## 9.1 新增服务与职责

### `services/ai_context_store.py`

职责：

- Redis + 内存兜底封装

建议函数：

- `get_snapshot(session_id)`
- `set_snapshot(session_id, snapshot, ttl=None)`
- `append_event(session_id, event, max_len=30)`
- `get_recent_cached_events(session_id, limit=15)`
- `get_diag(session_id)`
- `set_diag(session_id, diag, ttl=None)`

### `services/ai_session_service.py`

职责：

- 会话入库与更新

建议函数：

- `get_or_create_session(...)`
- `touch_session(...)`
- `update_session_snapshot(...)`
- `close_session(...)`

### `services/ai_context_service.py`

职责：

- 事件落库
- snapshot 入库
- 上下文拼装
- 事件压缩

建议函数：

- `record_event(...)`
- `save_snapshot(...)`
- `build_request_context(question, raw_context, group_id)`
- `compress_recent_events(events, limit=15)`
- `build_context_used(...)`

### `services/ai_rule_service.py`

职责：

- 规则诊断
- 卡点检测
- 下一步建议

建议函数：

- `detect_stuck(context)`
- `detect_face_emotion_rules(snapshot, recent_events, question)`
- `detect_emotion_computing_rules(snapshot, recent_events, question)`
- `detect_ecobottle_rules(snapshot, recent_events, question)`
- `build_rule_based_next_step(rule_hit, context)`

### `services/ai_knowledge_service.py`

职责：

- markdown 知识读取
- 按课程、步骤、诊断命中知识片段

建议函数：

- `load_knowledge_index()`
- `build_knowledge_context(course, step_code, diagnosis, question)`

### `services/ai_action_hint_service.py`

职责：

- 把规则结果转成前端轻量动作提示
- 仅允许：
  - 高亮按钮
  - 切换 tab

### `services/ai_tutor_service.py`

现有文件保留，新增能力：

- `answer_with_context(...)`
- `compose_structured_response(...)`
- `build_llm_messages_from_context(...)`

要求：

- 原有 `get_answer(...)` 继续可用
- 内部可转调新链路

---

## 10. markdown 知识库设计

目录：

```text
docs/ai_knowledge/
  emotion_computing/
    step_select_model.md
    step_record_audio.md
    step_fusion.md
    stuck_missing_audio.md
    stuck_missing_camera.md
    explain_fusion_result.md
  face_emotion/
    step_select_model.md
    step_start_camera.md
    stuck_no_face.md
    explain_result.md
  ecobottle/
    step_collect_data.md
    step_explore.md
    step_train.md
    step_predict.md
    step_control.md
    stuck_not_enough_data.md
    stuck_wrong_tab.md
    explain_prediction.md
```

一期知识源只覆盖：

- 页面操作说明
- 常见错误处理
- 模型概念简述

---

## 11. 课程流程定义

## 11.1 `emotion_computing` 标准流程

1. 选择表情模型和声音模型
2. 开摄像头 / 开录音
3. 获取单模态结果
4. 进行融合
5. 选择玩具反馈并查看解释

允许自由探索，但卡住时按推荐顺序引导。

## 11.2 `face_emotion` 标准流程

1. 选择模型
2. 开启摄像头
3. 检测人脸
4. 查看表情结果
5. 理解结果含义或继续识别

## 11.3 `ecobottle` 标准流程

1. 采集数据
2. 探索分析
3. 模型训练
4. 预测
5. 控制
6. 生成报告

---

## 12. 事件字典与页面快照

本节是一期最关键部分。后续编码必须严格按这里实现。

### 12.1 通用事件规范

字段约定：

| 字段 | 含义 |
|---|---|
| `event_type` | 事件大类，如 `model` / `camera` / `result` |
| `event_name` | 细粒度事件名，如 `face_model_selected` |
| `step_code` | 当前学习步骤 |
| `payload` | 结构化补充信息 |
| `dedupe_key` | 高频事件去重键 |

规则：

- 高频动作合并记录，只保留最终值
- 滑块不按拖动每一步上报，只在停止后上报最终值
- tab 切换可合并相邻重复记录
- 每次问答前必须额外打包当前 snapshot

---

## 12.2 `emotion_computing`

### A. 页面快照字段

一期必采集：

- `face_model_id`
- `audio_model_id`
- `fusion_strategy`
- `face_weight`
- `camera_started`
- `recording`
- `last_face_result`
- `last_audio_result`
- `last_fusion_result`
- `selected_toy`

说明：

- `selected_toy` 是现有真实步骤，不可遗漏。[static/js/emotion_computing.js](/d:/codeC/VsCodeP/eduplatform/static/js/emotion_computing.js:622)

### B. 一期 P0 必采事件

| event_name | event_type | 触发位置 | step_code | payload |
|---|---|---|---|---|
| `face_model_selected` | `model` | `switchFaceModel()` in `templates/emotion_computing.html` | `select_model` | `face_model_id` |
| `audio_model_selected` | `model` | `switchAudioModel()` in `templates/emotion_computing.html` | `select_model` | `audio_model_id` |
| `fusion_strategy_changed` | `fusion` | strategy radio change in `templates/emotion_computing.html` | `fusion_config` | `fusion_strategy` |
| `face_weight_changed` | `fusion` | `setWeightPreset()` / slider final value in `templates/emotion_computing.html` | `fusion_config` | `face_weight` |
| `camera_started` | `camera` | `startCamera()` | `single_modal_capture` | none |
| `camera_stopped` | `camera` | `stopCamera()` | `single_modal_capture` | none |
| `recording_started` | `audio` | `toggleRecording()` | `single_modal_capture` | none |
| `recording_stopped` | `audio` | `toggleRecording()` | `single_modal_capture` | none |
| `face_result_updated` | `result` | face prediction success path in `startCamera()` flow | `single_modal_result` | `emotion`, `confidence` |
| `audio_result_updated` | `result` | audio recognition success path | `single_modal_result` | `emotion`, `confidence` |
| `fusion_result_updated` | `result` | `updateFusion()` | `fusion_result` | `emotion`, `fusion_method` |
| `toy_selected` | `feedback` | `selectToy(toy)` | `toy_feedback` | `selected_toy` |

### C. 一期 P1 可选事件

| event_name | event_type | 触发位置 | 说明 |
|---|---|---|---|
| `weight_preset_selected` | `fusion` | `setWeightPreset()` | 如果想区分预设与手动滑块 |
| `fusion_strategy_auto_disabled_weight` | `fusion` | strategy change | 记录策略导致权重不可手调 |

### D. 推荐接入函数

- `startCamera()`
- `stopCamera()`
- `toggleRecording()`
- `updateFusion()`
- `selectToy(toy)`
- `switchFaceModel()` in template inline script
- `switchAudioModel()` in template inline script
- strategy change handler in template inline script
- `setWeightPreset()` / slider change handler in template inline script

---

## 12.3 `face_emotion`

### A. 页面快照字段

一期必采集：

- `current_model`
- `camera_status`
- `last_result`
- `consecutive_no_face_count`
- `last_face_count`
- `last_status_text`

说明：

- `consecutive_no_face_count` 不是现有变量，必须新增本地推导状态：
  - 连续预测 `face_count == 0` 时加一
  - 检测到人脸时清零

### B. 一期 P0 必采事件

| event_name | event_type | 触发位置 | step_code | payload |
|---|---|---|---|---|
| `face_model_selected` | `model` | `switchModel()` in `templates/face_emotion.html` | `select_model` | `model_id` |
| `camera_started` | `camera` | `startCamera()` | `detecting` | none |
| `camera_stopped` | `camera` | `stopCamera()` | `detecting` | none |
| `predict_requested` | `predict` | `captureAndPredict()` | `detecting` | `model_id` |
| `face_result_updated` | `result` | `renderFaceResult(data)` with face | `result_ready` | `emotion`, `confidence`, `face_count` |
| `no_face_detected` | `result` | `renderFaceResult(data)` without face | `detecting` | `consecutive_no_face_count`, `face_count=0` |

### C. 一期 P1 可选事件

| event_name | event_type | 触发位置 | 说明 |
|---|---|---|---|
| `status_hint_changed` | `ui` | `setStatus()` | 仅用于细粒度调试 |

### D. 推荐接入函数

- `startCamera()`
- `stopCamera()`
- `captureAndPredict()`
- `renderFaceResult(data)`
- `switchModel()` in template inline script

---

## 12.4 `ecobottle`

### A. 页面快照字段

一期必采集：

- `current_tab`
- `prediction_model`
- `train_model`
- `preprocessing`
- `prediction_steps`
- `data_count`
- `last_prediction`
- `last_control_strategy`
- `last_control_action`
- `last_explore_summary`
- `last_report_export_type`

说明：

- `last_control_action` 虽然不是你最初的最小字段，但代码里确实存在自动控制动作返回，一期保留可显著提升“你刚刚做了什么”的解释能力。[static/js/ecobottle.js](/d:/codeC/VsCodeP/eduplatform/static/js/ecobottle.js:600)

### B. 一期 P0 必采事件

这些是必须纳入上下文的最小闭环事件。

| event_name | event_type | 触发位置 | step_code | payload |
|---|---|---|---|---|
| `tab_changed` | `navigation` | `showTab(tabName)` | dynamic | `current_tab` |
| `manual_values_applied` | `collect` | `ecoApplyManual()` | `collect_data` | sensor values |
| `quick_action_applied` | `collect` | `ecoQuickAction(action)` | `collect_data` | `action` |
| `data_record_added` | `collect` | `ecoAddData()` | `collect_data` | `data_count` |
| `explore_analysis_run` | `explore` | `runExploreAnalysis()` | `explore_data` | `data_count` |
| `correlation_analysis_run` | `explore` | `runCorrelationAnalysis()` | `explore_data` | `data_count` |
| `train_model_selected` | `train` | `selectModel(modelType)` | `train_model` | `train_model` |
| `prediction_steps_changed` | `train` | `updatePredStep(value)` | `train_model` | `prediction_steps` |
| `preprocessing_changed` | `train` | `#preprocessMethod` change | `train_model` | `preprocessing` |
| `training_started` | `train` | `runTraining()` before request | `train_model` | `train_model`, `data_count` |
| `training_blocked_not_enough_data` | `train` | `runTraining()` when `< 3` | `train_model` | `data_count` |
| `prediction_requested` | `predict` | `runPrediction()` | `predict` | `prediction_model` |
| `control_strategy_changed` | `control` | `input[name="ctrlStrategy"]` change | `control` | `strategy` |
| `control_actions_applied` | `control` | `applyAutoActions(strategy, thresholds)` | `control` | `actions`, `strategy` |
| `report_exported` | `report` | export report actions | `report` | `export_type` |

### C. 一期 P1 可选事件

这些先定义，实际接入可以放后半段。

| event_name | event_type | 触发位置 | 说明 |
|---|---|---|---|
| `data_record_deleted` | `collect` | `ecoDeleteRecord(timestamp)` | 对理解“为什么数据不够了”有帮助 |
| `data_table_cleared` | `collect` | `ecoClearTable()` | 对训练失败诊断有帮助 |
| `csv_imported` | `collect` | `ecoImportCsv()` | 可补充数据来源 |
| `csv_exported` | `collect` | `ecoExportCsv()` | 可记录操作路径 |
| `history_loaded` | `collect` | `ecoLoadHistory()` | 调试价值大于教学价值 |
| `poly_degree_changed` | `train` | `updatePolyDegree(value)` | 仅 polynomial 模型需要 |
| `practice_started` / `practice_submitted` | `practice` | 练习模块 | 一期可不接入 |

### D. 推荐接入函数

- `showTab(tabName)`
- `ecoApplyManual()`
- `ecoQuickAction(action)`
- `ecoAddData()`
- `ecoDeleteRecord(timestamp)`
- `ecoClearTable()`
- `ecoImportCsv()`
- `ecoExportCsv()`
- `ecoLoadHistory()`
- `runExploreAnalysis()`
- `runCorrelationAnalysis()`
- `runPrediction()`
- `selectModel(modelType)`
- `updatePredStep(value)`
- `updatePolyDegree(value)`
- `runTraining()`
- `applyAutoActions(strategy, thresholds)`
- 导出报告按钮对应函数

### E. `G01` 清理清单

必须替换真实 `group_id` 读取逻辑的函数：

- `ecoAddData()`
- `ecoDeleteRecord(timestamp)`
- `ecoClearTable()`
- `ecoImportCsv()`
- `ecoExportCsv()`
- `ecoLoadHistory()`
- `runExploreAnalysis()`
- `runCorrelationAnalysis()`

---

## 13. 卡点规则设计

### 13.1 通用规则

- 停留 90 秒：轻提示
- 停留 180 秒：明确卡点
- 提问包含“不会 / 怎么做 / 下一步 / 为什么不行 / 看不懂”时提高诊断权重

### 13.2 `emotion_computing`

规则：

- `emotion_missing_face_model`
- `emotion_missing_audio_model`
- `emotion_missing_camera_start`
- `emotion_missing_audio_input`
- `emotion_has_single_modal_result_but_not_fused`
- `emotion_result_ready_but_user_not_understand`

### 13.3 `face_emotion`

规则：

- `face_missing_model_selection`
- `face_missing_camera_start`
- `face_no_face_detected`
  - 条件：`consecutive_no_face_count >= 3`
- `face_result_ready_but_user_not_understand`

### 13.4 `ecobottle`

一期重点规则：

- `ecobottle_data_not_enough_for_train`
- `ecobottle_wrong_tab_for_action`
- `ecobottle_prediction_without_data`
- `ecobottle_result_ready_but_user_not_understand`

---

## 14. 回答格式

默认回答格式固定为三段：

1. 当前状态
2. 下一步
3. 一条提示

风格要求：

- 小学高年级可懂
- 2 到 4 句
- 最多一句鼓励
- 尽量避免术语
- 必要术语要加括号解释

示例：

> 你现在已经选好了表情模型，也成功得到了表情结果。下一步建议点击“开始录音”，让系统再读取声音情绪。提示：录音 3 到 5 秒就够了，周围尽量安静一些。

---

## 15. 需要新增或修改的文件

## 15.1 后端

### 必改文件

- [app.py](/d:/codeC/VsCodeP/eduplatform/app.py:1)
  - 注册新增上下文蓝图
- [models/orm_models.py](/d:/codeC/VsCodeP/eduplatform/models/orm_models.py:1)
  - 新增 4 个 ORM 模型
- [routes/ai_tutor.py](/d:/codeC/VsCodeP/eduplatform/routes/ai_tutor.py:1)
  - 扩展 `/ai/ask`
- [services/ai_tutor_service.py](/d:/codeC/VsCodeP/eduplatform/services/ai_tutor_service.py:1)
  - 增加上下文版问答链路

### 新增文件

- `routes/ai_context.py`
- `services/ai_context_store.py`
- `services/ai_session_service.py`
- `services/ai_context_service.py`
- `services/ai_rule_service.py`
- `services/ai_knowledge_service.py`
- `services/ai_action_hint_service.py`

## 15.2 前端

### 必改文件

- [templates/base.html](/d:/codeC/VsCodeP/eduplatform/templates/base.html:1)
  - 悬浮助教请求体追加 `context`
  - 支持显示结构化返回的下一步提示
- [templates/emotion_computing.html](/d:/codeC/VsCodeP/eduplatform/templates/emotion_computing.html:1)
  - 初始化 tracker / provider
- [templates/face_emotion.html](/d:/codeC/VsCodeP/eduplatform/templates/face_emotion.html:1)
  - 初始化 tracker / provider
- [templates/ecobottle.html](/d:/codeC/VsCodeP/eduplatform/templates/ecobottle.html:1)
  - 初始化 tracker / provider
- [static/js/emotion_computing.js](/d:/codeC/VsCodeP/eduplatform/static/js/emotion_computing.js:1)
  - 埋点与 snapshot 更新
- [static/js/face_emotion.js](/d:/codeC/VsCodeP/eduplatform/static/js/face_emotion.js:1)
  - 埋点、snapshot 更新、无脸计数器
- [static/js/ecobottle.js](/d:/codeC/VsCodeP/eduplatform/static/js/ecobottle.js:1)
  - 埋点、snapshot 更新、清理 `G01`

### 新增文件

- `static/js/ai_context_tracker.js`
- `static/js/ai_course_bridge.js`

## 15.3 文档与知识库

### 新增目录

- `docs/ai_knowledge/`

---

## 16. 逐步实施顺序

### Step 1

修改：

- `models/orm_models.py`

实现：

- 新增 4 个 ORM 模型类

### Step 2

新增：

- `services/ai_context_store.py`

实现：

- Redis + 内存兜底读写

### Step 3

新增：

- `services/ai_session_service.py`
- `services/ai_context_service.py`

实现：

- 会话创建
- 事件写入
- 快照写入

### Step 4

新增：

- `services/ai_rule_service.py`

实现：

- 三门课一期规则

### Step 5

新增：

- `services/ai_knowledge_service.py`
- `docs/ai_knowledge/...`

实现：

- markdown 知识组织

### Step 6

修改：

- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`

实现：

- `/ai/ask` 结构化增强
- 老接口兼容

### Step 7

新增：

- `routes/ai_context.py`

实现：

- `/ai/context/event`
- `/ai/context/snapshot`
- `/ai/context/delete_memory`
- `/ai/context/debug/<session_id>`

### Step 8

新增：

- `static/js/ai_context_tracker.js`
- `static/js/ai_course_bridge.js`

实现：

- 通用 tracker
- UI 动作桥接

### Step 9

修改：

- `templates/base.html`

实现：

- 悬浮助教上下文注入

### Step 10

修改：

- `templates/emotion_computing.html`
- `static/js/emotion_computing.js`

实现：

- `emotion_computing` 接入 P0 事件与 snapshot

### Step 11

修改：

- `templates/face_emotion.html`
- `static/js/face_emotion.js`

实现：

- `face_emotion` 接入 P0 事件与 snapshot
- 新增 `consecutive_no_face_count`

### Step 12

修改：

- `templates/ecobottle.html`
- `static/js/ecobottle.js`

实现：

- `ecobottle` 接入 P0 事件与 snapshot
- 清理 `G01`

### Step 13

修改：

- `services/ai_action_hint_service.py`
- `static/js/ai_course_bridge.js`

实现：

- 按钮高亮
- tab 切换

---

## 17. 验收用例

### 用例 1

课程：

- `emotion_computing`

场景：

- 已选表情模型
- 摄像头已开启
- 已得到表情结果
- 没有录音
- 用户问“下一步怎么做”

要求：

- 回答必须指出已经完成了表情识别
- 下一步必须引导录音

### 用例 2

课程：

- `face_emotion`

场景：

- 摄像头已开启
- 连续 3 次无脸
- 用户问“为什么没结果”

要求：

- 回答必须提示没有检测到人脸
- 要给出调整站位的下一步建议

### 用例 3

课程：

- `face_emotion`

场景：

- 已有识别结果
- 用户问“这个结果是什么意思”

要求：

- 回答必须解释当前结果含义
- 不能只说“识别成功”

### 用例 4

课程：

- `ecobottle`

场景：

- 当前在训练页
- `data_count < 3`
- 用户问“为什么训练不了”

要求：

- 必须明确指出数据量不足
- 下一步建议必须是继续采集数据

### 用例 5

课程：

- `ecobottle`

场景：

- 已成功预测
- 用户问“下一步是什么”

要求：

- 回答必须说明已经完成预测
- 下一步建议进入控制或报告

---

## 18. 最终结论

一期的核心不是“做一个向量 RAG 聊天框”，而是：

**让 AI 助教记住学生刚刚做过什么，并结合当前页面状态，回答下一步该怎么做。**

本方案的最终实现形式是：

- 统一 `/ai/ask`
- 统一事件 tracker
- 统一 snapshot provider
- 规则优先诊断
- markdown 知识补充
- LLM 负责自然语言组织

这份文档是后续编码时的最终版基准。
