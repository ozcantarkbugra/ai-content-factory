"""Generate .cursor/mcp.json for n8n instance-level MCP from .env values."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.env import get_env, load_dotenv, require_env  # noqa: E402

MCP_PATH = ROOT / ".cursor" / "mcp.json"
MCP_ENDPOINT = "/mcp-server/http"


def build_config() -> dict[str, object]:
    base_url = require_env("N8N_API_URL").rstrip("/")
    token = require_env("N8N_MCP_TOKEN")
    return {
        "mcpServers": {
            "n8n": {
                "url": f"{base_url}{MCP_ENDPOINT}",
                "headers": {
                    "Authorization": f"Bearer {token}",
                },
            }
        }
    }


def main() -> int:
    load_dotenv()
    try:
        config = build_config()
    except EnvironmentError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        print(
            "\nSet N8N_API_URL and N8N_MCP_TOKEN in .env first.\n"
            "MCP token: n8n → Settings → Instance-level MCP → Connection details → Access Token",
            file=sys.stderr,
        )
        return 1

    MCP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MCP_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MCP_PATH}")
    print("Restart Cursor completely so the n8n MCP server loads.")
    print("Then enable MCP access on workflows in n8n (Settings > Instance-level MCP).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
