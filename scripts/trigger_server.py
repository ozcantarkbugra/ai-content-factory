"""Minimal local HTTP trigger for n8n / external orchestrators (Step 13)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.env import get_env, load_dotenv  # noqa: E402

_run_lock = threading.Lock()
_pipeline_running = False


def _python_executable() -> str:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


def _build_main_command(payload: dict[str, Any]) -> list[str]:
    command = [_python_executable(), str(ROOT / "main.py")]
    if payload.get("no_upload"):
        command.append("--no-upload")
    if payload.get("skip_thumbnail_upload"):
        command.append("--skip-thumbnail-upload")
    if payload.get("no_notify"):
        command.append("--no-notify")
    topic = str(payload.get("topic", "")).strip()
    if topic:
        command.extend(["--topic", topic])
    angle = str(payload.get("angle", "")).strip()
    if angle:
        command.extend(["--angle", angle])
    privacy = str(payload.get("privacy", "")).strip().lower()
    if privacy in {"public", "unlisted", "private"}:
        command.extend(["--privacy", privacy])
    return command


def _run_pipeline(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    global _pipeline_running
    with _run_lock:
        if _pipeline_running:
            return 409, {"error": "pipeline already running"}
        _pipeline_running = True

    log_dir = ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "trigger_server_latest.log"

    def worker() -> None:
        global _pipeline_running
        command = _build_main_command(payload)
        try:
            with log_path.open("w", encoding="utf-8") as handle:
                handle.write("Command: " + " ".join(command) + "\n\n")
                handle.flush()
                process = subprocess.run(
                    command,
                    cwd=str(ROOT),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                handle.write(f"\nExit code: {process.returncode}\n")
        finally:
            with _run_lock:
                _pipeline_running = False

    threading.Thread(target=worker, name="factory-pipeline", daemon=True).start()
    return 202, {
        "status": "started",
        "log_file": str(log_path),
        "command": _build_main_command(payload),
    }


def _authorized(headers: BaseHTTPRequestHandler) -> bool:
    api_key = get_env("TRIGGER_API_KEY")
    if not api_key:
        return True
    provided = headers.headers.get("X-Trigger-Key", "").strip()
    return provided == api_key


class TriggerHandler(BaseHTTPRequestHandler):
    server_version = "AIContentFactoryTrigger/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            with _run_lock:
                running = _pipeline_running
            self._send_json(200, {"ok": True, "running": running})
            return
        if self.path == "/status":
            log_path = ROOT / "data" / "logs" / "trigger_server_latest.log"
            tail = ""
            if log_path.is_file():
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            with _run_lock:
                running = _pipeline_running
            self._send_json(
                200,
                {
                    "running": running,
                    "log_file": str(log_path),
                    "log_tail": tail,
                },
            )
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send_json(404, {"error": "not found"})
            return
        if not _authorized(self):
            self._send_json(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "JSON body must be an object"})
            return

        status, response = _run_pipeline(payload)
        self._send_json(status, response)


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Local HTTP trigger for n8n")
    parser.add_argument("--host", default=get_env("TRIGGER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(get_env("TRIGGER_PORT", "8765") or "8765"))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), TriggerHandler)
    print(f"Trigger server listening on http://{args.host}:{args.port}")
    print("POST /run  — start pipeline")
    print("GET  /health — health check")
    print("GET  /status — latest log tail")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping trigger server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
