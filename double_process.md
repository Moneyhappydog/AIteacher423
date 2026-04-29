# AI 助教双模式改造进度文档

## 文档用途

本文档用于记录每一步实际改动了什么，方便后续按文件同步到服务器。记录原则如下：

- 一次只记录一个步骤
- 每执行完一步立即更新本文档
- 写清楚修改的文件、函数、行为变化、验收结果、待同步项
- 如果某一步没有改代码，也要明确写“仅改文档”

主方案基线见 [double_plan.md](/d:/codeC/VsCodeP/eduplatform/double_plan.md)。

## 总体进度

| 步骤 | 名称 | 状态 | 说明 |
| --- | --- | --- | --- |
| Step 1 | 补全文档与锁定协议 | 已完成 | 已建立实施基线与进度记录格式 |
| Step 2 | 前端浮窗模式开关设计 | 已完成 | 已在浮窗中加入模式切换 UI 与统一状态源 |
| Step 3 | 前端提问请求装配改造 | 已完成 | 已按模式构造不同 `/ai/ask` 请求体 |
| Step 4 | 前端埋点总开关改造 | 已完成 | 已让 event/snapshot 上报受 ask_mode 总开关控制 |
| Step 5 | 后端 `/ai/ask` 显式分流改造 | 已完成 | 已改为 `ask_mode` 优先分流并保留旧接口兼容 |
| Step 6 | 普通问答链路的 LLM 直连约束 | 已完成 | 已补齐普通问答链路的 LLM 尝试与回退可观测性 |
| Step 7 | 全链路模式兼容验证 | 已完成 | 已确认 context 模式关键结构化能力未退化，无需额外代码修正 |
| Step 8 | 页面与课程场景回归 | 已完成 | 已确认三门重点课程页埋点入口统一受总开关控制，无需额外代码修正 |
| Step 9 | 观察项与调试信息 | 已完成 | 已确认前后端最小调试能力到位，无需新增代码字段 |

## 记录模板

后续每一步按以下结构追加：

### Step X：步骤名称

- 执行时间：
- 执行目标：
- 实际修改文件：
- 实际修改函数：
- 实际修改内容：
- 接口影响：
- 验收结果：
- 回滚说明：
- 服务器同步提示：

## 执行记录

### Step 1：补全文档与锁定协议

- 执行时间：2026-04-29
- 执行目标：把双模式改造方案固化为正式实施文档，并建立后续逐步同步所需的进度文档
- 实际修改文件：
  - `double_plan.md`
  - `double_process.md`
- 实际修改函数：
  - 无
- 实际修改内容：
  - 重写 `double_plan.md`，将其升级为本次“双模式 AI 助教改造”的唯一实施基线
  - 在文档中锁定了模式命名：`simple` / `context`
  - 在文档中锁定了新增请求字段：`ask_mode`
  - 在文档中锁定了默认行为：页面首次打开默认为 `simple`
  - 在文档中锁定了状态策略：仅本页临时有效，刷新后恢复默认 `simple`
  - 在文档中锁定了后续九个实施步骤、验收标准与回滚原则
  - 新建本进度文档的固定记录格式，供后续每一步持续追加
- 接口影响：
  - 本步没有修改任何业务代码
  - 本步没有改变任何真实接口行为
  - 本步只锁定了后续将实施的协议和分流规则
- 验收结果：
  - 已形成完整实施文档
  - 后续执行时可以直接按步骤推进，不需要再次讨论字段命名和总方案边界
- 回滚说明：
  - 本步仅文档变更，无业务回滚动作
- 服务器同步提示：
  - 本步只需要同步两个根目录文档文件：
    - `double_plan.md`
    - `double_process.md`

### Step 2：前端浮窗模式开关设计

- 执行时间：2026-04-29
- 执行目标：在浮窗中加入可视化模式切换，并建立前端统一模式状态源，不改后端逻辑
- 实际修改文件：
  - `templates/base.html`
- 实际修改函数：
  - `getMaoAskMode()`
  - `getMaoModeText(mode)`
  - `applyMaoAskMode(mode)`
  - `setMaoAskMode(mode)`
  - `DOMContentLoaded` 初始化逻辑
- 实际修改内容：
  - 在 AI 浮窗头部与消息列表之间新增模式切换区域
  - 增加两个可视化按钮：`轻问答`、`全链路`
  - 增加当前模式说明文案，明确两种模式的用途差异
  - 增加前端统一状态源 `window.__aiAskMode`
  - 增加全局读取入口 `window.getAiAskMode`
  - 页面首次加载时默认初始化为 `simple`
  - 当前状态不写入本地存储，因此刷新页面后会自动恢复 `simple`
  - 当前会话消息列表不因切换模式而被清空，符合 Step 2 设计基线
- 接口影响：
  - 本步未修改 `/ai/ask` 请求体
  - 本步未修改 `/ai/context/event` 与 `/ai/context/snapshot`
  - 本步只建立模式 UI 和状态源，为后续 Step 3 / Step 4 提供基础
- 验收结果：
  - 前端已具备明确模式状态源
  - 浮窗中已可显式切换“轻问答 / 全链路”
  - 刷新页面后默认回到 `simple`
- 回滚说明：
  - 如需回滚，只需回退 `templates/base.html` 中新增的模式切换 UI、样式和状态函数
- 服务器同步提示：
  - 本步只需要同步：
    - `templates/base.html`

### Step 3：前端提问请求装配改造

- 执行时间：2026-04-29
- 执行目标：让浮窗提问根据当前模式构造不同的 `/ai/ask` 请求体，不改后端分流逻辑
- 实际修改文件：
  - `templates/base.html`
- 实际修改函数：
  - `buildSimpleMaoAskPayload(question)`
  - `buildContextMaoAskPayload(question)`
  - `getMaoAskPayload(question)`
  - `askMaoApi(question)`
- 实际修改内容：
  - 将原先单一路径的 `getMaoAskPayload()` 拆分为 `simple` 和 `context` 两种请求装配函数
  - `simple` 模式下固定发送最小请求体：
    - `question`
    - `prefer_llm: true`
    - `ask_mode: "simple"`
  - `simple` 模式下不再调用 `AiCourseBridge.attachAskContext()`，也不再调用 `AiContextTracker.wrapAskPayload()` 来附加上下文
  - `context` 模式下继续沿用现有上下文组装逻辑，并显式补充：
    - `prefer_llm: true`
    - `ask_mode: "context"`
  - 当 bridge/tracker 不可用时，`context` 模式下仍会回退生成包含基础 `context` 的请求体
  - 在 `askMaoApi(question)` 中增加前端 console 调试输出，打印本次发送的：
    - `ask_mode`
    - `prefer_llm`
    - 是否携带 `context`
    - `context` 键列表
- 接口影响：
  - `/ai/ask` 前端请求体开始显式区分两种模式
  - `simple` 模式请求体不再包含 `context`
  - `context` 模式请求体显式包含 `ask_mode: "context"`
  - 本步仍未改后端，所以当前只是前端请求协议先到位
- 验收结果：
  - `simple` 模式下请求体可稳定观察到为最小 payload
  - `context` 模式下请求体可稳定观察到恢复完整 `context`
  - 两种模式切换后，浏览器 console 可辅助确认实际发送内容
- 回滚说明：
  - 如需回滚，可将 `getMaoAskPayload()` 恢复为原先统一附加上下文的实现，并移除新增调试日志
- 服务器同步提示：
  - 本步只需要同步：
    - `templates/base.html`

### Step 4：前端埋点总开关改造

- 执行时间：2026-04-29
- 执行目标：让 `/ai/context/event` 与 `/ai/context/snapshot` 上报受当前 `ask_mode` 总开关控制
- 实际修改文件：
  - `static/js/ai_context_tracker.js`
- 实际修改函数：
  - `getGlobalAskMode()`
  - `Tracker.prototype.getAskMode()`
  - `Tracker.prototype.isContextModeEnabled()`
  - `Tracker.prototype.reportEvent()`
  - `Tracker.prototype.reportSnapshot()`
- 实际修改内容：
  - 在 `AiContextTracker` 内新增统一模式读取逻辑，优先读取 `window.getAiAskMode()`，否则回退到 `window.__aiAskMode`
  - 新增 `getAskMode()` 与 `isContextModeEnabled()`，把“是否允许上下文链路上报”的判断集中到 tracker 内部
  - 在 `reportEvent()` 中加入短路判断：
    - 当前模式不是 `context` 时直接返回 `skipped`
    - 不再向 `/ai/context/event` 发请求
  - 在 `reportSnapshot()` 中加入短路判断：
    - 当前模式不是 `context` 时直接返回 `skipped`
    - 不再向 `/ai/context/snapshot` 发请求
  - 这样课程页原有的 `AiCourseBridge.track()` / `snapshot()` 调用无需逐页改造，也会统一服从浮窗模式总开关
- 接口影响：
  - `/ai/context/event` 协议未变，但 `simple` 模式下前端不再实际调用
  - `/ai/context/snapshot` 协议未变，但 `simple` 模式下前端不再实际调用
  - `context` 模式下现有上报协议与调用路径保持不变
- 验收结果：
  - 默认 `simple` 模式下课程页操作不会继续产生 event/snapshot 上报请求
  - 切换回 `context` 模式后，上报调用可恢复
  - 课程页现有 `track()` / `snapshot()` 入口无需重写即可服从总开关
- 回滚说明：
  - 如需回滚，只需移除 `ai_context_tracker.js` 中新增的模式判定与短路逻辑
- 服务器同步提示：
  - 本步只需要同步：
    - `static/js/ai_context_tracker.js`

### Step 5：后端 `/ai/ask` 显式分流改造

- 执行时间：2026-04-29
- 执行目标：让 `/ai/ask` 以 `ask_mode` 作为主分流依据，同时保留旧调用兼容
- 实际修改文件：
  - `routes/ai_tutor.py`
- 实际修改函数：
  - `ask()`
- 实际修改内容：
  - 在 `routes/ai_tutor.py` 中新增 `logging` 与模块级 `logger`
  - 在 `ask()` 中新增对 `ask_mode` 的读取与标准化处理
  - 新增 `has_session_context`，明确区分“是否存在 `context.session_id`”
  - 显式分流规则已落地：
    - `ask_mode == "simple"`：
      - 强制走 `get_answer()`
      - 强制 `prefer_llm = True`
    - `ask_mode == "context"` 且存在 `context.session_id`：
      - 走 `answer_with_context()`
    - `ask_mode == "context"` 但缺失 `context.session_id`：
      - 降级到 `get_answer()`
      - 不直接报错，便于兼容前端联调
    - 未传 `ask_mode`：
      - 保留旧逻辑
      - 有 `context.session_id` 走上下文问答
      - 否则走普通问答
  - 增加后端分流日志，记录：
    - 最终命中的分流路径 `route_name`
    - 原始 `ask_mode`
    - 生效模式 `effective_ask_mode`
    - 是否存在 `session_id`
    - 最终 `prefer_llm`
    - 当前用户
- 接口影响：
  - `/ai/ask` 现在正式支持以前端显式传入的 `ask_mode` 作为主分流依据
  - 旧请求体不需要修改，仍能继续工作
  - `ask_mode == "context"` 但缺少 `session_id` 时当前采用降级兼容策略，不直接 400
- 验收结果：
  - `simple` 模式请求可以稳定强制走普通问答链路
  - `context` 模式且带 `session_id` 时可以稳定走上下文问答链路
  - 未传 `ask_mode` 的旧调用仍保持原有行为
  - 后端日志已具备最小分流排查能力
- 回滚说明：
  - 如需回滚，可将 `ask()` 中的显式 `ask_mode` 分流逻辑恢复为原先仅依赖 `context.session_id` 判断的实现
- 服务器同步提示：
  - 本步只需要同步：
    - `routes/ai_tutor.py`

### Step 6：普通问答链路的 LLM 直连约束

- 执行时间：2026-04-29
- 执行目标：确保默认轻问答模式下“优先直连 LLM”这件事既成立，又能从返回字段中明确观测
- 实际修改文件：
  - `services/ai_tutor_service.py`
- 实际修改函数：
  - `get_answer(question, context=None, prefer_llm=False)`
- 实际修改内容：
  - 复核后确认：`get_answer()` 原有逻辑在 `prefer_llm=True` 时已经会优先跳过“本地直接返回”，先尝试 `call_llm_api()`
  - 本步没有重写普通问答主策略，而是补齐其返回可观测性
  - 在 `get_answer()` 中新增局部 `mode` 缓存，避免重复计算 `detect_mode(question)`
  - 为普通问答各个返回分支补齐统一字段：
    - `llm_attempted`
    - `llm_error`
  - 具体效果如下：
    - 本地直接命中且 `prefer_llm=False`：
      - `llm_attempted=False`
      - `llm_error=None`
    - LLM 成功返回：
      - `llm_attempted=True`
      - `source=llm_api`
    - LLM 失败后回退本地答案：
      - `llm_attempted=True`
      - `source=local`
      - `llm_error` 保留失败原因
    - LLM 失败且本地也没有命中时：
      - `llm_attempted=True`
      - `source=fallback`
      - `llm_error` 保留失败原因
- 接口影响：
  - 普通问答返回结构现在能更准确表达“是否已经尝试过外部 LLM”
  - 前端在 `simple` 模式下更容易区分：
    - 真正命中 LLM
    - LLM 失败后回退到本地
    - 完全 fallback
  - 本步没有改变 `get_answer()` 的主调用顺序，只增强了返回字段
- 验收结果：
  - `simple` 模式下只要由 Step 5 强制传入 `prefer_llm=True`，普通问答就会优先尝试外部 LLM
  - 即使最终不是 `llm_api`，也能通过 `source + llm_attempted + llm_error` 看清是否发生了回退
- 回滚说明：
  - 如需回滚，只需移除 `get_answer()` 中新增的 `llm_attempted / llm_error / mode` 补充逻辑
- 服务器同步提示：
  - 本步只需要同步：
    - `services/ai_tutor_service.py`

### Step 7：全链路模式兼容验证

- 执行时间：2026-04-29
- 执行目标：确认切回 `context` 模式后，现有上下文增强能力与结构化返回没有因前面步骤退化
- 实际修改文件：
  - `double_process.md`
- 实际修改函数：
  - 无代码修改
- 实际修改内容：
  - 对 `routes/ai_tutor.py` 的 `/ai/ask` 分流进行了链路核对
  - 对 `services/ai_tutor_service.py` 的 `answer_with_context()`、`compose_structured_response()` 进行了结构化能力核对
  - 重点确认了以下能力仍然保留在 `context` 模式链路中：
    - `answer_with_context()` 仍是完整上下文问答入口
    - `rule_result` 仍参与诊断判断
    - `knowledge_context` 仍参与知识补充
    - `compose_structured_response()` 仍返回：
      - `diagnosis`
      - `next_step`
      - `tips`
      - `context_used`
      - `llm_attempted`
      - `llm_error`
    - `/ai/ask` 路由层仍会把上述字段透传给前端响应
  - 同时确认 Step 5 的新分流逻辑不会影响以下场景：
    - `ask_mode="context"` 且存在 `context.session_id` 时，仍然命中 `answer_with_context()`
    - 未传 `ask_mode` 但带 `context.session_id` 的旧调用，仍然命中兼容上下文链路
  - 本次验证未发现需要为 Step 7 额外修改业务代码的问题，因此本步不产生新的代码变更
- 接口影响：
  - 无新增接口变更
  - 无响应字段删减
  - 本步是兼容性验证，不改变现有代码行为
- 验收结果：
  - `context` 模式核心能力未退化
  - 结构化字段返回链路保持完整
  - 旧的上下文请求兼容逻辑仍在
  - 当前未发现必须在 Step 7 修补的代码问题
- 回滚说明：
  - 本步没有业务代码修改，无需回滚
- 服务器同步提示：
  - 本步只需要同步：
    - `double_process.md`

### Step 8：页面与课程场景回归

- 执行时间：2026-04-29
- 执行目标：核对三门重点课程页在 `simple / context` 双模式下的埋点入口是否统一受控，并确认页面业务交互未被本次改造破坏
- 实际修改文件：
  - `double_process.md`
- 实际修改函数：
  - 无代码修改
- 实际修改内容：
  - 对以下重点课程页及其对应脚本进行了回归核对：
    - `templates/emotion_computing.html`
    - `templates/face_emotion.html`
    - `templates/ecobottle.html`
    - `static/js/emotion_computing.js`
    - `static/js/face_emotion.js`
    - `static/js/ecobottle.js`
  - 核对结果如下：
    - 三门课程页的事件上报入口都统一走 `window.AiCourseBridge.track(...)`
    - 三门课程页的快照上报入口都统一走：
      - `window.AiContextTracker.scheduleSnapshot(...)`
      - 或回退到 `window.AiCourseBridge.snapshot(...)`
    - 三门课程页都会先通过 `window.AiContextTracker.setStep(...)` 更新当前步骤，再进入统一上报入口
  - 因此 Step 4 在 `ai_context_tracker.js` 中加入的模式总开关，会自动覆盖这三门课程页：
    - `simple` 模式下，`reportEvent()` / `reportSnapshot()` 会直接 `skipped`
    - `context` 模式下，现有埋点与快照链路正常恢复
  - 本次核对未发现需要对三门课程页分别追加模式判断或改造埋点函数的地方
  - 同时从代码层面确认：
    - 页面原有业务函数仍然在本地完成摄像头、录音、预测、图表、控制等交互
    - AI 助教双模式改造只影响“是否上报上下文链路”，不影响页面原有实验业务逻辑
- 接口影响：
  - 无新增接口变更
  - 无课程页业务接口改动
  - 本步是页面级回归核对，不改变现有代码行为
- 验收结果：
  - 三门重点课程页的埋点入口已经统一受模式总开关控制
  - `simple` 模式下默认不会继续打上下文事件/快照链路
  - `context` 模式下现有埋点恢复路径保持不变
  - 当前未发现必须为 Step 8 单独修补的页面代码问题
- 回滚说明：
  - 本步没有业务代码修改，无需回滚
- 服务器同步提示：
  - 本步只需要同步：
    - `double_process.md`

### Step 9：观察项与调试信息

- 执行时间：2026-04-29
- 执行目标：确认双模式改造后已经具备最小但足够的调试能力，便于后续定位“模式问题 / 请求体问题 / 后端分流问题”
- 实际修改文件：
  - `double_process.md`
- 实际修改函数：
  - 无代码修改
- 实际修改内容：
  - 核对前端调试信息：
    - `templates/base.html` 已在切换模式时输出当前 `ask_mode`
    - `templates/base.html` 已在发起提问前输出请求摘要：
      - `ask_mode`
      - `prefer_llm`
      - 是否携带 `context`
      - `context` 键列表
    - `templates/base.html` 已在收到回答后输出：
      - `source`
      - `model`
      - `llm_attempted`
      - `llm_error`
      - `diagnosis`
  - 核对后端调试信息：
    - `routes/ai_tutor.py` 已记录 `/ai/ask` 最终分流日志，包括：
      - `route_name`
      - 原始 `ask_mode`
      - `effective_ask_mode`
      - `has_session_context`
      - `prefer_llm`
      - `user`
    - `services/ai_tutor_service.py` 已在上下文问答链路记录：
      - `source`
      - `llm_attempted`
      - `llm_error`
      - `diagnosis`
      - `session_id`
  - 核对返回字段：
    - `/ai/ask` 路由层当前已稳定返回：
      - `source`
      - `llm_attempted`
      - `llm_error`
      - `context_used`
      - `diagnosis`
      - `next_step`
      - `tips`
    - 普通问答链路 `get_answer()` 也已补齐 `llm_attempted / llm_error`
  - 结论：
    - 现有信息已经足够排查大部分问题
    - 本步不再额外增加调试字段，避免把临时排查信息扩散成长期接口负担
- 接口影响：
  - 无新增接口变更
  - 无新增返回字段
  - 本步是调试能力核对，不改变现有代码行为
- 验收结果：
  - 可以从前端快速判断本次请求是不是 `simple` 还是 `context`
  - 可以从请求摘要快速判断是否带了 `context`
  - 可以从后端日志快速判断最终分流路径
  - 可以从返回字段判断 LLM 是否尝试、是否失败、是否使用了上下文
- 回滚说明：
  - 本步没有业务代码修改，无需回滚
- 服务器同步提示：
  - 本步只需要同步：
    - `double_process.md`

## 下一步待执行

当前 9 个步骤已全部完成。

当前建议你同步的文件清单如下：

- `double_plan.md`
- `double_process.md`
- `templates/base.html`
- `static/js/ai_context_tracker.js`
- `routes/ai_tutor.py`
- `services/ai_tutor_service.py`

其中按步骤对应为：

- Step 1：
  - `double_plan.md`
  - `double_process.md`
- Step 2：
  - `templates/base.html`
- Step 3：
  - `templates/base.html`
- Step 4：
  - `static/js/ai_context_tracker.js`
- Step 5：
  - `routes/ai_tutor.py`
- Step 6：
  - `services/ai_tutor_service.py`
- Step 7：
  - `double_process.md`
- Step 8：
  - `double_process.md`
- Step 9：
  - `double_process.md`
