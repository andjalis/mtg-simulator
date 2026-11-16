"""Kicker cost forms (#859): two kickers ("Kicker {A} and/or {B}"), non-mana kickers ("Kicker—Sacrifice a land."),
and "if kicked, it enters with N +1/+1 counters on it and with <keyword>|"<trigger>"" (the Volvers, Pouncing Kavu)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.coverage import card_coverage
from mtgsim.engine import Game, Player
from tests.test_templates import card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

NOW_FULL = ["Ana Battlemage", "Nightscape Battlemage", "Stormscape Battlemage", "Sunscape Battlemage",
            "Thornscape Battlemage", "Thunderscape Battlemage", "Wastescape Battlemage", "Illuminate",
            "Stronghold Arena", "Archangel of Wrath", "Cetavolver", "Necravolver", "Rakavolver",
            "Vicious Offering", "Final Flourish", "Eject the Warp Core", "Stomped by the Foot", "Vayne's Treachery",
            "Rushing River", "Bog Down", "Primal Growth", "Dwarven Landslide", "Phyrexian Scuta", "Arctic Merfolk",
            "Pouncing Kavu", "Pouncing Wurm", "Duskwalker", "Faerie Squadron", "Benalish Lancer", "Kavu Titan"]


def kicks(c):
    return sorted(a.kicks for a in c.alt_costs if a.kind == "kicker")


class Refusals(unittest.TestCase):
    def test_three_kickers_stay_ignored(self):
        c = card("Zork", "{1}{R}", "Creature — Ox", "Kicker {1} and/or {2} and/or {3}", 2, 2)
        self.assertEqual(kicks(c), [])
        self.assertTrue(c.unsupported)

    def test_counted_or_alternative_non_mana_kickers_stay_ignored(self):
        for cost in ("Sacrifice X lands", "Sacrifice a creature or pay 3 life", "Sacrifice any number of lands"):
            c = card("Zork", "{1}{R}", "Sorcery", f"Kicker—{cost}.\nZork deals 2 damage to any target.")
            self.assertEqual([a for a in c.alt_costs if a.kind == "kicker"], [], cost)
            self.assertIn(f"Kicker—{cost}.", c.unsupported)

    def test_quoted_activated_ability_on_entry_stays_ignored(self):
        c = card("Zork", "{1}{B}", "Creature — Beast", "Kicker {1}{B}\nIf this creature was kicked, it enters with "
                 "two +1/+1 counters on it and with \"Pay 3 life: Regenerate this creature.\"", 2, 2)
        self.assertTrue(c.unsupported)
        self.assertNotIn("kick_entry", c.advanced_rules)

    def test_unknown_entry_keyword_stays_ignored(self):
        c = card("Zork", "{1}{G}", "Creature — Beast", "Kicker {2}\nIf this creature was kicked, it enters with "
                 "two +1/+1 counters on it and with sparkle.", 2, 2)
        self.assertTrue(c.unsupported)

    def test_kicked_with_condition_needs_a_mana_cost(self):
        from mtgsim.cx_condlib import parse
        self.assertEqual(parse("it was kicked with its {1}{U} kicker"), 'lib:["kicked_with","{1}{U}"]')
        self.assertEqual(parse("it was kicked with its blue kicker"), "")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        cls.db._all.close()

    def test_cards_now_full(self):
        for name in NOW_FULL:
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)

    def test_two_kickers_give_three_options(self):
        c = self.db.get("Ana Battlemage")
        self.assertEqual(kicks(c), [("{1}{B}",), ("{2}{U}",), ("{2}{U}", "{1}{B}")])
        both = next(a for a in c.alt_costs if len(a.kicks) == 2)
        self.assertEqual(both.cost, {"generic": 5, "G": 1, "U": 1, "B": 1})
        self.assertEqual(sorted(t.intervening_if for t in c.triggers if t.event == "etb"),
                         ['lib:["kicked_with","{1}{B}"]', 'lib:["kicked_with","{2}{U}"]'])

    def test_non_mana_kicker_cost(self):
        alt = next(a for a in self.db.get("Vicious Offering").alt_costs if a.kind == "kicker")
        self.assertEqual(alt.add_cost, ((("sac", 1, {"types": ["creature"]}),),))
        alt = next(a for a in self.db.get("Dwarven Landslide").alt_costs if a.kind == "kicker")
        self.assertEqual(alt.cost, {"generic": 5, "R": 2})      # {3}{R} plus the {2}{R} of "Kicker—{2}{R}, ..."
        self.assertEqual(alt.add_cost, ((("sac", 1, {"types": ["land"]}),),))

    def test_entry_with_keyword_and_trigger(self):
        rules = self.db.get("Rakavolver").advanced_rules["kick_entry"]
        self.assertEqual([(code, n, kws, len(trigs)) for code, n, kws, trigs in rules],
                         [('lib:["kicked_with","{1}{W}"]', 2, (), 1), ('lib:["kicked_with","{U}"]', 1, ("flying",), 0)])


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    return g, a, b


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)
        self.g, self.a, self.b = game()
        island = self.db.get("Island")
        self.a.library, self.b.library = [island] * 20, [island] * 20

    def ready(self, p, name, n=1):
        for _ in range(n):
            self.g.enter_battlefield(p, self.db.get(name)).sick = False
        self.g.settle()

    def option(self, paid):
        g, a = self.g, self.a
        return next(o for o in g.spell_options(a) if g._origin(o)[1] == "kicker" and g._origin(o)[2].kicks == paid)

    def names(self, p):
        return sorted(x.card.name for x in p.battlefield)

    def test_ai_kicks_battlemage_for_the_artifact(self):
        g, a, b = self.g, self.a, self.b
        self.ready(a, "Mountain", 3)
        self.ready(a, "Forest")
        self.ready(a, "Plains")
        self.ready(b, "Sol Ring")
        a.hand = [self.db.get("Thornscape Battlemage")]
        a.ai.main_phase(g, a)
        g.settle()
        mage = next(x for x in a.battlefield if x.card.name == "Thornscape Battlemage")
        self.assertIn("{W}", mage.kicked_with)
        self.assertNotIn("Sol Ring", self.names(b))

    def test_only_the_paid_kicker_triggers(self):
        g, a, b = self.g, self.a, self.b
        self.ready(a, "Mountain", 3)
        self.ready(a, "Forest")
        self.ready(b, "Sol Ring")
        a.hand = [self.db.get("Thornscape Battlemage")]
        self.assertTrue(g.cast(a, self.option(("{R}",))))
        g.settle()
        self.assertIn("Sol Ring", self.names(b))           # the {W} kicker wasn't paid
        self.assertEqual(b.life, 18)                        # the {R} kicker's 2 damage (no creature to aim at)
        mage = next(x for x in a.battlefield if x.card.name == "Thornscape Battlemage")
        self.assertEqual((mage.kicked, mage.kicks, mage.kicked_with), (True, 1, ("{R}",)))

    def test_illuminate_both_kickers(self):
        g, a, b = self.g, self.a, self.b
        self.ready(a, "Mountain", 6)
        self.ready(a, "Island", 4)
        self.ready(b, "Hill Giant")
        a.hand = [self.db.get("Illuminate")]
        self.assertTrue(g.cast(a, self.option(("{2}{R}", "{3}{U}")), [b.battlefield[0]]))
        g.settle()
        self.assertEqual(b.life, 18)        # X = 2: two damage to the creature's controller
        self.assertEqual(len(a.hand), 2)    # and two cards

    def test_stronghold_arena_counts_each_kicker(self):
        g, a = self.g, self.a
        self.ready(a, "Swamp", 2)
        self.ready(a, "Forest")
        self.ready(a, "Plains")
        a.hand = [self.db.get("Stronghold Arena")]
        self.assertTrue(g.cast(a, self.option(("{G}", "{W}"))))
        g.settle()
        self.assertEqual(a.life, 26)

    def test_archangel_kicked_twice(self):
        g, a, b = self.g, self.a, self.b
        for land in ("Plains", "Plains", "Swamp", "Mountain", "Island", "Island"):
            self.ready(a, land)
        a.hand = [self.db.get("Archangel of Wrath")]
        self.assertTrue(g.cast(a, self.option(("{B}", "{R}"))))
        g.settle()
        self.assertEqual(b.life, 16)

    def test_ai_kicks_vicious_offering_with_a_sacrifice(self):
        g, a, b = self.g, self.a, self.b
        self.ready(a, "Swamp", 2)
        self.ready(a, "Llanowar Elves")
        self.ready(b, "Craw Wurm")
        a.hand = [self.db.get("Vicious Offering")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual(self.names(b), [])                  # -5/-5 kills the 6/4
        self.assertNotIn("Llanowar Elves", self.names(a))    # sacrificed for the kicker
        self.assertIn("Llanowar Elves", [c.name for c in a.graveyard])

    def test_unkicked_offering_without_a_creature_to_sacrifice(self):
        g, a, b = self.g, self.a, self.b
        self.ready(a, "Swamp", 2)
        self.ready(b, "Craw Wurm")
        a.hand = [self.db.get("Vicious Offering")]
        self.assertFalse(any(g._origin(o)[1] == "kicker" and g.can_cast_now(a, o) for o in g.spell_options(a)))
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual(self.names(b), ["Craw Wurm"])

    def test_ai_pays_life_for_phyrexian_scuta(self):
        g, a = self.g, self.a
        self.ready(a, "Swamp", 4)
        a.hand = [self.db.get("Phyrexian Scuta")]
        a.ai.main_phase(g, a)
        g.settle()
        scuta = next(x for x in a.battlefield if x.card.name == "Phyrexian Scuta")
        self.assertEqual((a.life, scuta.power, scuta.toughness), (17, 5, 5))

    def test_ai_kicks_pouncing_kavu(self):
        g, a = self.g, self.a
        self.ready(a, "Mountain", 6)
        a.hand = [self.db.get("Pouncing Kavu")]
        a.ai.main_phase(g, a)
        g.settle()
        kavu = next(x for x in a.battlefield if x.card.name == "Pouncing Kavu")
        self.assertEqual((kavu.power, kavu.toughness, kavu.has("haste")), (3, 3, True))

    def test_unkicked_kavu_has_no_haste(self):
        g, a = self.g, self.a
        self.ready(a, "Mountain", 2)
        a.hand = [self.db.get("Pouncing Kavu")]
        self.assertTrue(g.cast(a, a.hand[0]))
        g.settle()
        kavu = next(x for x in a.battlefield if x.card.name == "Pouncing Kavu")
        self.assertEqual((kavu.power, kavu.has("haste")), (1, False))

    def test_rakavolver_both_kickers(self):
        g, a, b = self.g, self.a, self.b
        self.ready(a, "Mountain", 3)
        self.ready(a, "Plains", 2)
        self.ready(a, "Island")
        a.hand = [self.db.get("Rakavolver")]
        self.assertTrue(g.cast(a, self.option(("{1}{W}", "{U}"))))
        g.settle()
        rak = next(x for x in a.battlefield if x.card.name == "Rakavolver")
        self.assertEqual((rak.power, rak.toughness, rak.has("flying")), (5, 5, True))
        g.deal_damage(b, 5, a, source=rak)
        g.settle()
        self.assertEqual((a.life, b.life), (25, 15))      # "Whenever this creature deals damage, you gain that much life"


if __name__ == "__main__":
    unittest.main()
