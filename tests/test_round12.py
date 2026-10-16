"""Round 12: graveyard returns by description, granted flashback, graveyard-count statics."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card

RAISE = card("Test Raise", "{2}{B}", "Sorcery", "Return up to two target creature cards each with mana value 2 or less "
             "from your graveyard to the battlefield.")
RELIC = card("Test Relic Return", "{1}{B}", "Sorcery", "Return target noncreature, nonland permanent card with mana value "
             "3 or less from your graveyard to the battlefield tapped.")
LANDS = card("Test Lands", "{1}{G}", "Sorcery", "Return all land cards from your graveyard to the battlefield tapped.")
REPLAY = card("Test Replay", "{1}{R}", "Sorcery", "Target instant or sorcery card in your graveyard gains flashback until "
              "end of turn.")
DELVER = card("Test Delver", "{3}", "Creature — Wizard", "Threshold — ~ gets +1/+1 and has deathtouch as long as there are "
              "seven or more cards in your graveyard.", 2, 2)
CHEAP = card("Test Cheap", "{5}", "Artifact Creature — Golem", "~ costs {1} less to cast for each artifact and/or creature "
             "card in your graveyard.", 4, 4)
LEAVER = card("Test Leaver", "{2}", "Creature — Spirit", "Whenever one or more creature cards leave your graveyard, you "
              "gain 1 life.", 1, 1)
EXILE3 = card("Test Exile", "{1}{W}", "Instant", "Exile target creature with mana value 3 or less.")
ANYTHING = card("Test Banish", "{2}{W}", "Sorcery", "Exile up to one target artifact or creature.")
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
ART = card("Test Trinket", "{2}", "Artifact", "")
BOLT = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")
MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")


class Round12(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def cast(self, spell, lands):
        for l in lands:
            self.perm(l)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()

    def test_templates(self):
        for c in (RAISE, RELIC, LANDS, REPLAY, DELVER, CHEAP):
            self.assertEqual(c.unsupported, [], c.name)

    def test_returns_creatures_up_to_the_mana_limit(self):
        ogre = card("Ogre", "{4}", "Creature — Ogre", "", 5, 5)
        self.a.graveyard += [BEAR, BEAR, ogre]
        self.cast(RAISE, [SWAMP] * 3)
        self.assertEqual(sum(x.card is BEAR for x in self.a.battlefield), 2)
        self.assertIn(ogre, self.a.graveyard)

    def test_returns_a_noncreature_permanent_tapped(self):
        self.a.graveyard += [BEAR, ART]
        self.cast(RELIC, [SWAMP] * 2)
        back = [x for x in self.a.battlefield if x.card is ART]
        self.assertEqual(len(back), 1)
        self.assertTrue(back[0].tapped)
        self.assertIn(BEAR, self.a.graveyard)

    def test_returns_all_lands(self):
        self.a.graveyard += [FOREST, FOREST, BEAR]
        self.cast(LANDS, [FOREST] * 2)
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 4)

    def test_granted_flashback_lets_the_spell_be_cast_again(self):
        self.a.graveyard.append(BOLT)
        self.cast(REPLAY, [MOUNTAIN] * 2)
        opts = [c for c in self.game.spell_options(self.a) if c.name.startswith(BOLT.name)]
        self.assertTrue(opts)
        self.game.turn = 3                         # next turn the grant is gone
        self.game.cleanup_for_test = None
        for pl in self.game.players:
            pl.granted_fb = []
        self.assertFalse([c for c in self.game.spell_options(self.a) if c.name.startswith(BOLT.name)])

    def test_threshold_static(self):
        d = self.perm(DELVER)
        self.assertEqual((d.power, d.has("deathtouch")), (2, False))
        self.a.graveyard += [BEAR] * 7
        self.assertEqual((d.power, d.has("deathtouch")), (3, True))

    def test_cost_reduction_counts_matching_graveyard_cards(self):
        self.assertEqual(self.game.cost_of(self.a, CHEAP).get("generic"), 5)
        self.a.graveyard += [BEAR, ART, ISLAND]
        self.assertEqual(self.game.cost_of(self.a, CHEAP).get("generic"), 3)

    def test_cards_leaving_the_graveyard_trigger_once_per_batch(self):
        self.perm(LEAVER)
        self.a.graveyard += [BEAR, BEAR, ART]
        self.cast(RAISE, [SWAMP] * 3)
        self.assertEqual(self.a.life, 21)

    def test_exile_with_a_mana_value_limit(self):
        small = self.perm(BEAR, self.b)
        big = self.perm(card("Ogre", "{4}", "Creature — Ogre", "", 5, 5), self.b)
        self.assertEqual(EXILE3.unsupported, [])
        self.assertTrue(self.game.passes_filter(EXILE3.spell_effects[0], small, self.a))
        self.assertFalse(self.game.passes_filter(EXILE3.spell_effects[0], big, self.a))

    def test_exile_artifact_or_creature_template(self):
        self.assertEqual(ANYTHING.unsupported, [])


if __name__ == "__main__":
    unittest.main()
