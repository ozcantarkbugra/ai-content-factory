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

1. Project skeleton, cursor rules, agent prompts
2. Channel config and content package schema
3. Gemini agent pipeline (topic → master → reviewer)
4. Pexels + Pollinations image fetchers
5. edge-tts narration
6. FFmpeg 9:16 renderer
7. Thumbnail generator
8. SQLite topic tracking
9. YouTube publisher (OAuth)
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

Edit `config/channel.yaml` to set your niche, tone, and format before running production.

## Workflow

The user commits step-by-step. Each phase adds one layer of the pipeline. Do not skip the Reviewer quality gate.

## License

TBD
