# CLAUDE.md

## 核心目标

当前任务不是做普通聊天框，而是做“能记住学生刚刚做过什么，并据此回答下一步操作”的 AI 助教。

优先级：

- P0：记住最近操作 + 回答下一步
- P1：明显卡住时主动提示
- P2：长期画像与长期陪伴

## 一期范围

- 统一入口：`/ai/ask`
- 覆盖页面：
  - 全站悬浮助教
  - `emotion_computing`
  - `face_emotion`
  - `ecobottle`
- 一期不做：
  - 向量 RAG
  - 教师后台
  - `data_collect` / `model_import` / `model_eval`

## 兼容性红线

- 只新增表，不改现有表结构
- `/ai/ask` 只能向后兼容扩展
- 不改课程页主流程函数的业务含义
- 课程页只做外挂式增强：
  - 事件上报
  - snapshot provider
- Redis 默认可用，但必须有内存兜底
- MySQL 是持久化真源

## 记忆粒度

- 账号模式：小组账号
- 记忆粒度：`group_id` 为主，`session_id` 为当前课程会话
- `member_id` 可选附带
- 共享记忆，不区分个人

## 一期技术路线

- 不做向量库
- 用：
  - 页面状态
  - 最近事件
  - 规则诊断
  - markdown 知识库
  - LLM 组织语言

## 回答格式

固定输出：

1. 当前状态
2. 下一步
3. 一条提示

风格：

- 小学高年级可懂
- 2 到 4 句
- 最多一句鼓励
- 避免术语

## 卡点策略

- 规则优先，LLM 补充
- 依据：
  - 停留时间
  - 关键步骤未完成
  - 提问关键词
- 阈值：
  - 90 秒轻提示
  - 180 秒明确卡点

## `/ai/ask` 结构化目标返回

- `answer`
- `diagnosis`
- `next_step`
- `tips`
- `context_used`

## 一期必须采集的页面快照

### `emotion_computing`

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

### `face_emotion`

- `current_model`
- `camera_status`
- `last_result`
- `consecutive_no_face_count`
- `last_face_count`
- `last_status_text`

### `ecobottle`

- `current_tab`
- `prediction_model`
- `train_model`
- `preprocessing`
- `prediction_steps`
- `data_count`
- `last_prediction`
- `last_control_strategy`
- `last_control_action`

## 一期事件边界

### `emotion_computing` P0

- 选表情模型
- 选声音模型
- 改融合策略
- 改权重
- 开关摄像头
- 开关录音
- 表情结果更新
- 声音结果更新
- 融合结果更新
- 选择玩具反馈

### `face_emotion` P0

- 选模型
- 开关摄像头
- 发起预测
- 有人脸结果
- 连续无人脸

说明：

- `consecutive_no_face_count` 是新增推导状态，不是现成字段

### `ecobottle` P0

- 切 tab
- 应用手动环境值
- 快捷动作
- 添加数据
- 运行探索分析
- 运行相关性分析
- 选择训练模型
- 修改预测步数
- 修改预处理
- 开始训练
- 数据不足导致训练被拦截
- 发起预测
- 切换控制策略
- 应用控制动作
- 导出报告

### `ecobottle` P1

- 删除记录
- 清空表
- 导入导出 CSV
- 加载历史
- 修改多项式阶数
- 练习模块事件

## `ecobottle` 特别提醒

以下函数中的写死 `G01` 一期必须清理：

- `ecoAddData()`
- `ecoDeleteRecord()`
- `ecoClearTable()`
- `ecoImportCsv()`
- `ecoExportCsv()`
- `ecoLoadHistory()`
- `runExploreAnalysis()`
- `runCorrelationAnalysis()`

## 新增表

- `ai_tutor_sessions`
- `ai_tutor_events`
- `ai_tutor_memory_summaries`
- `ai_tutor_messages`

## 推荐编码顺序

1. ORM 新表
2. Redis/内存 store
3. session/context service
4. rule service
5. knowledge service
6. `ai_tutor_service` / `routes/ai_tutor.py`
7. `routes/ai_context.py`
8. 通用前端 tracker
9. `base.html`
10. `emotion_computing`
11. `face_emotion`
12. `ecobottle`
