"""Local web server for mtgsim, standard library only.

    python3 -m web                  # then open http://127.0.0.1:8000
    python3 -m web --port 8080 --jobs 4

GET  /                 the page
GET  /api/tiers        tiers and their decks
POST /api/check        {"deck": text}                       -> card counts, unknown and partial cards
POST /api/run          {"deck", "name", "ladder", "tiers", "games", "full", "seed", "grade"} -> {"id"}
GET  /api/runs/<id>    progress and results so far
GET  /leaderboard      every tested deck ranked by MMR (JSON at /api/leaderboard)
GET  /leaderboard/{history,ladder,assess,run}/<name>   one deck's latest results
"""
from __future__ import annotations

import argparse
import json
import re
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import leaderboard, sim

try:
    from mtgsim.ladder_report import render_page as ladder_page
except ImportError:
    ladder_page = None

STATIC = Path(__file__).parent / "static"
MAX_BODY = 1 << 20


def validate_body(body: dict, *, run: bool = False) -> None:
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    if not isinstance(body.get("deck", ""), str):
        raise ValueError("deck must be text")
    if not run:
        return
    if not isinstance(body.get("name", ""), str):
        raise ValueError("name must be text")
    tiers = body.get("tiers")
    if tiers is not None and (not isinstance(tiers, list) or
                              any(not isinstance(t, str) for t in tiers)):
        raise ValueError("tiers must be a list of rank names")
    for key in ("ladder", "full", "grade"):
        if key in body and not isinstance(body[key], bool):
            raise ValueError(f"{key} must be a boolean")
    for key in ("games", "seed"):
        if key not in body or (key == "seed" and body[key] in (None, "")):
            continue
        value = body[key]
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError(f"{key} must be an integer")
        try:
            int(value)
        except ValueError:
            raise ValueError(f"{key} must be an integer") from None


class App:
    def __init__(self, jobs: int | None = None, offline: bool = False, results: Path = leaderboard.RESULTS,
                 history_path=None):
        self.offline = offline
        self.results = Path(results)
        self.history_path = history_path  # None: mtgsim.history's default store
        self.pool = sim.make_pool(jobs)
        self.runs: dict[str, dict] = {}
        self.lock = threading.Lock()  # one run at a time; they share the pool anyway

    def start(self, body: dict) -> str:
        validate_body(body, run=True)
        text = body.get("deck", "")
        check = sim.check_deck(text, offline=self.offline)
        if check.get("error"):
            raise ValueError(check["error"])
        run = sim.make_run(body.get("name", "").strip(), text, body.get("tiers"), bool(body.get("ladder")),
                           int(body.get("games", 100)), bool(body.get("full")),
                           None if body.get("seed") in (None, "") else int(body["seed"]),
                           bool(body.get("grade", True)))
        run.history_path = self.history_path
        rid = uuid.uuid4().hex[:12]
        entry = {"run": run, "status": "queued", "error": None, "check": check}
        self.runs[rid] = entry
        threading.Thread(target=self._execute, args=(entry,), daemon=True).start()
        return rid

    def _execute(self, entry):
        with self.lock:
            entry["status"] = "running"
            try:
                entry["run"].execute(self.pool)
                entry["status"] = "done"
                entry["finished"] = time.time()
            except Exception as e:  # report to the page rather than dying silently
                traceback.print_exc()
                entry["status"], entry["error"] = "error", f"{type(e).__name__}: {e}"

    def status(self, rid: str) -> dict | None:
        entry = self.runs.get(rid)
        if not entry:
            return None
        return {"status": entry["status"], "error": entry["error"], "partial": entry["check"]["partial"],
                **entry["run"].snapshot()}


    def ladder_data(self, rid: str) -> dict | None:
        entry = self.runs.get(rid)
        tracker = entry and entry["status"] == "done" and entry["run"].tracker
        return tracker.to_dict() if tracker else None

    def leaderboard(self) -> list[dict]:
        web_runs = []
        for rid, entry in list(self.runs.items()):
            d = self.ladder_data(rid)
            if d:
                web_runs.append(leaderboard.ladder_entry(d, entry["finished"], f"/leaderboard/run/{rid}", "web"))
        return leaderboard.collect(self.results, web_runs, self.history_path)


NAME = re.compile(r"^[\w.-]+$")


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, payload, ctype="application/json"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 <= n <= MAX_BODY:
                raise ValueError("request too large")
            body = json.loads(self.rfile.read(n) or b"{}")
            validate_body(body)
            return body

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/tiers":
                self._send(200, {"tiers": sim.tier_info(), "pass_rate": sim.PASS_RATE, "max_games": sim.MAX_GAMES})
            elif self.path == "/api/leaderboard":
                self._send(200, {"decks": app.leaderboard()})
            elif self.path in ("/leaderboard", "/leaderboard/"):
                self._send(200, leaderboard.render_page(app.leaderboard()).encode(), "text/html; charset=utf-8")
            elif self.path.startswith("/leaderboard/"):
                self._deck_page(*(self.path.split("/", 3)[2:] + [""])[:2])
            elif self.path.startswith("/api/runs/"):
                st = app.status(self.path.rsplit("/", 1)[1])
                self._send(200, st) if st else self._send(404, {"error": "no such run"})
            else:
                self._send(404, {"error": "not found"})

        def _deck_page(self, kind: str, name: str):
            data = None
            if NAME.match(name) and not name.startswith("."):
                if kind == "run":
                    data = app.ladder_data(name)
                elif kind == "history" and name.isdigit():
                    run = leaderboard.history_run(int(name), app.history_path)
                    if run:
                        kind = "assess" if run["kind"] == "assess" else "ladder"
                        data = run["result"]
                elif kind in ("ladder", "assess"):
                    data = leaderboard._read(app.results / kind / f"{name}.json")
            if not data:
                return self._send(404, {"error": "no such results"})
            if kind == "assess":
                page = leaderboard.render_assessment(data)
            elif ladder_page:
                page = ladder_page(data).replace("<body>", "<body><nav style='font:14px system-ui;padding:12px 16px'>"
                                                 "<a href='/leaderboard'>← Leaderboard</a></nav>", 1)
            else:
                return self._send(200, data)
            self._send(200, page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            try:
                body = self._body()
                if self.path == "/api/check":
                    self._send(200, sim.check_deck(body.get("deck", ""), offline=app.offline))
                elif self.path == "/api/run":
                    self._send(200, {"id": app.start(body)})
                else:
                    self._send(404, {"error": "not found"})
            except (ValueError, TypeError) as e:
                self._send(400, {"error": str(e)})

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m web", description="Web page for the MTG simulator.")
    ap.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1, this computer only)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--jobs", type=int, default=None, help="processes playing games (default: one per CPU core)")
    ap.add_argument("--offline", action="store_true", help="don't fetch unknown cards from Scryfall")
    args = ap.parse_args(argv)
    app = App(args.jobs, args.offline)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"MTG simulator page: http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.pool.shutdown(cancel_futures=True)


if __name__ == "__main__":
    main()
