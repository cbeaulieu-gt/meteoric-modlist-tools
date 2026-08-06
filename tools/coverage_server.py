"""
Local server for the coverage view's click-to-ignore feature.

``generate_coverage.py --serve`` starts this server instead of writing a static
HTML file. It serves the coverage report at http://127.0.0.1:<port>/ with
interactive rows; clicking a mod row POSTs to /api/ignore, which updates the
per-target ignore file immediately. The report is re-rendered from the current
source/target (and, in base mode, base) JSON and ignore file on every GET, so a
mid-session re-export is reflected on refresh.

Bound to 127.0.0.1 only — it writes files and must not be exposed.
"""

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import coverage_ignore
from modlist_utils import load_modlist
from generate_coverage import (
    build_report,
    compute_summary,
    map_sections_to_majors,
    render_html,
)


def apply_ignore_change(ignore_path, name, ignored):
    """Add or remove a name in the ignore file. Pure dispatch over the store."""
    if ignored:
        coverage_ignore.add(ignore_path, name)
    else:
        coverage_ignore.remove(ignore_path, name)


def _render_current(source_path, target_path, min_confidence, ignore_path,
                    base_path=None):
    """Render the coverage HTML from the current files, in serve mode."""
    source_data = load_modlist(source_path)
    target_data = load_modlist(target_path)
    ignore = coverage_ignore.load_ignore(ignore_path)
    base_data = load_modlist(base_path) if base_path else None
    base_name = (
        os.path.splitext(os.path.basename(base_path))[0] if base_path else None
    )
    rows_by_section = build_report(
        source_data, target_data, min_confidence, ignore, base_data
    )
    summary = compute_summary(rows_by_section)
    section_majors = map_sections_to_majors(source_data)
    source_name = os.path.splitext(os.path.basename(source_path))[0]
    target_name = os.path.splitext(os.path.basename(target_path))[0]
    return render_html(
        rows_by_section, summary, source_name, target_name, section_majors,
        serve=True, base_name=base_name,
    )


def make_handler(source_path, target_path, min_confidence, ignore_path,
                 base_path=None):
    """Build a request handler class bound to these report parameters."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            try:
                body = _render_current(
                    source_path, target_path, min_confidence, ignore_path, base_path
                ).encode("utf-8")
            except Exception as exc:  # corrupt/locked list JSON, etc. — show it, don't drop the connection
                self.send_error(500, str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/api/ignore":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                name = payload["name"]
                ignored = bool(payload["ignored"])
            except (ValueError, KeyError, TypeError):
                self._json(400, {"ok": False, "error": "bad request"})
                return
            apply_ignore_change(ignore_path, name, ignored)
            self._json(200, {"ok": True})

        def _json(self, status, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _bind(port, handler, max_tries=20):
    """Bind to 127.0.0.1:port, incrementing on OSError up to max_tries (e.g. 8000-8019)."""
    last_err = None
    for p in range(port, port + max_tries):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), handler), p
        except OSError as e:
            last_err = e
    raise last_err


def serve(source_path, target_path, min_confidence, ignore_path, port=8000,
          open_browser=True, base_path=None):
    """Serve the coverage report with click-to-ignore until interrupted."""
    if not ignore_path:
        print(
            "Serve mode needs an ignore file location: pass -o <dir> or --ignore-file.",
            file=sys.stderr,
        )
        sys.exit(2)
    handler = make_handler(
        source_path, target_path, min_confidence, ignore_path, base_path
    )
    httpd, bound_port = _bind(port, handler)
    url = f"http://127.0.0.1:{bound_port}/"
    print(f"Coverage server running at {url}", file=sys.stderr)
    print(f"Ignore file: {ignore_path}", file=sys.stderr)
    print("Press Ctrl-C to stop.", file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.", file=sys.stderr)
    finally:
        httpd.server_close()
