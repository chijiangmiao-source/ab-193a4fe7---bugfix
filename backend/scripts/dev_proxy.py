"""Minimal local stand-in for the nginx container used in production.

Serves the built frontend from ../frontend/dist and reverse-proxies
/api/* and /health to the backend -- exactly the routing declared in
frontend/nginx.conf.  Only used to exercise scripts/acceptance.py on a
machine without Docker; it is not part of the delivered images.
"""

import http.server
import os
import urllib.request
import sys

DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
BACKEND = "http://127.0.0.1:8000"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090

TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
         ".svg": "image/svg+xml", ".json": "application/json"}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _proxy(self):
        url = BACKEND + self.path
        body = None
        if self.command == "POST":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
        req = urllib.request.Request(url, data=body, method=self.command)
        if body:
            req.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                self.send_response(r.status)
                self.send_header("Content-Type", r.headers.get("Content-Type", "application/json"))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health" or self.path.startswith("/api/"):
            return self._proxy()
        path = self.path.split("?", 1)[0]
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(DIST, rel))
        if not full.startswith(os.path.abspath(DIST)) or not os.path.isfile(full):
            full = os.path.join(DIST, "index.html")
        with open(full, "rb") as f:
            data = f.read()
        ext = os.path.splitext(full)[1]
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(ext, "application/octet-stream"))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self._proxy()


if __name__ == "__main__":
    http.server.HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
