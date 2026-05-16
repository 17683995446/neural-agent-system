"""CPA App Server: Serves frontend static files + proxies API to backend"""
import os
import json
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
API_BASE = "http://127.0.0.1:9000"
PORT = 3001


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIST_DIR, **kw)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy_api()
        fp = self.path.split("?")[0].split("#")[0]
        if fp == "/":
            fp = "/index.html"
        local_path = os.path.normpath(os.path.join(DIST_DIR, fp.lstrip("/")))
        if os.path.isfile(local_path):
            self.path = fp
            return super().do_GET()
        self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._proxy_api()

    def do_PUT(self):
        if self.path.startswith("/api/"):
            return self._proxy_api()

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")

    def _proxy_api(self):
        try:
            url = API_BASE + self.path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else None
            hdrs = {}
            for k in ["Authorization", "Content-Type", "Accept"]:
                v = self.headers.get(k)
                if v:
                    hdrs[k] = v
            req = urllib.request.Request(url, data=body, headers=hdrs, method=self.command)
            resp = urllib.request.urlopen(req, timeout=120)
            self.send_response(resp.status)
            ct = resp.headers.get("Content-Type", "application/json")
            self.send_header("Content-Type", ct)
            self._cors_headers()
            self.end_headers()
            data = resp.read()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"detail": str(e)}).encode())

    def log_message(self, fmt, *args):
        if "/api/" in str(args):
            print(f"[API] {args[0]}")


if __name__ == "__main__":
    os.chdir(DIST_DIR)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"")
    print(f"  ╔══════════════════════════════════════════╗")
    print(f"  ║   AI CPA 智能备考网站已启动              ║")
    print(f"  ╠══════════════════════════════════════════╣")
    print(f"  ║   前端: http://localhost:{PORT}            ║")
    print(f"  ║   后端: http://localhost:9000/docs        ║")
    print(f"  ║   测试账号: 15800158000 / Test1234       ║")
    print(f"  ╚══════════════════════════════════════════╝")
    print(f"")
    server.serve_forever()
