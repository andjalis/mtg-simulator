"""#626 DMG-BACKREF: "~ deals that much damage to <recipients>" for any plain damage recipient, and "it" in the
permanent's own combat-damage trigger (Balefire Dragon, Questing Beast)."""
import unittest

from mtgsim.cards.parse import _parse_effects

from tests.test_combat_triggers import Scripted
from tests.test_cx_abil_damage import arena
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import card

BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
GIANT = card("Test Giant", "{5}{G}", "Creature — Giant", "", 7, 7)
WALKER = card("Test Walker", "{3}", "Legendary Planeswalker — Testy", "[+1]: You gain 1 life.")


def db():
    from mtgsim.carddb import CardDB
    return CardDB()


class Parse(unittest.TestCase):
    def test_shapes(self):
        effs, bad = _parse_effects("~ deals that much damage to each creature that player controls.")
        self.assertEqual((bad, effs[0].kind, effs[0].amount, effs[0].data["that_much"]), ([], "group_remove", 0, True))
        effs, bad = _parse_effects("~ deals that much damage to target planeswalker that player controls.")
        self.assertEqual((bad, effs[0].kind, effs[0].data["selector"]["types_all"]), ([], "damage", ["planeswalker"]))

    def test_refusals(self):
        for s in ("~ deals that much damage to target planeswalker that player controls or battle that player protects.",
                  "~ deals that much damage to each creature and each player.",          # two effects
                  "~ deals that much damage plus 1 to each creature that player controls.",
                  "~ deals twice that much damage to each creature that player controls."):
            with self.subTest(s=s):
                self.assertTrue(_parse_effects(s)[1], s)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards(self):
        cards = db()
        for name in ("Balefire Dragon", "Questing Beast"):
            c = cards.get(name)
            self.assertEqual((c.unsupported, c.approximations), ([], []), name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Combat(unittest.TestCase):
    def attack(self, name, blockers=()):
        game, a, b = arena(Scripted)
        game.turn, game.step = 2, "main1"
        attacker = game.enter_battlefield(a, db().get(name))
        attacker.sick = False
        return game, a, b, attacker

    def test_balefire_dragon_hits_each_of_their_creatures_for_the_damage_dealt(self):
        game, a, b, dragon = self.attack("Balefire Dragon")
        bear, giant = game.enter_battlefield(b, BEAR), game.enter_battlefield(b, GIANT)
        mine = game.enter_battlefield(a, BEAR)
        a.ai.attack, b.ai.block = [dragon], {}
        game.combat(a, b)
        game.settle()
        self.assertEqual(b.life, 14)
        self.assertNotIn(bear, b.battlefield)
        self.assertEqual(giant.damage, 6)
        self.assertIn(mine, a.battlefield)
        self.assertEqual(mine.damage, 0)

    def test_questing_beast_hits_their_planeswalker(self):
        game, a, b, beast = self.attack("Questing Beast")
        walker = game.enter_battlefield(b, WALKER, counters={"loyalty": 5})
        a.ai.attack, b.ai.block = [beast], {}
        a.ai.choose_attack_targets = lambda game, me, attackers: {x: b for x in attackers}    # the player, not it
        game.combat(a, b)
        game.settle()
        self.assertEqual(b.life, 16)
        self.assertIn(walker, b.battlefield)
        self.assertEqual(walker.loyalty, 1)            # 4 combat damage dealt: 4 to the planeswalker


class CombatDamageAmount(unittest.TestCase):
    """combat_damage_player triggers see the damage dealt (the same engine line as #624): on main "that much" was 0."""

    def test_gain_that_much_life(self):
        game, a, b = arena(Scripted)
        game.turn, game.step = 2, "main1"
        hitter = game.enter_battlefield(a, card("Test Hitter", "{3}", "Creature — Beast", "Whenever ~ deals combat "
                                                "damage to a player, you gain that much life.", 3, 3))
        hitter.sick = False
        a.ai.attack = [hitter]
        game.combat(a, b)
        game.settle()
        self.assertEqual((a.life, b.life), (23, 17))
