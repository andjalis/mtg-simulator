"""Separate exile/return abilities keep source and zone-object identity."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, ISLAND, PLAINS


class LinkedBlinkTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = [Player(n, [ISLAND] * 20, HeuristicAI()) for n in ('a', 'b')]
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, 'main1'
        self.db = CardDB(offline=True)
        for _ in range(8):
            self.perm(PLAINS, self.a)

    def perm(self, card, owner):
        perm = Permanent(card, owner)
        perm.sick, perm.tapped = False, False
        owner.battlefield.append(perm)
        return perm

    def apply(self, source, effects, target=None):
        self.game.stack.append(StackItem(source.controller, effects,
                                        [target] * len(effects), source=source))
        self.game.settle()

    def test_real_linked_cards_parse(self):
        for name in ('Synod Sanctum', 'Helvault', 'The Princess Takes Flight',
                     'Admonition Angel', 'Realm Razer', 'Worldgorger Dragon', 'Fiend Hunter',
                     'Oblivion Ring', 'Voyager Staff'):
            with self.subTest(name=name):
                self.assertEqual(self.db.get(name).unsupported, [])

    def test_sources_return_only_their_own_exact_still_exiled_cards(self):
        sanctum = self.db.get('Synod Sanctum')
        first, second = self.perm(sanctum, self.a), self.perm(sanctum, self.a)
        one, two, three = [self.perm(BEAR, self.a) for _ in range(3)]
        self.apply(first, sanctum.activated[0].effects, one)
        self.apply(first, sanctum.activated[0].effects, two)
        self.apply(second, sanctum.activated[0].effects, three)
        self.a.exile.remove(one.front)
        self.a.hand.append(one.front)
        self.game.move_card(one.front, self.a.hand, self.a.exile, reason='test')
        self.apply(first, sanctum.activated[1].effects)
        self.assertIn(one.front, self.a.exile)
        self.assertIn(three.front, self.a.exile)
        returned = [x for x in self.a.battlefield if x.card.name == BEAR.name]
        self.assertEqual([x.front for x in returned], [two.front])
        self.apply(second, sanctum.activated[1].effects)
        self.assertNotIn(three.front, self.a.exile)

    def test_sacrifice_cost_keeps_source_links_for_return_ability(self):
        sanctum = self.db.get('Synod Sanctum')
        source, bear = self.perm(sanctum, self.a), self.perm(BEAR, self.a)
        self.apply(source, sanctum.activated[0].effects, bear)
        self.assertTrue(self.game.activate(self.a, source, 'ability:1'))
        self.assertNotIn(source, self.a.battlefield)
        self.game.settle()
        self.assertTrue(any(x.front is bear.front for x in self.a.battlefield))

    def test_leaves_return_is_a_trigger_and_does_not_follow_new_source(self):
        hunter = self.db.get('Fiend Hunter')
        source, bear = self.perm(hunter, self.a), self.perm(BEAR, self.b)
        effects = hunter.triggers[0].effects
        with self.game.targeting(source):
            self.assertNotIn(source, self.game.legal_targets(self.a, effects[-1]))
        self.apply(source, effects, bear)
        self.assertIn(bear.front, self.b.exile)
        self.game.leave_battlefield(source, 'graveyard')
        self.assertIn(bear.front, self.b.exile)
        self.game.settle()
        self.assertTrue(any(x.front is bear.front for x in self.b.battlefield))

    def test_source_departing_before_exile_leaves_card_exiled(self):
        hunter = self.db.get('Fiend Hunter')
        source, bear = self.perm(hunter, self.a), self.perm(BEAR, self.b)
        exile = StackItem(self.a, hunter.triggers[0].effects, [bear, bear], source=source)
        self.game.stack.append(exile)
        self.game.leave_battlefield(source, 'graveyard')
        self.game.settle()
        self.assertIn(bear.front, self.b.exile)
        self.assertFalse(any(x.front is bear.front for x in self.b.battlefield))

    def test_group_return_tapped_under_owner_despite_changed_controller(self):
        razer = self.db.get('Realm Razer')
        source = self.perm(razer, self.a)
        land = self.perm(ISLAND, self.b)
        self.b.battlefield.remove(land)
        land.controller = self.a
        self.a.battlefield.append(land)
        self.apply(source, razer.triggers[0].effects)
        self.assertIn(land.front, self.b.exile)
        self.game.leave_battlefield(source, 'graveyard')
        self.game.settle()
        returned = next(x for x in self.b.battlefield if x.front is land.front)
        self.assertTrue(returned.tapped)
        self.assertIs(returned.owner, self.b)

    def test_worldgorger_excludes_itself_and_keeps_tokens_gone(self):
        from mtgsim.cards import make_token
        dragon = self.db.get('Worldgorger Dragon')
        source = self.perm(dragon, self.a)
        bear = self.perm(BEAR, self.a)
        token = self.perm(make_token('Bear', 2, 2), self.a)
        self.apply(source, dragon.triggers[0].effects)
        self.assertIn(source, self.a.battlefield)
        self.assertNotIn(token, self.a.battlefield)
        self.game.leave_battlefield(source, 'graveyard')
        self.game.settle()
        self.assertTrue(any(x.front is bear.front for x in self.a.battlefield))
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))


if __name__ == '__main__':
    unittest.main()
