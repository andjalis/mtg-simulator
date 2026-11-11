"""Blink templates (mtgsim.blink): exile, then return as a new object. Card text is written out."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from mtgsim.carddb import CardDB

from tests.test_templates import BEAR, ISLAND, PLAINS, card

FLICKER = card("Test Flicker", "{1}{W}", "Instant",
               "Exile target nontoken permanent, then return it to the battlefield under its owner's control.")
HIDE = card("Test Hide", "{2}{W}", "Instant",
            "Exile target creature you control. Return it to the battlefield under its owner's control at the beginning of the next end step.")
SPACE = card("Test Space", "{1}{W}", "Instant",
             "Exile target artifact or creature, then return that card to the battlefield under its owner's control with a +1/+1 counter on it.")
TAPPED = card("Test Tapped", "{1}{W}", "Instant",
              "Exile target creature, then return it to the battlefield tapped under its owner's control.")
TWO = card("Test Two", "{2}{W}", "Instant",
           "Exile up to two target creatures you control, then return those cards to the battlefield under their owner's control.")
LATER = card("Test Later", "{2}{W}", "Instant",
             "Exile target creature. Return it to the battlefield tapped under your control at the beginning of the next end step.")
GOBLIN = card("Test Etb", "{2}", "Creature — Goblin", "When ~ enters, you gain 2 life.", 1, 1)
SPIRIT = card("Test Spirit", "{1}", "Creature — Spirit", "{1}: Exile ~, then return it to the battlefield under its owner's control.", 1, 1)


class BlinkTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        for _ in range(4):
            self.perm(PLAINS, self.a)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (FLICKER, HIDE, LATER, SPACE, TAPPED, TWO, SPIRIT):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_returns_a_new_object_and_triggers_etb(self):
        old = self.perm(GOBLIN, self.a)
        old.counters["+1/+1"] = 2
        old.damage = 1
        life = self.a.life
        self.a.hand = [FLICKER]
        self.game.cast(self.a, FLICKER, [old])
        self.game.settle()
        new = [x for x in self.a.battlefield if x.card.name == "Test Etb"]
        self.assertEqual(len(new), 1)
        self.assertIsNot(new[0], old)
        self.assertEqual((new[0].counters.get("+1/+1", 0), new[0].damage), (0, 0))
        self.assertEqual(self.a.life, life + 2)

    def test_returns_under_its_owners_control(self):
        theirs = self.perm(BEAR, self.b)
        self.b.battlefield.remove(theirs)
        theirs.controller = self.a
        self.a.battlefield.append(theirs)
        self.a.hand = [FLICKER]
        self.game.cast(self.a, FLICKER, [theirs])
        self.game.settle()
        self.assertEqual(len([x for x in self.b.battlefield if x.card.name == BEAR.name]), 1)

    def test_extra_counter_and_tapped(self):
        bear = self.perm(BEAR, self.a)
        self.a.hand = [SPACE]
        self.game.cast(self.a, SPACE, [bear])
        self.game.settle()
        new = [x for x in self.a.battlefield if x.card.name == BEAR.name]
        self.assertEqual(new[0].counters.get("+1/+1"), 1)
        other = self.perm(BEAR, self.b)
        self.a.hand = [TAPPED]
        self.game.cast(self.a, TAPPED, [other])
        self.game.settle()
        back = [x for x in self.b.battlefield if x.card.name == BEAR.name]
        self.assertEqual(len(back), 1)
        self.assertTrue(back[0].tapped)

    def test_delayed_return_waits_for_the_end_step(self):
        bear = self.perm(BEAR, self.b)
        self.a.hand = [LATER]
        self.game.cast(self.a, LATER, [bear])
        self.game.settle()
        for p in (self.a, self.b):
            self.assertFalse([x for x in p.battlefield if x.card.name == BEAR.name])
        self.game.begin_end_step(self.a)
        self.game.settle()
        back = [x for x in self.a.battlefield if x.card.name == BEAR.name]
        self.assertEqual(len(back), 1)
        self.assertTrue(back[0].tapped)

    def test_up_to_two_targets(self):
        one, two = self.perm(GOBLIN, self.a), self.perm(GOBLIN, self.a)
        life = self.a.life
        self.a.hand = [TWO]
        self.game.cast(self.a, TWO, [one, two])
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.name == "Test Etb"]), 2)
        self.assertEqual(self.a.life, life + 4)

    def test_self_blink(self):
        spirit = self.perm(SPIRIT, self.a)
        self.assertTrue(self.game.activate(self.a, spirit, "ability:0"))
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.name == "Test Spirit"]), 1)

    def test_self_blink_transformed_returns_on_the_back_face(self):
        vorinclex = CardDB(offline=True).get("Vorinclex")
        self.assertEqual(vorinclex.unsupported, [])
        eff = vorinclex.activated[0].effects[0]
        self.assertEqual((eff.kind, eff.target), ("blink", "self"))
        self.assertTrue(eff.data["transformed"])
        dfc = card("Test DFC", "{2}{G}", "Creature — Beast",
                   "{6}{G}{G}: Exile ~, then return it to the battlefield transformed under its owner's control.\n"
                   "When ~ enters, you gain 2 life.", 4, 4)
        dfc.back = card("Test DFC Back", "", "Creature — Beast", "", 6, 6)
        self.assertEqual(dfc.unsupported, [])
        src = self.perm(dfc, self.a)
        life = self.a.life
        self.game.resolve(self.a, dfc.activated[0].effects[0], src)
        self.game.settle()
        back = [x for x in self.a.battlefield if x.front is src.front]
        self.assertEqual(len(back), 1)
        self.assertIsNot(back[0], src)
        self.assertEqual(back[0].card.name, "Test DFC Back")   # the back face entered, not the front
        self.assertEqual(self.a.life, life)                    # the front face's ETB did not fire

    def test_target_blink_transformed_and_delayed(self):
        from mtgsim.cards import _parse_effects
        effects, bad = _parse_effects("Exile target creature. Return it to the battlefield transformed under its owner's control at the beginning of the next end step.")
        self.assertEqual(bad, [])
        self.assertEqual(len(effects), 1)
        self.assertTrue(effects[0].data["transformed"] and effects[0].data["delayed"])
        vorinclex = CardDB(offline=True).get("Vorinclex")
        src = self.perm(vorinclex, self.a)
        self.game.resolve(self.a, effects[0], src)
        self.assertIn(src.front, self.a.exile)
        self.assertFalse(any(x.front is src.front for x in self.a.battlefield))
        self.game.begin_end_step(self.a)
        self.game.settle()
        back = [x for x in self.a.battlefield if x.front is src.front]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].card.name, vorinclex.back.name)

    def test_blink_transformed_without_a_back_face_returns_the_front(self):
        from mtgsim.cards import _parse_effects
        effects, bad = _parse_effects("Exile target creature, then return it to the battlefield transformed under its owner's control.")
        self.assertEqual(bad, [])
        bear = self.perm(BEAR, self.a)
        self.game.resolve(self.a, effects[0], bear)
        self.game.settle()
        back = [x for x in self.a.battlefield if x.front is bear.front]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].card.name, BEAR.name)

    def test_owned_target_includes_stolen_creature_but_not_borrowed_creature(self):
        spell = CardDB(offline=True).get("Slip on the Ring")
        self.assertEqual(spell.unsupported, [])
        owned = self.perm(BEAR, self.a)
        borrowed = self.perm(BEAR, self.b)
        self.a.battlefield.remove(owned)
        owned.controller = self.b
        self.b.battlefield.append(owned)
        self.b.battlefield.remove(borrowed)
        borrowed.controller = self.a
        self.a.battlefield.append(borrowed)
        eff = spell.spell_effects[0]
        self.assertIn(owned, self.game.legal_targets(self.a, eff))
        self.assertNotIn(borrowed, self.game.legal_targets(self.a, eff))
        self.a.hand = [spell]
        self.assertTrue(self.game.cast(self.a, spell, [owned]))
        self.game.settle()
        returned = [x for x in self.a.battlefield if x is not borrowed and x.card.name == BEAR.name]
        self.assertEqual(len(returned), 1)
        self.assertIs(returned[0].owner, self.a)

    def test_charming_prince_preserves_another_and_delayed_return(self):
        prince = CardDB(offline=True).get("Charming Prince")
        self.assertEqual(prince.unsupported, [])
        from mtgsim.cards import _parse_effects
        effects, bad = _parse_effects("Exile another target creature you own. Return it to the battlefield under your control at the beginning of the next end step.")
        self.assertEqual(bad, [])
        self.assertEqual(len(effects), 1)
        source = self.perm(prince, self.a)
        from mtgsim.engine import StackItem
        item = StackItem(self.a, effects, [], source=source)
        with self.game.targeting(item):
            self.assertNotIn(source, self.game.legal_targets(self.a, effects[0]))
        bear = self.perm(BEAR, self.a)
        self.game.resolve(self.a, effects[0], bear, item)
        self.assertIn(bear.front, self.a.exile)
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertNotIn(bear.front, self.a.exile)
        self.assertTrue(any(x.front is bear.front for x in self.a.battlefield))

    def test_salvation_swan_returns_with_flying_counter(self):
        swan = CardDB(offline=True).get("Salvation Swan")
        self.assertEqual(swan.unsupported, [])
        source = self.perm(swan, self.a)
        bear = self.perm(BEAR, self.a)
        from mtgsim.engine import StackItem
        effects = swan.triggers[0].effects
        self.assertEqual(len(effects), 1)
        eff = effects[0]
        self.assertNotIn(source, self.game.legal_targets(self.a, eff))
        self.assertIn(bear, self.game.legal_targets(self.a, eff))
        self.game.stack.append(StackItem(self.a, effects, [bear], source=source))
        self.game.settle()
        self.assertIn(bear.front, self.a.exile)
        self.assertFalse(any(x.front is bear.front for x in self.a.battlefield))
        self.game.begin_end_step(self.a)
        self.game.settle()
        new = next(x for x in self.a.battlefield if x.front is bear.front)
        self.assertEqual(new.counters.get("flying"), 1)
        self.assertTrue(new.has("flying"))
        self.assertNotIn(new, self.game.legal_targets(self.a, eff))

    def test_delayed_counter_return_does_not_follow_card_reexiled(self):
        from mtgsim.cards import _parse_effects
        effects, bad = _parse_effects("Exile target creature. Return it to the battlefield under its owner's control with a flying counter on it at the beginning of the next end step.")
        self.assertEqual(bad, [])
        bear = self.perm(BEAR, self.a)
        self.game.resolve(self.a, effects[0], bear)
        self.a.exile.remove(bear.front)
        self.a.hand.append(bear.front)
        self.game.move_card(bear.front, self.a.hand, self.a.exile, reason="test")
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertIn(bear.front, self.a.exile)
        self.assertFalse(any(x.front is bear.front for x in self.a.battlefield))

    def test_unknown_counter_rider_stays_unsupported(self):
        unknown = card("Unknown return", "{W}", "Instant", "Exile target creature, then return it to the battlefield under its owner's control with a shield counter on it.")
        self.assertTrue(unknown.unsupported)

    def test_acrobatics_low_roll_delays_only_selected_nontokens(self):
        from mtgsim.cards import make_token
        spell = CardDB(offline=True).get("Lae'zel's Acrobatics")
        self.assertEqual(spell.unsupported, [])
        self.assertEqual([e.kind for e in spell.spell_effects], ['blink_roll'])
        self.assertEqual(spell.triggers, [])
        old = self.perm(GOBLIN, self.a)
        token = self.perm(make_token('Bear', 2, 2), self.a)
        enemy = self.perm(BEAR, self.b)
        life = self.a.life
        self.a.hand = [spell]
        with patch.object(self.game.rng, 'randint', return_value=9):
            self.assertTrue(self.game.cast(self.a, spell, []))
            self.game.settle()
        self.assertIn(old.front, self.a.exile)
        self.assertIn(token, self.a.battlefield)
        self.assertIn(enemy, self.b.battlefield)
        self.assertEqual(self.a.life, life)
        self.game.begin_end_step(self.b)
        self.game.settle()
        self.assertNotIn(old.front, self.a.exile)
        self.assertEqual(self.a.life, life + 2)

    def test_acrobatics_high_roll_returns_then_exiles_new_objects(self):
        spell = CardDB(offline=True).get("Lae'zel's Acrobatics")
        first, second = self.perm(GOBLIN, self.a), self.perm(GOBLIN, self.a)
        life = self.a.life
        self.a.hand = [spell]
        with patch.object(self.game.rng, 'randint', return_value=10):
            self.assertTrue(self.game.cast(self.a, spell, []))
            self.game.settle()
        self.assertEqual(self.a.life, life + 4)
        self.assertFalse(self.a.creatures)
        self.assertIn(first.front, self.a.exile)
        self.assertIn(second.front, self.a.exile)
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertEqual(self.a.life, life + 8)
        self.assertEqual(len(self.a.creatures), 2)
        self.assertTrue(all(x is not first and x is not second for x in self.a.creatures))

    def test_acrobatics_batches_do_not_mix_and_do_not_follow_reexile(self):
        spell = CardDB(offline=True).get("Lae'zel's Acrobatics")
        first = self.perm(BEAR, self.a)
        with patch.object(self.game.rng, 'randint', return_value=1):
            self.game.resolve(self.a, spell.spell_effects[0], None)
            second = self.perm(BEAR, self.a)
            self.game.resolve(self.a, spell.spell_effects[0], None)
        self.a.exile.remove(first.front)
        self.a.hand.append(first.front)
        self.game.move_card(first.front, self.a.hand, self.a.exile, reason='test')
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertIn(first.front, self.a.exile)
        self.assertNotIn(second.front, self.a.exile)
        self.assertEqual([x.front for x in self.a.creatures], [second.front])


if __name__ == "__main__":
    unittest.main()
