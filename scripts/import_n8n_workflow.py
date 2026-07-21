"""Import or update factory workflows in local n8n via REST API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.env import get_env, load_dotenv, require_env  # noqa: E402

DEFAULT_WORKFLOW_FILE = ROOT / "n8n" / "workflow-factory-trigger.json"


def _api_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = require_env("N8N_API_URL").rstrip("/")
    api_key = require_env("N8N_API_KEY")
    url = f"{base_url}{path}"
    data = None
    headers = {
        "Accept": "application/json",
        "X-N8N-API-KEY": api_key,
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"n8n API {method} {path} failed ({exc.code}): {detail}") from exc


def _list_workflows() -> list[dict[str, Any]]:
    response = _api_request("GET", "/api/v1/workflows")
    return response.get("data", [])


def _find_workflow_id(name: str) -> str | None:
    for workflow in _list_workflows():
        if workflow.get("name") == name:
            return str(workflow["id"])
    return None


def _prepare_payload(source: dict[str, Any]) -> dict[str, Any]:
    trigger_key = get_env("TRIGGER_API_KEY")
    if not trigger_key:
        raise EnvironmentError(
            "Missing TRIGGER_API_KEY in .env. Set it before importing the workflow."
        )

    payload = {
        "name": source["name"],
        "nodes": source["nodes"],
        "connections": source["connections"],
        "settings": source.get("settings") or {"executionOrder": "v1"},
    }

    for node in payload["nodes"]:
        if node.get("name") != "Start Factory":
            continue
        headers = node.get("parameters", {}).get("headerParameters", {}).get("parameters", [])
        for header in headers:
            if header.get("name") == "X-Trigger-Key":
                header["value"] = trigger_key

    return payload


def import_workflow_file(workflow_file: Path, *, update: bool) -> dict[str, Any]:
    if not workflow_file.is_file():
        raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

    source = json.loads(workflow_file.read_text(encoding="utf-8"))
    workflow_name = source["name"]
    payload = _prepare_payload(source)
    existing_id = _find_workflow_id(workflow_name)

    if existing_id and update:
        result = _api_request("PUT", f"/api/v1/workflows/{existing_id}", payload=payload)
        action = "updated"
    elif existing_id:
        print(f"Workflow already exists (id={existing_id}). Use --update to refresh it.")
        return {"id": existing_id, "action": "skipped", "name": workflow_name}
    else:
        result = _api_request("POST", "/api/v1/workflows", payload=payload)
        action = "created"

    workflow_id = result.get("id") or result.get("data", {}).get("id")
    print(f"Workflow {action}: {workflow_name}")
    if workflow_id:
        print(f"Open: {require_env('N8N_API_URL').rstrip('/')}/workflow/{workflow_id}")
    return {"id": workflow_id, "action": action, "name": workflow_name}


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Import factory workflows into local n8n")
    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        help="Workflow JSON file (default: n8n/workflow-factory-trigger.json)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update existing workflows with the same name",
    )
    args = parser.parse_args()
    files = [Path(item) for item in args.files] if args.files else [DEFAULT_WORKFLOW_FILE]

    try:
        for workflow_file in files:
            import_workflow_file(workflow_file, update=args.update)
    except EnvironmentError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
