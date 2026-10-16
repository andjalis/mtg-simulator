"""The simulation side of the web page: check a pasted deck, then play it against tiers.

Games run in a process pool, split into chunks so the page can show progress and use
every CPU core. The ladder plays tier by tier and stops at the first tier it fails.
"""
from __future__ import annotations

import os
import random
import threading
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field

from mtgsim import history
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck, parse_decklist
from mtgsim.runner import build_deck, run_match, wilson
from mtgsim.tiers import PASS_RATE, TIERS, resolve_tiers

try:  # rank badge and MMR chart, from the ranked-ladder visuals (mtgsim/rating.py)
    from mtgsim.ladder_report import render_fragment
    from mtgsim.rating import LadderTracker
except ImportError:
    LadderTracker = render_fragment = None

try:  # deck grades: meta, mana, speed, consistency (mtgsim/assess.py)
    from mtgsim.assess import AUTO_THRESHOLD, assess, coverage_share, load_metagame
    from mtgsim.ladder_report import meta_caveat, render_grades
except ImportError:
    assess = None

CHUNK = 20  # games per task; even, so play and draw stay balanced
MAX_GAMES = 2000
FORGE_META_GAMES = 20  # most Forge games per meta matchup; Forge is far slower than the built-in engine
META_ENGINES = ("forge", "auto", "python")

_db: CardDB | None = None
_db_lock = threading.Lock()  # CardDB shares one sqlite connection; the server checks decks from many threads


def _card_db(offline: bool = False) -> CardDB:
    global _db
    if _db is None or (_db.offline and not offline):
        _db = CardDB(offline=offline)
    return _db


def forge_dir() -> str | None:
    """The Forge install the meta field is played in: $MTGSIM_FORGE_DIR, else $FORGE_HOME; None
    when neither points at a Forge desktop jar."""
    folder = os.environ.get("MTGSIM_FORGE_DIR") or os.environ.get("FORGE_HOME")
    if not folder:
        return None
    from mtgsim.forge import ForgeError, find_forge
    try:
        return str(find_forge(folder)[0])
    except ForgeError:
        return None


def _forge_match(me_counts, opp_counts, games, seed, folder):
    """Play one meta matchup in Forge; returns (points, games)."""
    from mtgsim.forge import run_forge_match
    res = run_forge_match("me", me_counts, "opp", opp_counts, games=games, seed=seed, forge_dir=folder,
                          jobs=max(1, min(games, os.cpu_count() or 1)))
    return res.wins_a + 0.5 * res.draws, res.games


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
    grade: bool = True            # grade the deck after the ladder (see mtgsim.assess)
    goldfish_games: int = 200
    samples: int = 20000
    assessment: dict | None = None
    grade_error: str = ""
    record_history: bool = True
    meta_engine: str = "forge"    # with a Forge install: forge (whole meta field), auto (low coverage only), python
    forge_dir: str | None = None  # None: the meta field stays in the built-in engine
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
        if self.grade and assess:
            try:
                self._grade(pool, rng, chunks)
            except Exception as e:  # keep the ladder results; say why the grades are missing
                traceback.print_exc()
                self.grade_error = f"{type(e).__name__}: {e}"
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
            if self.record_history:
                history.try_record(history.record_ladder, self.tracker.to_dict(), self.counts, source="web")
        if self.record_history and self.assessment:
            history.try_record(history.record_assessment, self.assessment, self.counts, source="web")

    def _grade(self, pool, rng, chunks) -> None:
        """Grade the deck. Without Forge the meta criterion reuses the games against the Grandmaster
        pool and plays whichever meta decks the ladder didn't reach. With a Forge install the meta
        field is played in Forge: every matchup, or with meta_engine "auto" only those where either
        deck is below the coverage threshold. The other criteria are quick."""
        self.current = "the meta field"
        results = {o["name"]: (o["wins"] + 0.5 * o["draws"], o["games"])
                   for t in self.rows if t["key"] == "grandmaster" for o in t["opponents"] if o["games"]}
        engines = dict.fromkeys(results, "python")
        _, archetypes = load_metagame()
        decks = {a.key: load_deck(a.path)[1] for a in archetypes}
        forge = []
        if self.forge_dir and self.meta_engine != "python":
            with _db_lock:
                db = _card_db(True)
                mine = coverage_share(db, self.counts)
                forge = [a for a in archetypes if self.meta_engine == "forge"
                         or min(mine, coverage_share(db, decks[a.key])) < AUTO_THRESHOLD]
        todo = [a for a in archetypes if a.key not in results and a not in forge]
        forge_games = min(self.games, FORGE_META_GAMES)
        with self.lock:
            self.total += len(todo) * self.games + len(forge) * forge_games
        for a in forge:
            self.current = f"the meta field in Forge ({a.name})"
            results[a.key] = _forge_match(self.counts, decks[a.key], forge_games, rng.randrange(2**31), self.forge_dir)
            engines[a.key] = "forge"
            with self.lock:
                self.done += forge_games
        self.current = "the meta field"
        futures = {pool.submit(_play_chunk, self.counts, decks[a.key], n, rng.randrange(2**32)): (a, n)
                   for a in todo for n in chunks}
        for f in as_completed(futures):
            a, n = futures[f]
            r = f.result()
            pts, games = results.get(a.key, (0.0, 0))
            results[a.key] = (pts + r["wins"] + 0.5 * r["draws"], games + r["games"])
            engines[a.key] = "python"
            with self.lock:
                self.done += n
        self.current = "goldfish games and sample hands"
        with _db_lock:
            a = assess(self.deck_name, self.counts, _card_db(True), goldfish_games=self.goldfish_games,
                       samples=self.samples, seed=rng.randrange(2**32), meta_results=results,
                       result_engines=engines)
        with self.lock:
            self.assessment = a

    def snapshot(self) -> dict:
        with self.lock:
            rank = None
            if self.tracker:
                d = self.tracker.to_dict()
                rank = {"html": render_fragment(d), "data": d}
            grades = None
            if self.assessment:
                grades = {"html": render_grades(self.assessment), "data": self.assessment,
                          "caveat": meta_caveat(self.assessment)}
        return {"rank": rank, "assessment": grades, "grade_error": self.grade_error,
                "reliability": self.assessment.get("reliability") if self.assessment else None,
                "meta_engine": self.meta_engine if self.forge_dir else "python",
                "deck": self.deck_name, "ladder": self.ladder, "pass_rate": self.pass_rate,
                "games_per_opponent": self.games, "done": self.done, "total": self.total,
                "current": self.current, "tiers": self.rows, "verdict": self.verdict}


def make_run(deck_name: str, text: str, tiers: list[str] | None, ladder: bool, games: int,
             full: bool = False, seed: int | None = None, grade: bool = True, meta_engine: str = "forge") -> Run:
    if not 2 <= games <= MAX_GAMES:
        raise ValueError(f"games per opponent must be between 2 and {MAX_GAMES}")
    chosen = TIERS if ladder and not tiers else resolve_tiers(tiers or [])
    if not chosen:
        raise ValueError("pick at least one tier")
    if meta_engine not in META_ENGINES:
        raise ValueError(f"meta engine must be one of {', '.join(META_ENGINES)}")
    return Run(deck_name or "my deck", parse_decklist(text), chosen, ladder, games, full, seed, grade=grade,
               meta_engine=meta_engine, forge_dir=forge_dir())


def make_pool(jobs: int | None = None) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=jobs or os.cpu_count() or 1)
