from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import argparse
import json
import sys
import time
import webbrowser
from .runner import Store, MAX_INPUT, ROOT, dump

MAX_REQUEST = MAX_INPUT * 12 + 4096
class Server(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    def __init__(self, port, store, bind="127.0.0.1"):
        if bind not in ("127.0.0.1", "0.0.0.0"):
            raise ValueError("Bind must be 127.0.0.1 or 0.0.0.0")
        self.store = store
        super().__init__((bind, port), Handler)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, code, data, mime="application/json; charset=utf-8", filename=None):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(data)

    def reject_local_request(self, reason):
        self.reply(403, dump({"error": reason}))

        if self.command == "POST":
            try:
                remaining = int(self.headers.get("Content-Length", "0"))
                deadline = time.monotonic() + 1
                if 0 < remaining <= MAX_REQUEST:
                    while remaining:
                        budget = deadline - time.monotonic()
                        if budget <= 0:
                            break
                        self.connection.settimeout(budget)
                        chunk = self.rfile.read1(min(remaining, 65536))
                        if not chunk:
                            break
                        remaining -= len(chunk)
            except (ValueError, OSError):
                pass

    def route(self, method):
        try:
            port = self.server.server_port
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in allowed:
                return self.reject_local_request("Only the local server Host is accepted")
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + h for h in allowed}:
                return self.reject_local_request("Cross-origin requests are refused")
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self.reject_local_request("Cross-site requests are refused")
            parts = urlsplit(self.path)
            if parts.query or parts.fragment or "%" in parts.path or ".." in parts.path or "\\" in parts.path:
                raise ValueError("Invalid route")
            route = parts.path
            store = self.server.store
            static = {"/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"),
                      "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css"),
                      "/tour": ("tour.html", "text/html")}
            if method == "GET" and route in static:
                name, mime = static[route]
                return self.reply(200, (ROOT / "ui/static" / name).read_bytes(), mime + "; charset=utf-8")
            tour_images = {"01-open.jpg", "02-check.jpg", "03-export.jpg", "04-lean.jpg", "05-traces.jpg", "06-evidence.jpg"}
            if method == "GET" and route.startswith("/tour-images/") and route[len("/tour-images/"):] in tour_images:
                return self.reply(200, (ROOT / "docs/onboarding" / route[len("/tour-images/"):]).read_bytes(), "image/jpeg")
            if method == "GET" and route == "/api/health":
                return self.reply(200, dump({"status": "ready", "bind": self.server.server_address[0], "port": port}))
            if method == "GET" and route == "/api/examples":
                return self.reply(200, dump(store.examples()))
            body = None
            if method == "POST":
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("POST requires application/json")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST:
                    return self.reply(413, dump({"error": "Request size exceeded or Content-Length missing"}))
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(body, dict): raise ValueError("Expected a JSON object")
            if route == "/api/runs":
                value = store.create(body) if method == "POST" else store.history()
                return self.reply(201 if method == "POST" else 200, dump(value))
            bits = route.strip("/").split("/")
            if len(bits) >= 3 and bits[:2] == ["api", "runs"]:
                run_id = bits[2]
                if len(bits) == 3 and method == "GET":
                    manifest = store.refresh(run_id)
                    manifest["reproduce_commands"] = store.normalized([r.get("command", []) for r in manifest["stages"]], store.directory(run_id))
                    return self.reply(200, dump(manifest))
                if len(bits) == 4 and method == "POST" and bits[3] in ("check", "export", "verify", "trace", "controls"):
                    return self.reply(202, dump(store.start(run_id, bits[3])))
                if len(bits) == 4 and method == "GET" and bits[3] == "bundle":
                    return self.reply(200, store.bundle(run_id), "application/zip", run_id + ".zip")
                if len(bits) == 5 and method == "GET" and bits[3] in ("files", "download"):
                    path, row = store.artifact(run_id, bits[4])
                    return self.reply(200, path.read_bytes(), "text/plain; charset=utf-8",
                                      path.name if bits[3] == "download" else None)
            self.reply(404, dump({"error": "Unknown route"}))
        except FileNotFoundError as error:
            self.reply(404, dump({"error": str(error)}))
        except (ValueError, TypeError, UnicodeError, RecursionError) as error:
            self.reply(400, dump({"error": str(error)}))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            self.reply(500, dump({"error": type(error).__name__ + ": " + str(error)}))

    def do_GET(self):
        self.route("GET")
    def do_POST(self):
        self.route("POST")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Local port; 0 chooses a free port")
    parser.add_argument("--bind", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1",
                        help="0.0.0.0 is for a container with a host-local published port")
    parser.add_argument("--timeout", type=float, default=600, help="Per-command timeout in seconds")
    parser.add_argument("--open", action="store_true", help="Open the local URL in the default browser")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or args.timeout <= 0:
        parser.error("Port must be 0..65535 and timeout must be positive")
    try:
        store = Store(timeout=args.timeout)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    try:
        server = Server(args.port, store, args.bind)
    except OSError as error:
        store.close()
        print(f"Cannot bind {args.bind}:{args.port}: {error}. Use --port 0 or another free local port.", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"VAKE local UI: {url}\nStop with Ctrl+C. Jobs and evidence remain in reports/ui-runs/.", flush=True)
    if args.open: webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("Stopping UI and active tool processes.", flush=True)
    finally:
        server.server_close()
        store.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
