"""MMR and ranks for a deck tested against pools of opponent decks.

Ranks run Bronze to Grandmaster, each a band of MMR (an Elo-scale rating: 400 points
apart means the stronger deck is expected to win about 91% of games). Each opponent is
rated at its fitted rating from decks/ranks/ratings.json (written by mtgsim.calibrate
from simulated results) when that file lists it. Otherwise its pool's anchor is used: a
pool keyed by a rank name ("gold") sits at the centre of that rank's band, other pools
are spread evenly over the bands in the order given. A tested deck's MMR is its performance rating: the rating at which its expected score
against the opponents it has played equals the score it actually got.

    tracker = LadderTracker("my_deck", [("gold", "Gold", ["gold/a", "gold/b"]), ...])
    tracker.update_match("gold/a", wins=12, draws=1, games=20)   # cumulative, after any game
    tracker.mmr, tracker.rank.name, tracker.to_dict()           # to_dict() is plain JSON

The tracker calls each function in tracker.listeners after every change, so a live view
(terminal, HTML report, web page) only has to render tracker.to_dict().
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Rank:
    name: str
    floor: int    # lowest MMR in this rank
    color: str    # badge colour

    @property
    def key(self) -> str:
        return self.name.lower()

    @property
    def anchor(self) -> int:
        """Centre of the band: a pool of this rank's decks is rated here."""
        return self.floor + BAND // 2 if self.floor else RANKS[1].floor - BAND // 2


BAND = 200
RANKS = [
    Rank("Bronze", 0, "#a86b3c"),
    Rank("Silver", 1000, "#8e9aa6"),
    Rank("Gold", 1200, "#d4a017"),
    Rank("Platinum", 1400, "#2fa59a"),
    Rank("Diamond", 1600, "#3b7ddd"),
    Rank("Master", 1800, "#9b4fd1"),
    Rank("Grandmaster", 2000, "#d6403a"),
]
START_MMR = 1000       # an unplayed deck sits at the bottom of Silver
PRIOR_GAMES = 2        # virtual draws at START_MMR, so the first few games don't swing to the extremes
MMR_MIN, MMR_MAX = 0, 3000
RATINGS_FILE = Path(__file__).resolve().parent.parent / "decks" / "ranks" / "ratings.json"


def load_ratings(path: Path | str | None = None) -> dict[str, int]:
    """Fitted opponent ratings by deck name ("gold/boros_burn"); empty if the file is missing or unreadable."""
    try:
        doc = json.loads(Path(path or RATINGS_FILE).read_text(encoding="utf-8"))
        return {name: int(d["rating"]) for name, d in doc.get("decks", {}).items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return {}


def rank_for(mmr: float) -> Rank:
    return [r for r in RANKS if mmr >= r.floor][-1]


def next_rank(mmr: float) -> Rank | None:
    above = [r for r in RANKS if r.floor > mmr]
    return above[0] if above else None


def expected(r_a: float, r_b: float) -> float:
    """Expected score of a deck rated r_a against one rated r_b."""
    return 1 / (1 + 10 ** ((r_b - r_a) / 400))


def performance_rating(results: list[tuple[float, float, float]], prior=(START_MMR, PRIOR_GAMES)) -> float:
    """results: (opponent rating, points scored, games). Returns the rating R at which the
    expected score equals the points scored, with `prior` games drawn against prior[0]."""
    rows = [r for r in results if r[2] > 0]
    if prior and prior[1]:
        rows.append((prior[0], prior[1] / 2, prior[1]))
    if not rows:
        return float(START_MMR)
    points = sum(p for _, p, _ in rows)
    lo, hi = MMR_MIN, MMR_MAX
    for _ in range(50):  # expected score rises with R, so bisect
        mid = (lo + hi) / 2
        if sum(g * expected(mid, r) for r, _, g in rows) < points:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def pool_anchors(keys: list[str], ratings: dict[str, int] | None = None) -> dict[str, int]:
    """MMR for each pool: the mean fitted rating of its decks when `ratings` (from load_ratings)
    has any deck named "<key>/...", else its rank's band centre if the key names a rank, else
    spread evenly."""
    base = _band_anchors(keys)
    for k in keys:
        mine = [v for n, v in (ratings or {}).items() if n.split("/", 1)[0] == k]
        if mine:
            base[k] = round(sum(mine) / len(mine))
    return base


def _band_anchors(keys: list[str]) -> dict[str, int]:
    by_name = {r.key: r for r in RANKS}
    if all(k.lower() in by_name for k in keys):
        return {k: by_name[k.lower()].anchor for k in keys}
    lo, hi = RANKS[0].anchor, RANKS[-1].anchor
    if len(keys) == 1:
        return {keys[0]: (lo + hi) // 2}
    return {k: round(lo + i * (hi - lo) / (len(keys) - 1)) for i, k in enumerate(keys)}


@dataclass
class Opponent:
    name: str
    pool: str
    rating: int
    games: int = 0
    points: float = 0.0
    wins: int = 0
    draws: int = 0
    total: int = 0     # games scheduled, for progress

    @property
    def win_rate(self) -> float | None:
        return self.points / self.games if self.games else None


@dataclass
class LadderTracker:
    deck: str
    pools: list[tuple[str, str, list[str]]]   # (key, label, opponent names) in ladder order
    pass_rate: float = 0.5
    ladder: bool = False
    listeners: list = field(default_factory=list)
    ratings: dict | None = None   # deck name -> fitted rating; None reads decks/ranks/ratings.json

    def __post_init__(self):
        if self.ratings is None:
            self.ratings = load_ratings()
        anchors = pool_anchors([k for k, _, _ in self.pools])
        self.opponents = {n: Opponent(n, k, self.ratings.get(n, anchors[k]))
                          for k, _, names in self.pools for n in names}
        self.pool_results: dict[str, dict] = {}
        self.current: str | None = None
        self.mmr = float(START_MMR)
        self.peak = self.mmr
        self.history: list[tuple[int, float]] = [(0, self.mmr)]   # (games played, MMR after them)
        self.status = "running"
        self.verdict = ""
        self.started = time.time()

    # -- feeding results ----------------------------------------------------------
    def start_match(self, opp: str, total: int):
        self.current = opp
        self.opponents[opp].total = total
        self._changed()

    def update_match(self, opp: str, wins: int, draws: int, games: int):
        """Cumulative result of the tested deck against `opp` so far."""
        o = self.opponents[opp]
        o.wins, o.draws, o.games = wins, draws, games
        o.points = wins + 0.5 * draws
        self.mmr = performance_rating([(x.rating, x.points, x.games) for x in self.opponents.values()])
        self.peak = max(self.peak, self.mmr)
        n = self.games
        if self.history[-1][0] == n:
            self.history[-1] = (n, self.mmr)
        else:
            self.history.append((n, self.mmr))
        self._changed()

    def end_pool(self, key: str, cleared: bool | None = None):
        opps = [o for o in self.opponents.values() if o.pool == key and o.games]
        games = sum(o.games for o in opps)
        points = sum(o.points for o in opps)
        rates = [o.points / o.games for o in opps]   # mean of matchups: see runner.pool_rate
        self.pool_results[key] = {"games": games, "points": points,
                                  "rate": sum(rates) / len(rates) if rates else None, "cleared": cleared}
        self.current = None
        self._changed()

    def finish(self, verdict: str = ""):
        self.status, self.verdict, self.current = "done", verdict, None
        self._changed()

    def _changed(self):
        for fn in self.listeners:
            fn(self)

    # -- reading ------------------------------------------------------------------
    @property
    def games(self) -> int:
        return sum(o.games for o in self.opponents.values())

    @property
    def rank(self) -> Rank:
        return rank_for(self.mmr)

    def to_dict(self) -> dict:
        nxt = next_rank(self.mmr)
        cur = self.opponents.get(self.current) if self.current else None
        pools = []
        for key, label, names in self.pools:
            res = self.pool_results.get(key, {})
            anchor = round(sum(self.opponents[n].rating for n in names) / len(names)) if names else None
            named = next((r for r in RANKS if r.key == key.lower()), None)
            pools.append({"key": key, "label": label, "rating": anchor,
                          "rank": named.name if named else rank_for(anchor).name if anchor is not None else None,
                          "games": res.get("games", 0), "rate": res.get("rate"),
                          "cleared": res.get("cleared"), "done": key in self.pool_results})
        return {
            "deck": self.deck,
            "status": self.status,
            "verdict": self.verdict,
            "ladder": self.ladder,
            "pass_rate": self.pass_rate,
            "mmr": round(self.mmr),
            "peak": round(self.peak),
            "rank": self.rank.name,
            "rank_color": self.rank.color,
            "next_rank": nxt.name if nxt else None,
            "to_next": round(nxt.floor - self.mmr) if nxt else None,
            "games": self.games,
            "elapsed": round(time.time() - self.started, 1),
            "current": {"opponent": cur.name, "games": cur.games, "total": cur.total,
                        "win_rate": cur.win_rate} if cur else None,
            "ranks": [{"name": r.name, "floor": r.floor, "color": r.color} for r in RANKS],
            "pools": pools,
            "opponents": [{"name": o.name, "pool": o.pool, "rating": o.rating, "games": o.games, "total": o.total,
                           "wins": o.wins, "draws": o.draws, "win_rate": o.win_rate}
                          for o in self.opponents.values()],
            "history": [[g, round(m, 1)] for g, m in self.history],
        }
