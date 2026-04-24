# AI Tutor Phase 1 Progress

This file is the root progress record for the AI tutor phase 1 implementation. Each step should be appended after completion, then work pauses until the next "continue" instruction.

## Step Plan

| Step | Scope | Status |
|---|---|---|
| 1 | Add ORM models and SQL schema for AI tutor context tables | Done |
| 2 | Add Redis-first context store with in-memory fallback | Done |
| 3 | Add session and context services for events, snapshots, and context assembly | Done |
| 4 | Add rule service for phase 1 stuck-state diagnosis | Done |
| 5 | Add markdown knowledge service and initial knowledge files | Done |
| 6 | Extend `/ai/ask` with structured, backward-compatible responses | Done |
| 7 | Add `/ai/context/*` backend routes and register the blueprint | Done |
| 8 | Add shared frontend tracker and course bridge scripts | Done |
| 9 | Inject page context into the floating AI tutor in `base.html` | Done |
| 10 | Connect `emotion_computing` P0 events and snapshot provider | Done |
| 11 | Connect `face_emotion` P0 events, snapshot provider, and no-face counter | Done |
| 12 | Connect `ecobottle` P0 events, snapshot provider, and clean up hard-coded `G01` | Done |
| 13 | Final consistency checks and phase 1 cleanup | Done |

## Step 1 - ORM Models And SQL Schema

Status: Done

### Goal

Create the database foundation for AI tutor session memory, event history, memory summaries, and persisted Q&A messages without changing existing business tables or routes.

### Modified Files

- `models/orm_models.py`
- `models/__init__.py`
- `docs/sql/ai_tutor_context_tables.sql`
- `ai_tutor_phase1_progress.md`

### Implemented

- Added `AiTutorSession` for the current course-level AI tutor session.
- Added `AiTutorEvent` for structured page operation events.
- Added `AiTutorMemorySummary` for longer-lived group memory summaries. Phase 1 stores this but does not consume it yet.
- Added `AiTutorMessage` for persisted tutor question and answer text.
- Added `to_dict()` methods following the existing model style.
- Exported the new models from `models/__init__.py`.
- Added standalone MySQL DDL for the four new tables in `docs/sql/ai_tutor_context_tables.sql`.

### Interface / Data Structure Changes

- New ORM tables:
  - `ai_tutor_sessions`
  - `ai_tutor_events`
  - `ai_tutor_memory_summaries`
  - `ai_tutor_messages`
- Foreign keys use the existing group identity convention: `group_id -> groups.user_id`.
- JSON fields are reserved for snapshots, diagnosis payloads, event payloads, tips, and context evidence.

### Verification

- AST syntax check passed for `models/orm_models.py` and `models/__init__.py`.
- Full model import was not completed in this shell because `flask_sqlalchemy` is not installed in the active Python environment.
- `py_compile` could not write `models/__pycache__` because Windows returned an access-denied error for the `.pyc` replacement.

### Not Done Yet

- No Redis or memory fallback store yet.
- No session/context service logic yet.
- No `/ai/ask` behavior change yet.
- No `/ai/context/*` routes yet.
- No frontend tracker or course-page integration yet.

## Step 2 - Redis-First Context Store

Status: Done

### Goal

Add a short-lived cache layer for AI tutor snapshots, recent events, diagnosis, and proactive hint cooldowns. Redis/Flask-Caching is preferred when available; in-memory TTL storage is the fallback so development and degraded runtime can continue.

### Modified Files

- `services/ai_context_store.py`
- `ai_tutor_phase1_progress.md`

### Implemented

- Added `get_snapshot()` and `set_snapshot()` for `ai:snapshot:{session_id}`.
- Added `append_event()` and `get_recent_cached_events()` for `ai:events:{session_id}`.
- Added `get_diag()` and `set_diag()` for `ai:diag:{session_id}`.
- Added `get_cooldown()` and `set_cooldown()` for `ai:cooldown:{session_id}:{rule}`.
- Added `clear_session_cache()` for direct session hot-cache cleanup.
- Added `get_store_status()` for later debug-route visibility.
- Implemented an in-process TTL dictionary fallback guarded by `RLock`.
- Used lazy imports for the existing `utils.cache` backend so the module can be imported before Flask app/cache initialization.

### Interface / Data Structure Changes

- New service module: `services/ai_context_store.py`.
- Redis key conventions now exist in code:
  - `ai:snapshot:{session_id}`
  - `ai:events:{session_id}`
  - `ai:diag:{session_id}`
  - `ai:cooldown:{session_id}:{rule}`
- Cached events are stored as a bounded list, newest event last.

### Verification

- AST syntax check passed for `services/ai_context_store.py`.
- Fallback behavior check passed without Flask app/cache initialization:
  - snapshot can be set and read.
  - events append in order and can be limited by `limit`.
  - diagnosis can be set and read.
  - cooldown can be set and read.
  - `clear_session_cache()` clears snapshot, events, and diagnosis.

### Not Done Yet

- No database persistence of events or snapshots yet.
- No session/context service that calls this store yet.
- No route exposes `get_store_status()` yet.
- No frontend event reporting yet.

## Step 3 - Session And Context Services

Status: Done

### Goal

Connect the phase 1 ORM models and the short-lived context store so later routes can create/touch sessions, persist events, persist snapshots, and assemble the current AI tutor request context.

### Modified Files

- `services/ai_session_service.py`
- `services/ai_context_service.py`
- `ai_tutor_phase1_progress.md`

### Implemented

- Added `resolve_group_user_id()` to convert UI/login group identifiers such as `G01` into the persisted `groups.user_id` foreign key.
- Added `get_or_create_session()` for `AiTutorSession`.
- Added `touch_session()`, `update_session_snapshot()`, `update_session_diagnosis()`, and `close_session()`.
- Added `record_event()` to persist `AiTutorEvent` and append it to `ai_context_store`.
- Added `save_snapshot()` to persist the latest snapshot and mirror it into cache.
- Added `get_recent_db_events()` as a cache-miss fallback for recent event history.
- Added `compress_recent_events()` for compact context evidence strings.
- Added `build_request_context()` to normalize incoming `context`, load snapshot/events/diagnosis, and return a single context object for later answer generation.
- Added `build_context_used()` to shape the future structured `/ai/ask` response evidence.

### Interface / Data Structure Changes

- New service module: `services/ai_session_service.py`.
- New service module: `services/ai_context_service.py`.
- Service functions accept either database numeric group id or group code like `G01` where group resolution is needed.
- Request context assembly now expects `context.session_id` when used by the new context-aware path.

### Verification

- AST syntax check passed for `services/ai_session_service.py` and `services/ai_context_service.py`.
- Full database behavior was not executed in this shell because the active Python environment still lacks `flask_sqlalchemy`.

### Not Done Yet

- No rule diagnosis service yet.
- No markdown knowledge service yet.
- `/ai/ask` has not been changed to call `build_request_context()` yet.
- `/ai/context/*` routes have not been added yet.
- No frontend tracker calls these services yet.

## Step 4 - Rule Diagnosis Service

Status: Done

### Goal

Add phase 1 rule-based stuck-state diagnosis for the three target course pages. The service should be pure and callable by later `/ai/ask` and proactive hint logic.

### Modified Files

- `services/ai_rule_service.py`
- `ai_tutor_phase1_progress.md`

### Implemented

- Added unified rule result shape with `diagnosis`, `rule_hits`, `next_step`, `tips`, `confidence`, `mode`, and `source`.
- Added `detect_stuck(context)` dispatcher based on `course` and `page`.
- Added `detect_emotion_computing_rules()` covering:
  - `emotion_missing_face_model`
  - `emotion_missing_audio_model`
  - `emotion_missing_camera_start`
  - `emotion_missing_audio_input`
  - `emotion_has_single_modal_result_but_not_fused`
  - `emotion_result_ready_but_user_not_understand`
- Added `detect_face_emotion_rules()` covering:
  - `face_missing_model_selection`
  - `face_missing_camera_start`
  - `face_no_face_detected`
  - `face_result_ready_but_user_not_understand`
- Added `detect_ecobottle_rules()` covering:
  - `ecobottle_data_not_enough_for_train`
  - `ecobottle_prediction_without_data`
  - `ecobottle_wrong_tab_for_action`
  - `ecobottle_result_ready_but_user_not_understand`
- Added `build_rule_based_next_step()` to normalize a diagnosis code or full rule result into the standard payload.
- Added Chinese and English help-intent keyword detection so questions like "下一步怎么做" or "为什么没结果" raise confidence on relevant rules.

### Interface / Data Structure Changes

- New service module: `services/ai_rule_service.py`.
- Rule service input is the context dict produced by `build_request_context()`.
- Rule output is a dict designed to feed later structured `/ai/ask` fields.

### Verification

- AST syntax check passed for `services/ai_rule_service.py`.
- Focused rule checks passed:
  - `emotion_computing` with face result but no audio result returns `emotion_missing_audio_input`.
  - `face_emotion` with `consecutive_no_face_count = 3` returns `face_no_face_detected`.
  - `ecobottle` training tab with `data_count = 2` returns `ecobottle_data_not_enough_for_train`.
  - `ecobottle` with completed prediction returns `ecobottle_result_ready_but_user_not_understand`.

### Not Done Yet

- Rules are not connected to `/ai/ask` yet.
- Rules are not persisted into `AiTutorSession.latest_diagnosis` yet.
- Knowledge markdown is not used yet.
- Proactive hints are not generated yet.

## Step 5 - Markdown Knowledge Service

Status: Done

### Goal

Add a lightweight markdown knowledge base for phase 1 course guidance and a service that selects relevant snippets by course, step code, and diagnosis.

### Modified Files

- `services/ai_knowledge_service.py`
- `docs/ai_knowledge/emotion_computing/step_select_model.md`
- `docs/ai_knowledge/emotion_computing/step_record_audio.md`
- `docs/ai_knowledge/emotion_computing/step_fusion.md`
- `docs/ai_knowledge/emotion_computing/stuck_missing_audio.md`
- `docs/ai_knowledge/emotion_computing/stuck_missing_camera.md`
- `docs/ai_knowledge/emotion_computing/explain_fusion_result.md`
- `docs/ai_knowledge/face_emotion/step_select_model.md`
- `docs/ai_knowledge/face_emotion/step_start_camera.md`
- `docs/ai_knowledge/face_emotion/stuck_no_face.md`
- `docs/ai_knowledge/face_emotion/explain_result.md`
- `docs/ai_knowledge/ecobottle/step_collect_data.md`
- `docs/ai_knowledge/ecobottle/step_explore.md`
- `docs/ai_knowledge/ecobottle/step_train.md`
- `docs/ai_knowledge/ecobottle/step_predict.md`
- `docs/ai_knowledge/ecobottle/step_control.md`
- `docs/ai_knowledge/ecobottle/stuck_not_enough_data.md`
- `docs/ai_knowledge/ecobottle/stuck_wrong_tab.md`
- `docs/ai_knowledge/ecobottle/explain_prediction.md`
- `ai_tutor_phase1_progress.md`

### Implemented

- Added `load_knowledge_index()` to expose the static phase 1 knowledge map.
- Added `build_knowledge_context()` to select markdown snippets by `course`, `step_code`, and `diagnosis`.
- Added course aliases for `emotion_computing`, `face_emotion`, and `ecobottle`.
- Added initial markdown guidance for the three phase 1 courses.
- Covered operation steps, common stuck states, and result explanation snippets.

### Interface / Data Structure Changes

- New service module: `services/ai_knowledge_service.py`.
- New knowledge root: `docs/ai_knowledge/`.
- Knowledge service returns:
  - `knowledge_refs`
  - `snippets`
  - concatenated `text`
  - normalized `course`, `step_code`, and `diagnosis`

### Verification

- AST syntax check passed for `services/ai_knowledge_service.py`.
- Snippet lookup checks passed:
  - `emotion_missing_audio_input` returns `stuck_missing_audio.md` and `step_record_audio.md`.
  - `face_no_face_detected` returns `stuck_no_face.md` and `step_start_camera.md`.
  - `ecobottle_data_not_enough_for_train` returns `stuck_not_enough_data.md` and `step_train.md`.
- Confirmed 18 markdown files under `docs/ai_knowledge/`.

### Not Done Yet

- Knowledge snippets are not connected to `/ai/ask` yet.
- No vector search or embeddings are included in phase 1.
- The markdown set is intentionally small and only covers phase 1 paths.

## Step 6 - Structured `/ai/ask`

Status: Done

### Goal

Extend `/ai/ask` so context-aware requests can use session context, recent events, rule diagnosis, and markdown knowledge while old `{ "question": "..." }` requests keep working.

### Modified Files

- `services/ai_tutor_service.py`
- `routes/ai_tutor.py`
- `ai_tutor_phase1_progress.md`

### Implemented

- Added `answer_with_context()` for the new context-aware answer path.
- Added `compose_structured_response()` to return fixed fields:
  - `answer`
  - `diagnosis`
  - `next_step`
  - `tips`
  - `context_used`
  - `source`
  - `mode`
- Added `build_llm_messages_from_context()` as the future context-aware LLM message builder.
- Added best-effort `AiTutorMessage` persistence for tutor Q&A text.
- Added best-effort latest diagnosis cache/database persistence.
- Updated `/ai/ask`:
  - Requests with `context.session_id` use `answer_with_context()`.
  - Requests without `context.session_id` still use the original `get_answer()`.
  - Response keeps old fields and appends new structured fields.
- Current user group code is copied into request context when available.

### Interface / Data Structure Changes

- Old request remains valid:
  - `{ "question": "..." }`
- New context-aware request is supported:
  - `{ "question": "...", "prefer_llm": false, "context": { "session_id": "...", ... } }`
- `/ai/ask` now may include additional fields:
  - `diagnosis`
  - `next_step`
  - `tips`
  - `context_used`

### Verification

- AST syntax check passed for `services/ai_tutor_service.py` and `routes/ai_tutor.py`.
- Old non-context answer path still works through `get_answer("什么是人工智能")` and returns a local answer.
- Full context-aware `/ai/ask` runtime test was not executed in this shell because that path imports database models and the active Python environment still lacks `flask_sqlalchemy`.

### Not Done Yet

- `/ai/context/*` routes are not added yet.
- Frontend still does not send real context/session snapshots.
- Rule-based answers are connected, but proactive hints are not.

## Step 7 - Context Routes

Status: Done

### Goal

Add backend context ingestion/debug routes and register them in the Flask app.

### Modified Files

- `routes/ai_context.py`
- `app.py`
- `ai_tutor_phase1_progress.md`

### Implemented

- Added `POST /ai/context/event`.
  - Validates required fields.
  - Uses login session group id when request `group_id` is absent.
  - Persists event through `record_event()`.
  - Returns `event_id`.
- Added `POST /ai/context/snapshot`.
  - Validates required fields.
  - Persists latest snapshot through `save_snapshot()`.
  - Returns `session_id` and `updated_at`.
- Added `POST /ai/context/delete_memory`.
  - Deletes only AI tutor phase 1 memory tables for a group.
  - Clears hot cache for affected sessions.
  - Does not touch existing business/course tables.
- Added `GET /ai/context/debug/<session_id>`.
  - Requires login.
  - Only enabled in Flask debug mode, `DEBUG`, or `AI_CONTEXT_DEBUG_ENABLED`.
  - Returns cache and recent database context.

### Interface / Data Structure Changes

- New blueprint: `ai_context_bp` with prefix `/ai/context`.
- New endpoints:
  - `POST /ai/context/event`
  - `POST /ai/context/snapshot`
  - `POST /ai/context/delete_memory`
  - `GET /ai/context/debug/<session_id>`

### Verification

- AST syntax check passed for `routes/ai_context.py` and `app.py`.
- Confirmed `ai_context_bp` is registered in `app.py`.
- Confirmed route declarations exist for `/event`, `/snapshot`, `/delete_memory`, and `/debug/<session_id>`.
- Full endpoint runtime tests were not executed in this shell because the active Python environment still lacks `flask_sqlalchemy`.

### Not Done Yet

- Frontend tracker is not created yet.
- Course pages do not call these endpoints yet.
- Delete memory has no frontend UI in phase 1.

## Step 8 - Shared Frontend Tracker And Bridge

Status: Done

### Goal

Add reusable frontend scripts for session identity, event reporting, snapshot reporting, AI ask context injection, and lightweight action hints. This step creates the shared tools only; course pages are connected in later steps.

### Modified Files

- `static/js/ai_context_tracker.js`
- `static/js/ai_course_bridge.js`
- `ai_tutor_phase1_progress.md`

### Implemented

- Added `window.AiContextTracker`.
  - Generates and stores a per-page/course `session_id` in `sessionStorage`.
  - Supports `init()`, `configure()`, `getSessionId()`, and `setStep()`.
  - Supports `setSnapshotProvider()` and `getSnapshot()`.
  - Supports `reportEvent()` to `POST /ai/context/event`.
  - Supports `reportSnapshot()` to `POST /ai/context/snapshot`.
  - Supports debounced `scheduleSnapshot()`.
  - Supports `buildAskContext()` and `wrapAskPayload()` for later `/ai/ask` integration.
- Added `window.AiCourseBridge`.
  - Wraps tracker initialization for course pages.
  - Supports `track()`, `snapshot()`, and `getAskContext()`.
  - Supports `attachAskContext()` for chat request payloads.
  - Adds lightweight action handling for button highlight and tab switching.
  - Keeps action hints non-invasive: no modal, no forced operation.

### Interface / Data Structure Changes

- New frontend globals:
  - `window.AiContextTracker`
  - `window.AiCourseBridge`
- New expected page integration pattern:
  - Initialize bridge with `page`, `course`, optional `stepCode`, and `snapshotProvider`.
  - Course code calls `AiCourseBridge.track(...)` at key operations.
  - Course code calls `AiCourseBridge.snapshot(...)` at key state changes or before asking AI.

### Verification

- `node --check static/js/ai_context_tracker.js` passed.
- `node --check static/js/ai_course_bridge.js` passed.
- Confirmed exported globals and key methods exist: `AiContextTracker`, `AiCourseBridge`, `reportEvent`, `reportSnapshot`, `attachAskContext`, and `applyHint`.

### Not Done Yet

- `base.html` does not load these scripts yet.
- Course pages do not initialize or call the tracker yet.
- No real frontend events are sent until Steps 9-12.

## Step 9 - Floating Tutor Context Injection

Status: Done

### Goal

Update the global floating tutor in `base.html` so AI questions include page context and structured answers can show next-step guidance and tips.

### Modified Files

- `templates/base.html`
- `ai_tutor_phase1_progress.md`

### Implemented

- Loaded shared frontend scripts globally:
  - `static/js/ai_context_tracker.js`
  - `static/js/ai_course_bridge.js`
- Added `inferMaoPageInfo()` to infer page/course from the current URL.
- Added `getMaoAskPayload()` to attach AI context to floating tutor requests.
- Added `askMaoApi()` so manual questions and quick questions share one `/ai/ask` path.
- Added `formatMaoReply()` to display structured response fields:
  - `answer`
  - `next_step`
  - first item in `tips`
- Floating tutor now initializes a default bridge context if the course page has not initialized one yet.
- Floating tutor reports a snapshot before asking when the bridge is available.

### Interface / Data Structure Changes

- Global floating tutor `/ai/ask` requests now include `context` with:
  - `session_id`
  - `page`
  - `course`
  - `group_id` when available from login session
  - `snapshot` from the active page bridge/provider when available
- Existing visible chat UI remains the same; structured fields are appended as plain assistant text.

### Verification

- Jinja parse check passed for `templates/base.html`.
- Confirmed required script markers and helper functions are present.
- Extracted updated inline floating tutor script and ran `node --check` successfully with UTF-8 output.

### Not Done Yet

- Course pages still need page-specific bridge initialization and snapshot providers.
- The floating tutor can infer page/course, but detailed course state is added in Steps 10-12.

## Step 10 - Emotion Computing Context Events

Status: Done

### Goal

Connect the emotion computing course page to the AI tutor context tracker so the tutor can see model choices, capture state, recognition results, fusion configuration, fusion results, and toy feedback.

### Modified Files

- `templates/emotion_computing.html`
- `static/js/emotion_computing.js`
- `ai_tutor_phase1_progress.md`

### Implemented

- Initialized `AiCourseBridge` on the emotion computing page with:
  - `page: emotion_computing`
  - `course: emotion_computing`
  - `stepCode: select_model`
  - a page-specific snapshot provider
- Added emotion computing snapshot fields:
  - selected face/audio model IDs
  - fusion strategy
  - face weight
  - camera started state
  - recording state
  - selected toy
  - last face/audio/fusion result summaries
- Added configuration events:
  - `face_model_selected`
  - `audio_model_selected`
  - `face_weight_changed`
  - `weight_preset_selected`
  - `fusion_strategy_changed`
- Added runtime operation/result events:
  - `camera_started`
  - `camera_stopped`
  - `recording_started`
  - `recording_stopped`
  - `face_result_updated`
  - `audio_result_updated`
  - `fusion_result_updated`
  - `toy_selected`
- Added debouncing/throttling:
  - Weight slider changes are debounced before reporting.
  - High-frequency face/fusion result events are throttled to avoid flooding `/ai/context/event`.

### Interface / Data Structure Changes

- New frontend global helpers from `static/js/emotion_computing.js`:
  - `window.getEmotionComputingSnapshot()`
  - `window.reportEmotionEvent(...)`
  - `window.scheduleEmotionSnapshot(...)`
- Emotion computing snapshots now provide enough state for the rule service to diagnose missing camera/audio, fusion setup, result explanation, and toy feedback progress.

### Verification

- `node --check static/js/emotion_computing.js` passed.
- Jinja parse check passed for `templates/emotion_computing.html`.
- Confirmed bridge initialization and all Step 10 event markers are present with `rg`.

### Not Done Yet

- Face emotion page is not connected to the tracker yet.
- EcoBottle page is not connected to the tracker yet.
- No browser/manual end-to-end event POST test was run in this step because the local app runtime still depends on missing environment packages from earlier verification.

## Step 11 - Face Emotion Context Events

Status: Done

### Goal

Connect the standalone face emotion recognition page to the AI tutor context tracker so the tutor can diagnose model selection, camera startup, no-face states, and completed recognition results.

### Modified Files

- `templates/face_emotion.html`
- `static/js/face_emotion.js`
- `ai_tutor_phase1_progress.md`

### Implemented

- Initialized `AiCourseBridge` on the face emotion page with:
  - `page: face_emotion`
  - `course: face_emotion`
  - `stepCode: select_model`
  - a page-specific snapshot provider
- Added face emotion snapshot fields:
  - `current_model`
  - `model_id`
  - `camera_status`
  - `camera_started`
  - `last_result`
  - `last_face_count`
  - `consecutive_no_face_count`
- Added model/camera/result events:
  - `model_selected`
  - `camera_started`
  - `camera_stopped`
  - `camera_error`
  - `face_result_updated`
  - `no_face_detected`
- Added result summarization for the first detected face:
  - emotion index
  - English emotion label when available
  - Chinese emotion label
  - max confidence score
- Added throttling for high-frequency result events:
  - `face_result_updated`
  - `no_face_detected`

### Interface / Data Structure Changes

- New frontend globals from `static/js/face_emotion.js`:
  - `window.getFaceEmotionSnapshot()`
  - `window.reportFaceEmotionEvent(...)`
  - `window.scheduleFaceEmotionSnapshot(...)`
- The snapshot uses `current_model: system_default` when no custom model is selected, so the rule service treats the default model as a valid selection.

### Verification

- `node --check static/js/face_emotion.js` passed.
- Jinja parse check passed for `templates/face_emotion.html`.
- Confirmed bridge initialization and Step 11 event markers are present with `rg`.

### Not Done Yet

- EcoBottle page is not connected to the tracker yet.
- No browser/manual end-to-end event POST test was run in this step because the local app runtime still depends on missing environment packages from earlier verification.

## Step 12 - EcoBottle Context Events

Status: Done

### Goal

Connect the EcoBottle page to the AI tutor context tracker so the tutor can understand data collection, exploration, training, prediction, and control progress.

### Modified Files

- `templates/ecobottle.html`
- `static/js/ecobottle.js`
- `ai_tutor_phase1_progress.md`

### Implemented

- Initialized `AiCourseBridge` on the EcoBottle page with:
  - `page: ecobottle`
  - `course: ecobottle`
  - `stepCode: collect_data`
  - a page-specific snapshot provider
- Added EcoBottle snapshot fields:
  - `current_tab`
  - `data_count`
  - `table_data_count`
  - `training_data_count`
  - `prediction_model`
  - `selected_model_id`
  - `train_config`
  - `last_prediction`
  - `last_training`
  - `last_explore`
  - `last_control`
  - current sensor/control values
- Added collection events:
  - `sensor_values_changed`
  - `quick_action_used`
  - `data_point_added`
  - `csv_imported`
- Added exploration events:
  - `explore_channel_changed`
  - `explore_analysis_run`
  - `correlation_analysis_run`
- Added training and prediction events:
  - `training_model_selected`
  - `training_blocked_not_enough_data`
  - `training_completed`
  - `prediction_blocked_not_enough_data`
  - `prediction_requested`
  - `prediction_model_selected`
- Added control events:
  - `control_tab_initialized`
  - `manual_control_applied`
- Updated `/eco/predict` frontend payload to include the selected custom `model_id` when present, matching the existing backend support.

### Interface / Data Structure Changes

- New frontend globals from `static/js/ecobottle.js`:
  - `window.getEcobottleSnapshot()`
  - `window.reportEcobottleEvent(...)`
  - `window.scheduleEcobottleSnapshot(...)`
- Snapshot keys now align with the EcoBottle rule service:
  - `current_tab`
  - `data_count`
  - `prediction_model`
  - `last_prediction`
- Training blockers now emit `training_blocked_not_enough_data`, which the rule service already recognizes.
- Successful predictions emit `prediction_requested`, which the rule service already recognizes.

### Verification

- `node --check static/js/ecobottle.js` passed.
- Jinja parse check passed for `templates/ecobottle.html`.
- Confirmed bridge initialization, snapshot helper, and Step 12 event markers are present with `rg`.

### Not Done Yet

- No browser/manual end-to-end event POST test was run in this step because the local app runtime still depends on missing environment packages from earlier verification.
- Phase 1 still needs a final pass for consistency, lightweight integration checks, and any progress-document cleanup.

## Step 13 - Final Consistency Checks And Cleanup

Status: Done

### Goal

Run a final Phase 1 consistency pass, fix small mismatches, and make sure the progress record reflects the actual implementation state.

### Modified Files

- `templates/ecobottle.html`
- `static/js/ecobottle.js`
- `ai_tutor_phase1_progress.md`

### Implemented

- Updated the Step Plan table so Steps 10-13 reflect their completed status.
- Cleaned up EcoBottle frontend hard-coded `G01` usage:
  - Added `window.ECO_GROUP_ID` from Flask session in `templates/ecobottle.html`.
  - Added `getEcoGroupId()` in `static/js/ecobottle.js`.
  - Updated sensor add/delete/clear/import/export/history/explore calls to use the active group ID.
  - Kept `G01` only as a safe fallback when no group ID is available.
- Confirmed the existing shared action hint support is present in `AiCourseBridge`:
  - button/element highlight
  - tab switching
  - named action dispatch

### Verification

- `node --check` passed for:
  - `static/js/ai_context_tracker.js`
  - `static/js/ai_course_bridge.js`
  - `static/js/emotion_computing.js`
  - `static/js/face_emotion.js`
  - `static/js/ecobottle.js`
- Jinja parse checks passed for:
  - `templates/base.html`
  - `templates/emotion_computing.html`
  - `templates/face_emotion.html`
  - `templates/ecobottle.html`
- Python AST parse passed for the updated AI tutor backend modules and route/model files.
- Confirmed EcoBottle `G01` appears only as a fallback/default, not as the active hard-coded group for frontend operations.

### Not Done Yet

- Full browser end-to-end event POST testing was not run because the local runtime still lacks required Python packages such as `flask_sqlalchemy`.
- Database migration/application still needs to be run in the real deployment environment using `docs/sql/ai_tutor_context_tables.sql`.
