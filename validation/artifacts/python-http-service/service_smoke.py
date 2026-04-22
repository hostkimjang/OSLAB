from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._write_json({"ok": True, "service": "oslab-python-http-demo"})
            return
        if parsed.path == "/add":
            query = urllib.parse.parse_qs(parsed.query)
            left = int(query.get("left", ["0"])[0])
            right = int(query.get("right", ["0"])[0])
            self._write_json({"ok": True, "result": left + right})
            return
        self.send_error(404)

    def log_message(self, format, *args):  # noqa: A002 - inherited API name
        return

    def _write_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        health = fetch_json(f"http://127.0.0.1:{port}/health")
        added = fetch_json(f"http://127.0.0.1:{port}/add?left=20&right=22")
        if not health.get("ok"):
            raise RuntimeError("health check did not return ok=true")
        if added.get("result") != 42:
            raise RuntimeError(f"expected add result 42, got {added!r}")
        print("service smoke passed")
        print(f"port={port}")
        print(f"add_result={added['result']}")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
