"""Authenticated synthetic HTTP worker for ephemeral workflow replay tests."""
import hashlib
import hmac
import json
import math
import os
import platform
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

TOKEN = os.environ.get("WORKER_TOKEN", "")
INSTANCE = uuid4().hex
MAX_FILE = 2 * 1024 * 1024
MAX_STORE = 128 * 1024 * 1024


class Worker(BaseHTTPRequestHandler):
    files = {}

    def log_message(self, *args):
        pass

    def authorized(self):
        expected = "Bearer " + TOKEN
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            self.reply(401, b"Authentication required")
            return False
        return True

    def reply(self, status=200, body=b""):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.authorized():
            return
        if self.path == "/health":
            self.reply()
        elif self.path == "/identity":
            boot = Path("/proc/sys/kernel/random/boot_id")
            identity = {
                "instance": INSTANCE, "system": platform.system(),
                "kernel": platform.release(), "machine": platform.machine(),
                "python": platform.python_version(),
                "boot_id_sha256": hashlib.sha256(boot.read_bytes()).hexdigest() if boot.exists() else None,
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "github_repository": os.environ.get("GITHUB_REPOSITORY"),
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            }
            self.reply(body=json.dumps(identity).encode())
        elif self.path in self.files:
            self.reply(body=self.files[self.path])
        else:
            self.reply(404, b"Unknown file")

    def do_POST(self):
        if not self.authorized():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 8 * 1024 * 1024:
                raise ValueError("Request size")
            body = self.rfile.read(length)
            if self.path == "/reset":
                self.files.clear()
            elif self.path == "/run":
                job = json.loads(body)
                seconds = float(job["seconds"])
                if not math.isfinite(seconds) or not 0 <= seconds <= 10:
                    raise ValueError("Task duration")
                if not set(job["inputs"]).issubset(self.files):
                    self.reply(409, b"Missing task inputs")
                    return
                outputs = job["outputs"]
                if any(not isinstance(size, int) or not 0 <= size <= MAX_FILE
                       for size in outputs.values()):
                    raise ValueError("Output size")
                self.check_capacity(outputs)
                time.sleep(seconds)
                for name, size in outputs.items():
                    self.files[name] = b"x" * size
            elif self.path == "/probe" or self.path.startswith("/file/"):
                if length > MAX_FILE:
                    raise ValueError("File size")
                self.check_capacity({self.path: length})
                self.files[self.path] = body
            else:
                self.reply(404, b"Unknown operation")
                return
            self.reply()
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self.reply(400, b"Invalid test request")

    def check_capacity(self, replacements):
        total = sum(len(value) for key, value in self.files.items() if key not in replacements)
        if total + sum(replacements.values()) > MAX_STORE:
            raise ValueError("Test store capacity")


if __name__ == "__main__":
    if len(TOKEN) < 32:
        raise SystemExit("WORKER_TOKEN must contain at least 32 characters")
    ThreadingHTTPServer(("0.0.0.0", 8900), Worker).serve_forever()
