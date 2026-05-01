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
- No web server needs to be running — the CLI imports backend modules directly
