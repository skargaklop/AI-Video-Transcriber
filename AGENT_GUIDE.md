# AI Video Transcriber CLI — Agent Guide

## Capabilities

- **transcribe**: Convert video/audio URL or local file to text transcript
- **summarize**: Generate AI summary from transcript text
- **pipeline**: Transcribe + summarize in a single invocation
- **tasks**: List, inspect, or delete persisted task records

## Quick Reference

### transcribe
```bash
python cli.py transcribe --url <URL> --provider <groq|local|local_api> [options]
python cli.py transcribe --file <PATH> --provider <groq|local|local_api> [options]
```

### summarize
```bash
python cli.py summarize --task-id <ID> [options]
python cli.py summarize --transcript-file <PATH> [options]
```

### pipeline
```bash
python cli.py pipeline --url <URL> --provider <PROVIDER> --openai-api-key <KEY> [options]
```

### tasks
```bash
python cli.py tasks --list
python cli.py tasks --get <ID>
python cli.py tasks --delete <ID>
```

## All Flags

### transcribe / pipeline (transcription flags)

| Flag | Type | Default | Env Var | Description |
|------|------|---------|---------|-------------|
| `--url` | string | | | Video URL (YouTube, etc.) |
| `--file` | string | | | Local audio/video file path |
| `--provider` | enum | `groq` | | `groq`, `local`, or `local_api` |
| `--groq-api-key` | string | | `GROQ_API_KEY` | Groq API key |
| `--groq-model` | string | `whisper-large-v3-turbo` | | Groq model name |
| `--language` | string | `auto` | | Language code or `auto` |
| `--include-timecodes` | boolean | `false` | | Keep timecodes in transcript |
| `--skip-subtitles` | boolean | `false` | | Skip YouTube subtitle extraction |
| `--local-backend` | enum | `whisper` | | `whisper` or `parakeet` |
| `--local-model` | string | `base` | | Local model preset or ID |
| `--local-api-base-url` | string | | | Local API endpoint URL (for `local_api`) |
| `--local-api-key` | string | | | Local API key (for `local_api`) |
| `--local-api-model` | string | | | Local API model name (for `local_api`) |
| `--local-api-language` | string | | | Local API language code (for `local_api`) |
| `--local-api-prompt` | string | | | Local API prompt (for `local_api`) |
| `--output` | string | | | Write output to file path |
| `--format` | enum | `json` | | `json`, `markdown`, or `txt` |

### summarize (source flags — not available in pipeline)

| Flag | Type | Default | Env Var | Description |
|------|------|---------|---------|-------------|
| `--task-id` | string | | | Task ID from prior transcribe run |
| `--transcript-file` | string | | | Path to transcript text file |

### summarize / pipeline (summary config flags)

| Flag | Type | Default | Env Var | Description |
|------|------|---------|---------|-------------|
| `--task-id` | string | | | Task ID from prior transcribe run |
| `--transcript-file` | string | | | Path to transcript text file |
| `--openai-api-key` | string | | `OPENAI_API_KEY` | OpenAI API key |
| `--openai-base-url` | string | | `OPENAI_BASE_URL` | OpenAI base URL |
| `--model` | string | `gpt-4o` | | Model name |
| `--summary-language` | string | `en` | | Summary language code |
| `--output-format` | enum | `markdown` | | `markdown`, `html`, or `txt` |
| `--summary-output` | string | | | Write summary to file path |
| `--prompt` | string | | | Custom summary instructions |
| `--reasoning-effort` | enum | | | `none`, `minimal`, `low`, `medium`, `high`, `xhigh` |

### tasks

| Flag | Type | Description |
|------|------|-------------|
| `--list` | boolean | List all tasks |
| `--get` | string | Get task by ID |
| `--delete` | string | Delete task by ID |

### Global flags

| Flag | Type | Description |
|------|------|-------------|
| `--pretty` | boolean | Human-readable output instead of JSON |
| `--quiet` | boolean | Suppress progress messages on stderr |
| `--agent-help` | boolean | Print JSON capability manifest and exit |

## Output JSON Schema

### transcribe
```json
{
  "task_id": "uuid",
  "status": "completed",
  "video_title": "string",
  "transcript": "full transcript markdown text",
  "detected_language": "en",
  "transcript_source": "groq_audio_url",
  "transcription_provider_used": "groq",
  "script_path": "/path/to/transcript.md"
}
```

### summarize
```json
{
  "task_id": "uuid (if --task-id used)",
  "status": "completed",
  "summary": "full summary markdown text",
  "video_title": "string",
  "language": "en"
}
```

### pipeline
```json
{
  "task_id": "uuid",
  "video_title": "string",
  "detected_language": "en",
  "transcript_source": "groq_audio_url",
  "transcription_provider_used": "groq",
  "summary": "full summary markdown text",
  "summary_language": "en"
}
```

### tasks --list
```json
{
  "tasks": [
    {"task_id": "uuid", "status": "completed", "video_title": "...", ...},
    {"task_id": "uuid", "status": "completed", "video_title": "...", ...}
  ]
}
```

### tasks --get / tasks --delete
```json
{
  "status": "completed",
  "task_id": "uuid"
}
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Runtime error (API failure, file not found, etc.) |
| 2 | Invalid arguments |

## Environment Variables

| Variable | Used By | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | transcribe (groq) | Groq API key for Whisper transcription |
| `OPENAI_API_KEY` | summarize | OpenAI-compatible API key for summarization |
| `OPENAI_BASE_URL` | summarize | Custom OpenAI base URL (proxies, alternative endpoints) |

CLI flags always override environment variables. A `.env` file in the project root is auto-loaded if present.

## Provider Decision Matrix

| Provider | When to Use | Requirements |
|----------|-------------|--------------|
| `groq` | Fastest transcription, cloud-based, good for most use cases | `GROQ_API_KEY` or `--groq-api-key` |
| `local` | Privacy-sensitive content, offline use, no API limits | Local GPU/CPU with Whisper or Parakeet installed |
| `local_api` | Self-hosted Whisper-compatible API endpoint | Running local API server with `--local-api-*` config (via web UI) |

For `local` provider, use `--local-backend whisper` (default) or `--local-backend parakeet`, and `--local-model` to select the model size (e.g., `base`, `small`, `medium`, `large`).

## Example Workflows

### 1. Basic YouTube transcription (Groq)
```bash
python cli.py transcribe \
    --url "https://youtu.be/dQw4w9WgXcQ" \
    --groq-api-key "$GROQ_API_KEY"
```

### 2. Transcribe local audio file
```bash
python cli.py transcribe \
    --file recording.mp3 \
    --provider groq \
    --groq-api-key "$GROQ_API_KEY"
```

### 3. Full pipeline: transcribe + summarize
```bash
python cli.py pipeline \
    --url "https://youtu.be/dQw4w9WgXcQ" \
    --groq-api-key "$GROQ_API_KEY" \
    --openai-api-key "$OPENAI_API_KEY" \
    --summary-language en \
    --output-format markdown
```

### 4. Summarize from a saved transcript file
```bash
python cli.py summarize \
    --transcript-file transcript.md \
    --openai-api-key "$OPENAI_API_KEY" \
    --summary-language en \
    --summary-output summary.md
```

### 5. Summarize an existing task
```bash
python cli.py summarize \
    --task-id "abc-def-123" \
    --openai-api-key "$OPENAI_API_KEY" \
    --summary-language en
```

### 6. Transcribe with local Whisper, save to file
```bash
python cli.py transcribe \
    --url "https://youtu.be/dQw4w9WgXcQ" \
    --provider local \
    --local-backend whisper \
    --local-model base \
    --output transcript.md \
    --format markdown
```

### 7. List all tasks
```bash
python cli.py tasks --list
```

### 8. Discover capabilities (for AI agents)
```bash
python cli.py --agent-help
```

## Error Handling

- All errors are returned as JSON with `{"error": "...", "exit_code": N}` to stdout
- Progress messages go to stderr (suppressed with `--quiet`)
- On exit code 1, check the `error` field for details
- On exit code 2, re-run with `--help` to see valid arguments

## Notes

- The CLI reuses the same backend as the web UI — no web server required
- Task records are persisted in `temp/tasks.json` and shared with the web UI
- Transcribed files are saved in the `temp/` directory
- The `pipeline` command runs transcription first, then summarization on the result
