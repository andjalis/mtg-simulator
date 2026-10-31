"""Durations that last until the controller's next turn, and "player or planeswalker" damage targets."""
import random
import unittest

from mtgsim import cards
from mtgsim.advanced_templates import begin_turn
from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

WALKER = card_from_scryfall({"name": "Test Walker", "mana_cost": "{2}{R}", "cmc": 3, "loyalty": "3",
                             "type_line": "Legendary Planeswalker — Test", "oracle_text": "[+1]: Draw a card."})


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c, targets=None, by=None):
        effects = list(c.spell_effects)
        self.game.stack.append(StackItem(by or self.a, effects, targets or [None] * len(effects), card=c, name=c.name))
        self.game.resolve_top()

    def next_turn(self, p):
        """Cleanup of the current turn, then the start of p's turn."""
        self.game.expire_continuous_effects()
        for x in self.a.battlefield + self.b.battlefield:
            x.pump_p = x.pump_t = 0
            x.temp_kw.clear()
        self.game.turn += 1
        begin_turn(self.game, p)


class UntilNextTurn(Base):
    def test_debuff_lasts_through_the_opponents_turn(self):
        hag = card("Test Hex", "{B}", "Instant", "Target creature an opponent controls gets -2/-1 until your next turn.")
        self.assertEqual(hag.unsupported, [])
        bear = self.perm(BEAR, self.b)
        self.cast(hag, [bear])
        self.assertEqual((bear.power, bear.toughness), (0, 1))
        self.next_turn(self.b)
        self.assertEqual((bear.power, bear.toughness), (0, 1))
        self.next_turn(self.a)
        self.assertEqual((bear.power, bear.toughness), (2, 2))

    def test_group_keyword_with_a_type_filter(self):
        call = card("Test Call", "{W}", "Sorcery", "Non-Angel creatures you control gain indestructible until your next turn.")
        self.assertEqual(call.unsupported, [])
        bear = self.perm(BEAR, self.a)
        self.cast(call)
        self.next_turn(self.b)
        self.assertTrue(bear.has("indestructible"))
        self.next_turn(self.a)
        self.assertFalse(bear.has("indestructible"))

    def test_cant_attack_or_block_lock(self):
        lock = card("Test Lock", "{W}", "Instant", "Until your next turn, target creature can't attack or block.")
        self.assertEqual(lock.unsupported, [])
        bear = self.perm(BEAR, self.b)
        bear.sick = False
        self.assertTrue(bear.can_attack())
        self.cast(lock, [bear])
        self.next_turn(self.b)
        self.assertFalse(bear.can_attack())
        self.next_turn(self.a)
        self.assertTrue(bear.can_attack())

    def test_player_protection_and_life_lock(self):
        prot = card("Test Protection", "{1}{W}", "Instant",
                    "Until your next turn, your life total can't change and you gain protection from everything.")
        self.assertEqual(prot.unsupported, [])
        self.cast(prot)
        life = self.a.life
        self.next_turn(self.b)
        self.game.deal_damage(self.a, 5, by=self.b)
        self.assertEqual(self.a.life, life)
        self.next_turn(self.a)
        self.game.deal_damage(self.a, 5, by=self.b)
        self.assertEqual(self.a.life, life - 5)

    def test_this_turn_flags_end_with_the_turn(self):
        calm = card("Test Calm", "{W}", "Instant", "Creatures can't attack you this turn.")
        self.assertEqual(calm.unsupported, [])
        self.cast(calm)
        from mtgsim.advanced_templates import attack_tax
        self.assertGreater(attack_tax(self.game, self.a), 100)
        self.game.turn += 1
        self.assertEqual(attack_tax(self.game, self.a), 0)

    def test_unrecognised_bodies_stay_visible(self):
        _, unmatched = cards._parse_effects("Until your next turn, whenever a creature becomes tapped, destroy it.")
        self.assertTrue(unmatched)


class PlayerOrPlaneswalker(Base):
    def test_damage_can_target_a_planeswalker(self):
        bolt = card("Test Jab", "{R}", "Instant", "Test Jab deals 3 damage to target player or planeswalker.")
        self.assertEqual(bolt.unsupported, [])
        self.assertTrue(bolt.spell_effects[0].data.get("or_pw"))
        walker = self.perm(WALKER, self.b)
        walker.counters["loyalty"] = 3
        legal = self.game.legal_targets(self.a, bolt.spell_effects[0])
        self.assertIn(walker, legal)
        self.assertIn(self.b, legal)
        self.assertNotIn(self.perm(BEAR, self.b), legal)
        self.cast(bolt, [walker])
        self.assertNotIn(walker, self.b.battlefield)

    def test_ai_kills_a_walker_when_face_is_not_lethal(self):
        bolt = card("Test Jab", "{R}", "Instant", "Test Jab deals 3 damage to target opponent or planeswalker.")
        walker = self.perm(WALKER, self.b)
        walker.counters["loyalty"] = 2
        self.assertIs(self.a.ai.choose_target(self.game, self.a, bolt.spell_effects[0], bolt), walker)

    def test_player_and_each_creature_they_control(self):
        wave = card("Test Wave", "{3}{R}{R}", "Sorcery", "Test Wave deals 4 damage to target player or planeswalker and "
                    "each creature that player or that planeswalker's controller controls.")
        self.assertEqual(wave.unsupported, [])
        walker = self.perm(WALKER, self.b)
        walker.counters["loyalty"] = 5
        bear = self.perm(BEAR, self.b)
        mine = self.perm(BEAR, self.a)
        self.cast(wave, [walker, None])
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)
        self.assertEqual(walker.loyalty, 1)


if __name__ == "__main__":
    unittest.main()
