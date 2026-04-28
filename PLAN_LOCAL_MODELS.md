# Reintroduce Local Transcription Providers

## Summary
Add first-class local transcription support back into `D:\Projects\AI-Video-Transcriber` while keeping the current subtitle-first workflow optional. The app will let the user explicitly choose `Groq` or `Local` as the transcription provider, explicitly choose whether to try YouTube subtitles first, and explicitly choose whether `Local` should be used as a fallback when `Groq` fails.

Defaults:
- `Transcription provider`: `Groq`
- `Try subtitles first`: `on`
- `Use local fallback for Groq`: `off`

Backward compatibility:
- `/api/process-video` stays in place.
- If older clients do not send the new fields, backend defaults preserve current behavior: subtitle-first, then Groq, no local fallback.

## Key Changes

### Backend
- Extend `/api/process-video` to accept:
  - `transcription_provider`: `groq | local`
  - `try_subtitles_first`: `true | false`
  - `use_local_fallback`: `true | false`
  - `local_backend`: `whisper | parakeet`
  - `local_model_preset`: preset id or `custom`
  - `local_model_id`: free-form model id/path for custom local models
  - `local_language`: optional hint
- Remove `FORCE_GROQ_TRANSCRIPTION` from the product flow. Runtime choice comes from request data, not env override.
- Keep the current subtitle extractor in `video_processor.py`, but gate it behind `try_subtitles_first`.
- Reuse `video_processor.download_and_convert(...)` as the local-audio path. Normalize local transcription input to mono 16 kHz audio; use `.wav` for Parakeet-compatible inference.
- Keep the current Groq URL path and current Groq file-upload recovery path. New Groq order when subtitles are not used or unavailable:
  1. Groq URL transcription
  2. Existing Groq file-upload fallback for media-fetch failures
  3. Local fallback only if `use_local_fallback=true` and the Groq failure is fallback-eligible
- Fallback-eligible Groq failures:
  - media fetch failures
  - timeouts / deadline exceeded
  - rate limit / transient provider errors
  - other provider-side request failures that are not caused by invalid credentials or invalid configuration
- Non-fallback Groq failures:
  - invalid Groq API key
  - unsupported Groq model / malformed request
  - missing Groq settings while provider is `groq`
- Add a local-transcription abstraction:
  - `whisper` backend: reuse/refactor `backend/transcriber.py` around `faster-whisper`
  - `parakeet` backend: add a new Parakeet backend module using NVIDIA NeMo pretrained models
- Curated local presets:
  - Whisper: `tiny`, `base`, `small`, `medium`, `large-v3`
  - Parakeet: `nvidia/parakeet-tdt-0.6b-v3`, `nvidia/parakeet-tdt-0.6b-v2`
  - Custom: allowed via `local_model_id`
- Runtime policy for local models:
  - auto-detect CUDA and use it when available
  - otherwise attempt CPU execution
  - for Parakeet, CPU mode is allowed but should surface a warning in task state/UI that it may be slow
- Add a small capabilities endpoint, e.g. `/api/local-model-capabilities`, returning available backends, preset list, dependency availability, and resolved runtime mode so the UI can disable clearly unavailable options instead of failing late.
- Extend task/result fields with:
  - `transcription_provider_requested`
  - `transcription_provider_used`
  - `local_backend_used`
  - `local_model_used`
  - `used_local_fallback`
  - keep existing `transcript_source`, but extend values with `local_audio_file`
- Source-label rendering should show the actual engine, for example:
  - `Local Whisper transcription (base)`
  - `Local Parakeet transcription (nvidia/parakeet-tdt-0.6b-v3)`
- Keep `include_timecodes`. For local backends:
  - Whisper: keep current timestamp formatting path
  - Parakeet: use timestamp-capable inference when available
  - Custom local models with no timestamps must still succeed, but return transcript without timecodes and set a task warning

### Frontend
- Add a transcription-provider section above provider-specific settings:
  - provider select: `Groq` / `Local`
  - checkbox: `Try subtitles first`
  - checkbox: `Use local model as fallback for Groq` (visible only when provider=`Groq`)
- Keep existing Groq settings, but only enable/show them when provider=`Groq`.
- Add a local-settings section:
  - backend select: `Whisper` / `Parakeet`
  - preset select
  - custom model field shown when preset=`custom`
  - optional local language hint
  - small availability/runtime notice from `/api/local-model-capabilities`
- Persist all new settings in the existing `localStorage` settings blob.
- Update progress/mode UX:
  - subtitles path
  - Groq path
  - local path
  - local fallback from Groq
- Update result metadata so transcript tab clearly shows whether the final transcript came from subtitles, Groq, or local, and whether local was used as fallback.
- Keep summary flow unchanged except for preserving transcript metadata from the new provider path.

### Dependencies and Setup
- Re-add `faster-whisper` to active project dependencies.
- Do not make Parakeet a startup hard dependency. Load Parakeet dependencies lazily so the app still starts on systems without NeMo installed.
- Update startup checks and docs:
  - `start.py` should treat local backends as optional capabilities, not required startup dependencies
  - README should document:
    - Whisper local install path
    - Parakeet install path
    - CPU vs CUDA behavior
    - expected slowness on CPU-only Parakeet
    - curated preset list and custom-model behavior

## Public Interface Changes
- `POST /api/process-video` new request fields:
  - `transcription_provider`
  - `try_subtitles_first`
  - `use_local_fallback`
  - `local_backend`
  - `local_model_preset`
  - `local_model_id`
  - `local_language`
- New endpoint:
  - `GET /api/local-model-capabilities`
- Task payload additions:
  - `transcription_provider_requested`
  - `transcription_provider_used`
  - `local_backend_used`
  - `local_model_used`
  - `used_local_fallback`
  - optional `warnings[]`

## Test Plan
- Backend contract tests:
  - provider=`groq`, subtitles on, subtitle found -> transcript uses subtitles and skips Groq/local
  - provider=`groq`, subtitles off -> subtitle fetch is skipped
  - provider=`local`, subtitles on, no subtitles -> local backend runs
  - provider=`local`, subtitles off -> local backend runs directly
  - provider=`groq`, local fallback off -> eligible Groq failure stays an error
  - provider=`groq`, local fallback on -> eligible Groq failure falls through to local backend
  - provider=`groq`, invalid key + local fallback on -> no fallback, hard error
  - curated Whisper preset resolves correctly
  - curated Parakeet preset resolves correctly
  - custom local model id is passed through unchanged
  - `include_timecodes=false` strips timestamps for local outputs too
- Capability tests:
  - missing `faster_whisper` marks Whisper unavailable
  - missing Parakeet dependency marks Parakeet unavailable
  - CPU-only runtime still reports Parakeet as selectable with warning
- Frontend/manual tests:
  - provider selection hides/shows the right settings
  - subtitle toggle is persisted
  - local fallback toggle is persisted and only shown for Groq
  - selected local preset/custom model is persisted
  - progress badge switches correctly between subtitle / Groq / local / fallback
  - transcript metadata reflects actual provider used

## Assumptions
- Subtitle extraction remains a separate, optional fast path; provider choice does not automatically bypass subtitles unless the user turns the toggle off.
- `Local fallback` uses the same selected local backend/model settings as the explicit `Local` provider path.
- No Groq fallback is added for the `Local` provider path in this iteration.
- Parakeet support is best-effort on CPU and must surface warning text instead of being silently blocked.
