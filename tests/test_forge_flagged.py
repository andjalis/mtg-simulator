"""Cards the Forge cross-check flagged: Izzet, Dimir, Jund and Azorius decks."""
import unittest

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SWAMP, PLAINS, card
from tests.test_empower_discover import Base

HEARTH = card("Test Hearth", "{5}{R}", "Creature — Elemental",
              "This spell costs {X} less to cast, where X is the number of cards in your graveyard that are instant "
              "cards, sorcery cards, and/or have an Adventure.", 4, 5)
FLOCK = card("Test Flock", "{7}{U}{U}", "Creature — Elemental",
             "This spell costs {X} less to cast, where X is the greatest mana value among Elementals you control.\n"
             "Flying\nWhen this creature enters, if you cast it, return all non-Elemental creatures to their owners' hands.",
             5, 5)
GETOUT = card("Test Get Out", "{U}{U}", "Instant",
              "Choose one —\n• Counter target creature or enchantment spell.\n"
              "• Return one or two target creatures and/or enchantments you own to your hand.")
FLOW = card("Test Flow", "{1}{U}", "Sorcery",
            "Look at the top three cards of your library. Put one of them into your hand and the rest on the bottom of "
            "your library in any order. If there is an instant card and a sorcery card in your graveyard, instead put "
            "two of them into your hand and the rest on the bottom of your library in any order.")
AZOG = card("Azog", "{2}{B}", "Legendary Creature — Goblin Soldier",
            "When Azog enters, destroy up to one other target creature. Its controller amasses Goblins X, where X is "
            "that creature's power. If you controlled that creature, draw a card.", 1, 3)
PURSUIT = card("Test Pursuit", "{1}{B}", "Enchantment",
               "Whenever you attack, put X +1/+1 counters on target attacking creature, where X is the number of "
               "permanents you've sacrificed this turn. If X is three or greater, that creature gains lifelink until "
               "end of turn.")
SACK = card("Test Sack", "{1}{B}", "Legendary Creature — Halfling",
            "When Test Sack enter, you may sacrifice another creature or artifact. If you do, draw a card and create "
            "a Treasure token.", 2, 2)
THEORIST = card("Test Theorist", "{2}{U}{U}", "Legendary Planeswalker — Jace",
                "At the beginning of each opponent's draw step, you draw a card.\n+1: Create a 1/1 blue Illusion creature "
                "token.\n−2: For each opponent, return up to one target artifact or creature that player controls to its "
                "owner's hand.", None, None)
COVER = card("Test Cover", "{3}{B}{B}", "Sorcery",
             "As an additional cost to cast this spell, you may collect evidence 6.\nDestroy all creatures. If evidence "
             "was collected, exile a card from an opponent's graveyard. Then search its owner's graveyard, hand, and "
             "library for any number of cards with that name and exile them. That player shuffles, then draws a card "
             "for each card exiled from their hand this way.")
BAY = card("Test Bay", "{2}{U}", "Artifact",
           "{2}, {T}, Sacrifice another artifact: Search your library for an artifact card with mana value equal to 1 "
           "plus the sacrificed artifact's mana value, put that card onto the battlefield, then shuffle. Activate only "
           "as a sorcery.")
STONE = card("Test Stone", "{1}{W}", "Legendary Artifact — Infinity Stone",
             "Indestructible\n{T}: Add {W}.\n{5}{W}, {T}: Harness ~.\n∞ — At the beginning of your end step, exile up "
             "to one other target nonland permanent you control, then return that card to the battlefield under its "
             "owner's control.")
HAMLET = card("Test Hamlet", "", "Land",
              "When this land enters, choose a land card name.\nActivated abilities of sources with the chosen name "
              "can't be activated unless they're mana abilities.\nLands with the chosen name have \"{T}: Add {C}.\"\n"
              "{T}: Add {C}.")
SPREE = card("Test Dirge", "{1}{B}", "Sorcery",
             "Spree (Choose one or more additional costs.)\n+ {1} — Search your library for a card, put it into your "
             "graveyard, then shuffle.\n+ {2} — Return up to two creature cards with total mana value 4 or less from "
             "your graveyard to the battlefield.")
CAGE = card("Test Cage", "{1}{W}{W}", "Artifact",
            "{6}{W}{W}: Put each card exiled with ~ into its owner's graveyard, then create a 2/2 colorless Robot "
            "artifact creature token for each card put into a graveyard this way. Sacrifice ~.")


class ForgeFlagged(Base):
    def test_templates(self):
        for c in (HEARTH, FLOCK, GETOUT, FLOW, AZOG, PURSUIT, SACK, THEORIST, COVER, BAY, STONE, HAMLET, SPREE, CAGE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_hearth_cost_counts_graveyard(self):
        self.a.graveyard.extend([card("Bolt", "{R}", "Instant", "Draw a card."),
                                 card("Ritual", "{R}", "Sorcery", "Draw a card."), BEAR])
        self.assertEqual(self.game.cost_of(self.a, HEARTH).get("generic"), 3)

    def test_sunderflock_cost_and_bounce(self):
        elem = card("Elem", "{3}", "Creature — Elemental", "", 3, 3)
        self.perm(elem)
        self.assertEqual(self.game.cost_of(self.a, FLOCK).get("generic"), 4)
        bear = self.perm(BEAR, self.b)
        self.game.resolve(self.a, FLOCK.etb_effects[0] if FLOCK.etb_effects else FLOCK.triggers[0].effects[0], None)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(BEAR, self.b.hand)
        self.assertEqual(len(self.a.creatures), 1)

    def test_flow_state_takes_two_with_instant_and_sorcery(self):
        self.a.graveyard.extend([card("I", "{1}", "Instant", "Draw a card."), card("S", "{1}", "Sorcery", "Draw a card.")])
        self.a.library = [ISLAND] * 5
        self.game.resolve(self.a, FLOW.spell_effects[0], None)
        self.assertEqual(len(self.a.hand), 2)

    def test_azog_destroys_and_amasses_for_controller(self):
        big = self.perm(card("Ogre", "{3}", "Creature — Ogre", "", 3, 3), self.b)
        src = self.perm(AZOG)
        from mtgsim.engine import StackItem
        item = StackItem(self.a, [], [], kind="trigger", source=src)
        self.game.resolve(self.a, AZOG.triggers[0].effects[0], big, item)
        self.assertNotIn(big, self.b.battlefield)
        army = next(x for x in self.b.battlefield if "Army" in x.card.subtypes)
        self.assertEqual(army.power, 3)
        self.assertEqual(len(self.a.hand), 0)

    def test_obsessive_pursuit_counts_sacrifices(self):
        bear = self.perm(BEAR)
        self.a.sacrificed_turn = 3
        self.game.resolve(self.a, PURSUIT.triggers[0].effects[0], bear)
        self.assertEqual(bear.power, 5)
        self.assertTrue(bear.has("lifelink"))

    def test_theorist_draws_in_opponents_draw_step(self):
        self.perm(THEORIST)
        before = len(self.a.hand)
        self.game.take_turn(self.b)
        self.assertEqual(len(self.a.hand), before + 1)

    def test_cover_up_with_evidence(self):
        self.a.graveyard.extend([card("Big", "{6}", "Creature — Giant", "", 6, 6)])
        self.b.graveyard.append(card("Gem", "{2}", "Artifact", ""))
        self.b.hand.append(card("Gem", "{2}", "Artifact", ""))
        for _ in range(5):
            self.perm(SWAMP)
        self.a.hand.append(COVER)
        self.assertTrue(self.game.cast(self.a, COVER, []))
        self.game.settle()
        self.assertEqual(len(self.b.hand), 1)                # drew one for the exiled copy in hand
        self.assertFalse(any(c.name == "Gem" for c in self.b.graveyard))

    def test_repurposing_bay_fetches_next_mana_value(self):
        bay = self.perm(BAY)
        self.perm(card("Gem", "{1}", "Artifact", ""))
        target = card("Rock", "{2}", "Artifact", "")
        self.a.library = [target, ISLAND]
        for _ in range(2):
            self.perm(ISLAND)
        self.assertTrue(self.game.activate_ability(self.a, bay, 0))
        self.game.settle()
        self.assertTrue(any(x.card.name == "Rock" for x in self.a.battlefield))

    def test_mind_stone_harness_then_blink(self):
        stone = self.perm(STONE)
        for _ in range(6):
            self.perm(PLAINS)
        self.assertTrue(self.game.activate_ability(self.a, stone, 0))
        self.game.settle()
        self.assertTrue(stone.harnessed)

    def test_reanimate_total_returns_two_small_creatures(self):
        from mtgsim.cards import Effect
        self.a.graveyard.extend([BEAR, BEAR, BEAR])
        self.game.resolve(self.a, Effect("reanimate_total", 4), None)
        self.assertEqual(len(self.a.creatures), 2)

    def test_starcage_returns_exiled_cards_as_robots(self):
        cage = self.perm(CAGE)
        cage.exiled_cards.append((BEAR, self.b))
        self.b.exile.append(BEAR)
        for _ in range(8):
            self.perm(PLAINS)
        self.assertTrue(self.game.activate_ability(self.a, cage, 0))
        self.game.settle()
        self.assertIn(BEAR, self.b.graveyard)
        self.assertTrue(any(x.card.name == "Robot token" for x in self.a.battlefield))
        self.assertNotIn(cage, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()
