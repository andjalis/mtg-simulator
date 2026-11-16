"""#313: amounts read from a card an earlier effect moved or revealed ("equal to that card's mana value")."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, MOUNTAIN, SWAMP, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
BIG = card("Big Spell", "{4}{R}{R}", "Sorcery", "Draw a card.")              # mana value 6
OGRE = card("Ogre", "{3}{R}", "Creature — Ogre", "", 5, 3)                   # power 5, mana value 4


def kinds(text):
    effects, bad = _parse_effects(text)
    return None if bad else [(e.kind, (e.data.get("xq") or ("",))[0]) for e in effects]


class Parsing(unittest.TestCase):
    def test_after_a_recorder(self):
        self.assertEqual(kinds("Mill a card, then draw cards equal to the milled card's mana value."),
                         [("mill", ""), ("draw", "card")])
        self.assertEqual(kinds("Target opponent reveals a card at random from their hand. ~ deals damage equal to "
                               "that card's mana value to that player."),
                         [("reveal_random", ""), ("damage", "card")])
        self.assertEqual(kinds("Return target creature card from your graveyard to your hand. ~ deals damage equal "
                               "to that card's power to target creature."), [("gy_move", ""), ("damage", "card")])

    def test_cost_cards(self):
        self.assertEqual(kinds("~ deals damage to target creature equal to the discarded card's mana value."),
                         [("damage", "discarded")])
        self.assertEqual(kinds("~ deals damage equal to the exiled card's power to each creature."),
                         [("damage", "exiled_gy")])

    def test_rejected_without_a_recorder(self):
        for text in ("Draw a card. Each opponent loses life equal to that card's mana value.",   # draw records nothing
                     "Mill two cards. Each opponent loses life equal to that card's mana value.",  # two cards: which?
                     "Destroy target creature. You gain life equal to the discarded card's mana value.",
                     "Mill a card. Draw cards equal to that card's power and lose life equal to that card's mana "
                     "value."):
            self.assertIsNone(kinds(text), text)


class Resolving(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = [ISLAND] * 10
        self.b.library = [ISLAND] * 10

    def run_spell(self, text, targets=None, by=None):
        c = card("Test Spell", "{R}", "Sorcery", text)
        self.assertEqual(c.unsupported, [], text)
        effects = list(c.spell_effects)
        item = StackItem(by or self.a, effects, targets or [None] * len(effects), card=c, name=c.name)
        self.g.stack.append(item)
        self.g.resolve_top()
        return item

    def test_milled_card(self):
        self.a.library.append(BIG)             # top card
        hand = len(self.a.hand)
        self.run_spell("Mill a card, then draw cards equal to the milled card's mana value.")
        self.assertIn(BIG, self.a.graveyard)
        self.assertEqual(len(self.a.hand) - hand, 6)

    def test_revealed_at_random_stays_in_hand(self):
        self.b.hand = [BIG]
        self.run_spell("Target opponent reveals a card at random from their hand. ~ deals damage equal to that "
                       "card's mana value to that player.", [self.b, None])
        self.assertEqual(self.b.life, 14)
        self.assertEqual(self.b.hand, [BIG])

    def test_discarded_card_and_that_player(self):
        self.b.hand = [OGRE]
        self.run_spell("Target player discards a card. ~ deals damage to that player equal to that card's power.",
                       [self.b, None])
        self.assertIn(OGRE, self.b.graveyard)
        self.assertEqual(self.b.life, 15)

    def test_returned_card_is_frozen_when_it_moves(self):
        self.a.graveyard.append(OGRE)
        theirs = self.g.enter_battlefield(self.b, card("Wall", "{2}", "Creature — Wall", "", 0, 5))
        self.run_spell("Return target creature card from your graveyard to your hand. ~ deals damage equal to that "
                       "card's power to target creature.", [None, theirs])
        self.assertIn(OGRE, self.a.hand)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_nothing_moved_means_zero(self):
        hand = len(self.a.hand)
        self.a.library = []
        self.run_spell("Mill a card, then draw cards equal to the milled card's mana value.")
        self.assertEqual(len(self.a.hand), hand)

    def test_discard_cost_of_an_ability(self):
        chem = self.g.enter_battlefield(self.a, card(
            "Chemist", "{1}{R}", "Creature — Human", "{R}, {T}, Discard a card: ~ deals damage to target creature "
            "equal to the discarded card's mana value.", 1, 1))
        self.assertEqual(chem.card.unsupported, [])
        chem.sick = False
        for _ in range(2):
            self.g.enter_battlefield(self.a, MOUNTAIN).sick = False
        self.a.hand = [BIG]
        theirs = self.g.enter_battlefield(self.b, card("Wall", "{2}", "Creature — Wall", "", 0, 6))
        self.assertTrue(self.g.activate(self.a, chem, "ability:0", [theirs]))
        self.g.settle()
        self.assertIn(BIG, self.a.graveyard)
        self.assertNotIn(theirs, self.b.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Baneful Omen", "Planeswalker's Fury", "Mercurial Chemister", "Planeswalker's Mirth",
                     "Pyretic Rebirth", "Heed the Mists", "Dread Defiler", "Ignite Memories", "Singe-Mind Ogre",
                     "Corpse Explosion", "Hellhole Rats", "Lie in Wait", "Volcanic Vision", "Interpret the Signs"):
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def game(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = [ISLAND] * 10
        b.library = [ISLAND] * 10
        return g, a, b

    def test_singe_mind_ogre_trigger_hits_the_revealing_player(self):
        g, a, b = self.game()
        b.hand = [BIG]
        for land in (MOUNTAIN, MOUNTAIN, MOUNTAIN, SWAMP, SWAMP):
            g.enter_battlefield(a, land).sick = False
        a.hand.append(self.db.get("Singe-Mind Ogre"))
        g.main_phase(a)
        g.settle()
        self.assertEqual(b.life, 14)
        self.assertEqual(b.hand, [BIG])

    def test_ai_activates_planeswalkers_fury_at_the_opponent(self):
        g, a, b = self.game()
        b.hand = [BIG]
        fury = g.enter_battlefield(a, self.db.get("Planeswalker's Fury"))
        for _ in range(4):
            g.enter_battlefield(a, MOUNTAIN).sick = False
        item = StackItem(a, list(fury.card.activated[0].effects), g.auto_targets(a, fury.card.activated[0].effects,
                                                                                   fury), source=fury, name="Fury")
        self.assertIs(item.targets[0], b)
        g.stack.append(item)
        g.resolve_top()
        self.assertEqual(b.life, 14)

    def test_corpse_explosion_reads_the_card_exiled_to_cast_it(self):
        g, a, b = self.game()
        for land in (MOUNTAIN, MOUNTAIN, MOUNTAIN, SWAMP, SWAMP):
            g.enter_battlefield(a, land).sick = False
        a.graveyard.append(OGRE)
        theirs = g.enter_battlefield(b, card("Wall", "{2}", "Creature — Wall", "", 0, 5))
        explosion = self.db.get("Corpse Explosion")
        a.hand.append(explosion)
        self.assertTrue(g.cast(a, explosion))
        g.settle()
        self.assertIn(OGRE, a.exile)
        self.assertNotIn(theirs, b.battlefield)


if __name__ == "__main__":
    unittest.main()
