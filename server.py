#!/usr/bin/env python3
"""Web UI server - stdlib http.server only.

Run: python3 server.py [--port 8097] [--host 127.0.0.1]
Serves / from index.html (single-file UI) and /api/check as JSON.
"""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from scanner.core import is_valid_address, scan_address

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(HERE, "index.html")

FALLBACK_HTML = b"<!DOCTYPE html><html><body><h1>Robinhood Scanner</h1><p>index.html missing</p></body></html>"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Keep logs short
        import sys
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            try:
                with open(INDEX_PATH, "rb") as f:
                    body = f.read()
            except Exception:
                body = FALLBACK_HTML
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/check":
            qs = parse_qs(parsed.query)
            address = (qs.get("address") or [""])[0]
            chain = (qs.get("chain") or ["robinhood"])[0]
            if not is_valid_address(address):
                self._send_json(400, {"verdict": "UNKNOWN", "error": "invalid_address", "message": "expected 0x + 40 hex chars", "address": address})
                return
            try:
                report = scan_address(address, chain_key=chain)
            except Exception as e:
                self._send_json(200, {"verdict": "UNKNOWN", "error": "scan_failed", "message": f"scan failed at transport level: {e} - contract was not checked", "address": address})
                return
            self._send_json(200, report)
            return
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "service": "robinhood-scanner"})
            return
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"not found")

    def do_POST(self):
        # Support POST /api/check with JSON body {address, chain}
        parsed = urlparse(self.path)
        if parsed.path != "/api/check":
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except Exception:
            self._send_json(400, {"verdict": "UNKNOWN", "error": "invalid_json"}); return
        address = data.get("address", "")
        chain = data.get("chain", "robinhood")
        if not is_valid_address(address):
            self._send_json(400, {"verdict": "UNKNOWN", "error": "invalid_address", "address": address}); return
        report = scan_address(address, chain_key=chain)
        self._send_json(200, report)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8097)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Robinhood Scanner listening on http://{args.host}:{args.port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
