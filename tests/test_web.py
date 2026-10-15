import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

from mtgsim.tiers import TIERS
from web import sim
from web.server import App, make_handler

BURN = (Path(__file__).resolve().parent.parent / "decks" / "ranks" / "3-gold" / "boros_burn.txt").read_text()


class WebSimTests(unittest.TestCase):
    def test_check_deck(self):
        c = sim.check_deck(BURN, offline=True)
        self.assertEqual(c["cards"], 60)
        self.assertNotIn("error", c)
        bad = sim.check_deck("4 Lightning Bolt\n4 Not A Real Card Xyz", offline=True)
        self.assertEqual(bad["unknown"], ["Not A Real Card Xyz"])
        self.assertIn("error", sim.check_deck("hello", offline=True))

    def test_ladder_stops_at_failed_tier(self):
        run = sim.make_run("burn", BURN, None, ladder=True, games=4, seed=1)
        run.pass_rate = 1.01  # nothing clears, so only the first tier is played
        with ThreadPoolExecutor(2) as pool:
            run.execute(pool)
        snap = run.snapshot()
        self.assertEqual([t["key"] for t in snap["tiers"]], ["bronze"])
        self.assertEqual(snap["done"], snap["total"])
        self.assertEqual(snap["tiers"][0]["games"], 4 * len(TIERS[0].decks()))
        self.assertIn("did not clear the first rank", snap["verdict"])

    def test_chosen_tiers_play_every_opponent(self):
        run = sim.make_run("burn", BURN, ["silver", "1"], ladder=False, games=6, seed=2)
        with ThreadPoolExecutor(2) as pool:
            run.execute(pool)
        rows = run.snapshot()["tiers"]
        self.assertEqual([t["key"] for t in rows], ["bronze", "silver"])
        for t in rows:
            for o in t["opponents"]:
                self.assertEqual(o["games"], 6)
                self.assertEqual(o["wins"] + o["losses"] + o["draws"], 6)
        with self.assertRaises(ValueError):
            sim.make_run("x", BURN, ["9"], ladder=False, games=10)
        with self.assertRaises(ValueError):
            sim.make_run("x", BURN, None, ladder=True, games=1)


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

    def test_run_round_trip(self):
        code, body = self.call("/api/run", {"deck": BURN, "name": "burn", "tiers": ["bronze"], "games": 4, "seed": 3})
        self.assertEqual(code, 200)
        rid = json.loads(body)["id"]
        for _ in range(300):
            st = json.loads(self.call(f"/api/runs/{rid}")[1])
            if st["status"] in ("done", "error"):
                break
            time.sleep(0.1)
        self.assertEqual(st["status"], "done", st.get("error"))
        self.assertEqual(st["tiers"][0]["key"], "bronze")

    def test_bad_requests(self):
        self.assertEqual(self.call("/api/run", {"deck": "4 Not A Real Card Xyz", "games": 4})[0], 400)
        self.assertEqual(self.call("/api/runs/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
