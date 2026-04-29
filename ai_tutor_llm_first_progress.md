# AI Tutor LLM-First 改造进度

本文件用于记录按照 `ai_tutor_llm_first_optimization_plan.md` 执行的每一步实际修改。

规则：

- 每完成一步就记录
- 每一步完成后暂停，等待下一条“继续”指令
- 重点记录：
  - 改了哪些文件
  - 改了哪些函数
  - 解决了什么问题
  - 这一步是否影响旧功能

## Step Plan

| Step | Phase | Scope | Status |
|---|---|---|---|
| 1 | Phase 1 | 增加配置开关、性能观测字段和根目录进度文档 | Done |
| 2 | Phase 2 | 压缩 prompt 输入，新增 prompt 专用上下文摘要与知识裁剪 | Done |
| 3 | Phase 3 | 切换到更明确的 LLM-first 主回答策略 | Done |
| 4 | Phase 4 | 收紧 LLM timeout，降低长尾阻塞 | Done |
| 5 | Phase 5 | 延后非关键持久化，减少主请求尾部耗时 | Done |
| 6 | Phase 6 | 增加 LLM 结果短 TTL 缓存 | Done |
| 7 | Phase 7 | 进一步控制事件对 prompt 的副作用 | Done |

## Step 1 - Phase 1 配置开关与性能观测

Status: Done

### Goal

在不改变现有 AI Tutor 核心回答行为的前提下，为后续优化建立配置开关和可观测性基础，并新增一个根目录进度文档用于后续逐步同步与部署。

### Modified Files

- `config.py`
- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

## Step 7 - Phase 7 事件净化与 Prompt 副作用控制

Status: Done

### Goal

在不修改前端 `AiContextTracker` / `AiCourseBridge` 接口、不改变 `/ai/context/*` 协议的前提下，进一步降低高频事件和重 payload 对 prompt 的副作用，让 LLM 看到的是更轻、更稳定的事件摘要，而不是完整原始埋点。

### Modified Files

- `services/ai_context_service.py`
- `services/ai_tutor_service.py`
- `ai_tutor_llm_first_progress.md`

## Post-Phase Update - 取消 LLM Read Timeout

Status: Done

### Goal

根据当前使用诉求，取消 AI Tutor 对外部 LLM 响应读取阶段的强制超时，避免因为模型生成较慢时触发 `LLM API call timed out: The read operation timed out`，改为默认持续等待模型返回结果。

### Modified Files

- `config.py`
- `services/ai_tutor_service.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 调整 `config.py` 中的默认读取超时配置

将：
- `AI_TUTOR_LLM_READ_TIMEOUT` 默认值从 `12` 改为 `0`

这里的 `0` 不再表示“立即超时”，而是作为“关闭 read timeout”的开关值。

#### 2. 调整 `services/ai_tutor_service.py` 中的 timeout 构造逻辑

在 `_post_openai_compatible_messages()` 中：
- 保留 `connect` timeout
- 保留 `write` timeout
- 将 `read` timeout 改为：
  - 当 `AI_TUTOR_LLM_READ_TIMEOUT <= 0` 时，传入 `None`
  - 让 `httpx` 在读取响应阶段不主动超时

也就是说，现在默认行为变成：
- 如果接口能连上、请求也能发出去，就一直等模型把结果返回
- 不再因为读取阶段超过 12 秒而主动 fallback

### Problems Solved

## Post-Phase Update - `/ai/ask` 分段计时与 Prompt 体积观测

Status: Done

### Goal

先不调整 AI Tutor 的主回答策略，只给当前 `/ai/ask` 链路补上可直接测试的后端分段计时和 prompt 体积观测，方便定位瓶颈到底是在上下文构建、规则诊断、知识拼接、LLM 调用，还是持久化阶段。

### Modified Files

- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 在 `services/ai_tutor_service.py` 中新增统一毫秒计时函数

新增：
- `_now_ms()`

用于在 `answer_with_context()` 内部对每个阶段打点，避免重复写时间转换逻辑。

#### 2. 在 `answer_with_context()` 中增加后端分段耗时统计

新增统计字段：
- `context_build_ms`
- `rule_detect_ms`
- `knowledge_ms`
- `llm_ms`
- `persist_ms`
- `total_ms`

对应阶段分别是：
- 构建 request context
- 规则诊断
- 知识片段构建
- LLM 调用
- assistant 结果落库
- 整体请求总耗时

#### 3. 增加 prompt 体积观测

新增统计字段：
- `prompt_chars`
- `prompt_events_count`
- `knowledge_chars`

含义：
- `prompt_chars`：最终发给 LLM 的 messages 总字符数
- `prompt_events_count`：当前注入 prompt 的 recent event summaries 数量
- `knowledge_chars`：知识片段文本长度

这几个字段可以帮助判断：
- 是不是 prompt 太胖
- 事件摘要是不是过多
- knowledge snippet 是不是过长

#### 4. 在日志中输出完整 timing 信息

新增一条 `logger.info(...)`，会把这批 timing / prompt 体积字段一起打到后端日志里，方便你在服务器上看真实分布。

#### 5. 在 `/ai/ask` 响应中透出调试字段

在 `routes/ai_tutor.py` 的 `ask()` 返回中新增：
- `context_build_ms`
- `rule_detect_ms`
- `knowledge_ms`
- `llm_ms`
- `persist_ms`
- `total_ms`
- `prompt_chars`
- `prompt_events_count`
- `knowledge_chars`

这样你前端现有 `window.__lastMaoAskResponse` 就能直接拿到这些值，不需要先改前端页面结构。

### Problems Solved

- 解决了“现在只能感觉慢，但不知道慢在链路哪一段”的问题
- 解决了“怀疑 prompt 太长，但没有直接统计字段”的问题
- 解决了“后续服务器排查时缺少统一 timing 日志”的问题

### Compatibility Impact

这次改动不改变原有问答逻辑：

- `/ai/ask` 请求格式不变
- 回答策略不变
- LLM / fallback 决策不变
- 只是在响应里新增了调试字段

因此它是一个纯观测型改动，适合先上线做测试。

### Notes For Server Sync

这次如果要同步到服务器，需要复制这些文件：

- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

- 解决了“模型生成稍慢时直接报 `The read operation timed out`”的问题
- 解决了“你明确希望最后尽量等到 LLM 回答，而不是被短超时打断”的问题

### Compatibility Impact

这次修改会改变 LLM 超时行为：

- 以前：读取阶段超过设定时间会触发 timeout fallback
- 现在：默认不会因为 read timeout 中断

但以下行为仍然保留：

- 连接不上接口时仍会报连接错误
- 请求发送阶段异常时仍会报相应错误
- `/ai/ask` 接口格式不变
- 其他已有功能不变

### Risk Notes

这次修改的代价是：

- 如果模型端长时间不返回，当前请求会一直等待更久
- `/ai/ask` 的尾延迟可能重新变大

这是按你当前“宁可等，也不要 read timeout”的目标做的取舍。

### Notes For Server Sync

这次如果要同步到服务器，需要复制这些文件：

- `config.py`
- `services/ai_tutor_service.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 在 `services/ai_context_service.py` 中增加 prompt 专用事件净化

新增：
- `PROMPT_EXCLUDED_PAYLOAD_KEYS`
- `_sanitize_prompt_value()`
- `_sanitize_payload_for_prompt()`
- `sanitize_event_for_prompt()`

作用：
- 从事件 payload 中排除重字段，例如 `snapshot`、图片、音频、base64 等内容
- 只保留适合 prompt 的简单值
- 限制字符串长度和 payload 项数

这样即使前端仍然正常上报完整事件，进入 prompt 的事件视图也会自动变轻。

#### 2. 让 prompt 侧事件选择统一基于净化后的事件

本步调整了：
- `select_prompt_events()`
- `build_prompt_context_summary()`
- `build_request_context()`
- `build_context_used()`

具体变化：
- `select_prompt_events()` 先对事件做 prompt-safe 净化，再做关键事件筛选
- `build_request_context()` 新增：
  - `recent_events_prompt`
  - `recent_event_prompt_summaries`
- `build_context_used()` 优先返回 prompt-safe 的事件摘要

这样后端内部仍然保留原始 recent events，但问答链路和调试证据优先使用更干净的 prompt 版本。

#### 3. 在 `services/ai_tutor_service.py` 中统一读取 prompt-safe 事件摘要

本步调整了：
- `build_llm_messages_from_context()`
- `build_context_llm_messages()`
- `answer_with_context()`

具体变化：
- `build_llm_messages_from_context()` 现在优先读取 `recent_event_prompt_summaries`
- `build_context_llm_messages()` 默认优先读取 prompt-safe 的 recent events
- `answer_with_context()` 中的 `prompt_events_count` 改为：
  - 开启 prompt summary / minimal prompt 时，统计实际被选入 prompt 的关键事件数
  - 其他情况下，统计 prompt-safe summaries 数量

这样观测值和真实 prompt 注入量会更接近，不会继续把高频原始事件数直接当成 prompt 事件数。

### Problems Solved

- 解决了“事件 payload 里重复携带 snapshot / 图片 / 音频，容易把 prompt 变胖”的问题
- 解决了“虽然已经做了关键事件选择，但部分 prompt 读取点仍然可能读到原始事件摘要”的问题
- 解决了“`prompt_events_count` 和真实注入 prompt 的事件数量不一致，不利于观察优化效果”的问题

### Compatibility Impact

本步继续保持向后兼容：

- `/ai/context/event` 请求格式不变
- `/ai/context/snapshot` 请求格式不变
- 前端事件上报接口不变
- 原始事件仍然保留在后端缓存/数据库中

本步只影响：
- prompt 侧使用哪一版事件视图
- `/ai/ask` 返回里的事件观测更接近真实 prompt 输入

因此这一步不会破坏旧功能，只是在 LLM 问答链路里默认更偏向使用精简后的事件摘要。

### Verification

- Python AST parse should be rerun for:
  - `services/ai_context_service.py`
  - `services/ai_tutor_service.py`

建议联调时重点观察：
- `prompt_events_count` 是否下降到更合理的范围
- 相同提问下 `prompt_chars` 是否继续下降
- `/ai/context/*` 与前端埋点是否保持兼容

### Notes For Server Sync

本步如果要同步到服务器，需要复制这些文件：

- `services/ai_context_service.py`
- `services/ai_tutor_service.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 在 `config.py` 中新增了 Phase 1 所需配置项

新增配置：

- `AI_TUTOR_LLM_FIRST_ENABLED`
- `AI_TUTOR_CONTEXT_SUMMARY_ENABLED`
- `AI_TUTOR_MINIMAL_PROMPT_ENABLED`
- `AI_TUTOR_ASYNC_PERSIST_ENABLED`
- `AI_TUTOR_LLM_CACHE_TTL`
- `AI_TUTOR_LLM_CONNECT_TIMEOUT`
- `AI_TUTOR_LLM_WRITE_TIMEOUT`
- `AI_TUTOR_LLM_READ_TIMEOUT`
- `AI_TUTOR_MAX_RECENT_EVENTS`
- `AI_TUTOR_MAX_PROMPT_EVENTS`
- `AI_TUTOR_MAX_KNOWLEDGE_CHARS`

这些配置目前只作为后续阶段使用的准备项，本步不会改变原来的主回答策略。

#### 2. 在 `services/ai_tutor_service.py` 中为 `answer_with_context()` 增加分段耗时观测

新增记录了这些阶段耗时：

- `context_build_ms`
- `rule_detect_ms`
- `knowledge_ms`
- `llm_ms`
- `persist_ms`
- `total_ms`

同时新增了这些上下文体积观测字段：

- `prompt_chars`
- `prompt_events_count`
- `knowledge_chars`

这些字段会随着结构化结果一起返回，用于后续判断慢点主要在哪一段。

#### 3. 在 `routes/ai_tutor.py` 中把观测字段透出给 `/ai/ask` 响应

新增返回字段：

- `context_build_ms`
- `rule_detect_ms`
- `knowledge_ms`
- `llm_ms`
- `persist_ms`
- `total_ms`
- `prompt_chars`
- `prompt_events_count`
- `knowledge_chars`

这样前端或浏览器控制台可以直接看到每次问答的关键耗时。

#### 4. 新增根目录进度文档

新增：

- `ai_tutor_llm_first_progress.md`

用于后续逐步记录每一阶段改动，方便：

- 本地追踪
- 和服务器手动同步时核对文件
- 回滚时定位改动范围

### Problems Solved

- 解决了“后续改动没有统一开关”的问题
- 解决了“现在慢，但不知道慢在哪一段”的问题
- 解决了“后续每一步改了什么，不方便同步到服务器”的问题

### Compatibility Impact

本步骤不改变以下行为：

- `/ai/ask` 的原有入参不变
- `/ai/ask` 的原有核心返回字段不变
- 无 `session_id` 的旧问答路径不变
- 有 `session_id` 的上下文问答逻辑顺序不变
- `/ai/context/*` 接口不变
- 前端现有调用方式不变

唯一变化是 `/ai/ask` 新增了一批调试字段，但这是向后兼容的增强，不会破坏旧功能。

### Notes For Server Sync

本步如果要同步到服务器，需要复制这些文件：

- `config.py`
- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

## Step 2 - Phase 2 Prompt 压缩与最小有效上下文

Status: Done

### Goal

在不切换主回答策略的前提下，先把“压缩 prompt 输入”的能力接入当前代码，减少未来 LLM 请求中的无效上下文，并确保默认仍然通过配置开关控制，不影响现有线上行为。

### Modified Files

- `services/ai_context_service.py`
- `services/ai_knowledge_service.py`
- `services/ai_tutor_service.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 在 `services/ai_context_service.py` 中新增 prompt 专用事件选择逻辑

新增内容：

- `KEY_EVENT_PRIORITIES`
- `select_prompt_events()`
- `build_prompt_context_summary()`

同时增加了若干内部辅助函数，用于：

- 按事件重要性排序
- 去除低价值重复事件
- 从最近事件中选出少量高信号事件
- 将 snapshot 压缩成适合 prompt 的短摘要

这样后续 prompt 不必直接吃整段原始 recent events 列表，而是可以只看少量关键状态切换事件。

#### 2. 在 `services/ai_knowledge_service.py` 中新增 prompt 专用知识裁剪逻辑

新增：

- `build_prompt_knowledge_context()`

它和原来的 `build_knowledge_context()` 并存，职责不同：

- `build_knowledge_context()` 继续用于现有完整知识上下文
- `build_prompt_knowledge_context()` 专门用于 LLM prompt，默认只取更少 refs 和更短文本

这样不会破坏现有知识引用结构，同时为后续最小 prompt 做准备。

#### 3. 在 `services/ai_tutor_service.py` 中接入 Phase 2 的压缩能力

`build_context_llm_messages()` 现在已经支持：

- 当 `AI_TUTOR_CONTEXT_SUMMARY_ENABLED` 或 `AI_TUTOR_MINIMAL_PROMPT_ENABLED` 打开时：
  - 使用 `build_prompt_context_summary()` 选择少量关键事件
  - 使用压缩后的 snapshot 摘要

`answer_with_context()` 现在已经支持：

- 保留原有 `knowledge_context`
- 在 `AI_TUTOR_MINIMAL_PROMPT_ENABLED` 打开时，额外生成 `prompt_knowledge_context`
- LLM 消息构建时优先使用 `prompt_knowledge_context`

这意味着：

- 现有结构化返回继续保留完整 knowledge context
- LLM prompt 可以单独走更小的知识片段

### Problems Solved

- 解决了“原始 recent events 过多，未来 prompt 太胖”的问题
- 解决了“知识片段只有一个完整版本，无法单独给 prompt 做裁剪”的问题
- 解决了“无法在不破坏旧功能的前提下逐步接入 prompt 压缩逻辑”的问题

### Compatibility Impact

本步骤默认不会改变现有主流程行为，因为新增逻辑由配置开关控制：

- `AI_TUTOR_CONTEXT_SUMMARY_ENABLED`
- `AI_TUTOR_MINIMAL_PROMPT_ENABLED`

当这两个开关保持 `false` 时：

- 现有 prompt 构建方式继续生效
- 现有 `/ai/ask` 行为不变
- 旧功能不受影响

当未来打开这些开关时：

- 只影响 LLM prompt 组织方式
- 不影响 `/ai/ask` 接口格式
- 不影响 `/ai/context/*` 接口
- 不影响前端全局对象和调用方式

### Verification

- Python AST parse passed for:
  - `services/ai_context_service.py`
  - `services/ai_knowledge_service.py`
  - `services/ai_tutor_service.py`

### Notes For Server Sync

本步如果要同步到服务器，需要复制这些文件：

- `services/ai_context_service.py`
- `services/ai_knowledge_service.py`
- `services/ai_tutor_service.py`
- `ai_tutor_llm_first_progress.md`

## Step 3 - Phase 3 更明确的 LLM-first 主回答策略

Status: Done

### Goal

在不修改接口格式和不移除原有 fallback 能力的前提下，把有 `session_id` 的上下文问答更明确地切换为 `LLM-first`：

- LLM 成功时，主回答优先使用 LLM
- LLM 失败时，再进入 fallback
- rule diagnosis 继续保留，但不再优先抢占主回答

### Modified Files

- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 在 `compose_structured_response()` 中明确了 LLM-first 的主回答优先级

新增逻辑：

- 读取 `AI_TUTOR_LLM_FIRST_ENABLED`
- 当开关开启且 LLM 没有成功返回，但 `base_result` 已经生成时：
  - 主回答优先使用 `base_result`
  - 规则模板不再先于 `base_result` 抢占 `answer`

这样可以保证：

- LLM 成功时，最终 `answer` 来自 LLM
- LLM 失败时，才转为 fallback
- diagnosis 仍然继续通过 `diagnosis / next_step / tips` 结构化字段返回

#### 2. 在 `answer_with_context()` 中调整了上下文 LLM 的触发与 fallback 决策

新增逻辑：

- 增加 `llm_first_enabled`
- 增加 `should_try_context_llm`
- 增加 `llm_failed`
- 增加 `should_build_base_result`

行为变化：

- 当 `AI_TUTOR_LLM_FIRST_ENABLED=true` 时：
  - 只要有 LLM 配置，就优先尝试上下文 LLM
  - 只要 LLM 没成功，就继续构建 `base_result` 作为 fallback
  - 不再因为 diagnosis 存在而默认优先走规则模板主回答

#### 3. 在 `/ai/ask` 中增加了两个调试字段

新增透出：

- `llm_first_enabled`
- `llm_failed`

这样后续你在浏览器或日志里可以更容易判断：

- 当前是否处于 LLM-first 模式
- 这次请求是否发生了 LLM 失败并触发 fallback

### Problems Solved

- 解决了“有 diagnosis 时规则模板过早抢占主回答”的问题
- 解决了“想要 LLM-first，但主链路里 fallback 顺序还不够明确”的问题
- 解决了“上线后不容易判断这次到底是不是 LLM-first 命中的”问题

### Compatibility Impact

本步骤仍然保持向后兼容：

- `/ai/ask` 接口格式不变，只新增调试字段
- 无 `session_id` 的旧问答路径不变
- `/ai/context/*` 接口不变
- diagnosis / next_step / tips 结构化字段继续保留

最关键的是：

- 当 `AI_TUTOR_LLM_FIRST_ENABLED=false` 时，旧行为仍然基本保留
- 当 `AI_TUTOR_LLM_FIRST_ENABLED=true` 时，才更明确地切换到新的 LLM-first 主回答顺序

### Verification

- Python AST parse should be rerun after this step for:
  - `services/ai_tutor_service.py`
  - `routes/ai_tutor.py`

### Notes For Server Sync

本步如果要同步到服务器，需要复制这些文件：

- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

## Step 6 - Phase 6 LLM 结果短 TTL 缓存

Status: Done

### Goal

在不改变主接口和不扩大模板回答范围的前提下，为“同一状态下的重复问题”增加短 TTL 的 LLM 结果缓存，减少重复打外部模型的次数，让重复提问更快返回。

### Modified Files

- `services/ai_context_store.py`
- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 在 `services/ai_context_store.py` 中新增 LLM answer cache 能力

新增：

- `DEFAULT_LLM_ANSWER_TTL`
- `get_llm_answer_cache()`
- `set_llm_answer_cache()`

同时新增了专用 key 生成逻辑：

- `_llm_answer_key(cache_key)`

这样缓存仍然复用当前已有的：

- Redis / Flask-Caching
- 内存 fallback

不会引入新的缓存基础设施。

#### 2. 在 `services/ai_tutor_service.py` 中新增 LLM cache key 生成逻辑

新增：

- `_build_llm_cache_key()`

key 由这些要素共同决定：

- `question`
- `page`
- `course`
- `step_code`
- `diagnosis`
- 精简后的 `snapshot`

实现上只取 snapshot 中简单、稳定的值：

- `str / int / float / bool`
- 以及嵌套 dict 中的简单值

然后做 JSON 序列化并计算 `sha1`，从而保证：

- 同一状态下 key 稳定
- 状态变化后 key 自然变化

#### 3. 在 `answer_with_context()` 中接入缓存读写

新增逻辑：

- 读取 `AI_TUTOR_LLM_CACHE_TTL`
- 当 `should_try_context_llm` 为真时：
  - 先生成 `llm_cache_key`
  - 如果 TTL 大于 0，先查缓存
  - 命中且存在有效 answer 时，直接复用缓存结果
  - 未命中时，继续调用真实 LLM
  - 真实 LLM 成功返回后，写入缓存

缓存只用于：

- 成功的 LLM answer

不会缓存：

- fallback 结果
- 空响应
- 错误响应

#### 4. 在 `/ai/ask` 中新增调试字段

新增透出：

- `llm_cache_hit`
- `llm_cache_key`

这样你部署后可以直接从返回里看出：

- 这次是否命中了缓存
- 当前使用的缓存 key 是什么

### Problems Solved

- 解决了“同一个学生在相同状态下重复问同一个问题，每次都重新打 LLM”的问题
- 解决了“想要保持 LLM-first，但重复请求还是太慢”的问题
- 解决了“缓存是否生效不容易观察”的问题

### Compatibility Impact

本步骤继续保持兼容：

- `/ai/ask` 的请求格式不变
- `/ai/ask` 原有核心返回字段不变
- fallback 逻辑不变
- diagnosis / next_step / tips 结构化字段不变

最关键的是：

- 当 `AI_TUTOR_LLM_CACHE_TTL=0` 时，缓存逻辑等同关闭，旧行为继续生效
- 只有当 TTL 大于 0 时，才开始命中和写入缓存

### Verification

建议在本步后重点验证：

- Python AST parse:
  - `services/ai_context_store.py`
  - `services/ai_tutor_service.py`
  - `routes/ai_tutor.py`
- 当 `AI_TUTOR_LLM_CACHE_TTL=0` 时：
  - 应与旧行为一致
- 当 `AI_TUTOR_LLM_CACHE_TTL>0` 时：
  - 第一次问题走真实 LLM
  - 第二次相同状态下的问题应出现 `llm_cache_hit=true`

### Notes For Server Sync

本步如果要同步到服务器，需要复制这些文件：

- `services/ai_context_store.py`
- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

## Step 4 - Phase 4 收紧 LLM timeout 与错误分类

Status: Done

### Goal

在不改变 `/ai/ask` 接口格式和不改动主 fallback 结构的前提下，把外部 LLM 调用从原来的宽松总超时改成更严格的分段 timeout，并把常见失败场景标准化成更容易观察的错误码。

### Modified Files

- `services/ai_tutor_service.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 在 `_post_openai_compatible_messages()` 中将单一 45 秒 timeout 改成分段 timeout

原来：

- `httpx.Client(timeout=45.0, trust_env=False)`

现在改为使用 `httpx.Timeout(...)`，并接入 `config.py` 中 Phase 1 已准备好的配置项：

- `AI_TUTOR_LLM_CONNECT_TIMEOUT`
- `AI_TUTOR_LLM_WRITE_TIMEOUT`
- `AI_TUTOR_LLM_READ_TIMEOUT`

同时固定：

- `pool=3.0`

这样能更明确地控制：

- 建连时间
- 发送请求体时间
- 等待模型返回时间

#### 2. 统一了 LLM 失败时的错误分类

现在 `_post_openai_compatible_messages()` 会按类型返回更稳定的错误码：

- `timeout`
- `unauthorized`
- `forbidden`
- `http_<status>`
- `connect_error`
- `bad_response`
- `empty_response`
- `unknown_error`

这样后续前端、日志和调试都不需要再依赖一整段不稳定的异常字符串。

#### 3. 失败时也保留了真实 `latency_ms`

以前失败时通常直接返回：

- `latency_ms = 0`

现在在 timeout、HTTP 错误、连接错误、坏响应等场景下，都会返回实际耗时，这样更方便判断：

- 是瞬时失败
- 还是接近超时后失败

### Problems Solved

- 解决了“LLM 请求可能被单次 45 秒 timeout 长时间阻塞”的问题
- 解决了“失败类型只能看原始异常字符串，不利于统计和诊断”的问题
- 解决了“失败请求 latency_ms 总是 0，不利于判断是否被长尾拖住”的问题

### Compatibility Impact

本步骤不改变：

- `/ai/ask` 的请求格式
- `/ai/ask` 的主响应字段结构
- `/ai/context/*` 接口
- 前端调用方式

变化仅体现在：

- LLM 调用更快超时
- `llm_error` 的内容从原始异常字符串，逐步转为更规范的错误码

这是向后兼容的行为增强，不会破坏旧功能。

### Verification

建议在本步后重点验证：

- Python AST parse:
  - `services/ai_tutor_service.py`
- `/ai/llm_probe` 在错误 key、403、断网、慢响应下是否返回预期错误码
- `/ai/ask` 在 LLM 失败时是否还能正常 fallback

### Notes For Server Sync

本步如果要同步到服务器，需要复制这些文件：

- `services/ai_tutor_service.py`
- `ai_tutor_llm_first_progress.md`

## Step 5 - Phase 5 延后非关键持久化

Status: Done

### Goal

在不移除 diagnosis/message 持久化能力的前提下，把这些“非关键、但会拖慢主请求尾部耗时”的写库动作改成可选的后台异步执行，让用户更早拿到答案。

### Modified Files

- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`

### Implemented

#### 1. 在 `services/ai_tutor_service.py` 中新增后台持久化调度函数

新增：

- `_schedule_async_persistence()`

作用：

- 接收一个 Flask app 对象
- 在后台 daemon 线程中重新进入 `app.app_context()`
- 异步执行：
  - `update_session_diagnosis()`
  - `_persist_tutor_message()`

这样可以避免把这些非关键写库动作继续放在主请求尾部同步等待。

#### 2. 在 `answer_with_context()` 中接入异步持久化开关

新增逻辑：

- 读取 `AI_TUTOR_ASYNC_PERSIST_ENABLED`
- 保留 diagnosis hot cache 的即时写入
- 当异步开关关闭时：
  - 继续沿用原来的同步持久化行为
- 当异步开关开启时：
  - diagnosis 的数据库持久化改为后台执行
  - tutor message 的数据库持久化改为后台执行

也就是说，本步不是直接删除同步写库，而是把它改成“可开关切换”的模式。

#### 3. 将持久化所需上下文收缩成最小字段

新增了 `persist_context`，只保留后台持久化真正需要的字段：

- `session_id`
- `group_id`

原理是：

- 避免把完整 `request_context`（其中可能包含 session record 等重对象）直接传进线程
- 减小后台持久化的数据耦合和潜在风险

#### 4. 在 `/ai/ask` 中新增调试字段

新增透出：

- `async_persist_enabled`

方便后续验证某次请求是否已经处于异步持久化模式。

### Problems Solved

- 解决了“答案已经算出来了，但还要同步等 diagnosis/message 写库”的问题
- 解决了“想优化主请求尾部耗时，但又不想直接删掉持久化能力”的问题
- 解决了“后台线程持久化时没有 app context”的问题

### Compatibility Impact

本步骤继续保持兼容：

- `/ai/ask` 的请求格式不变
- `/ai/ask` 原有核心返回字段不变
- diagnosis hot cache 仍然即时写入
- diagnosis / message 持久化能力仍然保留

最关键的是：

- 当 `AI_TUTOR_ASYNC_PERSIST_ENABLED=false` 时，旧的同步写库行为继续生效
- 当 `AI_TUTOR_ASYNC_PERSIST_ENABLED=true` 时，才切到后台 best-effort 持久化

### Verification

建议在本步后重点验证：

- Python AST parse:
  - `services/ai_tutor_service.py`
  - `routes/ai_tutor.py`
- 开关关闭时：
  - 行为应与旧版一致
- 开关开启时：
  - `/ai/ask` 更快返回
  - `async_persist_enabled=true`
  - diagnosis/message 仍能在后台落库

### Notes For Server Sync

本步如果要同步到服务器，需要复制这些文件：

- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_llm_first_progress.md`
