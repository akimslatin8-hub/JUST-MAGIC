#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
import mimetypes, os

ROOT = Path(__file__).resolve().parent

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/health", "/healthz"):
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        routes = {
            "/": "index.html",
            "/index.html": "index.html",
            "/admin": "admin.html",
            "/admin/": "admin.html",
            "/admin.html": "admin.html",
        }
        filename = routes.get(path)
        if filename is None and path.startswith("/assets/"):
            filename = path.lstrip("/")
        if filename is None:
            self.send_error(404, "Not found")
            return

        target = (ROOT / filename).resolve()
        if ROOT not in target.parents or not target.is_file():
            self.send_error(404, "Not found")
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"JUST MAGIC listening on 0.0.0.0:{port}; root={ROOT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
