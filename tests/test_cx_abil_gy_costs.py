"""Graveyard return abilities with extra cost parts: discard N, exile other cards from the graveyard, mill."""

from tests import test_graveyard_activated as base
from tests.test_templates import BEAR, ISLAND


class GyCosts(base.GraveyardActivated):
    def test_discard_two(self):
        c = self.prepare("{2}, Discard two cards: Return this card from your graveyard to the battlefield tapped.")
        self.a.hand = [ISLAND]
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))
        self.a.hand = [ISLAND, BEAR, ISLAND]
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual([p.card for p in self.a.creatures], [c])
        self.assertTrue(self.a.creatures[0].tapped)

    def test_exile_other_creature_card(self):
        c = self.prepare("{1}, Exile another creature card from your graveyard: Return this card from your graveyard "
                         "to the battlefield.")
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))      # only itself is a creature card there
        self.a.graveyard.append(BEAR)
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertEqual(self.a.exile, [BEAR])
        self.assertEqual([p.card for p in self.a.creatures], [c])

    def test_mill_cost(self):
        c = self.prepare("{2}, Mill four cards: Return this card from your graveyard to the battlefield. "
                         "Activate only as a sorcery.", mana=2)
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertEqual(len(self.a.library), 6)

