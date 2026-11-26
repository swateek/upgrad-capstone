"""Answer GET / with JSON: can this Space open TCP connections to the course endpoints?

Only TCP connects (no TLS, no keys): the question is whether Hugging Face lets a Space reach
non-standard ports. huggingface.co:443 is the control.
"""

import json
import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

TARGETS = [
    ("chat endpoint", "103.42.50.41", 1033),
    ("embeddings endpoint", "103.42.50.41", 1035),
    ("control: huggingface.co", "huggingface.co", 443),
]


def check(host: str, port: int) -> dict:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=8):
            return {"ok": True, "ms": round((time.perf_counter() - t0) * 1000)}
    except OSError as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(
            {f"{name} ({host}:{port})": check(host, port) for name, host, port in TARGETS},
            indent=1,
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


HTTPServer(("0.0.0.0", 7860), Handler).serve_forever()
