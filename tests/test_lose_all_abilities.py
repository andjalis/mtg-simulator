""""Loses all abilities" as a layer-6 effect (#406 slice 3): mtgsim.cx_static_chars.strip and the lose_all operation."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
LIGNIFY = card("Test Lignify", "{1}{G}", "Enchantment — Aura",
               "Enchant creature\nEnchanted creature is a Treefolk with base power and toughness 0/4 and loses all "
               "abilities.")
STASIS = card("Test Stasis", "{1}{U}", "Enchantment — Aura",
              "Enchant creature\nEnchanted creature has base power and toughness 0/2, has defender, and loses all "
              "other abilities.")
LORD = card("Test Lord", "{2}{W}", "Creature — Human Knight",
            "Flying\nWhen ~ enters, you gain 3 life.\n{T}: You gain 1 life.\nOther creatures you control get +1/+1.",
            3, 3)
WINGS = card("Test Wings", "{1}", "Artifact — Equipment", "Equipped creature has flying.\nEquip {1}")


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def enchant(self, aura, host, who=None):
        self.game._aura_host = host
        x = self.game.enter_battlefield(who or self.a, aura)
        self.game.settle()
        return x


class Static(Base):
    def test_parses_without_a_simplification(self):
        for c in (LIGNIFY, STASIS):
            self.assertEqual((c.unsupported, c.approximations), ([], []), c.name)
            self.assertTrue(c.aura_hostile)

    def test_every_kind_of_ability_is_gone(self):
        lord = self.game.enter_battlefield(self.b, LORD)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.assertEqual(bear.power, 3)                                   # the lord's anthem
        aura = self.enchant(LIGNIFY, lord)
        self.assertFalse(lord.has("flying"))                              # keyword
        self.assertEqual(lord.triggers, [])                               # triggered ability
        self.assertEqual(lord.card.activated, [])                         # activated ability
        self.assertTrue(lord.abilities_suppressed)
        self.assertEqual(bear.power, 2)                                   # its static ability
        self.assertEqual((lord.power, lord.toughness), (0, 4))
        self.assertEqual(set(lord.card.subtypes), {"Treefolk"})
        self.assertEqual(lord.card.name, LORD.name)                       # not an ability: kept
        self.game.leave_battlefield(aura, "graveyard")
        self.game.settle()
        self.assertTrue(lord.has("flying"))
        self.assertEqual((lord.power, bear.power), (3, 3))

    def test_equipment_attached_later_still_grants(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        wings = self.game.enter_battlefield(self.a, WINGS)
        wings.attached_to = bear
        self.enchant(LIGNIFY, bear, self.b)
        self.assertFalse(bear.has("flying"))                              # attached before: removed
        wings.attached_to = None
        wings.attachment_timestamp = self.game.next_effect_timestamp()
        wings.attached_to = bear
        self.assertTrue(bear.has("flying"))                               # attached after: granted

    def test_loses_all_other_abilities_keeps_this_lines_grant(self):
        lord = self.game.enter_battlefield(self.b, LORD)
        self.enchant(STASIS, lord)
        self.assertTrue(lord.has("defender"))
        self.assertFalse(lord.has("flying"))
        self.assertEqual((lord.power, lord.toughness), (0, 2))


class OneShot(Base):
    def test_turn_to_frog_until_end_of_turn(self):
        lord = self.game.enter_battlefield(self.b, LORD)
        effs = parse_sentence("Until end of turn, target creature loses all abilities and becomes a blue Frog with "
                              "base power and toughness 1/1.")
        self.assertEqual(effs[0].data["side"], "theirs")
        for e in effs:
            self.game.resolve(self.a, e, lord)
        self.assertFalse(lord.has("flying"))
        self.assertEqual((lord.power, lord.toughness), (1, 1))
        self.assertEqual(set(lord.card.colors), {"U"})
        self.game.add_continuous_effect(lord, "grant", keyword="flying", until_eot=True)
        self.assertTrue(lord.has("flying"))                               # granted after: it has it
        self.game.expire_continuous_effects()
        lord.animated = None
        self.assertFalse(lord.abilities_suppressed)
        self.assertEqual(len(lord.triggers), 1)

    def test_until_your_next_turn(self):
        from mtgsim.advanced_templates import begin_turn
        from mtgsim.cx_next_turn import lasting
        lord = self.game.enter_battlefield(self.b, LORD)
        eff = parse_sentence("Target creature loses all abilities until end of turn.")[0]
        with lasting(self.game, self.a):
            self.game.resolve(self.a, eff, lord)
        self.game.expire_continuous_effects()
        self.assertFalse(lord.has("flying"))                              # still: until a's next turn
        begin_turn(self.game, self.a)
        self.assertTrue(lord.has("flying"))

    def test_ai_aims_it_at_the_opponents_creature(self):
        mine = self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, LORD)
        spell = card("Test Frog", "{U}", "Instant", "Until end of turn, target creature loses all abilities and "
                     "becomes a blue Frog with base power and toughness 1/1.")
        self.assertEqual(spell.unsupported, [])
        plan = self.a.ai.plan_spell(self.game, self.a, spell, precombat=True)
        self.assertIsNotNone(plan)
        self.assertIs(plan[1][0], theirs)
        self.assertIsNot(plan[1][0], mine)

    def test_ai_puts_lignify_on_their_creature(self):
        from mtgsim.auras import choose_host
        self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, LORD)
        self.assertIs(choose_host(self.game, self.a, LIGNIFY), theirs)


@unittest.skipUnless(os.path.exists(DB), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Lignify", "Kasmina's Transmutation", "Eaten by Piranhas", "Frogify", "Stasis Field", "Humble",
                     "Ovinize", "Turn to Frog", "Snakeform", "Polymorphist's Jest", "Dance of the Skywise",
                     "Oko, Thief of Crowns", "Ichthyomorphosis", "Deep Freeze"):
            with self.subTest(name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


if __name__ == "__main__":
    unittest.main()
