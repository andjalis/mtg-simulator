"""smol-chonk-2 batch 3: sac-stat X-quantities for any permanent, ability-word prefixes,
the "put a number of +1/+1 counters on ~ equal to <stat>" template, honest mana-amount
approximation notes, and the canonical copies.py "copy target spell" template.

Parser-side coverage for the batch's promotions plus engine checks that the ("sac", stat)
X-quantity feeds from the artifact/permanent sacrificed to pay a spell or ability cost.
"""
import random
import unittest

from mtgsim.cards import Effect
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, PLAINS, card

BEAST = card("Test Beast", "{2}{G}", "Creature — Beast", "", 3, 3)          # power/toughness 3, mana value 3
JUNK = card("Test Jar", "{2}", "Artifact", "")                              # mana value 2

# Red Priest of Yawgmoth / Priest of Yawgmoth: the sacrificed artifact's mana value
RED_PRIEST = card("Test Red Priest", "{1}{R}", "Creature — Human Cleric",
                  "{T}, Sacrifice an artifact: Add an amount of {R} equal to the sacrificed "
                  "artifact's mana value.", 1, 2)
# Illuminor Szeras: an ability word ("Secrets of the Soul — ") before the activated ability
SZERAS = card("Test Szeras", "{1}{B}", "Creature — Human Cleric",
              "Secrets of the Soul — {T}, Sacrifice another creature: Add an amount of {B} "
              "equal to the sacrificed creature's mana value.", 1, 2)
# Reckoner's Bargain: the sacrificed permanent's mana value, paid as a spell cost
BARGAIN = card("Test Bargain", "{1}", "Sorcery",
               "As an additional cost to cast this spell, sacrifice an artifact or creature.\n"
               "You gain life equal to the sacrificed permanent's mana value. Draw a card.")
GOLEM = card("Test Golem", "{3}", "Artifact Creature — Golem", "", 3, 3)    # mana value 3
# Bosh, Iron Golem: damage equal to the sacrificed artifact's mana value
BOSH = card("Test Bosh", "{7}", "Artifact Creature — Golem",
            "{3}{R}, Sacrifice an artifact: Test Bosh deals damage equal to the sacrificed "
            "artifact's mana value to any target.", 3, 3)
# Faith Healer: the sacrificed enchantment's mana value
HEALER = card("Test Healer", "{1}{W}", "Creature — Human Cleric",
              "{T}, Sacrifice an enchantment: You gain life equal to the sacrificed "
              "enchantment's mana value.", 1, 2)
RUNE = card("Test Rune", "{1}{W}", "Enchantment", "")                       # mana value 2
# Rhovanion Rampager: "If you do" gate plus a number of counters equal to the sacrificed power
RAMPAGER = card("Test Rampager", "{2}{G}", "Creature — Beast",
                "Whenever this creature attacks, you may sacrifice another creature. "
                "If you do, put a number of +1/+1 counters on this creature equal to the "
                "sacrificed creature's power.", 2, 2)
# Forge Armor: "where X is the sacrificed artifact's mana value" counters on a target
FORGE_ARMOR = card("Test Forge Armor", "{2}{W}", "Sorcery",
                   "As an additional cost to cast this spell, sacrifice an artifact.\n"
                   "Put X +1/+1 counters on target creature, where X is the sacrificed "
                   "artifact's mana value.")
BRUTE = card("Test Brute", "{0}", "Creature — Brute", "", 3, 1)             # power 3, cmc 0
# Cradle Clearcutter: a {T} mana ability with a dynamic amount
CLEARCUTTER = card("Test Clearcutter", "{4}", "Artifact Creature — Golem",
                   "{T}: Add an amount of {G} equal to this creature's power.", 3, 6)


class Smol2Batch3(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, c, n=1, who=None):
        for _ in range(n):
            perm = self.game.enter_battlefield(who or self.a, c)
            perm.sick = False
        self.game.settle()
        return perm

    def mana(self, p, color):
        return sum(1 for m in p.pool if color in m.card.produces)

    # ------------------------------------------------------------ parse: templates match

    def test_priority_cards_parse_full(self):
        for c in (RED_PRIEST, SZERAS, BARGAIN, BOSH, HEALER, RAMPAGER, FORGE_ARMOR):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertEqual(c.approximations, [], c.name)

    def test_sacrificed_permanent_nouns_in_xq(self):
        from mtgsim.cards.clauses import _xq
        for noun in ("creature", "artifact", "enchantment", "planeswalker", "land", "permanent"):
            for stat in ("power", "toughness", "mana value"):
                self.assertEqual(_xq(f"the sacrificed {noun}'s {stat}"), ("sac", stat), noun)
        self.assertIsNone(_xq("the sacrificed Dragon's power"))      # an unknown noun stays a gap

    def test_ability_word_prefix(self):
        (priest,) = SZERAS.activated
        self.assertEqual(priest.cost, {"generic": 0})
        self.assertEqual(priest.extra_costs, {"tap": True, "sacrifice": "other creature"})
        self.assertEqual(priest.text,
                         "Secrets of the Soul — {T}, Sacrifice another creature: "
                         "Add an amount of {B} equal to the sacrificed creature's mana value.")
        # the plain wording parses identically
        plain = card("Test Szeras Plain", "{1}{B}", "Creature — Human Cleric",
                     "{T}, Sacrifice another creature: Add an amount of {B} equal to the "
                     "sacrificed creature's mana value.", 1, 2)
        self.assertEqual(plain.activated[0].effects, priest.effects)

    def test_copy_target_spell_without_you_control(self):
        from mtgsim.cards.parse import _parse_effects
        bare, scoped = (_parse_effects("Copy target instant or sorcery spell."),
                        _parse_effects("Copy target instant or sorcery spell you control."))
        self.assertEqual(bare, scoped)
        self.assertEqual(bare[0][0].kind, "copy_spell")
        self.assertEqual(bare[0][0].data["what"], "instant or sorcery")
        self.assertEqual(_parse_effects("Copy target spell.")[0][0].data["what"], "")

    def test_clearcutter_records_mana_amount_approximation(self):
        self.assertEqual(CLEARCUTTER.unsupported, [])
        self.assertEqual(CLEARCUTTER.approximations,
                         ['mana amount fixed at 1: "Add an amount of {G} equal to ~\'s power"'])
        self.assertEqual(CLEARCUTTER.produces, frozenset({"G"}))
        self.assertEqual(CLEARCUTTER.mana_amount, 1)

    def test_plain_fixed_mana_amount_has_no_approximation(self):
        savannah = card("Test Savannah", types="Land", text="{T}: Add {G}{W}.")
        self.assertEqual(savannah.approximations, [])
        self.assertEqual(savannah.mana_amount, 2)

    # ------------------------------------------------------------ engine: the amounts flow

    def test_ability_mana_equal_to_sacrificed_artifact_mana_value(self):
        priest = self.put(RED_PRIEST)
        jar = self.put(JUNK)                              # mana value 2
        self.assertTrue(self.game.activate_ability(self.a, priest, 0))
        self.game.settle()
        self.assertNotIn(jar, self.a.battlefield)
        self.assertEqual(self.mana(self.a, "R"), 2)

    def test_szeras_mana_equal_to_sacrificed_creature_mana_value(self):
        szeras = self.put(SZERAS)
        beast = self.put(BEAST)                           # mana value 3
        self.assertTrue(self.game.activate_ability(self.a, szeras, 0))
        self.game.settle()
        self.assertNotIn(beast, self.a.battlefield)
        self.assertEqual(self.mana(self.a, "B"), 3)

    def test_bosh_damage_equal_to_sacrificed_artifact_mana_value(self):
        bosh = self.put(BOSH)
        self.put(JUNK)
        target = self.put(BEAR, who=self.b)               # 2/2: 2 damage kills it
        self.put(MOUNTAIN, 4)                             # pay {3}{R}
        self.assertTrue(self.game.activate_ability(self.a, bosh, 0, targets=[target]))
        self.game.settle()
        self.assertNotIn(target, self.b.battlefield)

    def test_healer_life_equal_to_sacrificed_enchantment_mana_value(self):
        healer = self.put(HEALER)
        rune = self.put(RUNE)
        self.assertTrue(self.game.activate_ability(self.a, healer, 0))
        self.game.settle()
        self.assertNotIn(rune, self.a.battlefield)
        self.assertEqual(self.a.life, 22)         # 20 + mana value 2

    def test_spell_life_equal_to_sacrificed_permanent_mana_value(self):
        self.put(MOUNTAIN, 2)
        victim = self.put(GOLEM)                          # mana value 3, an artifact creature
        self.a.hand = [BARGAIN]
        self.assertTrue(self.game.cast(self.a, BARGAIN))
        self.game.settle()
        self.assertNotIn(victim, self.a.battlefield)
        self.assertEqual(self.a.life, 23)                 # 20 + mana value 3
        self.assertEqual(len(self.a.hand), 1)             # ... and draw a card

    def test_rampager_counters_equal_to_sacrificed_power(self):
        rampager = self.put(RAMPAGER)
        victim = self.put(BRUTE)                          # power 3, cheap enough to sacrifice
        self.game.fire(self.a, "attacks", rampager)
        self.game.settle()
        self.assertNotIn(victim, self.a.battlefield)
        self.assertEqual(rampager.counters.get("+1/+1"), 3)

    def test_forge_armor_counters_equal_to_sacrificed_mana_value(self):
        self.put(PLAINS, 4)                              # pay {2}{W}
        jar = self.put(JUNK)                              # mana value 2
        target = self.put(BEAR)
        self.a.hand = [FORGE_ARMOR]
        self.assertTrue(self.game.cast(self.a, FORGE_ARMOR, targets=[target]))
        self.game.settle()
        self.assertNotIn(jar, self.a.battlefield)
        self.assertEqual(target.counters.get("+1/+1"), 2)

    def test_x_quantity_sac_reads_any_permanent_stats(self):
        item = StackItem(self.a, [Effect("gain_life", 1)], [], card=BEAST)
        item.sac_stats = (4, 5, 6)
        for stat, expect in (("power", 4), ("toughness", 5), ("mana value", 6)):
            self.assertEqual(self.game.x_quantity(self.a, ("sac", stat), item, None), expect)


if __name__ == "__main__":
    unittest.main()
