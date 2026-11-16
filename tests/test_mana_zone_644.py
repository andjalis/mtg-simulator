"""#644: restricted mana by where the spell is cast from: "from exile", "from your graveyard", "from anywhere other
than your hand", "spells with flashback from a graveyard" (mtgsim.cx_mana_zone, mana_restriction "zone:<where>")."""
import copy
import random
import unittest
from pathlib import Path

from mtgsim import cx_abil_mana as M
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Altar of the Lost", "Interdimensional Web Watch", "Lord of the Forsaken", "Mm'menon, the Right Hand")
WATCH = card("Test Watch", "{4}", "Artifact", "{T}: Add {C}{C}. Spend this mana only to cast spells from exile.")
LORD = card("Test Lord", "{3}", "Artifact", "{T}: Add {C}. Spend this mana only to cast a spell from your graveyard.")
MMENON = card("Test Mmenon", "{3}", "Artifact",
              "{T}: Add {U}. Spend this mana only to cast a spell from anywhere other than your hand.")
ALTAR = card("Test Altar", "{3}", "Artifact",
             "{T}: Add {C}{C}. Spend this mana only to cast spells with flashback from a graveyard.")
SHOCK = card("Test Shock", "{1}", "Instant", "Test Shock deals 2 damage to any target.")
THINK = card("Test Think", "{1}", "Sorcery", "Draw a card.\nFlashback {2}")
PUMP = card("Test Pump", "{1}", "Creature — Human", "{1}: You gain 1 life.", 1, 1)


def game(ai=Scripted):
    a, b = Player("a", [], ai()), Player("b", [], ai())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 2, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def ready(g, p, c):
    perm = g.enter_battlefield(p, c)
    perm.sick = False
    return perm


def from_(c, kind):
    v = copy.copy(c)
    v.origin = (c, kind, None)
    return v


class Parse(unittest.TestCase):
    def test_codes(self):
        for c, code in ((WATCH, "zone:exile"), (LORD, "zone:graveyard"), (MMENON, "zone:nothand"),
                        (ALTAR, "zone:flashback")):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertEqual(c.mana_restriction, code, c.name)

    def test_refusals(self):
        for text in ("to cast spells from exile this turn", "to cast spells from your hand",
                     "to cast spells from a graveyard other than yours"):
            self.assertIsNone(M.parse(text), text)


class Pay(unittest.TestCase):
    def test_where_from(self):
        g, a, b = game()
        watch, lord, mmenon, altar = (ready(g, a, c) for c in (WATCH, LORD, MMENON, ALTAR))
        pump = ready(g, a, PUMP)
        hand, exile, grave, flashback = SHOCK, from_(SHOCK, "impulse"), from_(SHOCK, "jump_start"), from_(THINK,
                                                                                                         "flashback")
        cases = {watch: (False, True, False, False), lord: (False, False, True, True),
                 mmenon: (False, True, True, True), altar: (False, False, False, True)}
        for src, want in cases.items():
            got = tuple(g.mana_allowed(src, s) for s in (hand, exile, grave, flashback))
            self.assertEqual(got, want, src.card.name)
            self.assertFalse(g.mana_allowed(src, M.AbilityPayment(pump)), src.card.name)   # never abilities

    def test_adventure_and_foretell_count_as_exile(self):
        g, a, b = game()
        watch = ready(g, a, WATCH)
        for kind in ("from_adventure", "foretold", "plotted"):
            self.assertTrue(g.mana_allowed(watch, from_(SHOCK, kind)), kind)

    def test_hand_spell_not_payable(self):
        g, a, b = game()
        ready(g, a, WATCH)
        a.hand = [SHOCK]
        self.assertFalse(g.spell_payable(a, SHOCK))


class AI(unittest.TestCase):
    def test_altar_mana_pays_the_flashback_only(self):
        g, a, b = game(HeuristicAI)
        altar = ready(g, a, ALTAR)
        a.hand = [card("Test Hand Think", "{2}", "Sorcery", "Draw a card.")]
        a.graveyard = [THINK]
        a.ai.main_phase(g, a)
        self.assertEqual([c.name for c in a.hand if c.name == "Test Hand Think"], ["Test Hand Think"])
        self.assertTrue(altar.tapped)                       # spent on the flashback
        self.assertIn("Test Think", [c.name for c in a.exile])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
