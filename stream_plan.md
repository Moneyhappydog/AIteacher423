# AI 助教流式输出改造计划

## Summary

在现有双模式基础上，为“浮窗 AI 助教”新增流式输出能力，但本次范围只覆盖浮窗，不改独立 [ai_tutor.html](/d:/codeC/VsCodeP/eduplatform/templates/ai_tutor.html:1)。接口方案采用“新增流式接口”，保留现有 `/ai/ask` 完全不动，前端通过 `fetch + ReadableStream` 接收分块数据。首期只让 `simple` 模式走真流式；`context` 模式、本地规则命中和 fallback 仍保持原有一次性返回。

同时，把这次流式改造拆成单独步骤写入 `double_process.md`，延续你现在的同步方式：每做一步，只改少量文件，并在进度文档里明确记录“改了哪个文件、哪个函数、怎么验证”。

## Key Changes

### 1. 新增流式后端能力

- 在 [routes/ai_tutor.py](/d:/codeC/VsCodeP/eduplatform/routes/ai_tutor.py:1) 新增专用流式路由，建议命名为：
  - `POST /ai/ask_stream`
- 该路由只服务浮窗流式问答，不替换现有 `/ai/ask`
- 路由输入沿用当前问答字段最小子集：
  - `question`
  - `ask_mode`
  - `prefer_llm`
  - `context`
- 但首期只支持：
  - `ask_mode == 'simple'`
- 若请求不是 `simple`，或未命中 LLM 直连能力，则直接返回“非流式降级事件”或普通错误事件，不走 context 流式

### 2. 后端流式协议

采用 `fetch + ReadableStream` 友好的流式文本协议，推荐 `application/x-ndjson` 或逐行 JSON。每一行一条 JSON 事件，最小事件集合：

- `start`
  - 包含 `ask_mode`、`source='llm_api'`、`model`
- `delta`
  - 包含本次新增文本片段 `text`
- `done`
  - 包含最终汇总信息：
    - `answer`
    - `source`
    - `model`
    - `tokens_used`
    - `latency_ms`
    - `llm_attempted`
    - `llm_error`
    - `ask_mode`
- `error`
  - 包含错误信息
- `fallback`
  - 表示本次没有进入真流式，前端应改走原 `/ai/ask`

这样前端可以边读边渲染，后端也能在完成时提供和原接口一致的收尾元信息。

### 3. 服务层最小扩展

在 [services/ai_tutor_service.py](/d:/codeC/VsCodeP/eduplatform/services/ai_tutor_service.py:1) 新增“流式 LLM 调用”能力，而不是改写现有 `call_llm_api()`：

- 保留：
  - `call_llm_api()`
  - `call_llm_messages()`
  - `get_answer()`
  - `answer_with_context()`
- 新增建议函数：
  - `_stream_openai_compatible_messages(...)`
  - `stream_simple_answer(question, context=None)`
- `stream_simple_answer(...)` 职责：
  - 只处理 `simple` 模式
  - 校验 LLM 配置
  - 直连上游兼容 OpenAI 的 stream 接口
  - 把上游 chunk 转换成内部 `start/delta/done/error` 事件
  - 如果不适合流式，明确产出 `fallback` 结果而不是硬失败

### 4. 浮窗前端流式接入

在 [templates/base.html](/d:/codeC/VsCodeP/eduplatform/templates/base.html:1) 中新增浮窗专用流式发送逻辑：

- 保留原：
  - `getMaoAskPayload(question)`
  - `formatMaoReply(data)`
  - `askMaoApi(question)`
- 新增建议函数：
  - `askMaoApiStream(question)`
  - `readNdjsonStream(response, handlers)`
  - `addMaoStreamingMsg()`
  - `updateMaoStreamingMsg(id, text)`
  - `finalizeMaoStreamingMsg(id, meta)`
- 行为：
  - 当 `getMaoTutorMode() === 'simple'` 时，优先调用流式接口
  - 当 `getMaoTutorMode() === 'context'` 时，继续调用现有 `/ai/ask`
  - 若流式接口返回 `fallback` 或失败，则自动退回 `askMaoApi(question)`

### 5. 文档与进度记录

把流式改造作为“第二阶段计划”写入现有文档体系：

- 在 [double_tech.md](/d:/codeC/VsCodeP/eduplatform/double_tech.md:1) 新增“流式输出改造”章节
- 在 [double_process.md](/d:/codeC/VsCodeP/eduplatform/double_process.md:1) 新增专门的流式步骤表
- 建议使用新的步骤编号，避免和 1-9 混淆，例如：
  - Stream Step 1
  - Stream Step 2
  - Stream Step 3
  - Stream Step 4
  - Stream Step 5

## Public Interface Changes

### 新增接口

- `POST /ai/ask_stream`

### 请求体

首期沿用现有问答字段，建议格式：

```json
{
  "question": "什么是人工智能？",
  "prefer_llm": true,
  "ask_mode": "simple"
}
```

### 流式响应事件

逐行 JSON，建议最小格式：

```json
{"type":"start","ask_mode":"simple","source":"llm_api","model":"qwen3.5-flash"}
{"type":"delta","text":"人工智能"}
{"type":"delta","text":"就是让计算机..."}
{"type":"done","answer":"人工智能就是让计算机...","source":"llm_api","model":"qwen3.5-flash","tokens_used":123,"latency_ms":1800,"llm_attempted":true,"llm_error":null,"ask_mode":"simple"}
```

降级场景：

```json
{"type":"fallback","reason":"non_streamable_path"}
```

错误场景：

```json
{"type":"error","error":"LLM stream failed"}
```

## Step Plan For `double_process.md`

### Stream Step 1：补文档与锁定协议

- 更新 `double_tech.md`
- 更新 `double_process.md`
- 固定：
  - 只改浮窗
  - 新增 `/ai/ask_stream`
  - 使用 `fetch + ReadableStream`
  - 只给 `simple` 模式做真流式
  - `context` 模式暂不流式

### Stream Step 2：新增后端流式服务能力

- 修改 `services/ai_tutor_service.py`
- 新增流式上游调用函数
- 新增 `stream_simple_answer(...)`
- 保留现有非流式逻辑不变

### Stream Step 3：新增流式路由

- 修改 `routes/ai_tutor.py`
- 新增 `POST /ai/ask_stream`
- 做输入校验、模式校验、事件输出和日志记录

### Stream Step 4：浮窗前端接入流式渲染

- 修改 `templates/base.html`
- `simple` 模式下改走 `/ai/ask_stream`
- 边接收边更新当前 AI 气泡
- 失败或降级时退回原 `/ai/ask`

### Stream Step 5：观察项与最终回归

- 更新 `templates/base.html`
- 更新 `routes/ai_tutor.py`
- 更新 `double_process.md`
- 补充流式专用调试输出和最终验收记录

## Test Plan

至少覆盖以下场景：

- `Light/simple` 模式下浮窗提问，前端开始逐步显示文本
- `Light/simple` 模式下，流结束后消息完整落定
- `Light/simple` 模式下，上游流失败时自动退回原 `/ai/ask`
- `Light/simple` 模式下，本地 fallback 时前端仍能拿到完整答案
- `Full/context` 模式下，仍继续走原 `/ai/ask`
- 原有 `/ai/ask` 不受影响
- 独立 `ai_tutor.html` 页面不受影响
- `double_process.md` 对每个流式步骤都有单独记录

## Assumptions

- 本次“流式输出”只改浮窗，不改独立 AI 页面。
- 本次只让 `simple` 模式走真流式；`context` 模式暂不流式。
- 首选新增 `/ai/ask_stream`，不替换现有 `/ai/ask`。
- 传输方式采用 `fetch + ReadableStream`，不采用 `EventSource/SSE` 主方案。
- `double_process.md` 将新增一组独立的“流式步骤记录”，而不是混入已完成的 1-9 步里。
