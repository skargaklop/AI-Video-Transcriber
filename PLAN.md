# Full Implementation Plan: Windows 10 YouTube Transcriber

## Summary
Build on `D:\Projects\AI-Video-Transcriber`, not `D:\Projects\youtube-transcriber`. Keep the current FastAPI + browser UI architecture, remove Docker from the intended workflow, change the default port to `8001`, and implement a two-stage user flow: first obtain a transcript, then ask the user before sending that transcript to an LLM for summarization.

The cloned `youtube-transcriber` repo is a reference only. We can borrow product ideas such as provider settings, fallback-order messaging, Groq usage diagnostics, and separate summarization, but we should not copy code from it.

## Target Workflow
1. User opens `http://localhost:8001`.
2. User enters a YouTube URL.
3. App checks for manual or automatic YouTube subtitles first.
4. If subtitles exist, parse them into the transcript immediately.
5. If subtitles do not exist, use `yt-dlp` to extract a temporary best-audio URL, preferring m4a-compatible audio when available.
6. Send that audio URL to Groq speech-to-text using the Groq `url` request parameter, not a downloaded file.
7. Display the transcript and save a transcript Markdown file.
8. Show a separate summarization panel.
9. User chooses summary provider settings, output format, and confirms sending the transcript.
10. App generates and saves Markdown and/or HTML summary files.

## Key Decisions
- **Runtime:** Windows 10, local Python virtual environment.
- **No Docker:** Ignore Dockerfile and docker-compose in v1 docs/startup flow.
- **Port:** Default to `8001`, still allow `PORT` environment override.
- **UI:** Improve existing browser page, no Streamlit/NiceGUI/Gradio rewrite in v1.
- **Transcription fallback:** Groq URL transcription only. If Groq cannot fetch/transcribe the direct audio URL, show a clear error instead of downloading audio.
- **API keys:** Browser settings are primary. `.env` may remain as optional fallback, but the normal UI should work with user-entered keys.
- **Groq model:** Default `whisper-large-v3-turbo`; allow `whisper-large-v3`.
- **Summary output:** Support Markdown and HTML.

## Backend Changes
- Update startup defaults from port `8000` to `8001` in `start.py` and `.env.example`.
- Add a Groq transcription service that calls `https://api.groq.com/openai/v1/audio/transcriptions` with:
  - `model`
  - `url`
  - `response_format=verbose_json`
  - `timestamp_granularities[]=segment`
  - optional `language`
  - optional `prompt`
- Add a `yt-dlp` audio URL extraction helper that returns title, duration, selected format, extension, and direct audio URL without downloading media.
- Keep the existing subtitle parser, but improve source reporting: `youtube_manual_subtitles`, `youtube_auto_subtitles`, or `groq_audio_url`.
- Split the current all-in-one processing into two backend operations:
  - transcription job: subtitle/Groq pipeline only
  - summary job: confirmed LLM call only
- Keep task status/SSE behavior for long transcription jobs and add equivalent progress states for summarization.
- Add HTML summary saving. Markdown remains plain `.md`; HTML should be standalone enough to open locally.

## API Shape
- Keep `/api/process-video` for starting a transcript job to avoid a large frontend rewrite.
- Change its result semantics so it produces transcript data, not automatic summary data.
- Add `/api/summarize-transcript` accepting:
  - `task_id`
  - `api_key`
  - `model_base_url`
  - `model_id`
  - `summary_language`
  - `output_format`: `markdown`, `html`, or `both`
  - optional custom prompt/style later, but not required for v1
- Extend `/api/task-status/{task_id}` so completed transcription tasks expose:
  - `video_title`
  - `transcript`
  - `transcript_source`
  - `detected_language`
  - `raw_script_file`
  - `script_path`
- Add summary task fields:
  - `summary`
  - `summary_markdown_path`
  - `summary_html_path`
  - `summary_language`
  - `summary_model`
- Extend `/api/download/{filename}` to allow `.md` and `.html` files, with path traversal protection.

## Frontend Changes
- Change visible local URL/documentation references to `localhost:8001`.
- Rework the page into a clear two-step workflow:
  - Step 1: “Get transcript”
  - Step 2: “Summarize transcript”
- Add Groq transcription settings in the UI:
  - Groq API key
  - Whisper model selector
  - optional language hint
  - optional prompt/context field
- Keep existing LLM settings for summary provider, base URL, API key, and model.
- Add a confirmation control before summarization: no summary request is sent until the user clicks the summary button.
- Add output format control: Markdown, HTML, or both.
- Show transcript source badge:
  - Subtitle
  - Auto subtitle
  - Groq audio URL
- Update progress labels:
  - Checking subtitles
  - Extracting audio URL
  - Transcribing with Groq
  - Transcript ready
  - Waiting for summary confirmation
  - Generating summary
  - Files ready
- Add download buttons for transcript Markdown, summary Markdown, and summary HTML.

## Windows Setup
- Add a Windows launcher script, for example `start_windows.bat`, that:
  - activates `.venv` if present
  - starts `python start.py --prod`
  - uses port `8001` by default
- Update README with Windows-only quick start:
  - install Python
  - create venv
  - install requirements
  - install or verify `ffmpeg`
  - install or verify `yt-dlp`
  - run launcher
  - open `http://localhost:8001`
- Remove Docker from the recommended path; leave Docker docs only if clearly marked unsupported/out of scope for this setup.

## Error Handling
- Missing Groq key: show “Groq API key is required for videos without subtitles.”
- No subtitles and no Groq key: stop after subtitle check with a clear message.
- `yt-dlp` cannot extract audio URL: show video unavailable/auth/rate-limit guidance where possible.
- Groq rejects URL: explain that temporary YouTube media URLs can expire or be inaccessible from Groq, and suggest retrying.
- Groq rate limit: surface the provider message and do not retry in a loop.
- Summary key missing: keep transcript visible and ask user to configure summary provider.
- Summary failure: keep transcript and downloads intact.

## Testing
- Unit-test VTT/SRT parsing with duplicated YouTube auto-caption cues.
- Unit-test safe filename generation for Markdown and HTML outputs.
- Unit-test Groq response normalization for `verbose_json` with segments and fallback `text`.
- Unit-test direct audio URL extraction using mocked `yt-dlp` info output.
- Manual test: video with manual subtitles.
- Manual test: video with automatic subtitles only.
- Manual test: video without captions using Groq URL transcription.
- Manual test: invalid Groq key.
- Manual test: summary confirmation path, ensuring no LLM request happens before click.
- Manual test: Markdown and HTML downloads open correctly on Windows 10.
- Manual test: app starts at `http://localhost:8001`.

## Out Of Scope For V1
- Docker.
- Rewriting UI in Streamlit, NiceGUI, Gradio, or Reflex.
- Chrome extension.
- SQLite transcript library.
- RAG/chat with transcript.
- Speaker diarization.
- Local Whisper fallback.
- Downloading full video/audio as the normal fallback path.
- Multi-provider transcription chain beyond Groq.

## Assumptions
- The implementation target is `D:\Projects\AI-Video-Transcriber`.
- The cloned `D:\Projects\youtube-transcriber` repo remains a reference only.
- The user prefers `8001`.
- The app should remain local and Windows 10 friendly.
- Browser-provided API keys are acceptable for v1.
- Groq URL transcription is technically attempted first for missing subtitles; if YouTube/Groq URL access fails, v1 reports the failure clearly rather than downloading audio.
