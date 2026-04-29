# 根目录技术文档方案：AI 助教双模式改造实施文档

## Summary

在根目录新增或重写一份面向后续实施的主文档，建议文件名沿用当前打开的 `double_plan.md`，定位为这次“双模式 AI 助教改造”的唯一实施基线。文档目标不是只讲思路，而是把后续每一步要改什么、为什么改、涉及哪些接口、如何验收，全部提前写清楚，方便你后面逐步让我按步骤实现。

文档采用“先总览、再分阶段”的结构。前半部分固定描述背景、目标、现状、方案边界、接口变更和运行逻辑，后半部分拆成多个实施步骤，每一步都包含目标、修改点、涉及文件、接口影响、验收标准、回滚点。这样后面你只需要说“做第 1 步”或“继续第 3 步”，我就能按文档执行。

## Main Document Structure

建议文档包含以下固定章节：

1. 文档目标与背景
- 当前问题：浮窗默认全链路，上下文拼装和事件记录影响响应速度
- 改造目标：默认轻问答，按需切换到完整上下文链路
- 设计原则：兼容旧接口、前端显式切换、逐步落地、可回滚

2. 当前系统现状
- `/ai/ask` 当前两条链路的真实分流方式
- `AiContextTracker`、`AiCourseBridge` 当前默认始终参与上下文组装
- 浮窗 `base.html` 当前默认会附带 `context`
- `/ai/context/event` 与 `/ai/context/snapshot` 当前默认持续上报
- 现有上下文链路包含的核心能力：
  - session
  - recent events
  - snapshot
  - diagnosis
  - knowledge
  - structured response

3. 目标架构
- 轻问答模式 `simple`
  - 只发送 `question`
  - 显式 `prefer_llm: true`
  - 显式 `ask_mode: simple`
  - 不带 `session_id / snapshot / recent events / diagnosis`
  - 不触发 event/snapshot 上报
- 全链路模式 `context`
  - 维持现有完整上下文能力
  - 显式 `ask_mode: context`
  - 保留 event/snapshot 上报
  - 继续走 `answer_with_context()`
- 模式状态策略
  - 默认关闭
  - 本页临时有效
  - 刷新页面后恢复默认关闭

4. 对外接口与兼容策略
- `POST /ai/ask` 新增可选字段 `ask_mode`
- `simple` 请求标准格式
- `context` 请求标准格式
- `/ai/context/event` 与 `/ai/context/snapshot` 协议保持不变
- 兼容旧调用：
  - 旧的仅 `question` 调用继续可用
  - 旧的 `context.session_id` 调用继续可用
- 后端分流优先级需要写死，避免再依赖隐式推断

5. 前端状态与数据流
- 浮窗模式开关按钮的职责
- 模式状态源建议统一到全局变量或单点函数
- `simple` 模式下哪些调用必须禁用
- `context` 模式下哪些调用恢复
- 课程页埋点如何服从浮窗模式总开关

6. 后端判定与服务职责
- `routes/ai_tutor.py` 中 `/ai/ask` 的新分流规则
- `services/ai_tutor_service.py` 中普通问答与上下文问答的职责边界
- `services/ai_context_service.py`、`ai_context_tracker.js` 不需要改协议，但要接受“前端可能完全不调用”
- 结构化字段在两种模式下的差异预期

7. 实施步骤
- 这是主文档的核心，按步骤拆开，后续实现严格按这里推进

8. 测试与验收总表
- 每一步的独立验收
- 整体回归项
- 兼容性验证项

9. 风险与回滚
- 前端 UI 风险
- 模式判断错误导致回答链路错走的风险
- 旧页面兼容风险
- 回滚原则：优先支持恢复为当前默认全链路行为

## Step-by-Step Implementation Plan

### Step 1：补全文档与锁定协议
- 目标：把双模式方案写成正式技术文档，固定字段名、模式名、分流规则、兼容策略
- 涉及内容：
  - 模式命名：`simple` / `context`
  - `ask_mode` 字段定义
  - 默认模式行为
  - 刷新后的状态策略
- 验收：
  - 文档足够完整，后续实现不再需要产品层面二次决策

### Step 2：前端浮窗模式开关设计
- 目标：在浮窗中加入可视化按钮，让用户明确切换“轻问答 / 全链路”
- 涉及文件：
  - `templates/base.html`
- 需要写清：
  - 按钮位置
  - 默认状态
  - 开关时的提示文案
  - 切换后是否影响当前会话消息展示
- 验收：
  - 不改后端时，前端已具备明确模式状态源

### Step 3：前端提问请求装配改造
- 目标：让浮窗提问根据模式构造不同请求体
- 涉及文件：
  - `templates/base.html`
- `simple` 模式：
  - `{ question, prefer_llm: true, ask_mode: "simple" }`
- `context` 模式：
  - `{ question, prefer_llm, ask_mode: "context", context: {...} }`
- 验收：
  - 两种模式下请求体结构稳定且可观察

### Step 4：前端埋点总开关改造
- 目标：让 event/snapshot 上报也受模式控制
- 涉及文件：
  - `static/js/ai_context_tracker.js`
  - 必要时 `static/js/ai_course_bridge.js`
- 需要写清：
  - `reportEvent()` 在 `simple` 模式下直接跳过
  - `reportSnapshot()` 在 `simple` 模式下直接跳过
  - `buildAskContext()` 在 `simple` 模式下不再被浮窗使用
- 验收：
  - 默认模式下课程页操作不会继续打上下文链路

### Step 5：后端 `/ai/ask` 显式分流改造
- 目标：用 `ask_mode` 做主判定，而不是继续主要依赖 `context.session_id`
- 涉及文件：
  - `routes/ai_tutor.py`
- 规则写清：
  - `ask_mode=simple` 时强制走普通问答链路并优先 LLM
  - `ask_mode=context` 且存在 `context.session_id` 时走 `answer_with_context()`
  - 缺少 `ask_mode` 时保留兼容旧逻辑
- 验收：
  - 分流可控、兼容不破坏现有调用方

### Step 6：普通问答链路的 LLM 直连约束
- 目标：确保默认模式真正符合“直接调用 API”
- 涉及文件：
  - `services/ai_tutor_service.py`
- 需要写清：
  - 轻问答模式下优先调用外部 LLM
  - 失败时是否允许本地 fallback
  - 返回字段最小保障是什么
- 默认建议：
  - 允许 fallback，但把 `source` 明确返回，便于排查
- 验收：
  - 默认模式下回答主要来自外部 LLM，而不是隐式本地规则

### Step 7：全链路模式兼容验证
- 目标：确保切回 `context` 模式后，现有能力不退化
- 涉及范围：
  - `answer_with_context()`
  - rules
  - knowledge
  - `context_used`
  - `diagnosis`
  - `next_step`
  - `tips`
- 验收：
  - 切换到全链路后，行为与当前系统基本一致

### Step 8：页面与课程场景回归
- 目标：验证三门重点课程页不因模式开关失效
- 覆盖页面：
  - `emotion_computing`
  - `face_emotion`
  - `ecobottle`
- 需要写清：
  - 默认模式下不再报链路数据
  - 全链路模式下恢复事件与快照
  - 页面原业务功能不受影响
- 验收：
  - 三门课程页通过最基本的人机交互回归

### Step 9：观察项与调试信息
- 目标：为后续排查提供最小调试能力
- 建议保留：
  - 前端 console 输出当前 `ask_mode`
  - 后端日志记录最终分流路径
  - 可选返回 `source / llm_attempted / context_used`
- 验收：
  - 出问题时能快速判断是模式、请求体还是后端分流的问题

## Test Plan

文档里应单独列出总体验收矩阵，至少包含这些场景：

- 页面首次打开，浮窗默认为轻问答模式
- 轻问答模式下提问，请求体无 `context`
- 轻问答模式下操作课程页，不产生 `/ai/context/event` 与 `/ai/context/snapshot`
- 切换到全链路模式后提问，请求体恢复完整 `context`
- 全链路模式下课程页操作恢复埋点
- 刷新页面后模式回到默认关闭
- 老的 `/ai/ask` 仅 `question` 请求仍能工作
- 老的 `/ai/ask` 带 `context.session_id` 请求仍能工作
- `context` 模式下结构化字段仍能正常返回
- `simple` 模式下回答优先来自外部 LLM

## Assumptions

- 根目录主文档文件名默认使用 `double_plan.md`
- 文档采用中文书写，偏实施说明风格，不写成纯产品 PRD
- 后续实现严格按步骤推进，一次只做一个步骤
- 第一步只生成和完善文档，不直接改业务逻辑
- 旧接口兼容是硬约束，不能因为双模式改造破坏现有调用
