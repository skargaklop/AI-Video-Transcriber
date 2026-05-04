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
- Generate an AI summary of a transcript
- Do both in a single step (pipeline)
- Manage previously created transcription tasks
- View or configure shared settings and credentials

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
python cli.py settings --help
```

## Credential Resolution

Credentials are resolved in priority order (highest → lowest):

1. **Environment variables** (`GROQ_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`)
2. **`settings.json`** (shared file, written by GUI and CLI)
3. Hardcoded defaults

**Recommended workflow:**
```
1. Start the server (python start.py)
2. Browser opens → enter all credentials & settings in the GUI
3. Settings are saved to settings.json on disk
4. From this point, both GUI and CLI read from the same settings.json
```

**Alternative — set credentials via CLI:**
```bash
python cli.py settings --set-groq-key
python cli.py settings --set-openai-key
```

A `.env` file in the project root is auto-loaded. Existing env vars are never overwritten.

## Commands

### 1. transcribe

Converts a video URL or local audio file into a text transcript.

**Minimum viable invocation:**
```bash
# From URL (Groq cloud — fastest)
python cli.py transcribe --url "https://youtu.be/VIDEO_ID"

# From local file
python cli.py transcribe --file /path/to/audio.mp3
```

**Full control:**
```bash
python cli.py transcribe \
    --url "URL" \
    --provider groq \
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
python cli.py summarize --task-id "TASK_UUID" --summary-language en
```

**From a file:**
```bash
python cli.py summarize --transcript-file transcript.md --summary-language en
```

**With custom prompt and output:**
```bash
python cli.py summarize \
    --transcript-file transcript.md \
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

### 5. settings

View and manage shared settings (`settings.json`).

```bash
# Show current settings (credentials masked)
python cli.py settings --show

# Set a single value
python cli.py settings --set groq_model=whisper-large-v3
python cli.py settings --set openai_base_url=https://api.openai.com/v1

# Securely set credentials (prompted, no echo)
python cli.py settings --set-groq-key
python cli.py settings --set-openai-key
```

## All Flags Reference

### transcribe / pipeline (transcription flags)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--url` | string | | Video URL (YouTube, etc.) |
| `--file` | string | | Local audio/video file path |
| `--provider` | enum | `groq` | `groq`, `local`, or `local_api` |
| `--groq-model` | string | `whisper-large-v3-turbo` | Groq model name |
| `--language` | string | `auto` | Language code or `auto` |
| `--include-timecodes` | boolean | `false` | Keep timecodes in transcript |
| `--skip-subtitles` | boolean | `false` | Skip YouTube subtitle extraction |
| `--local-backend` | enum | `whisper` | `whisper` or `parakeet` |
| `--local-model` | string | `base` | Local model preset or ID |
| `--local-api-base-url` | string | | Local API endpoint URL (for `local_api`) |
| `--local-api-key` | string | | Local API key (for `local_api`) |
| `--local-api-model` | string | | Local API model name (for `local_api`) |
| `--local-api-language` | string | | Local API language code (for `local_api`) |
| `--local-api-prompt` | string | | Local API prompt (for `local_api`) |
| `--output` | string | | Write output to file path |
| `--format` | enum | `json` | `json`, `markdown`, or `txt` |

### summarize (source flags — not available in pipeline)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--task-id` | string | | Task ID from prior transcribe run |
| `--transcript-file` | string | | Path to transcript text file |

### summarize / pipeline (summary config flags)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--model` | string | `gpt-4o` | Model name |
| `--summary-language` | string | `en` | Summary language code |
| `--output-format` | enum | `markdown` | `markdown`, `html`, or `txt` |
| `--summary-output` | string | | Write summary to file path |
| `--prompt` | string | | Custom summary instructions |
| `--reasoning-effort` | enum | | `none`, `minimal`, `low`, `medium`, `high`, `xhigh` |

### tasks

| Flag | Type | Description |
|------|------|-------------|
| `--list` | boolean | List all tasks |
| `--get` | string | Get task by ID |
| `--delete` | string | Delete task by ID |

### settings

| Flag | Type | Description |
|------|------|-------------|
| `--show` | boolean | Show current settings (credentials masked) |
| `--set KEY=VALUE` | string | Set a key=value pair |
| `--set-groq-key` | boolean | Prompt for Groq API key (no echo) |
| `--set-openai-key` | boolean | Prompt for OpenAI API key (no echo) |

### Global flags

| Flag | Type | Description |
|------|------|-------------|
| `--pretty` | boolean | Human-readable output instead of JSON |
| `--quiet` | boolean | Suppress progress messages on stderr |
| `--agent-help` | boolean | Print JSON capability manifest and exit |

## API Key Sourcing

Credentials are resolved automatically — no need to pass keys on every invocation.

**Priority (highest → lowest):**
1. Environment variables: `GROQ_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`
2. `settings.json` (shared, written by GUI or `cli.py settings`)
3. `.env` file (auto-loaded from project root)

**Recommended setup:**
```bash
# Option A: Via CLI
python cli.py settings --set-groq-key
python cli.py settings --set-openai-key

# Option B: Via GUI (start server, open browser, enter keys in settings panel)

# Option C: Via environment variables or .env file
```

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
| `Groq API key is required` | Missing key for groq provider | Set via env var, GUI, or `settings --set-groq-key` |
| `OpenAI API key is required` | Missing key for summarization | Set via env var, GUI, or `settings --set-openai-key` |
| `File not found: <path>` | Invalid `--file` or `--transcript-file` path | Verify file exists |
| `Task not found: <id>` | Invalid task ID | Run `tasks --list` to find valid IDs |
| `Local API base URL is required` | `--provider local_api` without URL | Add `--local-api-base-url` |
| `Unsupported transcription provider` | Invalid `--provider` value | Use `groq`, `local`, or `local_api` |

## Chained Workflow Patterns

### Pattern A: Transcribe, review, then summarize
```bash
# Step 1: Transcribe
RESULT=$(python cli.py transcribe --url "URL" --quiet)
TASK_ID=$(echo "$RESULT" | python -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

# Step 2: Inspect transcript
python cli.py tasks --get "$TASK_ID" --quiet

# Step 3: Summarize
python cli.py summarize --task-id "$TASK_ID" --quiet
```

### Pattern B: Batch transcribe multiple videos
```bash
for URL in "https://youtu.be/a" "https://youtu.be/b" "https://youtu.be/c"; do
    python cli.py transcribe --url "$URL" \
        --output "transcripts/$(echo $URL | md5sum | cut -c1-8).md" \
        --format markdown --quiet
done
```

### Pattern C: Summarize with different prompts
```bash
TASK_ID="existing-task-uuid"

# Technical summary
python cli.py summarize --task-id "$TASK_ID" \
    --prompt "Extract all technical details, tools, and architecture decisions" \
    --summary-output tech_summary.md --quiet

# Action items summary
python cli.py summarize --task-id "$TASK_ID" \
    --prompt "List all action items, deadlines, and assigned owners" \
    --summary-output actions.md --quiet
```

## Important Notes

- The CLI shares task state with the web UI via `temp/tasks.json`
- The CLI shares credentials and settings with the GUI via `settings.json`
- Transcript files are saved in the `temp/` directory
- The `--file` flag copies the file to `temp/` before processing (original is not modified)
- `pipeline` runs two separate `asyncio.run()` calls sequentially
- No web server needs to be running — the CLI imports backend modules directly
