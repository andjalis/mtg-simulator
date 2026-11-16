"""#327 slice: counter placement composed with
- the selector predicate "that entered (the battlefield) this turn" (Permanent.entered_turn), for groups and
  targets alike ("each green creature that entered this turn", "target creature that entered this turn");
- "put N <kind> counters on ~ for each <thing>" read through the grammar's count reader when the template's own
  quantities don't know the phrase ("artifact and/or creature card in your graveyard", domain)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.permanent_templates import selector

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


class Parse(unittest.TestCase):
    def test_entered_selector(self):
        self.assertEqual(selector("creatures you control that entered this turn", plural=True),
                         {"entered_turn": True, "controller": "mine", "types_all": ["creature"]})
        self.assertEqual(selector("green creatures that entered the battlefield this turn", plural=True),
                         {"entered_turn": True, "colors": ["G"], "types_all": ["creature"]})
        # the controller it entered under isn't recorded: refused, not read as "you control now"
        self.assertIsNone(selector("creatures that entered the battlefield under your control this turn", plural=True))
        self.assertIsNone(selector("creatures that entered this turn with flying", plural=True))

    def test_counter_for_each_on_self(self):
        for text, xq in (("Put a +1/+1 counter on ~ for each artifact and/or creature card in your graveyard.",
                          ("cxq", "cards", "your_gy", {"any": ["artifact", "creature"]})),
                         ("Put a +1/+1 counter on ~ for each basic land type among lands you control.", ("domain",))):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertEqual((effects[0].kind, effects[0].target, effects[0].data["xq"]), ("add_counter", "self", xq))

    def test_refusals(self):
        # ("... for each creature destroyed this way" is read since #576: the destroy just before it, checked in a game)
        for text in ("Put a +1/+1 counter on ~ for each frob you control.",
                     "Put a +1/+1 counter on ~ for each creature card exiled this way.",
                     "Put a +1/+1 counter on each creature that entered the battlefield under your control this turn."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [text], text)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Games(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [self.db.get("Island")] * 20

    def enter(self, p, name, turn=None):
        perm = self.game.enter_battlefield(p, self.db.get(name))
        self.game.settle()
        if turn is not None:
            perm.entered_turn = turn
        perm.sick = perm.tapped = False
        return perm

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Ceti Eel", "Ooze Patrol", "Oran-Rief, the Vastwood", "Force of Despair", "Mabel, Valley Hero",
                     "Gallia, the Merrymaker", "Renet, Temporal Apprentice"):
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_oran_rief_counts_only_new_green_creatures(self):
        rief = self.enter(self.a, "Oran-Rief, the Vastwood", turn=1)
        old = self.enter(self.a, "Grizzly Bears", turn=1)
        new = self.enter(self.a, "Grizzly Bears")
        red = self.enter(self.a, "Raging Goblin")
        theirs = self.enter(self.b, "Grizzly Bears")
        self.assertEqual(len(rief.activated), 1)                       # {T}: Add {G} is its mana ability
        self.assertTrue(self.game.activate_ability(self.a, rief, 0))
        self.game.settle()
        self.assertEqual((old.counters.get("+1/+1", 0), new.counters.get("+1/+1", 0), red.counters.get("+1/+1", 0)),
                         (0, 1, 0))
        self.assertEqual(theirs.counters.get("+1/+1", 0), 1)       # "each green creature": any controller

    def test_force_of_despair_destroys_only_new_creatures(self):
        old = self.enter(self.b, "Grizzly Bears", turn=1)
        new = self.enter(self.b, "Hill Giant")
        mine = self.enter(self.a, "Llanowar Elves")
        for _ in range(3):
            self.enter(self.a, "Swamp", turn=1)
        spell = self.db.get("Force of Despair")
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell))
        self.game.settle()
        self.assertIn(old, self.b.battlefield)
        self.assertNotIn(new, self.b.battlefield)
        self.assertNotIn(mine, self.a.battlefield)

    def test_ceti_eel_counts_the_union_after_milling(self):
        eel = self.db.get("Ceti Eel")
        effects = [e for t in eel.triggers for e in t.effects] + list(eel.etb_effects)
        self.assertTrue(any(e.kind == "add_counter" and e.data.get("xq", ("",))[0] == "cxq" for e in effects))
        self.a.graveyard = [self.db.get(n) for n in ("Sol Ring", "Grizzly Bears", "Shock", "Forest")]
        add = next(e for e in effects if e.kind == "add_counter")
        self.assertEqual(self.game.x_quantity(self.a, add.data["xq"], None, None), 2)   # artifact + creature

    def test_mabel_aims_at_my_new_creature(self):
        """HeuristicAI picks the target: a creature that entered this turn, its own."""
        old = self.enter(self.a, "Hill Giant", turn=1)                 # before Mabel: no trigger
        mabel = self.enter(self.a, "Mabel, Valley Hero", turn=1)
        theirs = self.enter(self.b, "Grizzly Bears")                 # entered this turn too, but the opponent's
        mabel.counters.clear()
        new = self.enter(self.a, "Grizzly Bears")                    # its enter trigger targets
        self.game.settle()
        self.assertEqual(new.counters.get("+1/+1", 0), 1)
        self.assertEqual((old.counters.get("+1/+1", 0), theirs.counters.get("+1/+1", 0)), (0, 0))


if __name__ == "__main__":
    unittest.main()
