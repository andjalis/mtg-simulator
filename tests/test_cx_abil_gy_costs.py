"""Graveyard return abilities with extra cost parts: discard N, exile other cards from the graveyard, mill."""

from tests import test_graveyard_activated as base
from tests.test_templates import BEAR, ISLAND, card


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



class GyMore(base.GraveyardActivated):
    def test_sacrifice_two_creatures(self):
        c = self.prepare("{1}, Sacrifice two creatures: Return ~ from your graveyard to the battlefield. "
                         "Activate only as a sorcery.", mana=1)
        self.game.enter_battlefield(self.a, BEAR)
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))
        self.game.enter_battlefield(self.a, BEAR)
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertEqual([x.card for x in self.a.creatures], [c])

    def test_sacrifice_named_type(self):
        c = self.prepare("Sacrifice three Elves: Return this card from your graveyard to the battlefield.", mana=0)
        self.assertEqual(c.unsupported, [])
        elf = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
        for _ in range(3):
            self.game.enter_battlefield(self.a, elf)
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertEqual([x.card for x in self.a.creatures], [c])

    def test_only_during_your_upkeep(self):
        c = self.prepare("{1}: Return this card from your graveyard to the battlefield. Activate only during your upkeep.",
                         mana=1)
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))      # main phase
        self.game.step = "upkeep"
        self.assertTrue(self.game.activate_graveyard(self.a, c))

    def test_only_if_control(self):
        c = self.prepare("{1}: Return this card from your graveyard to the battlefield. "
                         "Activate only if you control a legendary creature.", mana=1)
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))
        self.game.enter_battlefield(self.a, card("Test Legend", "{1}", "Legendary Creature — Human", "", 1, 1))
        self.assertTrue(self.game.can_activate_graveyard(self.a, c))

    def test_counters_on_return(self):
        c = self.prepare("{1}: Return this card from your graveyard to the battlefield tapped with two +1/+1 counters on it.",
                         mana=1)
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        perm = self.a.creatures[0]
        self.assertEqual((perm.counters.get("+1/+1"), perm.tapped, perm.power), (2, True, 4))

    def test_return_to_hand_with_cost(self):
        c = self.prepare("Sacrifice a creature: Return this card from your graveyard to your hand. Activate only as a sorcery.",
                         mana=0)
        self.game.enter_battlefield(self.a, BEAR)
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertIn(c, self.a.hand)


class GyAI(base.GraveyardActivated):
    """HeuristicAI's end-of-turn graveyard pass (Game.graveyard_abilities) pays the new costs sensibly."""

    def run_ai(self, text, mana=3, **kw):
        c = self.prepare(text, mana=mana)
        self.game.graveyard_abilities(self.a)
        return c

    def test_ai_sacrifices_tokens_but_not_good_creatures(self):
        text = "{1}, Sacrifice two creatures: Return ~ from your graveyard to the battlefield."
        c = self.prepare(text, mana=1)
        for _ in range(2):
            self.game.enter_battlefield(self.a, card("Test Big", "{4}", "Creature — Giant", "", 5, 5))
        self.game.graveyard_abilities(self.a)
        self.assertIn(c, self.a.graveyard)                                  # two 5/5s are worth more than a 2/2

    def test_ai_sacrifices_cheap_permanents(self):
        c = self.prepare("{1}, Sacrifice two creatures: Return ~ from your graveyard to the battlefield.", mana=1)
        token = card("Test Token", "{0}", "Creature — Goblin", "", 1, 1)
        for _ in range(2):
            self.game.enter_battlefield(self.a, token)
        self.game.graveyard_abilities(self.a)
        self.assertEqual([x.card for x in self.a.creatures if x.card is c], [c])

    def test_ai_keeps_its_last_cards(self):
        c = self.prepare("{1}, Discard two cards: Return this card from your graveyard to the battlefield tapped.", mana=1)
        self.a.hand = [BEAR, BEAR]
        self.game.graveyard_abilities(self.a)
        self.assertIn(c, self.a.graveyard)
        self.a.hand = [BEAR, BEAR, ISLAND]
        self.game.graveyard_abilities(self.a)
        self.assertNotIn(c, self.a.graveyard)


del base
