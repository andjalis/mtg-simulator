"""Verification harness for per-card translations (mtgsim.translated).

Each translated card gets a scenario test that states, from the Oracle text alone, the observable outcome of
using the card on a concrete board, then drives the real engine (fixed seed) and asserts it. ``Scenario``
builds the board; ``smoke`` plays seeded HeuristicAI games with the card in the deck and records every effect
the card resolved, so a test can check that the AI used it without errors and aimed hostile effects at the
opponent. scripts/translate_verify.py runs the file checks, these tests and the smoke games together.
"""
from __future__ import annotations

import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Permanent, Player

DB_FILE = Path(__file__).resolve().parents[2] / "mtgsim" / "data" / "cards.sqlite3"
_DB = None


def db():
    global _DB
    if _DB is None:
        from mtgsim.carddb import CardDB
        _DB = CardDB(offline=True)
    return _DB


def basic(name):
    sub = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}[name]
    return card_from_scryfall({"name": name, "mana_cost": "", "cmc": 0, "type_line": f"Basic Land — {name}",
                               "oracle_text": f"({{T}}: Add {{{sub}}}.)"})


LAND_OF = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
BEAR = card_from_scryfall({"name": "Grizzly Bears", "mana_cost": "{1}{G}", "cmc": 2,
                           "type_line": "Creature — Bear", "oracle_text": "", "power": "2", "toughness": "2"})


def vanilla(name="Test Bear", power=2, toughness=2, cost="{1}{G}", types="Creature — Bear", text=""):
    return card_from_scryfall({"name": name, "mana_cost": cost, "cmc": sum(int(x) if x.isdigit() else 1 for x in
                               cost.strip("{}").split("}{") if x), "type_line": types, "oracle_text": text,
                               "power": str(power), "toughness": str(toughness)})


HOSTILE = {"damage", "destroy", "debuff", "debuff_one", "discard", "discard_choice", "bounce", "exile", "tap",
           "lose_life", "mill", "sacrifice", "edict", "fight", "steal", "gain_control", "counter", "wrath"}


class Scenario(unittest.TestCase):
    """Board helpers around a two-player Game. ``a`` is "you" (active, main phase 1), ``b`` the opponent."""
    seed = 0

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(self.seed), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [basic("Island")] * 20

    # ---------------------------------------------------------------- cards
    def translated(self, name):
        """The database card, which must load as a translated card."""
        from mtgsim.coverage import card_coverage
        c = db().get(name)
        self.assertEqual(card_coverage(c).status, "full (translated)", (name, card_coverage(c).ignored))
        return c

    def get(self, name):
        return db().get(name)

    # ---------------------------------------------------------------- board
    def put(self, c, who=None, tapped=False, counters=None, sick=False):
        """A permanent placed directly (no enters-the-battlefield triggers)."""
        who = who or self.a
        c = self.get(c) if isinstance(c, str) else c
        x = Permanent(c, who)
        x.tapped = tapped
        if not sick:
            x.sick = False
        for k, v in (counters or {}).items():
            x.counters[k] = v
        who.battlefield.append(x)
        return x

    def enter(self, c, who=None):
        """A permanent entering the battlefield for real (its triggers go on the stack and resolve)."""
        who = who or self.a
        c = self.get(c) if isinstance(c, str) else c
        x = self.game.enter_battlefield(who, c)
        self.game.settle()
        return x

    def lands(self, colors, who=None):
        """Untapped basic lands: lands("RR2") gives two Mountains and two Islands."""
        who = who or self.a
        out = []
        for ch in colors:
            if ch.isdigit():
                out += [self.put(basic("Island"), who) for _ in range(int(ch))]
            else:
                out.append(self.put(basic(LAND_OF[ch]), who))
        return out

    def to_hand(self, c, who=None):
        who = who or self.a
        c = self.get(c) if isinstance(c, str) else c
        who.hand.append(c)
        return c

    # ---------------------------------------------------------------- actions
    def cast(self, c, targets=None, who=None):
        who = who or self.a
        c = self.to_hand(c, who)
        ok = self.game.cast(who, c, targets)
        self.game.settle()
        return ok

    def activate(self, perm, idx=0, targets=None, who=None, **kw):
        who = who or self.a
        if targets is not None:      # one entry per effect: a shorter list would drop the later effects
            targets = list(targets) + [None] * (len(perm.activated[idx].effects) - len(targets))
        ok = self.game.activate_ability(who, perm, idx, targets, **kw)
        self.game.settle()
        return ok

    def loyalty(self, perm, idx, targets=None, who=None):
        who = who or self.a
        ok = self.game.activate_loyalty(who, perm, idx, targets)
        self.game.settle()
        return ok

    def end_step(self, who=None):
        self.game.step = "end"
        self.game.begin_end_step(who or self.a)
        self.game.settle()

    def upkeep(self, who=None):
        self.game.step = "upkeep"
        self.game.begin_upkeep(who or self.a)
        self.game.settle()

    def fire(self, event, who=None, **kw):
        self.game.fire(who or self.a, event, **kw)
        self.game.settle()

    # ---------------------------------------------------------------- reads
    @staticmethod
    def names(zone):
        return sorted(getattr(c, "name", None) or c.card.name for c in zone)

    def creature_names(self, who):
        return sorted(x.card.name for x in who.creatures)


def smoke(name, games=3, turns=12, seed=1):
    """Seeded HeuristicAI games with 4 copies of the card in a 40-card two-colour-matching deck against a
    deck of vanilla creatures. Returns a dict: errors (exception strings), uses (effect kind, whose target),
    hostile_at_self (hostile effects of the card that targeted its controller or their permanents)."""
    card = db().get(name)
    colors = sorted(card.colors) or ["G"]
    lands = [basic(LAND_OF[c]) for c in colors]
    filler = vanilla("Smoke Bear", 2, 2, "{1}{" + colors[0] + "}")
    deck = [card] * 4 + [lands[i % len(lands)] for i in range(17)] + [filler] * 19
    opp_deck = [basic("Forest")] * 17 + [BEAR] * 23
    out = {"errors": [], "uses": [], "hostile_at_self": [], "games": games}
    orig = Game.resolve

    def resolve(self, p, eff, target, item=None, prev=None):
        src = item.card.name if item is not None and item.card is not None else (
            item.source.card.name if item is not None and isinstance(item.source, Permanent) else None)
        if src == card.name or (item is not None and item.name.startswith(card.name)):
            whose = ("self" if target is p or isinstance(target, Permanent) and target.controller is p else
                     "opp" if target is not None and self.hostile_target(p, target) else
                     "none" if target is None else "other")
            out["uses"].append((eff.kind, whose))
            if eff.kind in HOSTILE and whose == "self" and eff.target not in ("self", "creature_mine"):
                out["hostile_at_self"].append(eff.kind)
        return orig(self, p, eff, target, item, prev)

    Game.resolve = resolve
    try:
        for i in range(games):
            a = Player("a", list(deck), HeuristicAI())
            b = Player("b", list(opp_deck), HeuristicAI())
            g = Game(a, b, random.Random(seed + i), max_turns=turns)
            try:
                g.play()
            except Exception as exc:       # noqa: BLE001 - a smoke test reports every failure
                out["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        Game.resolve = orig
    return out
