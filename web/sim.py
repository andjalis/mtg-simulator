"""The simulation side of the web page: check a pasted deck, then play it against tiers.

Games run in a process pool, split into chunks so the page can show progress and use
every CPU core. The ladder plays tier by tier and stops at the first tier it fails.
"""
from __future__ import annotations

import os
import random
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field

from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck, parse_decklist
from mtgsim.runner import build_deck, run_match, wilson
from mtgsim.tiers import PASS_RATE, TIERS, resolve_tiers

try:  # rank badge and MMR chart, from the ranked-ladder visuals (mtgsim/rating.py)
    from mtgsim.ladder_report import render_fragment
    from mtgsim.rating import LadderTracker
except ImportError:
    LadderTracker = render_fragment = None

CHUNK = 20  # games per task; even, so play and draw stay balanced
MAX_GAMES = 2000

_db: CardDB | None = None
_db_lock = threading.Lock()  # CardDB shares one sqlite connection; the server checks decks from many threads


def _card_db(offline: bool = False) -> CardDB:
    global _db
    if _db is None or (_db.offline and not offline):
        _db = CardDB(offline=offline)
    return _db


def tier_info() -> list[dict]:
    return [{"key": t.key, "label": t.label, "about": t.about, "decks": [p.stem for p in t.decks()]}
            for t in TIERS]


def check_deck(text: str, offline: bool = False) -> dict:
    """Parse a pasted decklist and look up its cards: the counts, unknown names and
    cards whose rules text the engine only partly simulates."""
    counts = parse_decklist(text)
    out = {"cards": sum(counts.values()), "distinct": len(counts), "unknown": [], "partial": []}
    if not counts:
        out["error"] = "No cards found. Each line should look like \"4 Lightning Bolt\"."
        return out
    with _db_lock:
        return _check(counts, out, _card_db(offline))


def _check(counts, out, db):
    try:
        db.ensure(counts)
    except KeyError as e:
        out["unknown"] = [n for n in counts if not _known(db, n)] or [str(e).strip("'\"")]
        out["error"] = "Unknown cards: " + ", ".join(out["unknown"])
        return out
    except OSError as e:  # Scryfall unreachable
        out["unknown"] = [n for n in counts if not _known(db, n)]
        out["error"] = f"Unknown cards, and Scryfall could not be reached ({e}): " + ", ".join(out["unknown"])
        return out
    for name in counts:
        card = db.get(name)
        if card.unsupported:
            out["partial"].append({"name": card.name, "ignored": list(card.unsupported)})
    return out


def _known(db: CardDB, name: str) -> bool:
    return name.lower() in db.raw or db.lookup(name) is not None


def _play_chunk(me_counts, opp_counts, games, seed):
    """Worker: play one chunk of games and return plain numbers."""
    global _db
    with _db_lock:
        try:
            mine, theirs = build_deck(_card_db(True), me_counts), build_deck(_card_db(True), opp_counts)
        except KeyError:  # the server fetched new cards into the cache after this worker started
            _db = None
            mine, theirs = build_deck(_card_db(True), me_counts), build_deck(_card_db(True), opp_counts)
    res, _ = run_match("me", mine, "opp", theirs, games=games, seed=seed)
    return {"games": res.games, "wins": res.wins_a, "losses": res.wins_b, "draws": res.draws,
            "on_play_wins": res.wins_a_on_play, "on_play_games": res.games_a_on_play,
            "turns": sum(res.turns)}


@dataclass
class Opponent:
    tier: str
    name: str
    counts: dict
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    on_play_wins: int = 0
    on_play_games: int = 0
    turns: int = 0

    def add(self, r: dict):
        for k, v in r.items():
            setattr(self, k, getattr(self, k) + v)

    def as_dict(self) -> dict:
        points = self.wins + 0.5 * self.draws
        lo, hi = wilson(points, self.games)
        on_draw = self.games - self.on_play_games
        return {"name": self.name, "games": self.games, "wins": self.wins, "losses": self.losses,
                "draws": self.draws, "rate": points / self.games if self.games else None, "lo": lo, "hi": hi,
                "on_play": f"{self.on_play_wins}/{self.on_play_games}",
                "on_draw": f"{self.wins - self.on_play_wins}/{on_draw}",
                "avg_turns": self.turns / self.games if self.games else None}


@dataclass
class Run:
    """One web request's worth of games. `progress` is read by the server while it runs."""
    deck_name: str
    counts: dict
    tiers: list
    ladder: bool
    games: int
    full: bool = False
    seed: int | None = None
    pass_rate: float = PASS_RATE
    done: int = 0
    total: int = 0
    current: str = ""
    rows: list = field(default_factory=list)
    verdict: str = ""
    tracker: object = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def opponents(self, tier) -> list[Opponent]:
        return [Opponent(tier.key, p.stem, load_deck(p)[1]) for p in tier.decks()]

    def execute(self, pool) -> None:
        rng = random.Random(self.seed)
        chunks = [CHUNK] * (self.games // CHUNK) + ([self.games % CHUNK] if self.games % CHUNK else [])
        self.total = sum(len(t.decks()) for t in self.tiers) * self.games
        if LadderTracker:
            self.tracker = LadderTracker(self.deck_name, [(t.key, t.label, [f"{t.key}/{p.stem}" for p in t.decks()])
                                                          for t in self.tiers], self.pass_rate, self.ladder)
        reached = failed = None
        for t in self.tiers:
            self.current = t.label
            opps = self.opponents(t)
            if self.tracker:
                with self.lock:
                    for o in opps:
                        self.tracker.start_match(f"{t.key}/{o.name}", self.games)
            futures = {pool.submit(_play_chunk, self.counts, o.counts, n, rng.randrange(2**32)): (o, n)
                       for o in opps for n in chunks}
            for f in as_completed(futures):
                o, n = futures[f]
                with self.lock:
                    o.add(f.result())
                    self.done += n
                    if self.tracker:
                        self.tracker.update_match(f"{t.key}/{o.name}", o.wins, o.draws, o.games)
            games = sum(o.games for o in opps)
            points = sum(o.wins + 0.5 * o.draws for o in opps)
            rate = points / games if games else 0.0
            lo, hi = wilson(points, games)
            cleared = rate >= self.pass_rate
            if self.tracker:
                with self.lock:
                    self.tracker.end_pool(t.key, cleared if self.ladder else None)
            self.rows.append({"key": t.key, "label": t.label, "rate": rate, "lo": lo, "hi": hi, "games": games,
                              "cleared": cleared if self.ladder else None,
                              "opponents": [o.as_dict() for o in opps]})
            if self.ladder and failed is None:
                if cleared:
                    reached = t
                else:
                    failed = t
                    if not self.full:
                        self.total = self.done
                        break
        self.current = ""
        if self.ladder:
            me = self.deck_name
            if failed is None:
                self.verdict = f"{me} cleared every rank, up to and including {reached.label}."
            elif reached is None:
                self.verdict = f"{me} did not clear the first rank ({failed.label})."
            else:
                self.verdict = f"{me} reached {reached.label} and stopped at {failed.label}."
        if self.tracker:
            with self.lock:
                self.tracker.finish(self.verdict)

    def snapshot(self) -> dict:
        with self.lock:
            rank = None
            if self.tracker:
                d = self.tracker.to_dict()
                rank = {"html": render_fragment(d), "data": d}
        return {"rank": rank, "deck": self.deck_name, "ladder": self.ladder, "pass_rate": self.pass_rate,
                "games_per_opponent": self.games, "done": self.done, "total": self.total,
                "current": self.current, "tiers": self.rows, "verdict": self.verdict}


def make_run(deck_name: str, text: str, tiers: list[str] | None, ladder: bool, games: int,
             full: bool = False, seed: int | None = None) -> Run:
    if not 2 <= games <= MAX_GAMES:
        raise ValueError(f"games per opponent must be between 2 and {MAX_GAMES}")
    chosen = TIERS if ladder and not tiers else resolve_tiers(tiers or [])
    if not chosen:
        raise ValueError("pick at least one tier")
    return Run(deck_name or "my deck", parse_decklist(text), chosen, ladder, games, full, seed)


def make_pool(jobs: int | None = None) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=jobs or os.cpu_count() or 1)
