# AI Tutor LLM-First 提速改造实施文档

## 目标

在保留现有 `/ai/ask`、`/ai/context/*`、前端埋点、规则诊断和知识库能力的前提下，把 session 场景下的回答路径优化成“LLM 优先、上下文更轻、超时更短、尾延迟更低”。

本次改造的最高约束是：

- 不影响以前的功能
- 不破坏现有接口
- 所有重要行为变更都尽量通过配置开关控制
- 任何阶段都可以回退

## 兼容性原则

- 旧的无 `session_id` 问答路径继续可用
- `/ai/ask` 返回字段不删除，只允许新增调试字段
- `/ai/context/event` 和 `/ai/context/snapshot` 请求协议不变
- 前端 `window.AiContextTracker` 和 `window.AiCourseBridge` 的公开方法不变
- 规则诊断、知识库选择、缓存和数据库持久化能力继续保留
- 新逻辑优先以“增强”方式接入，而不是推翻现有结构

## 当前代码现状理解

### 1. 问答主链路

当前 AI Tutor 的主问答入口位于：

- `routes/ai_tutor.py`

其中 `POST /ai/ask` 的逻辑是：

1. 读取 `question` 和 `context`
2. 如果 `context.session_id` 存在，则走 `answer_with_context()`
3. 否则走原有 `get_answer()` 路径

这意味着当前系统已经天然分成了两条链路：

- 旧链路：普通问答，不依赖 session context
- 新链路：上下文增强问答，依赖 session、events、snapshot、diagnosis、knowledge

### 2. 上下文增强路径

上下文增强路径主要位于：

- `services/ai_tutor_service.py`
- `services/ai_context_service.py`
- `services/ai_rule_service.py`
- `services/ai_knowledge_service.py`
- `services/ai_session_service.py`

当前 `answer_with_context()` 的同步流程大致是：

1. `build_request_context()`
2. `detect_stuck()`
3. `build_knowledge_context()`
4. `build_context_llm_messages()`
5. `call_llm_messages()`
6. `compose_structured_response()`
7. `update_session_diagnosis()`
8. `_persist_tutor_message()`

这里的主要问题不是某一个点绝对错误，而是整条链路过长，并且多个步骤都在主请求里同步完成。

### 3. 现有上下文来源

当前上下文主要来自三部分：

#### 3.1 最近事件和快照

由 `services/ai_context_service.py` 组装：

- `recent_events`
- `recent_event_summaries`
- `snapshot`

数据来源包括：

- Redis / Flask-Caching / 内存 fallback
- MySQL 中的 `AiTutorEvent` 和 `AiTutorSession`

#### 3.2 规则诊断

由 `services/ai_rule_service.py` 负责：

- `detect_stuck()`
- 分课程规则检测

它会给出：

- `diagnosis`
- `next_step`
- `tips`
- `rule_hits`

#### 3.3 markdown 知识片段

由 `services/ai_knowledge_service.py` 负责：

- `build_knowledge_context()`

它根据：

- `course`
- `step_code`
- `diagnosis`

返回：

- `knowledge_refs`
- `snippets`
- `text`

### 4. 当前性能风险点

结合现有代码和日志，当前慢的主要风险点是：

#### 4.1 LLM 请求尾延迟过大

`services/ai_tutor_service.py` 中 `_post_openai_compatible_messages()` 目前使用：

- `httpx.Client(timeout=45.0, trust_env=False)`

这意味着单次 LLM 调用可能阻塞很久。已有日志显示 `/ai/ask` 曾出现单次耗时 `337742ms`，说明长尾延迟已经发生。

#### 4.2 prompt 输入偏重

当前 `build_context_llm_messages()` 会把这些内容拼到 prompt 中：

- 页面和课程信息
- 最近事件摘要
- 快照字段
- 规则诊断
- tips
- markdown 知识片段

如果 recent events 偏多、knowledge 文本偏长、snapshot 字段冗余，prompt 会明显变胖，带来：

- 序列化时间变长
- 网络传输时间变长
- 模型首 token 延迟增加
- 总 token 消耗增加
- 模型更容易被噪声拖慢

#### 4.3 主请求中存在同步持久化

当前 `answer_with_context()` 在生成回答后，还会继续同步做：

- `update_session_diagnosis()`
- `_persist_tutor_message()`

这些操作虽然不是生成答案本身必需的，但会占用用户等待时间。

#### 4.4 diagnosis 对最终回答的影响仍然偏强

虽然当前代码已经尽量优先尝试 LLM，但 `compose_structured_response()` 中仍然存在 rule-based answer 的较强兜底逻辑。后续需要进一步明确：

- diagnosis 用于辅助 LLM
- fallback 只在 LLM 真失败时接管

#### 4.5 事件数量对 prompt 有间接拖累

“事件太多”不是一定让后端直接卡死，但会通过以下路径让 LLM 变慢：

1. recent events 读取和序列化变多
2. event summary 进入 prompt
3. snapshot 和 event payload 出现重复信息
4. 模型需要读更多低价值上下文

因此事件过多确实会影响速度，但主要是通过“上下文变胖”来影响。

## 总体改造策略

本次优化不走“扩大模板回答覆盖率”的路线，而是坚持：

- session 场景下尽量返回 LLM 答案
- 模板回答只做短超时或失败兜底
- 真正的提速手段是缩短 LLM 路径

核心原则：

1. LLM-first
2. prompt minimal
3. timeout strict
4. persistence delayed
5. behavior backward-compatible

## 分阶段实施计划

---

## Phase 1：增加配置开关和性能观测，不改变现有行为

### 目标

在不改变业务逻辑的前提下，为后续所有改动建立安全边界和观测能力。

### 修改点

文件：

- `config.py`
- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`

### 建议新增配置项

在 `config.py` 中新增：

- `AI_TUTOR_LLM_FIRST_ENABLED = True`
- `AI_TUTOR_CONTEXT_SUMMARY_ENABLED = False`
- `AI_TUTOR_MINIMAL_PROMPT_ENABLED = False`
- `AI_TUTOR_ASYNC_PERSIST_ENABLED = False`
- `AI_TUTOR_LLM_CACHE_TTL = 0`
- `AI_TUTOR_LLM_CONNECT_TIMEOUT = 3`
- `AI_TUTOR_LLM_WRITE_TIMEOUT = 5`
- `AI_TUTOR_LLM_READ_TIMEOUT = 12`
- `AI_TUTOR_MAX_RECENT_EVENTS = 15`
- `AI_TUTOR_MAX_PROMPT_EVENTS = 5`
- `AI_TUTOR_MAX_KNOWLEDGE_CHARS = 1200`

### 新增观测字段

在 `answer_with_context()` 中记录分段耗时：

- `context_build_ms`
- `rule_detect_ms`
- `knowledge_ms`
- `llm_ms`
- `persist_ms`
- `total_ms`

可选增加：

- `prompt_chars`
- `prompt_events_count`
- `knowledge_chars`

### 对外行为

- `/ai/ask` 原有字段保持不变
- 只新增调试字段
- 前端无需改动

### 验收标准

- 当前回答内容不变
- `/ai/ask` 可看到分段耗时
- 新配置未启用增强逻辑时，不改变现有结果

---

## Phase 2：压缩 prompt 输入，但先不调整主回答逻辑

### 目标

先减小 prompt 体积，降低 LLM 平均耗时和 token 消耗，但暂时不改 fallback 主逻辑，确保风险最小。

### 修改点

文件：

- `services/ai_context_service.py`
- `services/ai_knowledge_service.py`
- `services/ai_tutor_service.py`

### 2.1 新增 prompt 专用事件选择逻辑

在 `services/ai_context_service.py` 新增函数：

- `select_prompt_events(recent_events, limit=5)`
- `build_prompt_context_summary(context, rule_result)`

功能要求：

- 只选 `3-5` 条关键事件
- 同类高频事件去重
- 优先保留状态切换事件

建议优先事件类型：

- 模型选择
- 摄像头启动
- 录音启动
- 结果生成
- 融合完成
- 训练完成
- 预测失败 / 成功

### 2.2 新增 prompt 专用知识裁剪逻辑

保留现有 `build_knowledge_context()` 不动，再新增一个更轻量的方法，例如：

- `build_prompt_knowledge_context(...)`

要求：

- 只保留 1 段最相关 markdown
- 使用更小的 `max_chars`
- 不影响原来的 `knowledge_refs` 行为

### 2.3 改造 `build_context_llm_messages()`

不再直接把大量原始 recent event summaries 拼进 prompt，而是改为：

- 页面和课程
- 当前 step
- 一段结构化摘要
- 精简 snapshot
- 精简 knowledge
- diagnosis 作为参考背景

### 设计要求

- 不暴露内部字段名给学生
- 不把原始事件名直接原样说给学生
- 继续保留当前自然中文、老师式语气

### 验收标准

- `/ai/ask` 行为兼容
- `prompt_chars` 显著下降
- `tokens_used` 明显下降
- `source` 仍然优先是 `llm_api`

---

## Phase 3：明确 LLM-first 行为，弱化 diagnosis 对主回答的接管

### 目标

满足核心需求：尽量让最终 answer 来自 LLM，而不是模板。

### 修改点

文件：

- `services/ai_tutor_service.py`

### 3.1 调整 `answer_with_context()` 主流程

目标逻辑：

1. 有 `session_id`
2. 有可用 `LLM_API_KEY`
3. 配置 `AI_TUTOR_LLM_FIRST_ENABLED=True`
4. 则优先尝试 LLM

只有在以下情况下才 fallback：

- timeout
- 403 / 401
- network error
- empty response

### 3.2 调整 `compose_structured_response()`

要求：

- LLM 成功时，`answer` 必须优先用 LLM 结果
- `diagnosis`、`next_step`、`tips` 仍然保留在结构化字段中
- rule-based 文字不再抢占主 answer

### 3.3 兼容要求

- 旧的 `get_answer()` 路径完全保留
- 不删任何旧字段
- 如需回退，配置开关即可恢复旧行为

### 验收标准

- 有 `session_id` 的问题默认 `source=llm_api`
- 有 diagnosis 且 LLM 正常时，不再返回规则模板主答案
- 非 session 问答不受影响

---

## Phase 4：收紧 LLM 超时，解决长尾阻塞

### 目标

从根本上消除超长等待。

### 修改点

文件：

- `services/ai_tutor_service.py`

### 4.1 改造 httpx timeout

当前实现：

- `timeout=45.0`

修改为分段 timeout：

- connect: `Config.AI_TUTOR_LLM_CONNECT_TIMEOUT`
- write: `Config.AI_TUTOR_LLM_WRITE_TIMEOUT`
- read: `Config.AI_TUTOR_LLM_READ_TIMEOUT`
- pool: 3s

### 4.2 统一错误类型

建议归一化为：

- `timeout`
- `forbidden`
- `unauthorized`
- `connect_error`
- `empty_response`
- `bad_response`
- `unknown_error`

### 4.3 fallback 时机

只有 LLM 明确失败时才触发 fallback，而不是因为 diagnosis 存在就提前走 fallback。

### 验收标准

- LLM 失败时能在 `12-15s` 内结束
- `llm_error` 可读性明显提升
- 不再出现数百秒卡死

---

## Phase 5：将非关键持久化从主请求中移出或延后

### 目标

减少用户等待的尾部耗时，同时不移除原有持久化能力。

### 修改点

文件：

- `services/ai_tutor_service.py`
- `services/ai_session_service.py`

### 涉及逻辑

当前主请求中同步执行：

- `update_session_diagnosis()`
- `_persist_tutor_message()`

后续处理原则：

- diagnosis hot cache 继续即时写
- 数据库持久化允许延后
- 持久化失败不能影响主回答返回

### 推荐实现策略

第一版优先做“best-effort delayed persistence”：

- 回答先返回
- 持久化单独 try/except
- 保留耗时统计
- 配置开关控制是否启用

### 验收标准

- 用户拿到 answer 的时间变短
- 持久化能力仍存在
- 持久化失败不影响主流程

---

## Phase 6：增加 LLM 结果短 TTL 缓存

### 目标

降低高频重复问题对外部 LLM 的重复调用。

### 修改点

文件：

- `services/ai_context_store.py`
- `services/ai_tutor_service.py`

### 6.1 新增缓存能力

新增 LLM answer cache 的读写函数，例如：

- `get_llm_answer_cache(key)`
- `set_llm_answer_cache(key, value, ttl)`

### 6.2 cache key 设计

建议包含：

- question
- page
- course
- diagnosis
- 精简 snapshot hash

### 6.3 使用策略

- 只缓存成功的 LLM 结果
- 不缓存 fallback
- 状态变化后自动失效

### 验收标准

- 相同状态下重复问题响应明显变快
- 结果仍然来自 LLM 语义
- 不影响状态变化后的回答正确性

---

## Phase 7：控制事件对 prompt 的副作用，但不破坏现有前端埋点

### 目标

减少“事件太多把 prompt 变胖”的副作用，同时保持前端兼容。

### 修改点

文件：

- `services/ai_context_service.py`
- 如有必要，再调整：
  - `static/js/ai_context_tracker.js`
  - `static/js/ai_course_bridge.js`
  - 课程页 JS

### 处理原则

第一阶段不改前端协议，只改后端 prompt 选择逻辑：

- event 继续正常上报
- snapshot 继续正常上报
- prompt 中只取少量关键事件

第二阶段若仍需优化，再考虑精简 event payload 中的冗余 snapshot，但这一步必须在确认不影响现有调试和规则逻辑后再做。

### 验收标准

- 前端不需要同步大改
- 上报协议不破坏
- prompt 上下文显著变轻

## 回归测试清单

### 1. 旧问答链路回归

- 无 `session_id` 的 `/ai/ask` 仍正常工作
- 本地问答 / 普通 fallback 不受影响

### 2. 新问答链路回归

三门课程都要覆盖：

- `emotion_computing`
- `face_emotion`
- `ecobottle`

检查项：

- session context 能正常带上
- diagnosis 仍能生成
- knowledge 仍能匹配
- LLM 正常回答

### 3. 上下文接口回归

- `POST /ai/context/event`
- `POST /ai/context/snapshot`
- `GET /ai/context/debug/<session_id>`

都要确认：

- 原请求字段不变
- 旧前端无需改动也能继续使用

### 4. 结构化返回回归

确保这些字段继续存在：

- `answer`
- `source`
- `model`
- `tokens_used`
- `latency_ms`
- `mode`
- `diagnosis`
- `next_step`
- `tips`
- `context_used`
- `llm_attempted`
- `llm_error`

### 5. 异常场景回归

必须覆盖：

- `LLM_API_KEY` 缺失
- 模型名错误
- 403
- timeout
- empty response
- 网络连接失败

要求：

- 不影响页面继续使用
- 用户仍能得到兜底答复
- 错误能从调试字段中看出来

## 建议实施顺序

按风险从低到高、按收益从快到慢，推荐顺序如下：

1. Phase 1：配置开关和观测
2. Phase 2：prompt 压缩
3. Phase 3：LLM-first 行为切换
4. Phase 4：超时治理
5. Phase 5：移出同步持久化
6. Phase 6：LLM 结果缓存
7. Phase 7：事件副作用进一步治理

## 每阶段完成后的验收方式

每完成一个阶段，建议至少做三类验证：

1. 功能兼容验证
- 老页面是否还能正常提问
- 老接口是否还能正常响应

2. 性能验证
- `/ai/ask` 总耗时
- `llm_ms`
- `tokens_used`
- `prompt_chars`

3. 行为验证
- 是否仍以 LLM 为主回答来源
- fallback 是否只在真正失败时触发
- diagnosis / next_step / tips 是否仍然保留

## 最终成功标准

如果改造成功，应达到以下结果：

- session 问答默认仍以 LLM 输出为主
- fallback 触发率下降
- prompt 长度和 token 消耗下降
- `/ai/ask` 的 P95 延迟明显下降
- 不影响无 `session_id` 的旧功能
- 不破坏上下文事件和快照上报接口
- 不破坏前端现有交互

## 备注

这份文档用于后续分阶段实施。后续修改时应坚持以下原则：

- 一次只改一个阶段
- 每阶段都先做最小改动
- 每阶段改动后都做回归验证
- 如遇行为风险，优先加开关而不是强行替换旧逻辑

