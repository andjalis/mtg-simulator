"""Objective deck assessment: one rating plus a breakdown by the criteria competitive players use.

    python3 -m mtgsim.assess MY_DECK.txt                       # all four criteria, built-in engine
    python3 -m mtgsim.assess MY_DECK.txt -n 50 --engine forge --forge-dir ~/forge
    python3 -m mtgsim.assess MY_DECK.txt --skip-meta --key "Sheoldred, the Apocalypse"
    python3 -m mtgsim.assess MY_DECK.txt --json results/assess/my_deck.json

The criteria:

* Meta: win rate against the top tournament decks, each weighted by its current meta share
  (data/metagame.json, with sources and date). This drives the MMR and rank: the meta field is
  the Grandmaster pool, and its games are reweighted by meta share before rating.performance_rating
  turns them into an MMR.
* Mana: Frank Karsten's method. For every coloured spell, the chance of having enough sources of
  each colour to cast it on curve (on the play, given enough lands), compared with his 90% target.
* Speed: goldfishing. The average turn the deck kills an opponent who does nothing.
* Consistency: sampled opening hands and draws, with the AI's own mulligan rule: mulligans, mana
  screw and flood, castable plays on turns 1 to 4, and key cards by turn N.

Each criterion has a 0-100 score and a grade (S, A, B, C, D, F). assess() returns plain JSON;
see its docstring for the shape.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .ai import HeuristicAI
from .carddb import CardDB
from .cards import COLORS, CardDef
from .decklist import load_deck, load_deck_full
from .engine import Game, Player
from .rating import RANKS, next_rank, performance_rating, rank_for
from .runner import build_deck, run_match, wilson

DECKS_DIR = Path(__file__).resolve().parent.parent / "decks"
METAGAME = Path(__file__).parent / "data" / "metagame.json"
META_RATING = RANKS[-1].anchor   # the meta field is the Grandmaster pool
CAST_TARGET = 0.90               # Karsten: cast the spell on curve at least 90% of the time
GRADES = [(90, "S"), (75, "A"), (60, "B"), (45, "C"), (30, "D"), (0, "F")]


def grade(score: float) -> str:
    return next(g for floor, g in GRADES if score >= floor)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _criterion(label: str, score: float, summary: str, details: dict) -> dict:
    score = round(_clamp(score))
    return {"label": label, "score": score, "grade": grade(score), "summary": summary, "details": details}


# ------------------------------------------------------------------ metagame
@dataclass
class Archetype:
    name: str
    path: Path
    share: dict      # source name -> percent of the metagame
    weight: float    # normalised over the archetypes found

    @property
    def key(self) -> str:
        return self.path.stem


def _find_deck(file: str, decks_dir: Path) -> Path | None:
    """The Grandmaster rank pool if it has the deck, else the old pro tier."""
    candidates = sorted(decks_dir.glob(f"ranks/*grandmaster*/{file}")) + [decks_dir / "tiers" / "5-pro" / file]
    return next((p for p in candidates if p.exists()), None)


def load_metagame(path: Path = METAGAME, decks_dir: Path = DECKS_DIR) -> tuple[dict, list[Archetype]]:
    """The metagame file and its archetypes whose decklists exist, weighted by mean meta share."""
    meta = json.loads(Path(path).read_text(encoding="utf-8"))
    found, missing = [], []
    for a in meta["archetypes"]:
        p = _find_deck(a["file"], Path(decks_dir))
        if p is None:
            missing.append(a["name"])
        else:
            found.append((a, p, statistics.mean(a["share"].values())))
    total = sum(s for _, _, s in found) or 1.0
    meta["missing"] = missing
    return meta, [Archetype(a["name"], p, a["share"], s / total) for a, p, s in found]


def meta_weighted_rows(results: list[tuple[str, float, float, int]],
                       weights: dict[str, float]) -> list[tuple[float, float, float]]:
    """Rows for rating.performance_rating with the meta field reweighted by meta share.

    results: (opponent key, opponent rating, points, games). Opponents whose key (or the part
    after the last "/", so ladder names like "grandmaster/jund_sacrifice" work) is in `weights`
    keep their total games between them, but each gets games in proportion to its weight and
    keeps its own score per game. Everyone else passes through unchanged. Feed the rows to
    performance_rating to get the meta-weighted MMR."""
    rows, field = [], []
    for key, rating, points, games in results:
        k = key if key in weights else key.rsplit("/", 1)[-1]
        if k in weights and games > 0:
            field.append((weights[k], rating, points / games, games))
        elif games > 0:
            rows.append((rating, points, games))
    total_games = sum(g for *_, g in field)
    total_w = sum(w for w, *_ in field)
    for w, rating, rate, _ in field:
        g = total_games * w / total_w
        rows.append((rating, rate * g, g))
    return rows


def assess_meta(name: str, archetypes: list[Archetype], results: dict[str, tuple[float, int]],
                meta: dict) -> tuple[dict, dict]:
    """results: archetype key -> (points, games). Returns (rating, criterion)."""
    played = [a for a in archetypes if results.get(a.key, (0, 0))[1] > 0]
    rows = meta_weighted_rows([(a.key, META_RATING, *results[a.key]) for a in played],
                              {a.key: a.weight for a in played})
    mmr = performance_rating(rows)
    w_total = sum(a.weight for a in played) or 1.0
    weighted = sum(a.weight / w_total * results[a.key][0] / results[a.key][1] for a in played)
    points = sum(results[a.key][0] for a in played)
    games = sum(results[a.key][1] for a in played)
    lo, hi = wilson(points, games)
    # spread of the weighted rate: each matchup's binomial variance, weighted
    var = sum((a.weight / w_total) ** 2 * (r := results[a.key][0] / results[a.key][1]) * (1 - r) / results[a.key][1]
              for a in played)
    rank, nxt = rank_for(mmr), next_rank(mmr)
    rating = {"mmr": round(mmr), "rank": rank.name, "rank_color": rank.color,
              "next_rank": nxt.name if nxt else None, "to_next": round(nxt.floor - mmr) if nxt else None,
              "basis": "meta-weighted win rate against the Grandmaster field"}
    matchups = [{"name": a.name, "key": a.key, "share": a.share, "weight": round(a.weight, 4),
                 "games": results.get(a.key, (0, 0))[1], "points": results.get(a.key, (0, 0))[0],
                 "win_rate": (results[a.key][0] / results[a.key][1]) if a in played else None}
                for a in archetypes]
    worst = min(played, key=lambda a: results[a.key][0] / results[a.key][1], default=None)
    summary = (f"{weighted:.0%} meta-weighted win rate against the top {len(played)} Standard decks"
               + (f"; weakest against {worst.name}" if worst else ""))
    details = {
        "weighted_win_rate": round(weighted, 4),
        "weighted_ci": [round(max(0.0, weighted - 1.96 * math.sqrt(var)), 4),
                        round(min(1.0, weighted + 1.96 * math.sqrt(var)), 4)],
        "unweighted_win_rate": round(points / games, 4) if games else None,
        "unweighted_ci": [round(lo, 4), round(hi, 4)],
        "games": games,
        "field_rating": META_RATING,
        "metagame": {"format": meta.get("format"), "date": meta.get("date"), "window": meta.get("window"),
                     "sources": meta.get("sources", []), "not_covered": meta.get("not_covered", []),
                     "missing_decklists": meta.get("missing", [])},
        "matchups": matchups,
    }
    # 1000 MMR (bottom of Silver) scores 0, 2200 (mid Grandmaster) scores 100
    return rating, _criterion("Meta", (mmr - 1000) / 12, summary, details)


# ------------------------------------------------------------------ sideboard / best of three
def assess_bo3(name: str, counts: dict[str, int], sideboard: dict[str, int], bring_in: dict[str, str],
               archetypes: list[Archetype], db: CardDB, matches: int, seed=None, say=lambda _: None) -> dict:
    """Bo3 matches with sideboarding against the meta field, weighted by meta share. The score is
    the weighted gain of post-board games over game 1."""
    from .sideboard import run_bo3, sideboard_score

    rows, no_sb = [], []
    for a in archetypes:
        say(f"bo3: {name} vs {a.name}")
        opp = load_deck_full(a.path)[1]
        if not opp.sideboard:
            no_sb.append(a.name)
        r = run_bo3(name, counts, sideboard, a.name, opp.main, opp.sideboard, db, matches, seed=seed,
                    bring_in_a=bring_in, bring_in_b=opp.bring_in)
        rows.append((a, r))
    w_total = sum(a.weight for a, _ in rows) or 1.0
    wavg = lambda f: sum(a.weight / w_total * f(r) for a, r in rows)
    gain = wavg(lambda r: r.sideboard_gain_a)
    match_rate = wavg(lambda r: r.match_win_rate_a)
    bo1_rate = wavg(lambda r: r.bo1_match_rate_a)
    summary = (f"{match_rate:.0%} meta-weighted Bo3 match win rate; sideboarding moves post-board games "
               f"{gain:+.0%} against game 1" + ("" if sideboard else " (no sideboard: opponents still board)"))
    details = {
        "match_win_rate": round(match_rate, 4),
        "match_win_rate_without_sideboarding": round(bo1_rate, 4),
        "sideboard_gain": round(gain, 4),
        "matches_per_deck": matches,
        "has_sideboard": bool(sideboard),
        "opponents_without_sideboard": no_sb,
        "engine": "python",
        "matchups": [{"name": a.name, "key": a.key, "weight": round(a.weight, 4), "matches": r.matches,
                      "match_win_rate": round(r.match_win_rate_a, 4), "game1_win_rate": round(r.g1_win_rate_a, 4),
                      "postboard_win_rate": round(r.post_win_rate_a, 4), "sideboard_gain": round(r.sideboard_gain_a, 4),
                      "opponent_archetype": r.plan_a.opponent_archetype, "ins": r.plan_a.ins, "outs": r.plan_a.outs}
                     for a, r in rows],
    }
    return _criterion("Sideboard", sideboard_score(gain), summary, details)


# ------------------------------------------------------------------ mana base (Karsten)
def color_pips(mana_cost: str) -> dict[str, int]:
    """Coloured pips that must be paid with that colour. Hybrid and Phyrexian symbols are left
    out: they can be paid another way."""
    out: dict[str, int] = {}
    for sym in re.findall(r"\{([^}]+)\}", (mana_cost or "").split(" // ")[0]):
        if sym in COLORS:
            out[sym] = out.get(sym, 0) + 1
    return out


def p_on_curve(deck_size: int, lands: int, sources: int, pips: int, turn: int, on_play: bool = True) -> float:
    """Chance of at least `pips` sources of a colour among the cards seen by `turn`, given at least
    `turn` lands among them (Karsten's condition: the question is colour, not land count)."""
    seen = 7 + turn - (1 if on_play else 0)
    total = math.comb(deck_size, seen)
    num = den = 0
    others = deck_size - lands
    for s in range(0, min(sources, seen) + 1):
        for o in range(0, min(lands - sources, seen - s) + 1):
            if s + o < turn or seen - s - o > others:
                continue
            p = math.comb(sources, s) * math.comb(lands - sources, o) * math.comb(others, seen - s - o)
            den += p
            if s >= pips:
                num += p
    return num / den if den else 0.0


def sources_needed(deck_size: int, lands: int, pips: int, turn: int, target: float = CAST_TARGET) -> int | None:
    """Fewest sources that cast the spell on curve with probability >= target (None: not even all lands)."""
    for s in range(pips, lands + 1):
        if p_on_curve(deck_size, lands, s, pips, turn) >= target:
            return s
    return None


def _raw(db: CardDB, name: str) -> dict:
    db.ensure([name])
    return db.raw[db._key(name)]


def land_colors(card: CardDef, raw: dict, basic_colors: set[str]) -> set[str]:
    """Colours a land can make, counting fetch lands as the basics they can find."""
    cols = set(card.produces) & set(COLORS)
    text = raw.get("oracle_text", "") or ""
    if re.search(r"search your library for an? basic land", text, re.I):
        cols |= basic_colors
    else:
        types = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
        m = re.search(r"search your library for an? ([A-Za-z ,]+?) card", text, re.I)
        if m:
            cols |= {c for t, c in types.items() if t in m[1]}
    return cols


def assess_mana(counts: dict[str, int], db: CardDB) -> dict:
    cards = {n: db.get(n) for n in counts}
    deck_size = sum(counts.values())
    land_names = [n for n, c in cards.items() if c.is_land]
    lands = sum(counts[n] for n in land_names)
    basic_colors = {next(iter(cards[n].produces)) for n in land_names
                    if "Basic" in _raw(db, n).get("type_line", "") and cards[n].produces}
    sources = {c: 0 for c in COLORS}
    for n in land_names:
        for c in land_colors(cards[n], _raw(db, n), basic_colors):
            sources[c] += counts[n]
    spells, weighted, copies = [], 0.0, 0
    for n, card in cards.items():
        if card.is_land:
            continue
        raw = _raw(db, n)
        cost = raw.get("mana_cost") or (raw.get("card_faces") or [{}])[0].get("mana_cost", "")
        pips = color_pips(cost)
        if not pips:
            continue
        turn = max(1, card.cmc + cost.count("{X}"))
        needs, worst = {}, 1.0
        for col, k in pips.items():
            p = p_on_curve(deck_size, lands, sources[col], k, turn) if lands >= turn else 0.0
            needs[col] = {"pips": k, "sources": sources[col], "required": sources_needed(deck_size, lands, k, turn),
                          "p_on_curve": round(p, 4)}
            worst = min(worst, p)
        spells.append({"name": n, "copies": counts[n], "cost": cost, "turn": turn, "p_on_curve": round(worst, 4),
                       "ok": worst >= CAST_TARGET, "needs": needs})
        # full credit at the 90% target, none at 60% or below
        weighted += counts[n] * _clamp((worst - 0.6) / (CAST_TARGET - 0.6), 0.0, 1.0)
        copies += counts[n]
    spells.sort(key=lambda s: s["p_on_curve"])
    colors = {}
    for col in COLORS:
        reqs = [(s["needs"][col]["required"], s["name"]) for s in spells if col in s["needs"]]
        if reqs:
            req, by = max(reqs, key=lambda r: (r[0] is None, r[0] or 0))
            colors[col] = {"sources": sources[col], "required": req, "for": by}
    score = 100 * weighted / copies if copies else 100.0
    short = [s for s in spells if not s["ok"]]
    if not short:
        summary = f"Every coloured spell meets Karsten's 90% on-curve target ({lands} lands)"
    else:
        names = ", ".join(f"{s['name']} {s['p_on_curve']:.0%}" for s in short[:3])
        summary = f"{len(short)} of {len(spells)} coloured spells miss the 90% on-curve target: {names}"
    return _criterion("Mana", score, summary, {
        "deck_size": deck_size, "lands": lands, "sources": {c: n for c, n in sources.items() if n},
        "colors": colors, "target": CAST_TARGET, "spells": spells,
        "method": "Karsten: P(enough coloured sources by the spell's turn on the play | enough lands); "
                  "land sources only, fetch lands count for the basics they find, hybrid pips ignored"})


# ------------------------------------------------------------------ speed (goldfish)
def goldfish(deck: list[CardDef], db: CardDB, games: int = 200, max_turns: int = 20,
             seed: int | None = None) -> list[int | None]:
    """Kill turn (the deck's own turn count, on the play) against an opponent who only plays lands.
    None when it hasn't won by max_turns."""
    rng = random.Random(seed)
    dummy = [db.get("Plains")] * 60
    out = []
    for _ in range(games):
        me, opp = Player("deck", deck, HeuristicAI()), Player("goldfish", dummy, HeuristicAI())
        game = Game(me, opp, rng=rng, max_turns=2 * max_turns)
        out.append((game.turn + 1) // 2 if game.play() is me else None)
    return out


def assess_speed(kills: list[int | None], max_turns: int = 20) -> dict:
    turns = [t if t is not None else max_turns + 1 for t in kills]
    avg = statistics.mean(turns) if turns else float(max_turns + 1)
    won = [t for t in kills if t is not None]
    by_turn = {str(t): round(sum(1 for k in won if k <= t) / len(kills), 4) for t in range(3, 11)} if kills else {}
    summary = (f"Kills a goldfish on turn {avg:.1f} on average"
               + (f", by turn 4 in {by_turn['4']:.0%} of games" if kills and by_turn["4"] >= 0.05 else ""))
    # turn 4 scores 100, turn 12 scores 0
    return _criterion("Speed", (12 - avg) / 8 * 100, summary, {
        "games": len(kills), "avg_kill_turn": round(avg, 2),
        "median_kill_turn": statistics.median(turns) if turns else None,
        "fastest": min(won) if won else None, "no_kill_rate": round(1 - len(won) / len(kills), 4) if kills else None,
        "kill_by_turn": by_turn, "max_turns": max_turns,
        "note": "against an opponent who does nothing, on the play; control decks are meant to be slow here"})


# ------------------------------------------------------------------ consistency
def _castable(card: CardDef, lands_in_play: list[CardDef]) -> bool:
    if card.cmc > len(lands_in_play):
        return False
    for col, k in card.mana_cost.items():
        if col in COLORS and sum(col in l.produces for l in lands_in_play) < k:
            return False
    return True


def assess_consistency(deck: list[CardDef], samples: int = 20000, key_cards: list[str] | None = None,
                       seed: int | None = None) -> dict:
    """Sample opening hands (with the AI's mulligan and bottom rules) and the next draws, on the play."""
    rng = random.Random(seed)
    ai = HeuristicAI()
    names = {c.name for c in deck}
    if not key_cards:
        copies = {}
        for c in deck:
            if not c.is_land:
                copies[c.name] = copies.get(c.name, 0) + 1
        top = max(copies.values(), default=0)
        key_cards = sorted(n for n, k in copies.items() if k == top)
    key_cards = [k for k in key_cards if k in names]
    mull = [0, 0, 0]
    screw = flood = functional = 0
    play_on = {t: 0 for t in range(1, 5)}
    key_by = {k: {t: 0 for t in range(1, 5)} for k in key_cards}
    any_key_t3 = 0
    for _ in range(samples):
        m = 0
        while True:
            lib = list(deck)
            rng.shuffle(lib)
            hand, lib = lib[:7], lib[7:]
            if m >= 2 or ai.keep_hand(hand, m):
                break
            m += 1
        for c in ai.cards_to_bottom(hand, m):
            hand.remove(c)
        mull[min(m, 2)] += 1

        def seen(t):
            return hand + lib[:t - 1]

        by4 = sum(c.is_land for c in seen(4))
        s6 = seen(6)
        is_screwed = by4 < 3
        is_flooded = sum(c.is_land for c in s6) >= math.ceil(0.55 * len(s6))
        screw += is_screwed
        flood += is_flooded
        functional += m <= 1 and not is_screwed and not is_flooded
        for t in range(1, 5):
            cards = seen(t)
            lands = [c for c in cards if c.is_land][:t]
            if any(not c.is_land and c.cmc == t and _castable(c, lands) for c in cards):
                play_on[t] += 1
            for k in key_cards:
                key_by[k][t] += any(c.name == k for c in cards)
        any_key_t3 += any(c.name in key_cards for c in seen(3))
    n = samples
    f = functional / n
    summary = (f"{f:.0%} of games start functional (kept 7 or 6, not screwed or flooded); "
               f"mulligan {1 - mull[0] / n:.0%}, screw {screw / n:.0%}, flood {flood / n:.0%}")
    # 55% functional scores 0, 85% scores 100
    return _criterion("Consistency", (f - 0.55) / 0.30 * 100, summary, {
        "samples": n, "functional_rate": round(f, 4),
        "mulligan_rate": round(1 - mull[0] / n, 4), "mulligan_to_5_rate": round(mull[2] / n, 4),
        "screw_rate": round(screw / n, 4), "flood_rate": round(flood / n, 4),
        "curve": {str(t): round(v / n, 4) for t, v in play_on.items()},
        "key_cards": [{"name": k, "by_turn": {str(t): round(v / n, 4) for t, v in key_by[k].items()}} for k in key_cards],
        "any_key_card_by_turn_3": round(any_key_t3 / n, 4) if key_cards else None,
        "definitions": {
            "screw": "fewer than 3 lands among the cards seen by turn 4",
            "flood": "at least 55% lands among the cards seen by turn 6",
            "functional": "kept 7 or 6 cards, not screwed, not flooded",
            "curve": "chance of a castable spell costing exactly N on turn N (lands seen, capped at N)",
            "key_cards": "chance of at least one copy among the cards seen by turn N",
        }})


# ------------------------------------------------------------------ everything
def assess(name: str, counts: dict[str, int], db: CardDB | None = None, games: int = 100,
           goldfish_games: int = 200, samples: int = 20000, key_cards: list[str] | None = None,
           seed: int | None = None, metagame: Path = METAGAME, decks_dir: Path = DECKS_DIR,
           meta_results: dict[str, tuple[float, int]] | None = None, skip_meta: bool = False,
           play=None, progress=None, bo3: int = 0, sideboard: dict[str, int] | None = None,
           bring_in: dict[str, str] | None = None) -> dict:
    """Rate a deck. Returns plain JSON:

        {"deck", "assessed" (ISO date), "format",
         "rating": {"mmr", "rank", "rank_color", "next_rank", "to_next", "basis"} or None if skip_meta,
         "criteria": {"meta" | "sideboard" (only with bo3) | "mana" | "speed" | "consistency":
                      {"label", "score" 0-100, "grade" S/A/B/C/D/F, "summary" (one sentence), "details"}}}

    meta_results (archetype key -> (points, games)) reuses games already played, e.g. on the
    ladder; otherwise every archetype is played with play(name, deck, opp_name, opp_counts) ->
    (points, games), which defaults to the built-in engine. progress(text) is told what's running.
    bo3 > 0 also plays that many best-of-three matches with sideboards against each meta deck
    (built-in engine) and adds the "sideboard" criterion; see mtgsim.sideboard.
    """
    db = db or CardDB()
    say = progress or (lambda _: None)
    deck = build_deck(db, counts)
    criteria, rating, meta = {}, None, {}
    if not skip_meta:
        meta, archetypes = load_metagame(metagame, decks_dir)
        results = dict(meta_results or {})
        partial = set()
        for a in archetypes:
            if a.key in results:
                continue
            say(f"meta: {name} vs {a.name} ({a.weight:.0%} of the field)")
            opp_counts = load_deck(a.path)[1]
            if play:
                results[a.key] = play(name, counts, a.name, opp_counts)
            else:
                opp = build_deck(db, opp_counts)
                partial |= {c.name for c in opp if c.unsupported}
                res, _ = run_match(name, deck, a.name, opp, games=games, seed=seed)
                results[a.key] = (res.wins_a + 0.5 * res.draws, res.games)
        rating, criteria["meta"] = assess_meta(name, archetypes, results, meta)
        criteria["meta"]["details"]["engine"] = "given" if meta_results and not partial else (
            "forge" if play else "python")
        criteria["meta"]["details"]["partial_opponent_cards"] = len(partial)
    if bo3 and not skip_meta:
        criteria["sideboard"] = assess_bo3(name, counts, sideboard or {}, bring_in or {}, archetypes, db,
                                           bo3, seed=seed, say=say)
    say("mana base")
    criteria["mana"] = assess_mana(counts, db)
    say("goldfish")
    criteria["speed"] = assess_speed(goldfish(deck, db, goldfish_games, seed=seed))
    say("consistency")
    criteria["consistency"] = assess_consistency(deck, samples, key_cards, seed=seed)
    return {"deck": name, "assessed": date.today().isoformat(), "format": meta.get("format", "Standard"),
            "rating": rating, "criteria": criteria}


def text_report(a: dict) -> str:
    out = [f"{a['deck']}: deck assessment ({a['assessed']})"]
    r = a["rating"]
    if r:
        nxt = f", {r['to_next']} MMR to {r['next_rank']}" if r["next_rank"] else ""
        out.append(f"  Rank {r['rank']}, MMR {r['mmr']}{nxt} ({r['basis']})")
    for c in a["criteria"].values():
        out.append(f"  {c['label']:<12} {c['score']:>3}  {c['grade']}  {c['summary']}")
    meta = a["criteria"].get("meta")
    if meta:
        out.append("  Matchups (meta weight, win rate):")
        for m in meta["details"]["matchups"]:
            wr = f"{m['win_rate']:.0%} of {m['games']}" if m["win_rate"] is not None else "not played"
            out.append(f"    {m['name']:<26} {m['weight']:5.1%}  {wr}")
        if meta["details"].get("partial_opponent_cards"):
            out.append(f"  Note: the built-in engine ignores some text on {meta['details']['partial_opponent_cards']} "
                       "of the meta decks' cards; --engine forge plays them fully")
        md = meta["details"]["metagame"]
        out.append(f"  Metagame of {md['date']} ({md['window']}): " + ", ".join(s["name"] for s in md["sources"]))
    sb = a["criteria"].get("sideboard")
    if sb:
        out.append("  Best of three (match win rate, game 1 -> post-board):")
        for m in sb["details"]["matchups"]:
            out.append(f"    {m['name']:<26} {m['match_win_rate']:4.0%}  {m['game1_win_rate']:.0%} -> "
                       f"{m['postboard_win_rate']:.0%}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mtgsim.assess", description="Rate a deck on meta win rate, mana, speed "
                                                                   "and consistency.")
    ap.add_argument("deck", help="decklist text file")
    ap.add_argument("-n", "--games", type=int, default=100, help="games against each meta deck (default 100)")
    ap.add_argument("--goldfish", type=int, default=200, help="goldfish games (default 200)")
    ap.add_argument("--samples", type=int, default=20000, help="sampled hands for consistency (default 20000)")
    ap.add_argument("--key", action="append", metavar="CARD",
                    help="a key card to track by turn N (repeatable; default: the deck's most-played spells)")
    ap.add_argument("--bo3", type=int, default=0, metavar="N",
                    help="also play N best-of-three matches with sideboards against each meta deck")
    ap.add_argument("--skip-meta", action="store_true", help="skip the meta games (no MMR or rank)")
    ap.add_argument("--metagame", default=str(METAGAME), help="metagame JSON (default mtgsim/data/metagame.json)")
    ap.add_argument("--json", metavar="PATH", help="also write the assessment as JSON")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-history", action="store_true",
                    help="don't save the assessment to the deck's history (python3 -m mtgsim.history)")
    ap.add_argument("--offline", action="store_true", help="don't fetch unknown cards from Scryfall")
    ap.add_argument("--engine", choices=["python", "forge"], default="python",
                    help="engine for the meta games; goldfishing always uses the built-in engine")
    ap.add_argument("--forge-dir", help="Forge install folder (or set FORGE_HOME)")
    ap.add_argument("--java", default="java")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--clock", type=int, default=120)
    args = ap.parse_args(argv)

    name, full = load_deck_full(args.deck)
    counts = full.main
    play = None
    if args.engine == "forge":
        from .forge import ForgeError, run_forge_match

        def play(a, a_counts, b, b_counts):
            try:
                res = run_forge_match(a, a_counts, b, b_counts, games=args.games, seed=args.seed,
                                      forge_dir=args.forge_dir, java=args.java, clock=args.clock, jobs=args.jobs)
            except ForgeError as e:
                sys.exit(f"Forge: {e}")
            return res.wins_a + 0.5 * res.draws, res.games
    try:
        result = assess(name, counts, CardDB(offline=args.offline), games=args.games, goldfish_games=args.goldfish,
                        samples=args.samples, key_cards=args.key, seed=args.seed, metagame=Path(args.metagame),
                        skip_meta=args.skip_meta, play=play, bo3=args.bo3, sideboard=full.sideboard,
                        bring_in=full.bring_in,
                        progress=lambda s: print(f"  {s}...", file=sys.stderr, flush=True))
    except KeyError as e:
        sys.exit(f"{name}: {e}")
    print(text_report(result))
    if not args.no_history:
        from . import history
        history.try_record(history.record_assessment, result, counts, engine=args.engine, source="cli")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
