# AI Content Factory

Autonomous short-form video production pipeline for YouTube Shorts, designed to expand to TikTok and Instagram Reels.

## Architecture

| Directory | Role |
|-----------|------|
| `core/` | Production — agents, visuals, TTS, render, database |
| `publishers/` | Upload adapters — YouTube first, multi-platform later |
| `prompts/` | LLM system prompts (JSON-only outputs) |
| `config/` | Channel identity and production settings |

## Phase 1 roadmap

1. ✅ Project skeleton, cursor rules, agent prompts
2. ✅ Channel config and content package schema
3. ✅ Gemini agent pipeline (topic → master → reviewer)
4. ✅ Pexels + Pollinations image fetchers
5. ✅ edge-tts narration
6. ✅ FFmpeg 9:16 renderer
7. ✅ Thumbnail generator
8. ✅ SQLite topic tracking
9. ✅ YouTube publisher (OAuth)
10. End-to-end `main.py`
11. Task Scheduler documentation
12. Telegram notifications (optional)
13. n8n orchestration (Phase 2, optional)

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in API keys in `.env` as each step requires them. See `.env.example` for the list.

## Configuration

Edit `config/channel.yaml` to change niche, tone, and format **without modifying code**.

Current channel: **İlginç Tarih** (`ilginc-tarih`).

Verify config and prompt rendering:

```powershell
python scripts/verify_config.py
```

## Data models

| Module | Purpose |
|--------|---------|
| `core/config.py` | Load `channel.yaml`, render agent prompts |
| `core/schemas.py` | Topic, ContentPlan, ReviewResult, ContentPackage |
| `schemas/content_package.example.json` | Example final output after a successful run |

## Step 3 — Gemini agents

1. Open [Google AI Studio](https://aistudio.google.com/apikey) and create an API key.
2. Copy `.env.example` → `.env` and set `GEMINI_API_KEY`.
3. Install dependencies and run the pipeline:

```powershell
pip install -r requirements.txt
python scripts/run_agents.py
python scripts/run_agents.py --topic "Osmanlı'nın bilinmeyen savaşları"
```

Prompt-only check (no API call):

```powershell
python scripts/run_agents.py --dry-run --topic "Test konusu"
```

## Step 4 — Scene visuals (Pexels + Pollinations)

**Pollinations test (no API key):**

```powershell
python scripts/fetch_scenes.py --pollinations-only
```

**Full scene fetch (requires `PEXELS_API_KEY` in `.env` for stock scenes):**

```powershell
python scripts/fetch_scenes.py --topic "Osmanlı'nın bilinmeyen savaş taktiği"
```

## Step 5 — Narration (edge-tts)

Voice is configured in `config/channel.yaml` (`voice.voice`, default `tr-TR-AhmetNeural`).

**Quick test (no API keys):**

```powershell
python scripts/synthesize_voice.py --text "Osmanlı ordusu bu taktikle tarihe geçti."
```

**From agent pipeline:**

```powershell
python scripts/synthesize_voice.py --topic "Osmanlı'nın bilinmeyen savaş taktiği"
```

Output: `assets/voice.mp3` (duration shown if `ffprobe` is installed).

## Step 6 — FFmpeg render (9:16 Short)

Install FFmpeg first (includes `ffprobe`):

```powershell
winget install Gyan.FFmpeg
```

Restart the terminal, then verify:

```powershell
ffmpeg -version
```

If `ffmpeg` is still not recognized but winget says it is installed, restart Cursor/terminal or set `FFMPEG_PATH` / `FFPROBE_PATH` in `.env`. The app also auto-detects winget installs on Windows.

**Render using existing assets (fastest after Steps 4–5):**

```powershell
python scripts/render_video.py --topic "Osmanlı'nın bilinmeyen savaş taktiği" --reuse-assets
```

**Full pipeline (agents + images + voice + render):**

```powershell
python scripts/render_video.py --topic "Osmanlı'nın bilinmeyen savaş taktiği" --full
```

Output: `output/short.mp4`

## Step 7 — Thumbnail (1280x720)

YouTube custom thumbnails use **1280x720** (16:9). The generator uses the first scene image when available, then adds bold overlay text from the content plan.

**Quick test (no API keys):**

```powershell
python scripts/generate_thumbnail.py --base-image assets/scenes/scene_01.jpg --text "GIZLI TAKTIK"
```

**From agent plan + existing scenes:**

```powershell
python scripts/generate_thumbnail.py --topic "Osmanlı'nın bilinmeyen savaş taktiği" --reuse-assets
```

Output: `output/thumbnail.jpg`

## Step 8 — SQLite storage

Topic history and production runs are stored in `data/factory.db` (gitignored).

**Inspect database:**

```powershell
python scripts/manage_db.py
```

**Agent run with persistence (default):**

```powershell
python scripts/run_agents.py --topic "Osmanlı'nın bilinmeyen savaş taktiği"
```

Skip persistence:

```powershell
python scripts/run_agents.py --topic "Test konusu" --no-persist
```

The Topic Agent automatically receives previously used topics for the current niche from SQLite.

## Step 9 — YouTube upload (OAuth)

YouTube upload uses **OAuth 2.0** (not an API key). One-time Google Cloud setup:

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable **YouTube Data API v3** (APIs & Services → Library).
3. Configure **OAuth consent screen** (External, add your Google account as a test user).
4. Create **OAuth client ID** → Application type: **Desktop app**.
5. Download JSON → save as `credentials/client_secret.json` (gitignored).

Install upload dependencies:

```powershell
pip install -r requirements.txt
```

**First run — authorize channel (opens browser):**

```powershell
python scripts/upload_youtube.py --auth-only
```

Token is saved to `credentials/token.json` (gitignored). Re-auth only if you revoke access or delete the token.

**Dry-run (no upload, validates local files):**

```powershell
python scripts/upload_youtube.py --dry-run --video output/short.mp4 --thumbnail output/thumbnail.jpg --title "Test Short"
```

**Upload rendered Short + thumbnail:**

```powershell
python scripts/upload_youtube.py --video output/short.mp4 --thumbnail output/thumbnail.jpg --title "Osmanlı'nın Gizli Savaş Taktiği"
```

**Upload from content package JSON (uses SEO metadata + hashtags):**

```powershell
python scripts/upload_youtube.py --package schemas/content_package.example.json --video output/short.mp4 --thumbnail output/thumbnail.jpg
```

Default privacy is **`unlisted`** (`config/channel.yaml` → `youtube.privacy_status`). Override:

```powershell
python scripts/upload_youtube.py --video output/short.mp4 --privacy public
```

Modules: `publishers/base.py` (interface), `publishers/youtube.py` (OAuth + resumable upload + thumbnail).

## Workflow

The user commits step-by-step. Each phase adds one layer of the pipeline. Do not skip the Reviewer quality gate.

## License

TBD
