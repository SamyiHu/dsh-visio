"""Serve the repo statically AND expose the real Visio bridge over HTTP.

This lets tests/interactive.html drive the *real* client.js against the *real*
engine in a browser, with no Node in the loop (the Windows sandbox refuses to
spawn python from node).

    python tests/serve_engine.py 8933
"""
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'engine'))
import visio_bridge as vb  # noqa: E402

LOCK = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, *args):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('cache-control', 'no-store')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # The panel resolves its route against document.baseURI, so the harness has
        # to live at the root path ('/_harness.html') for the real fetch to work.
        if self.path.split('?')[0] == '/_harness.html':
            with open(os.path.join(ROOT, 'tests', 'interactive.html'), 'rb') as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header('content-type', 'text/html; charset=utf-8')
            self.send_header('cache-control', 'no-store')
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split('?')[0] == '/dsh-visio/config':
            self._json({'ok': True, 'defaultFolder': os.path.join(ROOT, 'tests', 'fixtures'),
                        'folderOk': True, 'python': 'in-process', 'pythonOk': True,
                        'engine': 'visio_bridge/1.0.0'})
            return
        return super().do_GET()

    def do_POST(self):
        if self.path.split('?')[0] != '/dsh-visio/op':
            self.send_error(404)
            return
        length = int(self.headers.get('content-length') or 0)
        try:
            request = json.loads(self.rfile.read(length) or b'{}')
        except ValueError:
            self._json({'ok': False, 'error': 'request body must be JSON'}, 400)
            return
        with LOCK:
            try:
                result = vb.handle(request)
            except Exception as exc:  # noqa: BLE001 - mirror the bridge's error shape
                self._json({'ok': False, 'error': '%s: %s' % (type(exc).__name__, exc)}, 400)
                return
        self._json(result, 200 if result.get('ok') else 400)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8933
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print('serving %s on http://127.0.0.1:%d' % (ROOT, port), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()