# AI 助教双模式改造实施基线文档

## 1. 文档目标与背景

### 1.1 文档定位

本文档是本次“AI 助教双模式改造”的唯一实施基线，后续所有代码改造、联调、验收、回滚，均以本文档为准。

文档目标不是讨论思路，而是提前锁定：

- 要改什么
- 为什么这样改
- 涉及哪些文件和函数
- 请求协议如何变化
- 每一步如何验收
- 出问题时如何回滚

后续执行方式按步骤推进，一次只做一步。执行口令约定为：

- “做第 1 步”
- “继续第 2 步”
- “执行第 5 步”

### 1.2 当前问题

当前浮窗 AI 助教默认走完整上下文链路，带来两个直接问题：

- 提问前会组装 `context`，默认引入 `session / recent events / snapshot / diagnosis / knowledge` 等上下文能力
- 课程页交互期间会持续触发 `/ai/context/event` 与 `/ai/context/snapshot` 上报，增加链路复杂度与响应开销

这导致“只是想快速问一个问题”的场景也被迫走完整链路，不利于默认响应速度、调试定位和后续运维。

### 1.3 改造目标

将 AI 助教改造成两种显式模式：

- `simple`
  - 默认模式
  - 面向轻问答
  - 默认优先走外部 LLM
  - 不携带上下文链路数据
  - 不触发事件与快照上报
- `context`
  - 显式开启
  - 保留现有完整上下文能力
  - 提问时继续附带完整 `context`
  - 继续触发事件与快照上报

### 1.4 设计原则

- 兼容旧接口：不能破坏现有仅传 `question` 或携带 `context.session_id` 的调用
- 前端显式切换：不再依赖“有没有 context”来暗示模式
- 后端显式分流：新增 `ask_mode` 作为主判定字段
- 逐步落地：前后端分步骤改造，每一步都可单独验收
- 可回滚：优先保证可以恢复到当前默认全链路行为

## 2. 当前系统现状

本节只描述当前真实实现，作为后续变更对照基线。

### 2.1 `/ai/ask` 当前真实分流方式

当前后端入口位于 `routes/ai_tutor.py` 的 `ask()`。

当前逻辑要点：

- 从请求体读取 `question`
- `context = data.get('context') or {}`
- `prefer_llm = bool(data['prefer_llm']) if 'prefer_llm' in data else bool(context.get('session_id'))`
- 若 `context.session_id` 存在，则进入 `answer_with_context()`
- 否则进入 `get_answer()`

当前问题：

- 分流主依据仍然是 `context.session_id`
- `prefer_llm` 默认值也受 `context.session_id` 隐式影响
- 前后端都没有统一的“模式”概念

### 2.2 当前上下文链路默认始终参与

前端浮窗当前实现位于 `templates/base.html`，相关逻辑包括：

- 页面初始化阶段会尝试调用 `AiCourseBridge.init(...)`
- 若 `AiCourseBridge` 不可用，则回退到 `AiContextTracker.init(...)`
- 提问前调用 `AiCourseBridge.attachAskContext(payload)`，或回退到 `AiContextTracker.wrapAskPayload(...)`
- 提问前还会触发 `AiCourseBridge.snapshot(...)`

这意味着当前浮窗默认会尽量附带上下文，不是“按需增强”，而是“默认增强”。

### 2.3 当前事件与快照默认持续上报

前端上下文跟踪相关文件：

- `static/js/ai_context_tracker.js`
- `static/js/ai_course_bridge.js`

当前关键函数：

- `AiContextTracker.buildAskContext()`
- `AiContextTracker.reportEvent()`
- `AiContextTracker.reportSnapshot()`
- `AiContextTracker.wrapAskPayload()`
- `AiCourseBridge.track()`
- `AiCourseBridge.snapshot()`
- `AiCourseBridge.attachAskContext()`

课程页当前会持续接入该链路，包括：

- `templates/emotion_computing.html`
- `templates/face_emotion.html`
- `templates/ecobottle.html`

以及对应独立脚本：

- `static/js/emotion_computing.js`
- `static/js/face_emotion.js`
- `static/js/ecobottle.js`

### 2.4 当前完整上下文链路包含的能力

根据现有代码与 `services/chain.md`，当前 `context` 链路包含以下核心能力：

- `session`
- `recent events`
- `snapshot`
- `diagnosis`
- `knowledge`
- `structured response`

### 2.5 当前后端职责边界

`services/ai_tutor_service.py` 中的主要职责如下：

- `get_answer(question, context=None, prefer_llm=False)`
  - 普通问答入口
  - 当前策略是“本地规则优先，必要时再调用 LLM”
- `answer_with_context(question, raw_context, group_id=None, prefer_llm=False)`
  - 完整上下文问答入口
  - 会继续构建 request context、规则诊断、知识补充、结构化返回
- `compose_structured_response(...)`
  - 负责上下文问答结果的结构化整合

## 3. 目标架构

### 3.1 轻问答模式 `simple`

`simple` 模式定义如下：

- 前端请求只发送最小问答载荷
- 显式传递 `prefer_llm: true`
- 显式传递 `ask_mode: "simple"`
- 不携带以下上下文链路数据：
  - `session_id`
  - `snapshot`
  - `recent events`
  - `diagnosis`
  - 其他上下文增强字段
- 不触发 `/ai/context/event`
- 不触发 `/ai/context/snapshot`
- 后端强制走普通问答链路，不进入 `answer_with_context()`

目标定位：

- 作为页面首次打开时的默认模式
- 面向“概念解释”“快速提问”“与当前课程步骤无强绑定”的问题

### 3.2 全链路模式 `context`

`context` 模式定义如下：

- 保留现有完整上下文能力
- 显式传递 `ask_mode: "context"`
- 继续附带 `context`
- 保留 `/ai/context/event` 与 `/ai/context/snapshot` 上报
- 后端继续走 `answer_with_context()`

目标定位：

- 面向“结合当前页面状态”“结合刚才操作记录”“希望获得诊断与下一步建议”的问题

### 3.3 模式状态策略

模式状态策略固定如下：

- 默认关闭全链路，等价于默认 `simple`
- 状态仅在当前页面生命周期内有效
- 不写入 `localStorage`
- 不写入 `sessionStorage`
- 刷新页面后恢复默认 `simple`

### 3.4 本次改造边界

本次改造只处理“模式显式化”和“默认链路降级”为轻问答，不做以下改动：

- 不修改 `/ai/context/event` 与 `/ai/context/snapshot` 协议结构
- 不新增数据库表
- 不重构现有 `answer_with_context()` 内部规则逻辑
- 不更换现有课程页业务交互逻辑

## 4. 对外接口与兼容策略

### 4.1 `POST /ai/ask` 新增字段

新增可选字段：

- `ask_mode: "simple" | "context"`

说明：

- 新字段为可选，不能导致旧调用直接失败
- 一旦前端新版本接入，必须显式传该字段

### 4.2 `simple` 请求标准格式

```json
{
  "question": "什么是多模态融合？",
  "prefer_llm": true,
  "ask_mode": "simple"
}
```

约束：

- 不发送 `context`
- 即使前端内部已有 tracker/session，也不能附带到请求体

### 4.3 `context` 请求标准格式

```json
{
  "question": "我下一步该怎么调参？",
  "prefer_llm": true,
  "ask_mode": "context",
  "context": {
    "session_id": "xxx",
    "page": "emotion_computing",
    "course": "emotion",
    "group_id": "G01",
    "step_code": "collect_data",
    "snapshot": {},
    "recent_events": []
  }
}
```

说明：

- `context` 的内部结构沿用现有机制，不在本次改造中重新设计协议
- `context` 模式下仍允许 `prefer_llm` 为前端现有值，但需显式随请求发送

### 4.4 `/ai/context/event` 与 `/ai/context/snapshot`

本次协议策略：

- 请求结构不变
- 响应结构不变
- 改造点只在前端是否调用

也就是说：

- `simple` 模式：前端不调用
- `context` 模式：前端照常调用

### 4.5 兼容旧调用策略

兼容要求是硬约束。

兼容场景 1：

- 旧请求只传 `question`
- 结果：继续可用

兼容场景 2：

- 旧请求传 `question + context.session_id`
- 结果：继续可用，并按当前旧逻辑走上下文链路

兼容场景 3：

- 旧请求未传 `ask_mode`，但传了 `prefer_llm`
- 结果：保留旧逻辑，不做强制破坏

### 4.6 后端分流优先级

后端分流优先级必须写死，避免继续依赖隐式推断。

目标优先级定义如下：

1. 若 `ask_mode == "simple"`，强制走普通问答链路
2. 若 `ask_mode == "context"` 且存在 `context.session_id`，走上下文链路
3. 若 `ask_mode == "context"` 但缺失 `context.session_id`，返回兼容性错误或降级策略，具体在第 5 步落地时确认
4. 若未传 `ask_mode`，保留现有兼容逻辑：
   - 有 `context.session_id` 走 `answer_with_context()`
   - 否则走 `get_answer()`

本实施基线的默认建议：

- `ask_mode == "context"` 但缺失 `context.session_id` 时，不直接 400
- 优先记录日志并降级到普通问答，避免误伤前端联调
- 但需要在响应中保留足够调试信息

## 5. 前端状态与数据流

### 5.1 浮窗模式开关职责

浮窗中的模式开关只负责两件事：

- 让用户显式知道当前是“轻问答”还是“全链路”
- 为浮窗提问、课程页埋点和快照上报提供统一状态源

不负责的事项：

- 不重置聊天历史
- 不清空页面业务状态
- 不持久化到刷新后

### 5.2 模式状态源

建议使用单点状态源，避免多个脚本各自维护。

建议形态：

- 全局变量，例如 `window.__aiAskMode`
- 或单点函数，例如 `window.getAiAskMode()`

文档基线要求：

- 浮窗提问读取同一状态源
- `AiContextTracker` / `AiCourseBridge` 的埋点开关读取同一状态源
- 课程页脚本不自行维护第二份模式状态

### 5.3 `simple` 模式下必须禁用的调用

`simple` 模式下必须满足：

- 浮窗提问请求体不附带 `context`
- 不调用 `AiCourseBridge.attachAskContext()`
- 不调用 `AiContextTracker.wrapAskPayload()` 来补充上下文
- 不调用 `AiCourseBridge.snapshot()`
- `AiContextTracker.reportEvent()` 直接跳过
- `AiContextTracker.reportSnapshot()` 直接跳过

### 5.4 `context` 模式下恢复的调用

`context` 模式下恢复现有行为：

- 提问前拼装 `context`
- 允许调用 `AiCourseBridge.attachAskContext()`
- 允许触发 `snapshot`
- 允许课程页继续上报 event/snapshot

### 5.5 课程页埋点如何服从总开关

课程页不需要知道浮窗 UI 细节，但必须服从统一模式判断。

约束如下：

- `AiContextTracker` 内部应具备“当前模式是否允许上报”的判断
- `AiCourseBridge.track()` / `snapshot()` 最好继续保持薄封装
- 各课程页模板和独立脚本无需各自散落写模式判断

## 6. 后端判定与服务职责

### 6.1 `routes/ai_tutor.py` 中 `/ai/ask` 的新规则

目标入口仍为 `ask()`，但分流策略调整为：

- 优先读取 `ask_mode`
- `ask_mode=simple`：
  - 强制走 `get_answer()`
  - 强制 `prefer_llm=True`
- `ask_mode=context`：
  - 要求优先进入 `answer_with_context()`
  - 前提是 `context.session_id` 可用
- 未传 `ask_mode`：
  - 保留兼容旧逻辑

### 6.2 `services/ai_tutor_service.py` 的职责边界

普通问答职责：

- 由 `get_answer()` 承担
- 负责“本地规则 + LLM + fallback”的普通问答策略
- 不负责上下文诊断链路组装

上下文问答职责：

- 由 `answer_with_context()` 承担
- 负责 request context、规则诊断、知识注入、结构化响应

### 6.3 `services/ai_context_service.py` 与前端 tracker 的要求

本次改造不要求修改 `services/ai_context_service.py` 协议，也不要求修改事件与快照接口结构。

但需要接受一个事实：

- 前端在 `simple` 模式下可能完全不调用这些接口

因此后端与服务层不能假设：

- 每次提问前一定已有 session
- 每个页面操作一定有 recent events
- 每个提问前一定有最新 snapshot

### 6.4 两种模式下结构化字段的差异预期

`simple` 模式预期：

- 允许只返回普通问答最小字段
- `diagnosis / next_step / tips / context_used` 可以为空
- `source / llm_attempted` 应尽量保留，便于排查

`context` 模式预期：

- 保持现有结构化字段能力
- 尽量继续返回：
  - `diagnosis`
  - `next_step`
  - `tips`
  - `context_used`
  - `llm_attempted`

## 7. 实施步骤

本节是后续逐步执行的唯一顺序基线。

---

### Step 1：补全文档与锁定协议

目标：

- 形成正式实施文档
- 固定模式名、字段名、默认行为、兼容策略、分流优先级

本步涉及文件：

- `double_plan.md`
- `double_process.md`

本步修改点：

- 补齐本主文档
- 初始化进度文档格式
- 固定模式命名为 `simple / context`
- 固定请求字段为 `ask_mode`
- 固定默认行为为页面首次打开时 `simple`
- 固定刷新后恢复默认 `simple`

接口影响：

- 无代码级接口变更
- 仅锁定后续将要实施的接口方案

验收标准：

- 后续实现不再需要产品层面二次决策
- 前后端改造字段名、模式名、默认行为已明确

回滚点：

- 无

---

### Step 2：前端浮窗模式开关设计

目标：

- 在浮窗中加入显式模式开关 UI

涉及文件：

- `templates/base.html`

拟修改点：

- 增加模式切换按钮或开关区域
- 增加统一模式状态源
- 默认状态为 `simple`
- 切换提示文案要明确说明：
  - `simple`：快速问答，不结合当前页面过程
  - `context`：结合当前页面过程与操作记录

接口影响：

- 暂无后端协议影响

验收标准：

- 不改后端的情况下，前端已存在明确模式状态源
- 刷新页面后恢复默认 `simple`

回滚点：

- 可仅移除 UI 与状态源，恢复原始浮窗结构

---

### Step 3：前端提问请求装配改造

目标：

- 让浮窗根据模式构造不同请求体

涉及文件：

- `templates/base.html`

拟修改点：

- 提取统一 payload 构建函数
- `simple` 请求体固定为：

```json
{
  "question": "xxx",
  "prefer_llm": true,
  "ask_mode": "simple"
}
```

- `context` 请求体固定为：

```json
{
  "question": "xxx",
  "prefer_llm": true,
  "ask_mode": "context",
  "context": {}
}
```

接口影响：

- 开始实际向 `/ai/ask` 发送 `ask_mode`

验收标准：

- 浏览器网络面板中两种模式的请求体结构稳定可观察

回滚点：

- 恢复为当前统一附带 `context` 的请求装配方式

---

### Step 4：前端埋点总开关改造

目标：

- 让事件与快照上报受模式控制

涉及文件：

- `static/js/ai_context_tracker.js`
- `static/js/ai_course_bridge.js`
- 必要时 `templates/base.html`

拟修改点：

- `AiContextTracker.reportEvent()` 在 `simple` 模式直接跳过
- `AiContextTracker.reportSnapshot()` 在 `simple` 模式直接跳过
- `AiCourseBridge.attachAskContext()` 继续存在，但 `simple` 模式下不再被浮窗调用
- 如有必要，在 tracker 内补充统一模式判断函数

接口影响：

- `/ai/context/event` 与 `/ai/context/snapshot` 的调用频率发生变化
- 协议本身不变

验收标准：

- 默认 `simple` 模式下课程页操作不再产生 event/snapshot 请求
- 切回 `context` 后上报恢复

回滚点：

- 去掉模式短路判断，恢复当前默认持续上报

---

### Step 5：后端 `/ai/ask` 显式分流改造

目标：

- 用 `ask_mode` 做主判定

涉及文件：

- `routes/ai_tutor.py`

拟修改点：

- 在 `ask()` 中读取 `ask_mode`
- 实现显式优先级分流
- 保留未传 `ask_mode` 时的兼容逻辑
- 增加必要日志，记录最终分流路径

接口影响：

- `/ai/ask` 正式支持 `ask_mode`

验收标准：

- `ask_mode=simple` 必定走普通问答
- `ask_mode=context` 且 `context.session_id` 存在时走上下文问答
- 旧调用不被破坏

回滚点：

- 退回为当前仅通过 `context.session_id` 判断

---

### Step 6：普通问答链路的 LLM 直连约束

目标：

- 让默认模式真正表现为“直接优先调用外部 LLM”

涉及文件：

- `services/ai_tutor_service.py`

拟修改点：

- 重新审视 `get_answer()` 在 `prefer_llm=True` 时的实际行为
- 确保 `simple` 模式下优先尝试外部 LLM
- 保留失败后的 fallback 机制
- 明确返回字段中的 `source`

默认建议：

- 允许 fallback
- 但必须明确告诉前端最终来源是 `llm_api`、`local` 还是 `fallback`

接口影响：

- 返回数据中的 `source / llm_attempted` 更重要

验收标准：

- `simple` 模式大多数正常场景优先来自外部 LLM
- 外部 LLM 失败时系统仍可回答

回滚点：

- 恢复为当前 `get_answer()` 既有策略

---

### Step 7：全链路模式兼容验证

目标：

- 确保 `context` 模式下现有能力不退化

涉及范围：

- `services/ai_tutor_service.py`
- `answer_with_context()`
- `compose_structured_response(...)`
- 上下文相关 service

重点验证：

- rules
- knowledge
- `context_used`
- `diagnosis`
- `next_step`
- `tips`

接口影响：

- 无新增协议
- 主要是行为一致性验证

验收标准：

- 切换到 `context` 模式后，行为与当前系统基本一致

回滚点：

- 必要时允许临时恢复“所有浮窗提问默认走全链路”

---

### Step 8：页面与课程场景回归

目标：

- 确保重点课程页不因模式开关失效

覆盖页面：

- `emotion_computing`
- `face_emotion`
- `ecobottle`

涉及文件：

- `templates/emotion_computing.html`
- `templates/face_emotion.html`
- `templates/ecobottle.html`
- 必要时对应 `static/js/*.js`

重点验证：

- 默认 `simple` 模式不再报上下文链路数据
- `context` 模式恢复事件与快照
- 页面原业务功能不受影响

验收标准：

- 三门课程页完成基础人机交互回归

回滚点：

- 对单页临时恢复原有 tracker/bridge 使用方式

---

### Step 9：观察项与调试信息

目标：

- 为后续排查保留最小调试能力

建议保留：

- 前端 console 输出当前 `ask_mode`
- 后端日志记录最终分流路径
- 返回字段尽量保留：
  - `source`
  - `llm_attempted`
  - `context_used`

涉及文件：

- `templates/base.html`
- `routes/ai_tutor.py`
- `services/ai_tutor_service.py`

验收标准：

- 出问题时能快速定位是模式判断、请求体构造还是后端分流异常

回滚点：

- 可移除非必要日志，但不应先于主功能回滚

## 8. 测试与验收总表

### 8.1 总体验收矩阵

必须覆盖以下场景：

1. 页面首次打开，浮窗默认为 `simple`
2. `simple` 模式下提问，请求体无 `context`
3. `simple` 模式下操作课程页，不产生 `/ai/context/event`
4. `simple` 模式下操作课程页，不产生 `/ai/context/snapshot`
5. 切换到 `context` 模式后提问，请求体恢复完整 `context`
6. `context` 模式下课程页操作恢复埋点
7. 刷新页面后模式回到默认 `simple`
8. 老的 `/ai/ask` 仅 `question` 请求仍能工作
9. 老的 `/ai/ask` 带 `context.session_id` 请求仍能工作
10. `context` 模式下结构化字段仍能正常返回
11. `simple` 模式下回答优先来自外部 LLM

### 8.2 分步验收原则

- 每一步都需要有独立验收结果
- 未完成当前步骤验收前，不进入下一步
- 只有当前步骤内容同步到服务器后，才继续下一步

### 8.3 回归验证原则

- 双模式改造不能破坏课程页面本身的教学业务流程
- 改造重点是 AI 助教链路，不是课程实验功能本身

## 9. 风险与回滚

### 9.1 前端 UI 风险

风险：

- 用户看不懂模式差异
- 切换按钮位置影响现有浮窗布局

缓解方式：

- 用明确文案区分“轻问答”和“全链路”
- 不引入复杂交互

### 9.2 模式判断错误导致链路错走

风险：

- 前端明明是 `simple`，后端仍进入 `answer_with_context()`
- 前端切到 `context`，却因为 `session_id` 缺失被降级

缓解方式：

- 后端记录最终分流路径
- 前端明确打印当前 `ask_mode`

### 9.3 旧页面兼容风险

风险：

- 某些旧页面未传 `ask_mode`
- 某些旧页面只会传 `question`

缓解方式：

- 保留未传 `ask_mode` 的旧逻辑

### 9.4 回滚原则

回滚优先级如下：

1. 优先保证旧接口继续可用
2. 优先保证可以恢复为当前默认全链路行为
3. UI 开关和日志属于次级功能，可先回滚
4. 不在未经确认的情况下回滚课程页原业务逻辑

## 10. 当前步骤结论

当前已锁定的关键结论如下：

- 模式名固定为 `simple / context`
- 请求字段固定为 `ask_mode`
- 页面默认模式固定为 `simple`
- 模式状态固定为“本页临时有效，刷新恢复默认”
- `/ai/ask` 后端后续改造以显式 `ask_mode` 分流为主
- 旧接口兼容是硬约束

以上内容自 Step 1 起生效，后续步骤不得随意改名或改协议；如确需调整，必须先修改本文档，再执行代码变更。
