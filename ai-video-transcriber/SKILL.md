---
name: ai-video-transcriber
description: Transcribe video/audio to text and generate AI summaries via the CLI — use when the user wants to transcribe, summarize, or pipeline video/audio content
---

# SKILL: AI Video Transcriber CLI

## Identity

- **Tool**: `cli.py` — Command-line interface for video/audio transcription and AI summarization
- **Location**: Project root (`D:\Projects\AI-Video-Transcriber\cli.py`)
- **Invocation**: `python cli.py <command> [flags]`
- **Output**: JSON to stdout (default), progress to stderr
- **Prerequisites**: Python 3.10+, project dependencies installed (`pip install -r requirements.txt`)

## When to Use This Tool

Use this CLI when you need to:
- Extract text transcript from a video URL (YouTube, etc.) or local audio/video file
- Run multi-source transcription across platform subtitles, Groq Whisper, local Whisper, and local Parakeet
- Return a raw bundle of source transcripts or merge them deterministically / with an OpenAI-compatible model
- Generate an AI summary of a transcript
- Do both in a single step (pipeline)
- Manage previously created transcription tasks

Do NOT use this CLI for:
- Real-time streaming transcription
- Translation-only tasks (not supported in v1)
- Direct audio editing or conversion

## Discovery

```bash
# Get structured JSON capability manifest
python cli.py --agent-help

# Get human-readable help
python cli.py --help
python cli.py transcribe --help
python cli.py summarize --help
python cli.py pipeline --help
python cli.py tasks --help
```

## Commands

### 1. transcribe

Converts a video URL or local audio file into a text transcript.

**Minimum viable invocation:**
```bash
# From URL (Groq cloud — fastest)
python cli.py transcribe --url "https://youtu.be/VIDEO_ID" --groq-api-key "gsk-xxx"

# From local file
python cli.py transcribe --file /path/to/audio.mp3 --groq-api-key "gsk-xxx"

# Local Whisper without cloud transcription
python cli.py transcribe --url "https://youtu.be/VIDEO_ID" --provider local --local-backend whisper --local-model base
```

**Full control:**
```bash
python cli.py transcribe \
    --url "URL" \
    --provider groq \
    --groq-api-key "gsk-xxx" \
    --groq-model "whisper-large-v3-turbo" \
    --language "en" \
    --include-timecodes \
    --skip-subtitles \
    --output transcript.md \
    --format markdown \
    --quiet
```

**Provider decision:**
| Condition | Use |
|-----------|-----|
| Have Groq API key, want speed | `--provider groq` (default) |
| Need offline/private | `--provider local --local-backend whisper --local-model base` |
| Have self-hosted Whisper API | `--provider local_api --local-api-base-url http://... --local-api-model ...` |
| Need concurrent comparison or merge | `--source platform,groq,local_whisper,local_parakeet --merge-mode raw|system|ai` |

**Multi-source examples:**
```bash
# Keep separate outputs for manual review
python cli.py transcribe \
    --url "https://youtu.be/VIDEO_ID" \
    --source platform,groq,local_parakeet \
    --merge-mode raw \
    --groq-api-key "gsk-xxx"

# Deterministic merge with explicit primary source
python cli.py transcribe \
    --url "https://youtu.be/VIDEO_ID" \
    --source platform,groq,local_whisper \
    --merge-mode system \
    --merge-primary-source groq \
    --groq-api-key "gsk-xxx"

# Local Whisper + local Parakeet through the canonical multi-source path
python cli.py transcribe \
    --url "https://youtu.be/VIDEO_ID" \
    --provider local \
    --source local_whisper,local_parakeet \
    --merge-mode system \
    --merge-primary-source local_whisper \
    --dual-whisper-model-preset large-v3 \
    --dual-parakeet-model-preset nvidia/parakeet-tdt-0.6b-v3

# AI merge through an OpenAI-compatible endpoint
python cli.py transcribe \
    --url "https://youtu.be/VIDEO_ID" \
    --source platform,groq,local_parakeet \
    --merge-mode ai \
    --merge-base-url "https://api.openai.com/v1" \
    --merge-api-key "sk-xxx" \
    --merge-model "gpt-4o"
```

**Legacy dual-local examples:**
```bash
# Backward-compatible dual local mode
python cli.py transcribe \
    --url "https://youtu.be/VIDEO_ID" \
    --provider local \
    --dual-local \
    --dual-whisper-model-preset large-v3 \
    --dual-parakeet-model-preset nvidia/parakeet-tdt-0.6b-v3

# Backward-compatible dual local mode with AI merge
python cli.py transcribe \
    --url "https://youtu.be/VIDEO_ID" \
    --provider local \
    --dual-local \
    --merge-use-ai \
    --merge-base-url "https://api.openai.com/v1" \
    --merge-api-key "sk-xxx" \
    --merge-model "gpt-4o"
```

**Output (JSON to stdout):**
```json
{
  "task_id": "uuid",
  "status": "completed",
  "video_title": "string",
  "transcript": "full markdown transcript text",
  "detected_language": "en",
  "transcript_source": "groq_audio_url",
  "transcription_provider_used": "groq",
  "script_path": "/absolute/path/to/transcript.md"
}
```

### 2. summarize

Generates an AI summary from an existing transcript.

**From a prior task:**
```bash
python cli.py summarize --task-id "TASK_UUID" --openai-api-key "sk-xxx" --summary-language en
```

**From a file:**
```bash
python cli.py summarize --transcript-file transcript.md --openai-api-key "sk-xxx" --summary-language en
```

**With custom prompt and output:**
```bash
python cli.py summarize \
    --transcript-file transcript.md \
    --openai-api-key "sk-xxx" \
    --openai-base-url "https://custom-endpoint/v1" \
    --model "gpt-4o" \
    --summary-language en \
    --prompt "Focus on key technical decisions and action items" \
    --reasoning-effort high \
    --summary-output summary.md \
    --output-format markdown
```

**Output (JSON to stdout):**
```json
{
  "status": "completed",
  "summary": "full summary markdown text",
  "video_title": "string",
  "language": "en",
  "task_id": "uuid (only if --task-id was used)"
}
```

### 3. pipeline

Transcribe + summarize in a single invocation. Combines all flags from `transcribe` and `summarize` (except `--task-id`/`--transcript-file`, which are auto-set from the transcription result).

```bash
python cli.py pipeline \
    --url "https://youtu.be/VIDEO_ID" \
    --groq-api-key "gsk-xxx" \
    --openai-api-key "sk-xxx" \
    --summary-language en \
    --output-format markdown \
    --summary-output summary.md
```

**Output (JSON to stdout):**
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

### 4. tasks

Manage persisted task records (stored in `temp/tasks.json`).

```bash
# List all tasks (each object includes task_id)
python cli.py tasks --list

# Get a specific task
python cli.py tasks --get "TASK_UUID"

# Delete a task
python cli.py tasks --delete "TASK_UUID"
```

**Output for --list:**
```json
{
  "tasks": [
    {"task_id": "uuid", "status": "completed", "video_title": "...", ...},
    {"task_id": "uuid", "status": "completed", "video_title": "...", ...}
  ]
}
```

## All Flags Reference

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
| `--source` | CSV string | | | Multi-source IDs: `platform`, `groq`, `local_whisper`, `local_parakeet` |
| `--merge-mode` | enum | `system` | | Multi-source merge mode: `system`, `raw`, or `ai` |
| `--merge-primary-source` | string | | | Required for `system` merge when two or more sources are selected |
| `--merge-base-url` | string | | | OpenAI-compatible API base URL for AI merge |
| `--merge-api-key` | string | | | API key for AI merge |
| `--merge-model` | string | | | Model name for AI merge |
| `--merge-prompt` | string | | | Optional AI merge instructions |
| `--merge-reasoning-effort` | enum | | | `none`, `minimal`, `low`, `medium`, `high`, `xhigh` |
| `--merge-use-ai` | boolean | `false` | | Legacy dual-local flag: use AI merge instead of deterministic merge |
| `--dual-local` | boolean | `false` | | Legacy compatibility alias for `--source local_whisper,local_parakeet` with `--provider local` |
| `--dual-whisper-model-preset` | string | `base` | | Whisper preset used by local Whisper in dual/multi-source local flows |
| `--dual-whisper-model-id` | string | | | Custom Whisper model ID |
| `--dual-parakeet-model-preset` | string | | | Parakeet preset used by local Parakeet in dual/multi-source local flows |
| `--dual-parakeet-model-id` | string | | | Custom Parakeet model ID |
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

## API Key Sourcing

Keys can be provided via CLI flags or environment variables. **Flags take precedence.**

| Key | Flag | Env Var |
|-----|------|---------|
| Groq (transcription) | `--groq-api-key` | `GROQ_API_KEY` |
| OpenAI (summarization) | `--openai-api-key` | `OPENAI_API_KEY` |
| OpenAI base URL | `--openai-base-url` | `OPENAI_BASE_URL` |

A `.env` file in the project root is auto-loaded. Existing env vars are never overwritten.

## Output Modes

| Mode | Behavior |
|------|----------|
| Default | JSON to stdout, progress to stderr |
| `--pretty` | Human-readable to stdout, progress to stderr |
| `--quiet` | JSON to stdout, no progress on stderr |
| `--quiet --pretty` | Human-readable to stdout, no progress |
| `--output <path>` | Write content to file, confirmation to stderr |
| `--format json\|markdown\|txt` | Controls file output format (transcribe) |
| `--output-format markdown\|html\|txt` | Controls file output format (summarize) |

## Exit Codes

| Code | Meaning | Agent Action |
|------|---------|--------------|
| 0 | Success | Parse stdout JSON |
| 1 | Runtime error | Read `error` field from stdout JSON |
| 2 | Invalid arguments | Re-check flags, run `--help` |

## Error Recovery

**Error JSON format:**
```json
{"error": "descriptive error message", "exit_code": 1}
```

**Common errors and fixes:**

| Error | Cause | Fix |
|-------|-------|-----|
| `Either --url or --file is required` | No input source | Add `--url` or `--file` |
| `Groq API key is required` | Missing key for groq provider | Set `--groq-api-key` or `GROQ_API_KEY` |
| `OpenAI API key is required` | Missing key for summarization | Set `--openai-api-key` or `OPENAI_API_KEY` |
| `File not found: <path>` | Invalid `--file` or `--transcript-file` path | Verify file exists |
| `Task not found: <id>` | Invalid task ID | Run `tasks --list` to find valid IDs |
| `Local API base URL is required` | `--provider local_api` without URL | Add `--local-api-base-url` |
| `Unsupported transcription provider` | Invalid `--provider` value | Use `groq`, `local`, or `local_api` |
| `Select a primary source for system merge` | Multi-source `system` merge has two or more sources but no primary source | Add `--merge-primary-source <source_id>` or use `--merge-mode raw` / `--merge-mode ai` |

## Chained Workflow Patterns

### Pattern A: Transcribe, review, then summarize
```bash
# Step 1: Transcribe
RESULT=$(python cli.py transcribe --url "URL" --groq-api-key "KEY" --quiet)
TASK_ID=$(echo "$RESULT" | python -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

# Step 2: Inspect transcript
python cli.py tasks --get "$TASK_ID" --quiet

# Step 3: Summarize
python cli.py summarize --task-id "$TASK_ID" --openai-api-key "KEY" --quiet
```

### Pattern B: Batch transcribe multiple videos
```bash
for URL in "https://youtu.be/a" "https://youtu.be/b" "https://youtu.be/c"; do
    python cli.py transcribe --url "$URL" --groq-api-key "KEY" \
        --output "transcripts/$(echo $URL | md5sum | cut -c1-8).md" \
        --format markdown --quiet
done
```

### Pattern C: Summarize with different prompts
```bash
TASK_ID="existing-task-uuid"

# Technical summary
python cli.py summarize --task-id "$TASK_ID" --openai-api-key "KEY" \
    --prompt "Extract all technical details, tools, and architecture decisions" \
    --summary-output tech_summary.md --quiet

# Action items summary
python cli.py summarize --task-id "$TASK_ID" --openai-api-key "KEY" \
    --prompt "List all action items, deadlines, and assigned owners" \
    --summary-output actions.md --quiet
```

## Important Notes

- The CLI shares task state with the web UI via `temp/tasks.json`
- Transcript files are saved in the `temp/` directory
- The `--file` flag copies the file to `temp/` before processing (original is not modified)
- `pipeline` runs two separate `asyncio.run()` calls sequentially
- The browser UI uses Multi-Source Transcription as the only concurrent transcription path
- The old separate Dual Local UI was removed; select `local_whisper` and `local_parakeet` in Multi-Source instead
- `--dual-local` remains available for CLI/API backward compatibility, but new automation should prefer `--source local_whisper,local_parakeet`
- For `--merge-mode raw`, failed sources do not hide successful source artifacts; inspect the returned raw bundle and per-source files
- No web server needs to be running — the CLI imports backend modules directly
