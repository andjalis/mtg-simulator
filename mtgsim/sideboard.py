"""Best-of-three matches with sideboarding, and how much sideboarding helps.

    python3 -m mtgsim.sideboard MY_DECK.txt OPPONENT.txt -n 50     # 50 Bo3 matches
    python3 -m mtgsim.sideboard MY_DECK.txt OPPONENT.txt --plan    # just show both sideboard plans

Game 1 of each match is played with the main decks. Before game 2 each side reads the
opponent's main deck, labels it aggro, midrange or control, and swaps up to MAX_SWAPS cards
with a rule-based plan: every card gets a value against that archetype from what its rules text
does (sweepers and cheap removal come in against aggro, discard and narrow counters against
control, and so on), plus a bonus for a "Bring in vs." note in the decklist. A sideboard card
replaces a main-deck spell only when it is clearly better; lands are never swapped. The loser of
each game is on the play in the next one.

The sideboard score compares post-board games (2 and 3) with game 1, on the play and on the draw
separately: that gain is what the sideboard and the plan are worth in this matchup. A deck without a sideboard still plays games 2
and 3 against a sideboarded opponent, so its gain is usually negative.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass, field

from .ai import HeuristicAI
from .carddb import CardDB
from .cards import CardDef
from .decklist import load_deck_full
from .engine import Game, Player
from .runner import build_deck, wilson

MAX_SWAPS = 6
MAIN_DECK_BONUS = 1.0   # a sideboard card must beat the card it replaces by more than this
ARCHETYPES = ("aggro", "midrange", "control")
NOTE_WORDS = {"aggro": ("aggro", "aggressive", "creature", "burn", "go-wide", "go wide"),
              "midrange": ("midrange", "grindy", "grind", "value"),
              "control": ("control", "grindy", "grind", "counter", "durdle")}

SWEEPER = re.compile(r"destroy all creatures|destroy all (?:nonland )?permanents|exile all creatures|"
                     r"each creature|all creatures get -|creatures your opponents control get -|damage to each creature|"
                     r"each creature with mana value", re.I)
REMOVAL = re.compile(r"(?:destroy|exile) target (?:\w+ )?(?:creature|nonland permanent|permanent)|"
                     r"damage to (?:any target|target creature|target attacking)|target creature gets -|"
                     r"fights? (?:target|up to one)|target (?:player|opponent) sacrifices", re.I)
COUNTER = re.compile(r"counter target", re.I)
NARROW_COUNTER = re.compile(r"counter target (?:noncreature|instant|sorcery|planeswalker|activated)", re.I)
DISCARD = re.compile(r"reveals? (?:their|his or her) hand|target (?:player|opponent) discards|"
                     r"each opponent discards", re.I)
LIFEGAIN = re.compile(r"you gain \d+ life|gain life equal|you gain life", re.I)
DRAW = re.compile(r"draws? (?:a|two|three|four|x|\d+) cards?", re.I)
RESILIENT = re.compile(r"can't be countered|hexproof|ward|haste|flash", re.I)


def roles(card: CardDef) -> set[str]:
    text = card.oracle or ""
    out = set()
    if SWEEPER.search(text):
        out.add("sweeper")
    if REMOVAL.search(text):
        out.add("removal")
    if NARROW_COUNTER.search(text):
        out.add("narrow_counter")
    elif COUNTER.search(text):
        out.add("counter")
    if DISCARD.search(text):
        out.add("discard")
    if LIFEGAIN.search(text) or "Lifelink" in card.keywords:
        out.add("lifegain")
    if DRAW.search(text):
        out.add("draw")
    if "Creature" in card.types:
        out.add("creature")
    if "Planeswalker" in card.types:
        out.add("planeswalker")
    if RESILIENT.search(text) or card.keywords & {"Haste", "Hexproof", "Flash"} or card.ward:
        out.add("resilient")
    return out


def classify(deck: list[CardDef]) -> str:
    """aggro, midrange or control, from the curve and the creature count."""
    spells = [c for c in deck if "Land" not in c.types]
    if not spells:
        return "midrange"
    avg = sum(c.cmc for c in spells) / len(spells)
    creatures = sum("Creature" in c.types for c in spells)
    burn = sum(bool(re.search(r"damage to any target|damage to each opponent|damage to target player", c.oracle or ""))
               and "Creature" not in c.types for c in spells)
    if avg <= 2.6 and (creatures >= 14 or creatures + burn >= 22):
        return "aggro"
    if creatures <= 10:
        return "control"
    return "midrange"


def card_value(card: CardDef, opp: str, note: str = "") -> float:
    """How much a card is worth against an archetype, on a rough scale where 0 is filler."""
    r = roles(card)
    v = 0.0
    if opp == "aggro":
        if "sweeper" in r:
            v += 3 + (card.cmc <= 3)
        if "removal" in r:
            v += 2 + (card.cmc <= 2) - (card.cmc >= 4)
        if "lifegain" in r:
            v += 1.5
        if "creature" in r and (card.toughness or 0) >= 3 and card.cmc <= 3:
            v += 1
        if "discard" in r:
            v -= 1.5
        if r & {"counter", "narrow_counter"}:
            v -= 1 if card.cmc >= 3 else 0.5
        if r == {"draw"} or (card.cmc >= 6 and "sweeper" not in r):
            v -= 1
    elif opp == "control":
        if "discard" in r:
            v += 3
        if "narrow_counter" in r:
            v += 3
        if "counter" in r:
            v += 2
        if "draw" in r:
            v += 1
        if r & {"creature", "planeswalker"}:
            v += 0.5 + 1.5 * ("resilient" in r) + (card.cmc <= 3)
        if "sweeper" in r:
            v -= 3
        if "removal" in r and "sweeper" not in r:
            v -= 1
        if "lifegain" in r and not r & {"creature", "draw"}:
            v -= 1.5
    else:
        if "removal" in r:
            v += 1.5
        if "draw" in r:
            v += 1
        if "planeswalker" in r:
            v += 1.5
        v += 0.5 * len(r & {"sweeper", "discard", "counter"})
    note = note.lower()
    if note:
        if any(w in note for w in NOTE_WORDS[opp]):
            v += 2.5
        elif any(w in note for a in ARCHETYPES for w in NOTE_WORDS[a]):
            v -= 1
    return v


@dataclass
class Plan:
    opponent_archetype: str
    ins: dict[str, int] = field(default_factory=dict)
    outs: dict[str, int] = field(default_factory=dict)
    deck: dict[str, int] = field(default_factory=dict)

    def describe(self) -> str:
        if not self.ins:
            return f"vs {self.opponent_archetype}: no changes"
        fmt = lambda d: ", ".join(f"{n} {c}" for c, n in d.items())
        return f"vs {self.opponent_archetype}: in {fmt(self.ins)}; out {fmt(self.outs)}"


def plan_sideboard(main: dict[str, int], sideboard: dict[str, int], db: CardDB, opp: str,
                   bring_in: dict[str, str] | None = None, max_swaps: int = MAX_SWAPS) -> Plan:
    """Swap sideboard copies for main-deck spells, best gain first, one copy at a time."""
    bring_in = bring_in or {}
    db.ensure({**main, **sideboard})
    sb = sorted(((card_value(db.get(c), opp, bring_in.get(c, "")), c)
                 for c, n in sideboard.items() for _ in range(n)), reverse=True)
    md = sorted((card_value(db.get(c), opp) + MAIN_DECK_BONUS, c)
                for c, n in main.items() if "Land" not in db.get(c).types for _ in range(n))
    plan = Plan(opp, deck=dict(main))
    for (v_in, c_in), (v_out, c_out) in zip(sb, md):
        if sum(plan.ins.values()) >= max_swaps or v_in <= v_out:
            break
        plan.ins[c_in] = plan.ins.get(c_in, 0) + 1
        plan.outs[c_out] = plan.outs.get(c_out, 0) + 1
        plan.deck[c_in] = plan.deck.get(c_in, 0) + 1
        plan.deck[c_out] -= 1
        if not plan.deck[c_out]:
            del plan.deck[c_out]
    return plan


# ------------------------------------------------------------------ best of three
@dataclass
class Bo3Result:
    deck_a: str
    deck_b: str
    plan_a: Plan | None = None
    plan_b: Plan | None = None
    matches: int = 0
    match_wins_a: int = 0
    match_draws: int = 0            # matches tied 1-1 with a drawn game, or all games drawn
    g1_games: int = 0
    g1_points_a: float = 0.0        # draws count half
    post_games: int = 0
    post_points_a: float = 0.0
    # (post-board?, A on the play?) -> [points, games], to compare like with like
    split: dict = field(default_factory=dict)

    # wins_a, wins_b, draws and games count matches, so a Bo3Result can stand in for a
    # runner.MatchResult (the ladder and LadderTracker read these four)
    @property
    def wins_a(self) -> int:
        return self.match_wins_a

    @property
    def wins_b(self) -> int:
        return self.matches - self.match_wins_a - self.match_draws

    @property
    def draws(self) -> int:
        return self.match_draws

    @property
    def games(self) -> int:
        return self.matches

    @property
    def match_win_rate_a(self) -> float:
        return (self.match_wins_a + 0.5 * self.match_draws) / self.matches if self.matches else 0.0

    @property
    def g1_win_rate_a(self) -> float:
        return self.g1_points_a / self.g1_games if self.g1_games else 0.0

    @property
    def post_win_rate_a(self) -> float:
        return self.post_points_a / self.post_games if self.post_games else 0.0

    @property
    def sideboard_gain_a(self) -> float:
        """Post-board game win rate minus game-1 win rate, on the play and on the draw separately
        and then averaged: the loser of a game goes first in the next, so post-board games lean
        toward the weaker deck being on the play, which a plain difference would count as a loss."""
        if not self.post_games:
            return 0.0
        diffs = []
        for on_play in (True, False):
            g1, post = self.split.get((False, on_play)), self.split.get((True, on_play))
            if g1 and post and g1[1] and post[1]:
                diffs.append(post[0] / post[1] - g1[0] / g1[1])
        return sum(diffs) / len(diffs) if diffs else self.post_win_rate_a - self.g1_win_rate_a

    @property
    def bo1_match_rate_a(self) -> float:
        """The Bo3 match win rate if every game were played at the game-1 rate (no sideboarding)."""
        p = self.g1_win_rate_a
        return p * p * (3 - 2 * p)

    def summary(self) -> str:
        lo, hi = wilson(self.match_wins_a + 0.5 * self.match_draws, self.matches)
        lines = [f"{self.deck_a} vs {self.deck_b}: {self.matches} best-of-three matches",
                 f"  {self.deck_a} match win rate {self.match_win_rate_a:.1%} (95% CI {lo:.1%} to {hi:.1%}); "
                 f"{self.bo1_match_rate_a:.1%} expected without sideboarding",
                 f"  game 1 {self.g1_win_rate_a:.1%} of {self.g1_games}, post-board {self.post_win_rate_a:.1%} "
                 f"of {self.post_games}: sideboarding {self.sideboard_gain_a:+.1%} (play/draw matched)"]
        for name, p in ((self.deck_a, self.plan_a), (self.deck_b, self.plan_b)):
            if p is not None:
                lines.append(f"  {name} {p.describe()}")
        return "\n".join(lines)


def run_bo3(name_a: str, main_a: dict[str, int], side_a: dict[str, int],
            name_b: str, main_b: dict[str, int], side_b: dict[str, int],
            db: CardDB, matches: int = 50, seed=None, bring_in_a=None, bring_in_b=None,
            on_match=None) -> Bo3Result:
    rng = random.Random(seed)
    g1_a, g1_b = build_deck(db, main_a), build_deck(db, main_b)
    plan_a = plan_sideboard(main_a, side_a, db, classify(g1_b), bring_in_a)
    plan_b = plan_sideboard(main_b, side_b, db, classify(g1_a), bring_in_b)
    post_a, post_b = build_deck(db, plan_a.deck), build_deck(db, plan_b.deck)
    def outside(side, plan):
        counts = dict(side)
        for name, n in plan.ins.items():
            counts[name] -= n
        for name, n in plan.outs.items():
            counts[name] = counts.get(name, 0) + n
        return build_deck(db, {name: n for name, n in counts.items() if n > 0})
    side1_a, side1_b = build_deck(db, side_a), build_deck(db, side_b)
    side2_a, side2_b = outside(side_a, plan_a), outside(side_b, plan_b)
    res = Bo3Result(name_a, name_b, plan_a, plan_b)
    for m in range(matches):
        a_on_play = m % 2 == 0
        score_a = score_b = 0.0
        game_no = 0
        while score_a < 2 and score_b < 2 and game_no < 3:
            deck_a, deck_b = (g1_a, g1_b) if game_no == 0 else (post_a, post_b)
            a = Player(name_a, deck_a, HeuristicAI(), sideboard=side1_a if game_no == 0 else side2_a)
            b = Player(name_b, deck_b, HeuristicAI(), sideboard=side1_b if game_no == 0 else side2_b)
            winner = Game(*((a, b) if a_on_play else (b, a)), rng=rng).play()
            pts = 1.0 if winner is a else 0.0 if winner is b else 0.5
            score_a += pts
            score_b += 1 - pts
            cell = res.split.setdefault((game_no > 0, a_on_play), [0.0, 0])
            cell[0] += pts
            cell[1] += 1
            if game_no == 0:
                res.g1_games += 1
                res.g1_points_a += pts
            else:
                res.post_games += 1
                res.post_points_a += pts
            if pts != 0.5:
                a_on_play = pts == 0.0   # the loser chooses to play
            game_no += 1
        res.matches += 1
        if score_a > score_b:
            res.match_wins_a += 1
        elif score_a == score_b:
            res.match_draws += 1
        if on_match:
            on_match(res)
    return res


def sideboard_score(gain: float) -> float:
    """0-100: no change scores 50, +12.5 points of post-board win rate scores 100."""
    return 50 + 400 * gain


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mtgsim.sideboard", description="Best-of-three matches with sideboarding.")
    ap.add_argument("deck_a")
    ap.add_argument("deck_b")
    ap.add_argument("-n", "--matches", type=int, default=50)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--plan", action="store_true", help="only print the sideboard plans")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)
    db = CardDB(offline=args.offline)
    (na, a), (nb, b) = load_deck_full(args.deck_a), load_deck_full(args.deck_b)
    for name, d in ((na, a), (nb, b)):
        if not d.sideboard:
            print(f"Note: {name} has no sideboard; it plays its main deck in every game", file=sys.stderr)
    if args.plan:
        arch_a, arch_b = classify(build_deck(db, a.main)), classify(build_deck(db, b.main))
        print(f"{na} ({arch_a}) {plan_sideboard(a.main, a.sideboard, db, arch_b, a.bring_in).describe()}")
        print(f"{nb} ({arch_b}) {plan_sideboard(b.main, b.sideboard, db, arch_a, b.bring_in).describe()}")
        return
    res = run_bo3(na, a.main, a.sideboard, nb, b.main, b.sideboard, db, args.matches, args.seed,
                  a.bring_in, b.bring_in)
    print(res.summary())


if __name__ == "__main__":
    main()
