"""#345 / Nihilith: "Whenever a card is put into an opponent's graveyard from anywhere, ..." (a new trigger event, fired
for every card, not token, that reaches an opponent's graveyard), also from a suspended card."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import SHOCK, card

MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
VULTURE = card("Test Vulture", "{3}{B}{G}", "Creature — Plant Zombie",
               "Whenever a card is put into an opponent's graveyard from anywhere, put a +1/+1 counter on this "
               "creature.", 3, 3)
NIHILITH = card("Test Nihilith", "{4}{B}{B}", "Creature — Horror",
                "Fear\nSuspend 7—{1}{B}\nWhenever a card is put into an opponent's graveyard from anywhere, if this "
                "card is suspended, you may remove a time counter from this card.", 4, 4)


def game():
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = [MOUNTAIN] * 10
    b.library = [MOUNTAIN] * 10
    for p in (a, b):
        g.enter_battlefield(p, MOUNTAIN).sick = False
    g.settle()
    return g, a, b


class OpponentCardToGraveyard(unittest.TestCase):
    def test_parsed(self):
        self.assertEqual(VULTURE.triggers[0].event, "opp_card_to_gy")

    def test_their_spell_and_their_creature_count_mine_dont(self):
        g, a, b = game()
        vulture = g.enter_battlefield(a, VULTURE)
        g.settle()
        b.hand.append(SHOCK)
        g.cast(b, SHOCK, targets=[a])            # their instant goes to their graveyard: +1
        g.settle()
        bear = g.enter_battlefield(b, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        g.settle()
        g.deal_damage(bear, 5, by=a)             # their creature dies: +1
        g.settle()
        a.hand.append(SHOCK)
        g.cast(a, SHOCK, targets=[b])            # my own spell: nothing
        g.settle()
        self.assertEqual(vulture.counters.get("+1/+1", 0), 2)

    def test_tokens_are_not_cards(self):
        g, a, b = game()
        vulture = g.enter_battlefield(a, VULTURE)
        g.settle()
        from mtgsim.cards import make_token
        tok = g.enter_battlefield(b, make_token("Goblin", 1, 1))
        g.settle()
        g.deal_damage(tok, 3, by=a)
        g.settle()
        self.assertEqual(vulture.counters.get("+1/+1", 0), 0)

    def test_suspended_nihilith_ticks_down(self):
        g, a, b = game()
        a.exile.append(NIHILITH)
        entry = [NIHILITH, 7]
        a.suspended.append(entry)
        b.hand.append(SHOCK)
        g.cast(b, SHOCK, targets=[a])
        g.settle()
        self.assertEqual(entry[1], 6)


if __name__ == "__main__":
    unittest.main()
