import http.server
import pathlib
import sys


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        data = pathlib.Path("index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


http.server.ThreadingHTTPServer(
    ("127.0.0.1", int(sys.argv[1])), Handler
).serve_forever()
