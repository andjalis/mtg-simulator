"""#634 RANDOM: numbers and targets chosen at random from the game's seeded generator, and the reveal / exile "at
random" wordings."""
import random
import unittest
from collections import Counter

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_random_number_quantity(self):
        effects, bad = _parse_effects("Target creature gets +X/+0 until end of turn, where X is a number from 0 to 6 "
                                      "chosen at random.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["xq"], ("cxq", "random", 0, 6))

    def test_random_target(self):
        effects, bad = _parse_effects("~ deals 2 damage to any target chosen at random.")
        self.assertEqual(bad, [])
        self.assertTrue(effects[0].data["random_target"])
        self.assertTrue(db("Witch Hunt").fully_supported)

    def test_reveal_wordings(self):
        for text in ("Reveal a card from your hand at random.", "That player reveals a card at random from their hand.",
                     "Look at a card at random in target player's hand.",
                     "Target opponent loses 2 life, then reveals a card at random from their hand."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertEqual(effects[-1].kind, "reveal_random", text)

    def test_refusals(self):
        for text in (
                # not targeted: hexproof doesn't stop it, so it isn't a random *target*
                "~ deals 7 damage to a creature an opponent controls chosen at random.",
                # "X creatures" is a count of creatures, not "every creature" (it used to read as tap all)
                "Tap X creatures, where X is a number from 0 to 5 chosen at random.",
                # an empty range
                "Target creature gets +X/+0 until end of turn, where X is a number from 6 to 2 chosen at random."):
            with self.subTest(text=text):
                self.assertTrue(_parse_effects(text)[1], text)

    def test_real_cards_full(self):
        for name in ("Goblin Secret Agent", "Goblin Test Pilot", "Hapato's Might", "Hired Torturer", "Merfolk Spy",
                     "Murgish Cemetery", "Scab-Clan Giant", "Tersa Lightshatter", "Urza's Bauble", "Witch Hunt"):
            self.assertTrue(db(name).fully_supported, name)
        self.assertFalse(db("Saji's Torrent").fully_supported)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def new(self, seed):
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(seed), log=True)
        game.turn, game.step = 3, "main1"
        a.library = b.library = [ISLAND] * 20
        return game, a, b

    def test_murgish_cemetery_sizes_cover_the_range_and_replay(self):
        sizes = Counter()
        for seed in range(60):
            game, a, _ = self.new(seed)
            cemetery = game.enter_battlefield(a, db("Murgish Cemetery"))
            for _ in range(4):
                game.enter_battlefield(a, SWAMP)
            a.hand = [ISLAND]
            self.assertTrue(game.activate_ability(a, cemetery, 0))
            game.settle()
            token = next(x for x in a.battlefield if x.card.is_token)
            self.assertEqual(token.power, token.toughness)
            sizes[token.power] += 1
        self.assertEqual(set(sizes), {2, 3, 4, 5, 6})
        runs = []
        for _ in range(2):
            game, a, _ = self.new(11)
            x = game.enter_battlefield(a, BEAR)
            c = db("Hapato's Might")
            game.stack.append(StackItem(a, list(c.spell_effects), [x], card=c, name=c.name))
            game.resolve_top()
            runs.append(x.power)
        self.assertEqual(runs[0], runs[1])          # same seed, same number

    def test_goblin_test_pilot_target_is_not_the_activators_pick(self):
        seen = Counter()
        for seed in range(40):
            game, a, b = self.new(seed)
            pilot = game.enter_battlefield(a, db("Goblin Test Pilot"))
            pilot.sick = False
            game.enter_battlefield(b, BEAR)
            game.activate_ability(a, pilot, 0, [b])         # asks for the opponent: the target is drawn instead
            game.settle()
            seen["me" if a.life < 20 else "them" if b.life < 20 else "a creature"] += 1
        self.assertEqual(set(seen), {"me", "them", "a creature"})

    def test_scab_clan_giant_fights_one_of_theirs(self):
        fought = Counter()
        for seed in range(30):
            game, a, b = self.new(seed)
            wurm = game.enter_battlefield(b, db("Craw Wurm"))
            game.enter_battlefield(b, BEAR)
            mine = game.enter_battlefield(a, BEAR)
            game.enter_battlefield(a, db("Scab-Clan Giant"))
            game.settle()
            self.assertEqual(mine.damage, 0)
            fought["wurm" if wurm.damage or wurm not in b.battlefield else "bear"] += 1
        self.assertEqual(set(fought), {"wurm", "bear"})


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class AI(unittest.TestCase):
    def test_random_pinger_only_when_their_side_is_bigger(self):
        from mtgsim.engine.policy import ability_worth
        for theirs, expect in ((1, False), (4, True)):
            a = Player("a", [], HeuristicAI())
            b = Player("b", [], HeuristicAI())
            game = Game(a, b, random.Random(0), log=True)
            game.turn, game.step = 3, "main1"
            pilot = game.enter_battlefield(a, db("Goblin Test Pilot"))
            pilot.sick = False
            game.enter_battlefield(a, db("Craw Wurm"))
            for _ in range(theirs):
                game.enter_battlefield(b, BEAR)
            self.assertEqual(ability_worth(game, a, pilot, 0), expect, theirs)


if __name__ == "__main__":
    unittest.main()
