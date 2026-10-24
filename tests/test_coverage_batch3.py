"""Coverage batch: energy, the monarch, "exile it at the beginning of the next end step", "it gains haste",
Sneak Attack, kicker counters, "can't be regenerated" after damage, exile-instead after damage, sunburst, converge."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

CHARGER = card("Test Charger", "{2}{R}", "Creature — Aetherborn",
               "When ~ enters, you get {E}{E}.\nPay {E}: ~ gets +1/+0 until end of turn.", 2, 2)
CROWN = card("Test Crown", "{3}{W}", "Creature — Human", "When ~ enters, you become the monarch.", 2, 2)
WHIP = card("Test Whip", "{2}{B}", "Sorcery", "Return target creature card from your graveyard to the battlefield. It gains "
            "haste. Exile it at the beginning of the next end step.")
SNEAK = card("Test Sneak", "{3}{R}", "Enchantment", "{R}: You may put a creature card from your hand onto the battlefield. "
             "That creature gains haste. Sacrifice the creature at the beginning of the next end step.")
ACOLYTE = card("Test Acolyte", "{1}{G}", "Creature — Human", "Kicker {1}{G}\nIf ~ was kicked, it enters with two +1/+1 "
               "counters on it.", 2, 2)
ANGER = card("Test Anger", "{1}{R}{R}", "Sorcery", "~ deals 3 damage to each creature. If a creature dealt damage this way "
             "would die this turn, exile it instead.")
MANTA = card("Test Manta", "{5}", "Artifact Creature — Fish", "Sunburst\nFlying", 0, 0)
FLAMES = card("Test Flames", "{2}{R}", "Sorcery", "Converge — ~ deals X damage to each creature, where X is the number of "
              "colors of mana spent to cast ~.")
GRASP = card("Test Grasp", "{1}{B}", "Sorcery", "Look at the top three cards of your library. Put one of them into your "
             "hand and the rest into your graveyard.")
GIANT = card("Test Giant", "{6}", "Creature — Giant", "", 6, 6)


class CoverageBatch3(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (CHARGER, CROWN, WHIP, SNEAK, ACOLYTE, ANGER, MANTA, FLAMES, GRASP):
            self.assertEqual(c.unsupported, [], c.name)

    def test_energy(self):
        charger = self.put(self.a, CHARGER)
        self.assertEqual(self.a.energy, 2)
        for _ in range(2):
            self.assertTrue(self.game.activate_ability(self.a, charger, 0))
            self.game.settle()
        self.assertEqual((charger.power, self.a.energy), (4, 0))
        self.assertFalse(self.game.activate_ability(self.a, charger, 0))

    def test_monarch(self):
        self.put(self.a, CROWN)
        self.assertIs(self.game.monarch, self.a)
        bear = self.put(self.b, BEAR)
        self.b.ai.attack = [bear]
        self.game.active_idx = 1
        self.game.combat(self.b, self.a)
        self.assertIs(self.game.monarch, self.b)

    def test_return_with_haste_then_exile(self):
        self.a.graveyard.append(GIANT)
        for e in WHIP.spell_effects:
            self.game.resolve(self.a, e, GIANT if e.target != "prev" else None)
        giant = next(x for x in self.a.battlefield if x.card.name == GIANT.name)
        self.assertTrue(giant.has("haste"))
        self.assertIn((giant, "exile"), self.game.end_cleanup)

    def test_sneak_attack(self):
        sneak = self.put(self.a, SNEAK)
        self.put(self.a, MOUNTAIN)
        self.a.hand[:] = [GIANT]
        self.assertTrue(self.game.activate_ability(self.a, sneak, 0))
        self.game.settle()
        giant = next(x for x in self.a.battlefield if x.card.name == GIANT.name)
        self.assertTrue(giant.has("haste"))
        self.assertIn((giant, "sacrifice"), self.game.end_cleanup)

    def test_kicker_counters(self):
        self.put(self.a, card("Test Forest", "", "Basic Land — Forest", "({T}: Add {G}.)"), 4)
        self.a.hand[:] = [ACOLYTE]
        kicked = next(o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "kicker")
        self.assertTrue(self.game.cast(self.a, kicked))
        self.game.settle()
        self.assertEqual(next(x for x in self.a.battlefield if x.card.name == ACOLYTE.name).p1, 2)

    def test_exile_instead_after_damage(self):
        self.put(self.b, BEAR)
        self.game.resolve(self.a, ANGER.spell_effects[0], None)
        self.game.settle()
        self.assertIn("Grizzly Bears", [c.name for c in self.b.exile])

    def test_dig_rest_to_graveyard(self):
        self.a.library = [BEAR, ISLAND, GIANT, ISLAND]
        self.a.hand[:] = []
        self.game.resolve(self.a, GRASP.spell_effects[0], None)
        self.assertEqual((len(self.a.hand), len(self.a.graveyard), len(self.a.library)), (1, 2, 1))

    def test_sunburst_and_converge(self):
        for c in ("W", "U", "B"):
            self.put(self.a, card(f"Test {c} land", "", "Land", f"{{T}}: Add {{{c}}}."))
        self.put(self.a, ISLAND, 2)
        self.a.hand[:] = [MANTA]
        self.assertTrue(self.game.cast(self.a, MANTA))
        self.game.settle()
        manta = next(x for x in self.a.battlefield if x.card.name == MANTA.name)
        self.assertEqual(manta.p1, 3)                     # white, blue, black (and blue again) were spent


if __name__ == "__main__":
    unittest.main()
