import json
import os
import threading
import time
import tempfile
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from mtgsim import history
from mtgsim.tiers import TIERS
from web import sim
from web.server import App, make_handler

BURN = (Path(__file__).resolve().parent.parent / "decks" / "ranks" / "3-gold" / "boros_burn.txt").read_text()


def setUpModule():
    # Exercise persistence without adding test decks to the user's leaderboard.
    tmp = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(tmp.cleanup)
    env = patch.dict(os.environ, {"MTGSIM_HISTORY": str(Path(tmp.name) / "history.sqlite3")})
    env.start()
    unittest.addModuleCleanup(env.stop)


class WebSimTests(unittest.TestCase):
    def test_check_deck(self):
        c = sim.check_deck(BURN, offline=True)
        self.assertEqual(c["cards"], 60)
        self.assertNotIn("error", c)
        bad = sim.check_deck("4 Lightning Bolt\n4 Not A Real Card Xyz", offline=True)
        self.assertEqual(bad["unknown"], ["Not A Real Card Xyz"])
        self.assertIn("error", sim.check_deck("hello", offline=True))
        for text in ("0 Mountain", "999999999999999 Mountain"):
            self.assertIn("error", sim.check_deck(text, offline=True))
            with self.assertRaises(ValueError):
                sim.make_run("bad", text, ["bronze"], False, 2, grade=False)

    def test_ladder_stops_at_failed_tier(self):
        run = sim.make_run("burn", BURN, None, ladder=True, games=4, seed=1, grade=False)
        run.pass_rate = 1.01  # nothing clears, so only the first tier is played
        with ThreadPoolExecutor(2) as pool:
            run.execute(pool)
        snap = run.snapshot()
        self.assertEqual([t["key"] for t in snap["tiers"]], ["bronze"])
        self.assertEqual(snap["done"], snap["total"])
        self.assertEqual(snap["tiers"][0]["games"], 4 * len(TIERS[0].decks()))
        self.assertIn("did not clear the first rank", snap["verdict"])

    def test_chosen_tiers_play_every_opponent(self):
        run = sim.make_run("burn", BURN, ["silver", "1"], ladder=False, games=6, seed=2, grade=False)
        with ThreadPoolExecutor(2) as pool:
            run.execute(pool)
        rows = run.snapshot()["tiers"]
        self.assertEqual([t["key"] for t in rows], ["bronze", "silver"])
        for t in rows:
            for o in t["opponents"]:
                self.assertEqual(o["games"], 6)
                self.assertEqual(o["wins"] + o["losses"] + o["draws"], 6)
        self.assertIsNone(run.snapshot()["assessment"])
        with self.assertRaises(ValueError):
            sim.make_run("x", BURN, ["9"], ladder=False, games=10)
        with self.assertRaises(ValueError):
            sim.make_run("x", BURN, None, ladder=True, games=1)

    def test_grades_reuse_the_grandmaster_games(self):
        run = sim.make_run("burn", BURN, ["grandmaster"], ladder=False, games=2, seed=4)
        run.goldfish_games, run.samples, run.record_history = 5, 300, False
        with ThreadPoolExecutor(2) as pool:
            run.execute(pool)
        snap = run.snapshot()
        self.assertEqual(snap["grade_error"], "")
        a = snap["assessment"]
        self.assertEqual(set(a["data"]["criteria"]), {"meta", "mana", "speed", "consistency"})
        self.assertEqual(snap["done"], snap["total"])
        played = {o["name"]: o["games"] for o in snap["tiers"][0]["opponents"]}
        for m in a["data"]["criteria"]["meta"]["details"]["matchups"]:
            self.assertEqual(m["games"], played.get(m["key"], 2))  # pool games reused, the rest played
        self.assertIn("Deck grades", a["html"])
        self.assertIn("built-in engine", a["caveat"])
        json.dumps(snap)


class WebServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = App(jobs=1, offline=True)
        cls.app.pool.shutdown()
        cls.app.pool = ThreadPoolExecutor(2)  # threads keep the test light; the server uses processes
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.pool.shutdown()

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, data=data)) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_page_and_tiers(self):
        code, page = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn(b"<title>", page)
        code, tiers = self.call("/api/tiers")
        self.assertEqual([t["key"] for t in json.loads(tiers)["tiers"]], [t.key for t in TIERS])
        self.assertEqual(json.loads(tiers)["ranks"][-1]["name"], "Grandmaster")
        self.assertIn(b"/static/theme.css", page)
        code, css = self.call("/static/theme.css")
        self.assertEqual(code, 200)
        self.assertIn(b".frame", css)
        for bad in ("/static/nope.css", "/static/index.html", "/static/..%2Fserver.py"):
            self.assertEqual(self.call(bad)[0], 404, bad)

    def test_run_round_trip(self):
        code, body = self.call("/api/run", {"deck": BURN, "name": "burn", "tiers": ["bronze"], "games": 4, "seed": 3,
                                            "grade": False, "where": "server"})
        self.assertEqual(code, 200)
        st = self.wait(json.loads(body)["id"])
        self.assertEqual(st["status"], "done", st.get("error"))
        self.assertEqual(st["tiers"][0]["key"], "bronze")
        self.assertIsNone(st["chunks"])

    def wait(self, rid, step=None):
        for _ in range(300):
            if step:
                step()
            st = json.loads(self.call(f"/api/runs/{rid}")[1])
            if st["status"] in ("done", "error"):
                return st
            time.sleep(0.1)
        return st

    def test_device_run_plays_in_the_page(self):
        # Stand in for the page's Web Workers: take chunks, play them, post the results back.
        code, body = self.call("/api/run", {"deck": BURN, "name": "burn", "tiers": ["bronze"], "games": 4, "seed": 5,
                                            "grade": False})
        rid = json.loads(body)["id"]
        state = {"cards": None, "results": []}

        def page():
            req = {"want": 4, "results": state["results"], "cards": state["cards"] is None}
            out = json.loads(self.call(f"/api/runs/{rid}/device", req)[1])
            state["cards"] = state["cards"] or out.get("cards")
            state["results"] = [{"id": t["id"], **sim._play_chunk(t["me"], t["opp"], t["games"], t["seed"])}
                                for t in out["tasks"]]

        st = self.wait(rid, page)
        self.assertEqual(st["status"], "done", st.get("error"))
        self.assertEqual(st["where"], "device")
        self.assertEqual(st["chunks"]["server"], 0)
        self.assertEqual(st["chunks"]["device"], len(TIERS[0].decks()))
        names = {c["name"] for c in state["cards"]}
        self.assertIn("Mountain", names)
        code, z = self.call("/engine/mtgsim.zip")
        self.assertEqual((code, z[:2]), (200, b"PK"))
        code, js = self.call("/static/device-worker.js")
        self.assertEqual(code, 200)
        self.assertIn(b"loadPyodide", js)

    def test_bad_requests(self):
        self.assertEqual(self.call("/api/run", {"deck": "4 Not A Real Card Xyz", "games": 4})[0], 400)
        self.assertEqual(self.call("/api/runs/nope")[0], 404)
        self.assertEqual(self.call("/api/runs/nope/device", {})[0], 404)
        self.assertEqual(self.call("/api/run", {"deck": BURN, "games": 4, "where": "moon"})[0], 400)

    def test_runs_can_be_found_without_browser_console(self):
        with patch("web.server.threading.Thread"):
            rid = self.app.start({"deck": BURN, "name": "inspect QA", "tiers": ["bronze"],
                                  "games": 2, "grade": False, "where": "server"})
        try:
            code, body = self.call("/api/runs")
            self.assertEqual(code, 200)
            row = next(r for r in json.loads(body)["runs"] if r["id"] == rid)
            self.assertEqual(row["deck"], "inspect QA")
            self.assertEqual(row["status"], "queued")
            self.assertEqual(row["done"], 0)
            self.assertNotIn("rank", row)
        finally:
            del self.app.runs[rid]


    def test_malformed_request_values(self):
        for path in ("/api/check", "/api/run"):
            for body in ([], "deck", 42, {"deck": None}, {"deck": []}):
                with self.subTest(path=path, body=body):
                    self.assertEqual(self.call(path, body)[0], 400)
        for extra in ({"name": None}, {"tiers": [None]}, {"tiers": "bronze"},
                      {"games": float("inf")}, {"games": 2.5}, {"games": True},
                      {"seed": []}, {"ladder": "false"}, {"grade": "false"}):
            with self.subTest(extra=extra):
                self.assertEqual(self.call("/api/run", {"deck": BURN, "tiers": ["bronze"],
                                                       "games": 2, **extra})[0], 400)

    def test_malformed_device_requests_preserve_assigned_work(self):
        with patch("web.server.threading.Thread"):
            rid = self.app.start({"deck": BURN, "tiers": ["bronze"], "games": 2, "grade": False})
        pool = self.app.runs[rid]["pool"]
        try:
            future = pool.submit(sim._play_chunk, {"Mountain": 60}, {"Mountain": 60}, 2, 1)
            tid = pool.take(1)[0]["id"]
            for body in ({"results": [{}]}, {"results": "bad"}, {"results": [None]},
                         {"want": float("inf")}, {"want": -1}, {"cards": "false"},
                         {"results": [{"id": tid}]}):
                with self.subTest(body=body):
                    self.assertEqual(self.call(f"/api/runs/{rid}/device", body)[0], 400)
                    self.assertFalse(future.done())
                    self.assertIn(tid, pool.tasks)
            self.assertEqual(self.call(f"/api/runs/{rid}/device", {"release": True})[0], 200)
            self.assertEqual(future.result(timeout=10)["games"], 2)
        finally:
            pool.close()
            del self.app.runs[rid]

    def test_history_survives_new_app_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.sqlite3"
            first = App(jobs=1, offline=True, results=Path(tmp), history_path=path)
            try:
                with patch("web.server.threading.Thread"):
                    rid = first.start({"deck": BURN, "name": "session-burn", "tiers": ["bronze"],
                                       "games": 2, "seed": 17, "grade": False, "where": "server"})
                first._execute(first.runs[rid])
                self.assertEqual(first.status(rid)["status"], "done")
                self.assertEqual(len(history.runs("session-burn", path)), 1)
            finally:
                first.pool.shutdown()
            second = App(jobs=1, offline=True, results=Path(tmp), history_path=path)
            try:
                rows = second.leaderboard()
                self.assertEqual([r["deck"] for r in rows], ["session-burn"])
            finally:
                second.pool.shutdown()


class DevicePoolTests(unittest.TestCase):
    def test_quiet_page_falls_back_to_the_server(self):
        run = sim.make_run("burn", BURN, ["bronze"], ladder=False, games=4, seed=6, grade=False)
        with ThreadPoolExecutor(2) as server:
            pool = sim.DevicePool(server, stall=0.4)
            run.execute(pool)  # nobody takes the chunks, so the server plays them after the stall
            pool.close()
        self.assertEqual(run.snapshot()["tiers"][0]["games"], 4 * len(TIERS[0].decks()))
        self.assertEqual(pool.chunks_on_device, 0)
        self.assertFalse(pool.active)

    def test_release_moves_claimed_chunks(self):
        with ThreadPoolExecutor(1) as server:
            pool = sim.DevicePool(server, stall=60)
            deck = {"Mountain": 20, "Raging Goblin": 20}
            futs = [pool.submit(sim._play_chunk, deck, deck, 2, i) for i in range(3)]
            taken = pool.take(2)
            self.assertEqual([t["id"] for t in taken], [0, 1])
            pool.finish(0, sim._play_chunk(deck, deck, 2, 0))
            pool.release()
            pool.finish(1, {"games": 99})  # too late: the server already has it
            self.assertEqual([f.result(timeout=30)["games"] for f in futs], [2, 2, 2])
            self.assertEqual((pool.chunks_on_device, pool.chunks_on_server), (1, 2))
            pool.close()



if __name__ == "__main__":
    unittest.main()
