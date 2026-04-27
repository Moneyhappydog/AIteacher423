你现在传给“大模型小助手”的，不是完整聊天历史，而是“当前问题 + 当前页面上下文 + 最近事件摘要 + 页面快照 + 规则诊断 + 知识片段”。
你现在记录下来的，主要是 4 类数据：session、event、snapshot/diagnosis、问答结果。这些会进缓存，也会部分落 MySQL。

关键入口在这些文件里：
templates/base.html (line 414)
static/js/ai_context_tracker.js (line 121)
routes/ai_tutor.py (line 35)
services/ai_context_service.py (line 177)
services/ai_tutor_service.py (line 786)

一步一步看实现

页面加载时先初始化上下文跟踪器。课程页会调用 AiCourseBridge.init(...)，把 page、course、groupId、stepCode、snapshotProvider 注册进去。
代码在 static/js/ai_course_bridge.js (line 33)

跟踪器生成 session_id。它按 page + course + 日期 + 随机串 生成，并放进 sessionStorage，所以同一页面会话里会复用。
代码在 static/js/ai_context_tracker.js (line 69)

课程页操作时会上报事件。前端统一调用 reportEvent()，发到 POST /ai/context/event。
单个事件基础字段是：
session_id
group_id
member_id
page
course
step_code
event_type
event_name
payload
summary_text
dedupe_key
event_time
代码在 static/js/ai_context_tracker.js (line 154) 和 routes/ai_context.py (line 52)

页面状态会定时或延迟上报快照。前端调用 reportSnapshot() 发到 POST /ai/context/snapshot，内容是基础字段再加：
snapshot
diagnosis
代码在 static/js/ai_context_tracker.js (line 170) 和 routes/ai_context.py (line 93)

后端收到事件后，先确保会话存在，再把事件写数据库，并追加到热缓存。
这里做了两层存储：
MySQL 表 ai_tutor_events
缓存键 ai:events:{session_id}
代码在 services/ai_context_service.py (line 57) 和 services/ai_context_store.py (line 132)

后端收到快照后，更新会话表，并把快照/诊断放缓存。
这里写：
MySQL 表 ai_tutor_sessions.latest_snapshot
MySQL 表 ai_tutor_sessions.latest_diagnosis
缓存键 ai:snapshot:{session_id}
缓存键 ai:diag:{session_id}
代码在 services/ai_context_service.py (line 116) 和 services/ai_context_store.py (line 127)

你点击小助手提问时，前端会把问题包装成 /ai/ask 请求。这里不是只传 question，而是把 context 一起塞进去。
实际拼出来的 context 至少包含：
session_id
group_id
member_id
page
course
step_code
snapshot
代码在 templates/base.html (line 414) 和 static/js/ai_context_tracker.js (line 133)

/ai/ask 收到后，如果发现有 context.session_id，就走上下文增强路径 answer_with_context()。
它会：
先补当前登录用户信息
再装配 request context
再做规则诊断
再取知识片段
最后决定要不要调 LLM
代码在 routes/ai_tutor.py (line 35) 和 services/ai_tutor_service.py (line 786)

build_request_context() 真正把“给大模型的隐式上下文”组出来。它会拿到：
question
session
session_id
group_id
member_id
page
course
step_code
snapshot
recent_events
recent_event_summaries
diagnosis
注意这里传给后续 LLM 的不是原始全量事件表，而是压缩过的 recent_event_summaries。
代码在 services/ai_context_service.py (line 177)

真正发给大模型前，会把上下文写成 messages。
发给 LLM 的用户消息里包括：
学生问题
页面
课程
步骤
诊断
建议下一步
提示
最近操作摘要
页面快照里最多 8 个标量字段
知识笔记
代码在 services/ai_tutor_service.py (line 709)

最终通过 OpenAI 兼容接口发出去，请求体是：
model
messages
temperature
max_tokens
请求地址是：
{LLM_BASE_URL}/chat/completions
代码在 services/ai_tutor_service.py (line 470)

回答生成后，会把最终问答结果再落一份库，但目前是“assistant 结果记录”为主，不是完整多轮聊天历史回放。
落表字段有：
session_id
group_id
role='assistant'
user_question_text
answer_text
diagnosis
next_step
tips
context_used
source
代码在 services/ai_tutor_service.py (line 759) 和 models/orm_models.py (line 698)

你现在到底记录了哪些东西

会话表 ai_tutor_sessions
字段重点：session_id、group_id、page、course、step_code、latest_snapshot、latest_diagnosis
见 models/orm_models.py (line 579)

事件表 ai_tutor_events
字段重点：event_type、event_name、payload、summary_text、dedupe_key、event_time
见 models/orm_models.py (line 624)

记忆摘要表 ai_tutor_memory_summaries
表已经建了，但你当前这条问答链路基本没消费它。
见 models/orm_models.py (line 665)

问答消息表 ai_tutor_messages
记录的是“本次回答用了什么上下文、给了什么答案”，不是把所有前端聊天消息原样回放给 LLM。
见 models/orm_models.py (line 698)

当前已上报的事件名

emotion_computing
face_model_selected
audio_model_selected
face_weight_changed
weight_preset_selected
fusion_strategy_changed
camera_started
camera_stopped
recording_started
recording_stopped
face_result_updated
audio_result_updated
fusion_result_updated
toy_selected

face_emotion
model_selected
camera_started
camera_stopped
camera_error
face_result_updated
no_face_detected

ecobottle
tab_changed
sensor_values_changed
quick_action_used
data_point_added
csv_imported
explore_channel_changed
explore_analysis_run
correlation_analysis_run
training_model_selected
training_blocked_not_enough_data
training_completed
prediction_model_selected
prediction_blocked_not_enough_data
prediction_requested
manual_control_applied
control_tab_initialized

一个很重要的事实
现在真正传给大模型的，不是“完整历史聊天记录”，而是“当前问题 + 当前会话状态摘要”。
也就是说：

事件历史会被压缩成短摘要再传。
页面快照只取当前最新状态。
ai_tutor_messages 目前只是落库保存结果，没有在 build_request_context() 里重新读出来喂给 LLM。
所以它更像“状态感知 tutor”，不是“长对话记忆 agent”。