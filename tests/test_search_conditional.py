"""Searches whose destination depends on the card found (Archdruid's Charm, Guidelight Pathmaker) and searches
for cards with the same name as a target creature (Mask of the Mimic, Bifurcate, Pack Hunt) (#339)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.policy import default_choose_target

from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
OGRE = card("Big Ogre", "{4}{R}", "Creature — Ogre", "", 5, 5)
ROCK = card("Test Rock", "{1}", "Artifact", "")
BIG_ROCK = card("Test Big Rock", "{5}", "Artifact", "")
CHARM = card("Test Charm", "{G}", "Sorcery", "Search your library for a creature or land card and reveal it. Put it "
             "onto the battlefield tapped if it's a land card. Otherwise, put it into your hand. Then shuffle.")
PATH = card("Test Path", "{2}", "Sorcery", "Search your library for an artifact card and reveal it. Put it onto the "
            "battlefield if its mana value is 2 or less. Otherwise, put it into your hand. If you search your "
            "library this way, shuffle.")
MIMIC = card("Test Mimic", "{U}", "Instant", "Search your library for a card with the same name as target nontoken "
             "creature, put that card onto the battlefield, then shuffle.")
HUNT = card("Test Hunt", "{G}", "Sorcery", "Search your library for up to three cards with the same name as target "
            "creature, reveal them, put them into your hand, then shuffle.")


class Parsing(unittest.TestCase):
    def test_written(self):
        for c in (CHARM, PATH, MIMIC, HUNT):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(CHARM.spell_effects[0].data["plan"][0][4], {"type": "land"})
        self.assertEqual(PATH.spell_effects[0].data["plan"][0][4], {"mv_max": 2})
        self.assertEqual((MIMIC.spell_effects[0].target, MIMIC.spell_effects[0].data["name_as_target"]),
                         ("permanent", True))

    def test_refusals(self):
        for text in ("Search your library for a basic land card and reveal it. You may put that card onto the "
                     "battlefield tapped if you control a land named Wastes. Otherwise, put that card into your hand. "
                     "Then shuffle.",
                     "Search your library for up to two cards and reveal them. Put them onto the battlefield if "
                     "they're land cards. Otherwise, put them into your hand. Then shuffle.",
                     "Target player searches their library for a card with the same name as target creature, puts it "
                     "onto the battlefield, then shuffles."):
            with self.subTest(text=text):
                self.assertTrue(_parse_effects(text)[1])

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards(self):
        db = CardDB(offline=True)
        for name in ("Archdruid's Charm", "Guidelight Pathmaker", "Pack Hunt", "Mask of the Mimic", "Bifurcate"):
            with self.subTest(name=name):
                self.assertEqual(db.get(name).unsupported, [])


class Resolving(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main1"

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick = p.tapped = False
        owner.battlefield.append(p)
        return p

    def cast(self, c, targets=None):
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), targets or [None], card=c, name=c.name))
        self.game.resolve_top()

    def test_a_land_goes_onto_the_battlefield_tapped(self):
        self.a.library = [FOREST, ISLAND]
        self.a.ai = HeuristicAI()
        self.a.hand = [OGRE]          # nothing to want from the creatures: the tutor takes a land
        self.cast(CHARM)
        lands = [x for x in self.a.battlefield if x.card.is_land]
        found_in_hand = [c for c in self.a.hand if c.name != OGRE.name]
        self.assertEqual(len(lands) + len(found_in_hand), 1)
        self.assertEqual(len(self.a.library), 1)
        for x in lands:
            self.assertTrue(x.tapped)

    def test_a_creature_goes_to_the_hand(self):
        self.a.library = [OGRE, BEAR]
        self.cast(CHARM)
        self.assertEqual(self.a.battlefield, [])
        self.assertEqual(len(self.a.hand), 1)
        self.assertTrue(self.a.hand[0].is_creature)

    def test_mana_value_decides(self):
        self.a.library = [ROCK]
        self.cast(PATH)
        self.assertEqual([x.card.name for x in self.a.battlefield], [ROCK.name])
        self.a.library = [BIG_ROCK]
        self.cast(PATH)
        self.assertIn(BIG_ROCK.name, [c.name for c in self.a.hand])

    def test_same_name_as_the_target(self):
        target = self.perm(BEAR, self.b)
        self.a.library = [OGRE, BEAR, BEAR, ISLAND]
        self.cast(MIMIC, [target])
        self.assertEqual([x.card.name for x in self.a.battlefield], [BEAR.name])
        self.assertEqual(sorted(c.name for c in self.a.library), sorted([OGRE.name, BEAR.name, ISLAND.name]))

    def test_up_to_three_with_that_name(self):
        target = self.perm(BEAR, self.a)
        self.a.library = [BEAR, OGRE, BEAR]
        self.cast(HUNT, [target])
        self.assertEqual([c.name for c in self.a.hand], [BEAR.name, BEAR.name])
        self.assertEqual([c.name for c in self.a.library], [OGRE.name])

    def test_target_gone_finds_nothing(self):
        target = self.perm(BEAR, self.b)
        self.a.library = [BEAR]
        self.game.stack.append(StackItem(self.a, list(MIMIC.spell_effects), [target], card=MIMIC, name=MIMIC.name))
        self.b.battlefield.remove(target)
        self.game.resolve_top()
        self.assertEqual(self.a.battlefield, [])
        self.assertEqual(len(self.a.library), 1)

    def test_ai_aims_at_the_name_its_library_holds(self):
        self.perm(OGRE, self.a)
        bear = self.perm(BEAR, self.b)
        self.a.library = [BEAR, BEAR, ISLAND]
        self.assertIs(default_choose_target(self.game, self.a, MIMIC.spell_effects[0]), bear)
        self.a.library = [ISLAND]
        self.assertIsNone(default_choose_target(self.game, self.a, MIMIC.spell_effects[0]))


if __name__ == "__main__":
    unittest.main()
