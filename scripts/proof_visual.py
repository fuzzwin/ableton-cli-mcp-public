"""Read-only, loopback-only display of actual Proof Loop command reports."""
import argparse
import json
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = None


def state():
    path = ROOT / ".runtime/visual.json"
    data = json.loads(path.read_text()) if path.exists() else {"phase": "waiting", "events": []}
    manifest = data.get("input_manifest")
    changed = []
    if manifest:
        for relative, expected in manifest.items():
            source = (ROOT / relative).resolve()
            try:
                actual = {"sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "mode": source.stat().st_mode & 0o777}
                if not source.is_relative_to(ROOT.resolve()) or actual != expected:
                    changed.append(relative)
            except OSError:
                changed.append(relative)
    if changed or (data.get("phase") == "checks complete" and not manifest):
        data.update(phase="Historical · source changed" if changed else "Freshness unavailable",
                    verification=None, validation=None, live_freshness={"state":"stale" if changed else "unavailable", "changed":changed})
    else:
        data["live_freshness"] = {"state": "current" if manifest else "pending", "changed": []}
    smoke = ROOT / "docs/PRODUCTION-SMOKE.json"
    if smoke.is_file():
        data["production"] = json.loads(smoke.read_text())
    workspace = WORKSPACE or ROOT / "production-workspace"
    if workspace.is_dir():
        from cli_anything.ableton.production.workspace import Workspace
        from cli_anything.ableton.production.progress import read_jobs
        data["production_jobs"] = read_jobs(Workspace(workspace),limit=8)["jobs"]
    else:
        data["production_jobs"] = []
    return data


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            body = json.dumps(state(), allow_nan=False).encode()
            kind = "application/json"
        elif self.path == "/":
            body = (ROOT / "docs/proof-visual.html").read_bytes()
            kind = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--workspace", type=Path, help="Production workspace whose local progress records should be displayed")
    args = parser.parse_args()
    WORKSPACE = args.workspace.resolve(strict=True) if args.workspace else None
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Proof Loop visual: http://127.0.0.1:%s" % server.server_port, flush=True)
    server.serve_forever()
