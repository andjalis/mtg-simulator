"""O4 round 3: counters and small abilities (mtgsim.counters_r3)."""
import unittest
from unittest.mock import patch

from mtgsim.carddb import CardDB
from tests.test_templates import BEAR, DRAGON3, MOUNTAIN, PLAINS, Base, card

SABOTEUR = card("Test Saboteur", "{1}{B}", "Creature — Human Rogue", "Menace\nWhenever this creature attacks, put a +1/+1 "
                "counter on target creature an opponent controls.", 4, 1)
MAKO = card("Test Mako", "{R}", "Creature — Shark Pirate", "Whenever you discard one or more cards, put that many "
            "+1/+1 counters on this creature.", 1, 1)
CLAW = card("Test Claw", "{R}", "Creature — Lizard Mercenary", "Whenever you attack with one or more Lizards, this "
            "creature deals 1 damage to target opponent.\n{1}{R}: Put a +1/+1 counter on this creature. Activate only if "
            "an opponent lost life this turn and only once each turn.", 1, 2)
DAYDREAM = card("Test Daydream", "{W}", "Sorcery", "Exile target creature you control, then return that card to the "
                "battlefield under its owner's control with a +1/+1 counter on it.")
PLAIN_BLINK = card("Test Flicker", "{1}{W}", "Instant", "Exile target creature you control, then return that card to the "
                   "battlefield under its owner's control.")
ELF = card("Test Elf", "{1}{B}", "Creature — Elf Warrior", "Discard a card: This creature gains indestructible until end "
           "of turn. Tap it.", 3, 1)
PURSUER = card("Test Pursuer", "{B}", "Creature — Wolf", "Menace\nFerocious — Whenever this creature attacks while you "
               "control a creature with power 4 or greater, this creature gets +2/+2 until end of turn.", 1, 1)
PRIEST = card("Test Priest", "{1}{W}", "Creature — Human Cleric", "When this creature enters, you gain 3 life.", 1, 3)
# Shapes that must stay unsupported.
OTHER_MANY = card("Test Gainer", "{G}", "Creature — Hydra", "Whenever you gain life, put that many +1/+1 counters on "
                  "this creature.", 1, 1)
TAP_IT = card("Test Binder", "{1}{U}", "Instant", "Draw a card. Tap it.")
CLAW_YOU = card("Test Claw Two", "{R}", "Creature — Lizard", "{1}{R}: Put a +1/+1 counter on this creature. Activate "
                "only if you gained life this turn.", 1, 1)
DAYDREAM_OTHER = card("Test Cloud", "{W}", "Sorcery", "Exile target creature you control, then return that card to the "
                      "battlefield tapped under its owner's control with a +1/+1 counter on it.")


def p1(perm):
    return perm.counters.get("+1/+1", 0)


class Parsing(Base):
    def test_templates(self):
        for c in (SABOTEUR, MAKO, CLAW, DAYDREAM, PLAIN_BLINK, ELF, PURSUER):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(SABOTEUR.triggers[0].effects[0].filter, "opp")
        self.assertEqual(DAYDREAM.spell_effects[0].data, {"counters": 1})
        self.assertEqual(PLAIN_BLINK.spell_effects[0].data, {})
        self.assertEqual((CLAW.activated[0].condition, CLAW.activated[0].once), ("opp_lost_life", True))
        self.assertEqual([e.kind for e in ELF.activated[0].effects], ["grant", "tap"])
        self.assertEqual(PURSUER.triggers[0].effects[0].data["intervening_if"], "power_ge:4")

    def test_other_shapes_stay_unsupported(self):
        for c in (OTHER_MANY, TAP_IT, CLAW_YOU, DAYDREAM_OTHER):
            with self.subTest(card=c.name):
                self.assertEqual(len(c.unsupported), 1)

    def test_real_cards(self):
        db = CardDB(offline=True)
        if db.lookup("Hired Claw") is None:
            self.skipTest("card database not built")
        for name in ("Sunset Saboteur", "Marauding Mako", "Scrounging Skyray", "Hired Claw", "Daydream",
                     "Iron-Shield Elf", "Nighthowl Pursuer"):
            with self.subTest(card=name):
                self.assertEqual(db.get(name).unsupported, [])


class Interactions(Base):
    def test_saboteur_attack_puts_counter_on_weakest_opposing_creature(self):
        saboteur = self.perm(SABOTEUR, self.a)
        small, big = self.perm(BEAR, self.b), self.perm(DRAGON3, self.b)
        mine = self.perm(BEAR, self.a)
        self.game.fire(self.a, "attacks", saboteur)
        self.game.settle()
        self.assertEqual((p1(small), p1(big), p1(mine), p1(saboteur)), (1, 0, 0, 0))

    def test_saboteur_without_opposing_creature_does_nothing(self):
        saboteur = self.perm(SABOTEUR, self.a)
        mine = self.perm(BEAR, self.a)
        self.game.fire(self.a, "attacks", saboteur)
        self.game.settle()
        self.assertEqual((p1(mine), p1(saboteur)), (0, 0))

    def test_mako_counts_each_discarded_card(self):
        mako = self.perm(MAKO, self.a)
        self.a.hand = [BEAR, BEAR, DRAGON3]
        self.game.discard_card(self.a, BEAR)
        self.game.settle()
        self.assertEqual(p1(mako), 1)
        self.game.discard_card(self.a, BEAR)
        self.game.discard_card(self.a, DRAGON3)
        self.game.settle()
        self.assertEqual(p1(mako), 3)

    def test_mako_ignores_opponent_discards(self):
        mako = self.perm(MAKO, self.a)
        self.b.hand = [BEAR]
        self.game.discard_card(self.b, BEAR)
        self.game.settle()
        self.assertEqual(p1(mako), 0)

    def test_claw_needs_life_loss_and_only_once_a_turn(self):
        claw = self.perm(CLAW, self.a)
        for _ in range(4):
            self.perm(MOUNTAIN, self.a)
        self.assertFalse(self.game.can_activate(self.a, claw, 0))
        self.a.life -= 1                                   # our own life loss does not count
        self.assertFalse(self.game.can_activate(self.a, claw, 0))
        self.b.life -= 1
        self.assertTrue(self.game.activate(self.a, claw, "ability:0"))
        self.game.settle()
        self.assertEqual(p1(claw), 1)
        self.assertFalse(self.game.can_activate(self.a, claw, 0))
        self.game.turn += 1
        self.assertTrue(self.game.can_activate(self.a, claw, 0))

    def test_claw_life_loss_does_not_carry_to_the_next_turn(self):
        claw = self.perm(CLAW, self.a)
        for _ in range(2):
            self.perm(MOUNTAIN, self.a)
        self.b.life -= 1
        self.assertTrue(self.game.can_activate(self.a, claw, 0))
        self.game.take_turn(self.b)
        self.assertFalse(self.b.lost_life_turn)
        self.assertFalse(self.game.can_activate(self.a, claw, 0))

    def test_claw_attack_trigger_makes_it_activatable(self):
        claw = self.perm(CLAW, self.a)
        liz = self.perm(CLAW, self.a)
        for _ in range(2):
            self.perm(MOUNTAIN, self.a)
        self.assertFalse(self.game.can_activate(self.a, claw, 0))
        self.game.attackers = [liz]
        self.game.fire(self.a, "you_attack")
        self.game.settle()
        self.assertEqual(self.b.life, 18)
        self.assertTrue(self.game.can_activate(self.a, liz, 0))

    def test_daydream_blinks_enters_trigger_and_adds_counter(self):
        priest = self.perm(PRIEST, self.a)
        priest.damage = 1
        self.perm(PLAINS, self.a)
        self.a.hand = [DAYDREAM]
        life = self.a.life
        self.assertTrue(self.game.cast(self.a, DAYDREAM))
        self.game.settle()
        new = [x for x in self.a.creatures if x.card.name == "Test Priest"]
        self.assertEqual(len(new), 1)
        self.assertIsNot(new[0], priest)
        self.assertEqual((p1(new[0]), new[0].damage), (1, 0))
        self.assertTrue(new[0].sick)
        self.assertEqual(self.a.life, life + 3)            # the enters trigger fired for the new object
        self.assertEqual(self.a.exile.count(PRIEST), 0)

    def test_blink_resets_counters_without_a_counter_rider(self):
        bear = self.perm(BEAR, self.a)
        bear.counters["+1/+1"] = 2
        self.perm(PLAINS, self.a)
        self.perm(PLAINS, self.a)
        self.a.hand = [PLAIN_BLINK]
        self.assertTrue(self.game.cast(self.a, PLAIN_BLINK))
        self.game.settle()
        self.assertEqual([p1(x) for x in self.a.creatures], [0])

    def test_blink_prefers_the_creature_with_an_enters_trigger(self):
        self.perm(DRAGON3, self.a)
        priest = self.perm(PRIEST, self.a)
        self.perm(PLAINS, self.a)
        self.a.hand = [DAYDREAM]
        self.game.cast(self.a, DAYDREAM)
        self.game.settle()
        self.assertNotIn(priest, self.a.battlefield)

    def test_daydream_needs_a_creature(self):
        self.perm(PLAINS, self.a)
        self.a.hand = [DAYDREAM]
        self.assertFalse(self.game.cast(self.a, DAYDREAM))

    def test_elf_discards_gains_indestructible_and_taps(self):
        elf = self.perm(ELF, self.a)
        self.assertFalse(self.game.can_activate(self.a, elf, 0))        # no card to discard
        self.a.hand = [BEAR]
        self.assertTrue(self.game.activate(self.a, elf, "ability:0"))
        self.game.settle()
        self.assertTrue(elf.has("indestructible"))
        self.assertTrue(elf.tapped)
        self.assertEqual(self.a.hand, [])
        elf.damage = 5
        self.game.state_based_actions()
        self.assertIn(elf, self.a.battlefield)

    def test_pursuer_pumps_only_with_a_power_four_creature(self):
        pursuer = self.perm(PURSUER, self.a)
        self.perm(DRAGON3, self.a)
        self.game.fire(self.a, "attacks", pursuer)
        self.game.settle()
        self.assertEqual((pursuer.power, pursuer.toughness), (1, 1))
        big = self.perm(BEAR, self.a)
        big.counters["+1/+1"] = 2
        self.game.fire(self.a, "attacks", pursuer)
        self.game.settle()
        self.assertEqual((pursuer.power, pursuer.toughness), (3, 3))

    def test_pursuer_in_a_real_attack(self):
        pursuer = self.perm(PURSUER, self.a)
        pursuer.sick = False
        brute = self.perm(card("Brute", "{3}", "Creature — Ogre", "", 4, 4), self.a)
        brute.sick = False
        with patch.object(self.a.ai, "choose_attackers", return_value=[pursuer]), \
             patch.object(self.b.ai, "choose_blocks", return_value={}):
            self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20 - 3)


if __name__ == "__main__":
    unittest.main()
