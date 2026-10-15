import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

from web import leaderboard
from web.server import App, make_handler

BURN = (Path(__file__).resolve().parent.parent / "decks" / "ranks" / "3-gold" / "boros_burn.txt").read_text()


def ladder_json(deck, mmr, rank):
    return {"deck": deck, "status": "done", "mmr": mmr, "rank": rank, "rank_color": "#d4a017", "games": 40,
            "peak": mmr, "verdict": "", "next_rank": None, "to_next": None, "current": None, "ladder": True,
            "pass_rate": 0.5, "elapsed": 1, "ranks": [{"name": "Gold", "floor": 1200, "color": "#d4a017"}],
            "pools": [], "opponents": [], "history": [[0, 1000], [40, mmr]]}


def write(path: Path, data: dict, mtime: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    os.utime(path, (mtime, mtime))


class LeaderboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        now = time.time()
        write(self.root / "ladder" / "burn.json", ladder_json("Burn", 1300, "Gold"), now - 7200)
        write(self.root / "ladder" / "burn_v2.json", ladder_json("burn", 1450, "Platinum"), now - 60)
        write(self.root / "ladder" / "elves.json", ladder_json("Elves", 1100, "Silver"), now - 600)
        write(self.root / "ladder" / "live.json", {**ladder_json("Live", 2500, "Grandmaster"), "status": "running"}, now)
        (self.root / "ladder" / "broken.json").write_text("{nope")
        write(self.root / "assess" / "elves.json",
              {"deck": "Elves", "assessed": time.strftime("%Y-%m-%d"), "rating": None,
               "criteria": {"meta": {"label": "Meta", "grade": "C", "score": 55, "summary": "ok"},
                            "mana": {"label": "Mana", "grade": "A", "score": 90, "summary": "good"}}}, now)

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_row_per_deck_ranked_by_mmr(self):
        rows = leaderboard.collect(self.root)
        self.assertEqual([(r["deck"], r["mmr"]) for r in rows], [("burn", 1450), ("Elves", 1100)])
        self.assertEqual(rows[0]["link"], "/leaderboard/ladder/burn_v2")
        self.assertEqual(rows[1]["grades"], {"meta": "C", "mana": "A"})  # unrated assessment still adds grades
        self.assertEqual([r["place"] for r in rows], [1, 2])

    def test_web_runs_join_and_page_renders(self):
        web = leaderboard.ladder_entry(ladder_json("Mono Red", 1700, "Diamond"), time.time(), "/leaderboard/run/x", "web")
        rows = leaderboard.collect(self.root, [web])
        self.assertEqual(rows[0]["deck"], "Mono Red")
        page = leaderboard.render_page(rows)
        self.assertIn("Mono Red", page)
        self.assertIn("Consistency", page)  # grade columns appear once any deck has grades
        self.assertIn("1 minute ago", page)
        self.assertIn("No decks tested yet", leaderboard.render_page([]))


class LeaderboardServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        write(root / "ladder" / "burn.json", ladder_json("Burn", 1300, "Gold"), time.time())
        write(root / "assess" / "burn.json", {"deck": "Burn", "assessed": "2026-10-01", "rating": None,
                                              "criteria": {"speed": {"label": "Speed", "grade": "B",
                                                                     "score": 70, "summary": "fast"}}}, time.time())
        cls.app = App(jobs=1, offline=True, results=root)
        cls.app.pool.shutdown()
        cls.app.pool = ThreadPoolExecutor(2)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.pool.shutdown()
        cls.tmp.cleanup()

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, data=data)) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_pages(self):
        code, page = self.call("/leaderboard")
        self.assertEqual(code, 200)
        self.assertIn(b"Leaderboard", page)
        self.assertIn(b"/leaderboard/ladder/burn", page)
        self.assertEqual(self.call("/leaderboard/ladder/burn")[0], 200)
        code, page = self.call("/leaderboard/assess/burn")
        self.assertEqual(code, 200)
        self.assertIn(b"fast", page)
        for bad in ("/leaderboard/ladder/..%2Fx", "/leaderboard/ladder/nope", "/leaderboard/run/nope", "/leaderboard/x/burn"):
            self.assertEqual(self.call(bad)[0], 404, bad)
        self.assertIn(b"/leaderboard", self.call("/")[1])

    def test_finished_web_run_is_listed(self):
        code, body = self.call("/api/run", {"deck": BURN, "name": "web burn", "tiers": ["bronze"], "games": 2, "seed": 1})
        self.assertEqual(code, 200)
        rid = json.loads(body)["id"]
        for _ in range(300):
            if json.loads(self.call(f"/api/runs/{rid}")[1])["status"] in ("done", "error"):
                break
            time.sleep(0.1)
        decks = json.loads(self.call("/api/leaderboard")[1])["decks"]
        row = next(d for d in decks if d["deck"] == "web burn")
        self.assertEqual(row["link"], f"/leaderboard/run/{rid}")
        self.assertEqual(self.call(row["link"])[0], 200)


if __name__ == "__main__":
    unittest.main()
