# Unified Settings & Credential Management

## Problem

Currently, the project has two independent settings/credential channels that don't talk to each other:

| | **GUI (browser)** | **CLI** |
|---|---|---|
| **Credential source** | User types into input fields; saved in browser `localStorage` (`vt_settings`) | `--groq-api-key` / `--openai-api-key` CLI flags, env vars as fallback |
| **Settings persistence** | `localStorage` only (browser-side) | None (flags each invocation) |
| **Shared state** | `.env` file is read by backend on startup for server-side defaults, but GUI inputs override per-request | CLI reads `.env` via `_load_env()` on its own |

**Pain points:**
1. Passing `--groq-api-key "$GROQ_API_KEY"` on every CLI invocation is tedious and insecure (shell history exposure).
2. A user who configures settings in the GUI has to re-enter the same credentials for CLI — there is no shared settings store.

---

## Intended User Workflow

```
1. User starts the server (python start.py)
2. Browser opens → user enters all credentials & settings in the GUI
3. Settings are saved to settings.json on disk
4. From this point, both GUI and CLI read from the same settings.json
   — no need to pass credentials again
```

This is the primary workflow. Power users can still override via environment variables or `.env` for CI/scripting scenarios.

---

## Solution: Shared `settings.json`

A single JSON file at the project root (`D:\Projects\AI-Video-Transcriber\settings.json`) serves as the canonical source of truth for both GUI and CLI.

### Credential priority chain (highest → lowest)

```
Environment variables (GROQ_API_KEY, OPENAI_API_KEY, etc.)
  → settings.json (shared file, written by GUI, readable by CLI)
    → Hardcoded defaults
```

> [!IMPORTANT]
> **Breaking change:** Three CLI flags are removed: `--groq-api-key`, `--openai-api-key`, `--openai-base-url`. Users must set credentials via the GUI settings panel (recommended), environment variables, or `.env` file. Existing scripts using these flags will need to be updated.

### Security

`settings.json` stores credentials in plaintext — same security level as the existing `.env` file. For a local desktop tool this is the industry-standard approach (VS Code, Docker, AWS CLI all do it). The file is `.gitignore`'d to prevent accidental commits.

---

## Proposed Changes

### Settings Module

#### [NEW] [settings.py](file:///D:/Projects/AI-Video-Transcriber/backend/settings.py)

A shared module imported by both `cli.py` and `backend/main.py`:

```python
SETTINGS_FILE = PROJECT_ROOT / "settings.json"

DEFAULT_SETTINGS = {
    "groq_api_key": "",
    "openai_api_key": "",
    "openai_base_url": "https://api.openai.com/v1",
    "groq_model": "whisper-large-v3-turbo",
    "groq_language": "",
    "groq_prompt": "",
    "transcription_provider": "groq",
    "try_subtitles_first": True,
    "use_local_fallback": False,
    "local_backend": "whisper",
    "local_model_preset": "base",
    "local_model_id": "",
    "local_language": "",
    "local_api_base_url": "",
    "local_api_key": "",
    "local_api_model": "",
    "local_api_language": "",
    "local_api_prompt": "",
    "include_timecodes": False,
    "summary_language": "en",
    "summary_model": "",
    "summary_format": "markdown",
    "summary_prompt": "",
    "reasoning_effort": "",
}
```

**Functions:**
- **`load_settings() → dict`** — Read `settings.json`, merge with defaults for missing keys. Returns full dict.
- **`save_settings(data: dict)`** — Merge with existing settings, write atomically (write to `.tmp` + rename).
- **`get_credential(env_var: str, settings_key: str) → str`** — Returns env var value if set, otherwise `settings.json` value, otherwise empty string.
- **`mask_credential(value: str) → str`** — Returns masked version like `"gsk_...xHsK"` for display (first 4 + last 4 chars).

---

### Backend API

#### [MODIFY] [main.py](file:///D:/Projects/AI-Video-Transcriber/backend/main.py)

**New endpoints:**

1. **`GET /api/settings`** — Returns current settings with credentials masked. Used by GUI on page load to populate form fields.
2. **`POST /api/settings`** — Accepts JSON body, merges with existing settings, writes `settings.json`. Returns saved settings (masked credentials).

**Modified endpoints:**

3. **`POST /api/process-video`** — When `groq_api_key` is empty/missing in form data, fall back to `get_credential("GROQ_API_KEY", "groq_api_key")` instead of proceeding with empty key.
4. **`POST /api/summarize-transcript`** — When `api_key` is empty/missing in form data, fall back to `get_credential("OPENAI_API_KEY", "openai_api_key")`. Same for `model_base_url` → fall back to settings `openai_base_url`.

---

### CLI

#### [MODIFY] [cli.py](file:///D:/Projects/AI-Video-Transcriber/cli.py)

**Removed flags** (from `transcribe`, `summarize`, `pipeline` subcommands):
- `--groq-api-key`
- `--openai-api-key`
- `--openai-base-url`

**New `settings` subcommand:**
```bash
# Show current settings (credentials masked)
python cli.py settings --show

# Set a single value
python cli.py settings --set groq_api_key=gsk_xxx
python cli.py settings --set openai_base_url=https://api.openai.com/v1

# Securely set credentials (prompted, no echo)
python cli.py settings --set-groq-key
python cli.py settings --set-openai-key
```

**Credential resolution changes:**
- `_run_transcribe()`: Replace `_resolve_api_key(args.groq_api_key, "GROQ_API_KEY")` with `get_credential("GROQ_API_KEY", "groq_api_key")`. If empty and provider is `groq`, exit with:
  ```
  Error: Groq API key is required. Set it via:
    • Environment variable: GROQ_API_KEY
    • GUI settings panel (start the server first)
    • CLI: python cli.py settings --set-groq-key
  ```
- `_run_summarize()`: Same pattern for OpenAI key.

**AGENT_MANIFEST update:**
- Remove `--groq-api-key`, `--openai-api-key`, `--openai-base-url` from flag definitions
- Add `settings` command definition
- Update `env_vars` list

---

### GUI (Frontend)

#### [MODIFY] [app.js](file:///D:/Projects/AI-Video-Transcriber/static/app.js)

**On page load (`_loadSettings`):**
1. First, restore UI-only prefs from `localStorage` (language, panel state, save formats)
2. Then, fetch `GET /api/settings` to populate credential and config fields (groq key, openai key, base URL, provider, etc.)
3. Server-side settings take precedence over `localStorage` for credential/config fields — this ensures CLI-set values appear in the GUI

**On settings change (`_saveSettings`):**
1. Continue saving to `localStorage` for UI-only prefs
2. Additionally, debounced `POST /api/settings` to persist credential and config fields to `settings.json`
3. Debounce at ~500ms to avoid excessive writes while the user is typing

**Per-request credential sending:**
- Still send credentials in form data when submitting requests (process-video, summarize-transcript) — but the backend will now also have its own fallback to `settings.json`, so even if the GUI sends empty values, the backend resolves them

> [!NOTE]
> `localStorage` continues to store UI-only preferences: UI language, settings panel open/closed state, save format selections, active tab. These don't belong in `settings.json` since they're per-browser preferences.

---

### Documentation & Config

#### [MODIFY] [README.md](file:///D:/Projects/AI-Video-Transcriber/README.md)
- Remove `--groq-api-key` / `--openai-api-key` / `--openai-base-url` from all CLI examples
- Add section about `settings.json` and the `cli.py settings` command
- Document the intended workflow (start server → configure in GUI → use CLI)

#### [MODIFY] [SKILL.md](file:///D:/Projects/AI-Video-Transcriber/ai-video-transcriber/SKILL.md)
- Update all CLI examples to remove credential flags
- Document credential resolution priority chain
- Document `settings` subcommand

#### [MODIFY] [.env.example](file:///D:/Projects/AI-Video-Transcriber/.env.example)
- Add `GROQ_API_KEY=your_groq_api_key_here` placeholder
- Add comment explaining that `settings.json` is the recommended alternative

#### [MODIFY] [.gitignore](file:///D:/Projects/AI-Video-Transcriber/.gitignore)
- Add `settings.json`

---

### Tests

#### [MODIFY] [test_cli.py](file:///D:/Projects/AI-Video-Transcriber/tests/test_cli.py)
- Remove `test_pipeline_has_summarize_config_flags` test (references `--openai-api-key`)
- Update parser tests that reference removed flags
- Add tests for `settings` subcommand (`--show`, `--set`)
- Add tests verifying missing credentials produce clear error messages

#### [NEW] [test_settings.py](file:///D:/Projects/AI-Video-Transcriber/tests/test_settings.py)
- `load_settings()` / `save_settings()` round-trip
- `get_credential()` priority: env var > settings.json > empty
- Default schema applied for missing keys
- Atomic write: concurrent reads don't see partial writes
- `mask_credential()` output format

---

## Verification Plan

### Automated Tests
```bash
cd D:\Projects\AI-Video-Transcriber
python -m pytest tests/test_settings.py tests/test_cli.py -v
```

### Manual Verification — Primary Workflow
1. Start server (`python start.py`)
2. Open browser, enter Groq + OpenAI credentials in settings panel
3. Confirm `settings.json` appears at project root with correct values
4. Run `python cli.py settings --show` — verify credentials are shown (masked)
5. Run `python cli.py transcribe --url "https://youtu.be/..." --provider groq` — verify it uses saved Groq key, no flags needed
6. Run `python cli.py summarize --task-id "..." --summary-language en` — verify it uses saved OpenAI key

### Manual Verification — Edge Cases
7. **Env override**: Set `GROQ_API_KEY` env var → verify it takes precedence over `settings.json` in both CLI and backend
8. **Missing credentials**: Delete `settings.json`, unset env vars → run CLI transcribe → verify clear error message with remediation steps
9. **CLI → GUI sync**: Run `python cli.py settings --set-groq-key` → enter key → open browser → verify field is pre-populated from server
10. **No server running**: Run CLI with `settings.json` present → verify it works standalone without the server
