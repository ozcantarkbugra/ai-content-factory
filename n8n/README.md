# n8n orchestration (Step 13)

n8n does **not** render videos or call Gemini. It only triggers the local Python factory.

## Architecture

```
n8n (schedule / manual / webhook)
  → HTTP POST http://host.docker.internal:8765/run
    → scripts/trigger_server.py
      → main.py (full pipeline + Telegram)
```

Windows Task Scheduler remains the primary scheduler for Phase 1. Use n8n when you want a visual workflow UI, manual runs, or extra orchestration later.

## Three different keys (do not mix them up)

| Variable | Where to get it | Used for |
|----------|-----------------|----------|
| `TRIGGER_API_KEY` | You choose it in `.env` | Auth for `trigger_server.py` (`X-Trigger-Key` header) |
| `N8N_API_KEY` | n8n → **Settings → n8n API** → Create API key | REST API: import/update workflows from scripts |
| `N8N_MCP_TOKEN` | n8n → **Settings → Instance-level MCP** → Connection details → Access Token | Cursor MCP: agent builds/runs workflows via chat |

The API key you created under **n8n API** is **not** the MCP token. MCP has its own token on the **Instance-level MCP** page.

## `.env` (for scripts and Cursor setup)

```env
TRIGGER_HOST=127.0.0.1
TRIGGER_PORT=8765
TRIGGER_API_KEY=your-long-random-secret

N8N_API_URL=http://localhost:5678
N8N_API_KEY=paste-from-settings-n8n-api
N8N_MCP_TOKEN=paste-from-instance-level-mcp-access-token
```

Never commit `.env`.

## Quick start

### 1. Trigger server (keep open)

```powershell
python scripts/trigger_server.py
```

### 2. n8n (Docker)

```powershell
docker compose up -d
```

Open http://localhost:5678 and complete first-time setup.

Enable MCP: **Settings → Instance-level MCP → Enable MCP access**.

### 3. Import workflow (REST API — no manual JSON import)

Paste your `N8N_API_KEY` into `.env`, then:

```powershell
python scripts/import_n8n_workflow.py
```

This uploads `n8n/workflow-factory-trigger.json` (manual trigger only) and injects `TRIGGER_API_KEY` into the **Start Factory** node automatically.

Run from **Manual Test → Test workflow**. Avoid **Execute step** on **Start Factory** before the manual trigger runs.

Optional daily schedule (only if Task Scheduler is disabled):

```powershell
python scripts/import_n8n_workflow.py --file n8n/workflow-factory-schedule.json
```

To refresh an existing workflow:

```powershell
python scripts/import_n8n_workflow.py --update
```

### 4. Cursor MCP (so the agent can manage n8n workflows)

1. In n8n: **Settings → Instance-level MCP → Connection details → Access Token** — copy the token once.
2. Paste it as `N8N_MCP_TOKEN` in `.env`.
3. Generate Cursor config:

```powershell
python scripts/setup_cursor_n8n_mcp.py
```

4. **Fully quit and restart Cursor** (MCP loads only at startup).
5. In n8n, enable the imported workflow for MCP: workflow menu → **Settings → Available in MCP** (or from Instance-level MCP page).

After restart, the Cursor agent can use n8n MCP tools to search, create, edit, and execute MCP-enabled workflows.

Manual template (if you prefer): copy `.cursor/mcp.json.example` → `.cursor/mcp.json` and fill the token.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | `{ "ok": true, "running": false }` |
| GET | `/status` | Latest log tail |
| POST | `/run` | Start pipeline in background |

Optional JSON body for `POST /run`:

```json
{
  "topic": "Osmanlı'nın bilinmeyen savaş taktiği",
  "no_upload": false,
  "privacy": "unlisted"
}
```

If `TRIGGER_API_KEY` is set, send header `X-Trigger-Key: your-secret`.

## Test without n8n UI

```powershell
curl -X POST http://127.0.0.1:8765/run -H "Content-Type: application/json" -H "X-Trigger-Key: YOUR_KEY" -d "{}"
```

Log: `data/logs/trigger_server_latest.log`

Telegram notifications still come from `main.py` when configured.

## Scheduler note

Do **not** enable both Windows Task Scheduler (10:00) and the n8n **Daily 10:00** cron unless you want two videos per day. Pick one primary scheduler.
