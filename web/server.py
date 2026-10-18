"""Local web server for mtgsim, standard library only.

    python3 -m web                  # then open http://127.0.0.1:8000
    python3 -m web --port 8080 --jobs 4

GET  /                 the page
GET  /api/tiers        tiers and their decks
POST /api/check        {"deck": text}                       -> card counts, unknown and partial cards
POST /api/run          {"deck", "name", "ladder", "tiers", "games", "full", "seed", "grade", "where"} -> {"id"}
GET  /api/runs/<id>    progress and results so far
POST /api/runs/<id>/device  {"want", "cards", "results", "release"} -> chunks for the page to play
GET  /engine/mtgsim.zip     the engine's Python source, for the page's Web Workers (Pyodide)
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

from mtgsim.browser import package_zip

from . import leaderboard, sim, theme

try:
    from mtgsim.ladder_report import emblem, render_page as ladder_page
    from mtgsim.rating import RANKS
except ImportError:
    ladder_page = emblem = None
    RANKS = []

STATIC = Path(__file__).parent / "static"
MAX_BODY = 1 << 20
STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}


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
        self.lock = threading.Lock()  # one server run at a time; they share the pool anyway
        self._engine_zip = None

    def engine_zip(self) -> bytes:
        if self._engine_zip is None:
            self._engine_zip = package_zip()
        return self._engine_zip

    def pool_for(self, where: str):
        """Where a run's games are played. "device" (the default) hands them to the visitor's
        browser and falls back to the server pool; "server" plays them here. A paid server mode
        would decide here which runs may use the server pool."""
        if where == "server":
            return self.pool
        return sim.DevicePool(self.pool)

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
        where = body.get("where") or "device"
        if where not in sim.WHERE:
            raise ValueError(f"where must be one of {', '.join(sim.WHERE)}")
        run.where = where
        if where == "device":
            run.chunk = sim.DEVICE_CHUNK
        run.history_path = self.history_path
        rid = uuid.uuid4().hex[:12]
        entry = {"run": run, "status": "queued", "error": None, "check": check, "pool": self.pool_for(where)}
        self.runs[rid] = entry
        threading.Thread(target=self._execute, args=(entry,), daemon=True).start()
        return rid

    def _execute(self, entry):
        pool = entry["pool"]
        if pool is self.pool:  # server runs queue; device runs use the visitor's CPU and start at once
            with self.lock:
                self._play(entry, pool)
        else:
            try:
                self._play(entry, pool)
            finally:
                pool.close()

    def _play(self, entry, pool):
        entry["status"] = "running"
        try:
            entry["run"].execute(pool)
            entry["status"] = "done"
            entry["finished"] = time.time()
        except Exception as e:  # report to the page rather than dying silently
            traceback.print_exc()
            entry["status"], entry["error"] = "error", f"{type(e).__name__}: {e}"

    def device(self, rid: str, body: dict) -> dict | None:
        """The page's side of a device run: take its finished chunks, hand it up to `want` more,
        and the run's card data when it asks. `active` turns false once nothing more will come."""
        entry = self.runs.get(rid)
        if not entry:
            return None
        pool = entry["pool"]
        if not isinstance(pool, sim.DevicePool):
            return {"active": False, "tasks": []}
        for r in body.get("results") or []:
            pool.finish(int(r["id"]), r)
        if body.get("release"):
            pool.release()
        out = {"active": pool.active, "tasks": pool.take(max(0, min(64, int(body.get("want") or 0))))}
        if body.get("cards"):
            out["cards"] = sim.card_data(entry["run"].decks())
        return out

    def status(self, rid: str) -> dict | None:
        entry = self.runs.get(rid)
        if not entry:
            return None
        pool = entry["pool"]
        played = None
        if isinstance(pool, sim.DevicePool):
            played = {"device": pool.chunks_on_device, "server": pool.chunks_on_server}
        return {"status": entry["status"], "error": entry["error"], "partial": entry["check"]["partial"],
                **entry["run"].snapshot(), "chunks": played}


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


def rank_info() -> list[dict]:
    """The ranks, low to high, with their badges for the page."""
    return [{"name": r.name, "key": r.key, "floor": r.floor, "color": r.color,
             "emblem": emblem(r.name, r.color) if emblem else ""} for r in RANKS]


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
            path = self.path.split("?", 1)[0]  # ?run=server, ?pyodide=... are read by the page
            if path in ("/", "/index.html"):
                page = theme.dress((STATIC / "index.html").read_text(encoding="utf-8"), "test")
                self._send(200, page.encode(), "text/html; charset=utf-8")
            elif path.startswith("/static/"):
                name = path[len("/static/"):]
                file = STATIC / name
                if NAME.match(name) and not name.startswith(".") and file.suffix in STATIC_TYPES and file.is_file():
                    self._send(200, file.read_bytes(), STATIC_TYPES[file.suffix])
                else:
                    self._send(404, {"error": "not found"})
            elif path == "/engine/mtgsim.zip":
                self._send(200, app.engine_zip(), "application/zip")
            elif path == "/api/tiers":
                self._send(200, {"tiers": sim.tier_info(), "ranks": rank_info(), "pass_rate": sim.PASS_RATE,
                                 "max_games": sim.MAX_GAMES})
            elif path == "/api/leaderboard":
                self._send(200, {"decks": app.leaderboard()})
            elif path in ("/leaderboard", "/leaderboard/"):
                self._send(200, leaderboard.render_page(app.leaderboard()).encode(), "text/html; charset=utf-8")
            elif path.startswith("/leaderboard/"):
                self._deck_page(*(path.split("/", 3)[2:] + [""])[:2])
            elif path.startswith("/api/runs/"):
                st = app.status(path.rsplit("/", 1)[1])
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
                panel, scripts = leaderboard.replay_panel(data)
                page = theme.dress(ladder_page(data), "leaderboard",
                                   f"<main class='page report'><a class=back href='/leaderboard'>‹ Leaderboard</a>{panel}"
                                   f"<section class=frame><div class=face>{theme.titlebar('Ranked ladder')}",
                                   f"</div></section></main>{scripts}")
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
                elif self.path.startswith("/api/runs/") and self.path.endswith("/device"):
                    out = app.device(self.path.split("/")[3], body)
                    self._send(200, out) if out else self._send(404, {"error": "no such run"})
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
