#!/usr/bin/env python3
"""Start/Stop for the menu page. Listens on 127.0.0.1:12781.

Start runs fpga.sh (overlay, server.py, safe SCPI). Stop ends server.py only.
"""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APPDIR = os.path.dirname(os.path.abspath(__file__))
HOST = "127.0.0.1"
PORT = 12781


def server_running() -> bool:
    try:
        out = subprocess.run(
            ["ps", "-eo", "args"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in out.stdout.splitlines():
        if "server.py --host 0.0.0.0 --port 8080" in line:
            return True
    return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path != "/status":
            self._send(404, {"error": "not found"})
            return
        self._send(200, {"ok": True, "server": server_running()})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/start":
            proc = subprocess.run(
                ["sh", os.path.join(APPDIR, "fpga.sh")],
                capture_output=True,
                text=True,
                timeout=90,
            )
            tail = (proc.stdout or "") + (proc.stderr or "")
            if not tail:
                try:
                    with open("/tmp/pitaya_delay_fpga.log", "r", encoding="utf-8", errors="replace") as handle:
                        tail = handle.read()[-2000:]
                except OSError:
                    tail = ""
            self._send(
                200 if proc.returncode == 0 else 500,
                {
                    "ok": proc.returncode == 0,
                    "error": None if proc.returncode == 0 else "fpga.sh failed",
                    "log": tail[-2000:],
                },
            )
            return
        if path == "/stop":
            subprocess.run(
                ["pkill", "-f", "server.py --host 0.0.0.0 --port 8080"],
                capture_output=True,
                timeout=5,
            )
            self._send(200, {"ok": True, "server": server_running()})
            return
        self._send(404, {"error": "not found"})


def main() -> None:
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
