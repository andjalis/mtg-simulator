"""Reveal-hand choose-and-move wordings: MV-constrained discards (Inquisition of Kozilek),
unfiltered choices (Coercion), permanent exiles with free-form filters (Castigate, Appetite
for Brains, Lifebane Zombie, Nimble Larcenist, Intimidation Tactics) and Lost Hours tucks."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.carddb import ALL_CARDS, CardDB
from tests.test_batch1 import Batch1
from tests.test_templates import ISLAND, card

GIANT = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)
ROCK = card("Test Rock", "{2}", "Artifact", "")
BOLT = card("Test Bolt", "{1}{R}", "Instant", "")
DECK = card("Test Deck", "{2}{U}", "Sorcery", "")
GREENGUY = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)


class Mega2HandDisruptParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_mv_bounded_discard(self):
        (eff,) = self.parse("Target player reveals their hand. You choose a nonland card from "
                            "it with mana value 3 or less. That player discards that card.")
        self.assertEqual((eff.kind, eff.filter, eff.data["mv"]), ("discard_choice", "nonland", (3, "less")))

    def test_unfiltered_discard(self):
        (eff,) = self.parse("Target opponent reveals their hand. You choose a card from it. "
                            "That player discards that card.")
        self.assertEqual((eff.kind, eff.filter), ("discard_choice", ""))

    def test_exile_with_filter_and_mv(self):
        (eff,) = self.parse("Target opponent reveals their hand. You choose a card from it "
                            "with mana value 4 or greater and exile that card.")
        self.assertEqual((eff.kind, eff.filter, eff.data["mv"]),
                         ("exile_hand_perm", "", (4, "greater")))
        (eff2,) = self.parse("Target opponent reveals their hand. You choose a green or white "
                             "creature card from it and exile that card.")
        self.assertEqual((eff2.kind, eff2.filter), ("exile_hand_perm", "green or white creature"))

    def test_exile_separate_sentence(self):
        (eff,) = self.parse("Target opponent reveals their hand. You choose an artifact or "
                            "creature card from it. Exile that card.")
        self.assertEqual((eff.kind, eff.filter), ("exile_hand_perm", "artifact or creature"))

    def test_tuck_third_from_top(self):
        (eff,) = self.parse("Target player reveals their hand. You choose a nonland card from "
                            "it. That player puts that card into their library third from the top.")
        self.assertEqual((eff.kind, eff.filter, eff.data["depth"]), ("tuck_choice", "nonland", 3))

    def test_oring_exile_until_leaves_stays_temporary(self):
        """The Kitesail-style wording (normalized by the parser to "until ~ leaves") must keep
        the hand_exile (until ~ leaves) behavior, not the new permanent exile."""
        effects, ignored = _parse_effects(
            "Target opponent reveals their hand. You choose a nonland card from it. "
            "Exile that card until ~ leaves the battlefield.")
        self.assertFalse(ignored, ignored)
        self.assertEqual([e.kind for e in effects], ["hand_exile"])


class Mega2HandDisruptBehavior(Batch1):
    def test_inquisition_only_takes_cheap_cards(self):
        self.b.hand = [GIANT, ROCK, ISLAND]
        self.apply("Target player reveals their hand. You choose a nonland card from it "
                   "with mana value 3 or less. That player discards that card.", [self.b])
        self.assertNotIn(ROCK, self.b.hand)
        self.assertIn(GIANT, self.b.hand)
        self.assertIn(ROCK, self.b.graveyard)

    def test_coercion_takes_the_best_card(self):
        self.b.hand = [GIANT, ISLAND]
        self.apply("Target opponent reveals their hand. You choose a card from it. "
                   "That player discards that card.", [self.b])
        self.assertEqual([c.name for c in self.b.graveyard], ["Test Giant"])

    def test_appetite_for_brains_only_takes_expensive_cards(self):
        self.b.hand = [GREENGUY, GIANT, ISLAND]
        self.apply("Target opponent reveals their hand. You choose a card from it with mana "
                   "value 4 or greater and exile that card.", [self.b])
        self.assertIn(GIANT, self.b.exile)
        self.assertNotIn(GIANT, self.b.hand)
        self.assertIn(GREENGUY, self.b.hand)

    def test_lifebane_zombie_takes_green_or_white_creatures(self):
        green = card("Test Warden", "{1}{G}", "Creature — Human", "", 1, 1)
        self.b.hand = [green, GREENGUY if GREENGUY.colors != frozenset({"G"}) else ROCK, BOLT]
        self.apply("Target opponent reveals their hand. You choose a green or white creature "
                   "card from it and exile that card.", [self.b])
        self.assertIn(green, self.b.exile)

    def test_nimble_larcenist_takes_artifacts_instants_sorceries(self):
        self.b.hand = [GIANT, ROCK, BOLT, DECK]
        self.apply("Target opponent reveals their hand. You choose an artifact, instant, or "
                   "sorcery card from it and exile that card.", [self.b])
        self.assertEqual([c.name for c in self.b.exile], ["Test Deck"])
        self.assertIn(ROCK, self.b.hand)

    def test_lost_hours_tucks_third_from_top(self):
        self.b.hand = [GIANT, ROCK]
        self.b.library = [ISLAND, ISLAND]
        self.apply("Target player reveals their hand. You choose a nonland card from it. "
                   "That player puts that card into their library third from the top.", [self.b])
        self.assertEqual(len(self.b.hand), 1)
        self.assertEqual(len(self.b.library), 3)
        # the top of the library is the end of the list: third from the top is the first card
        self.assertEqual(self.b.library[0].name, "Test Giant")

    def test_database_cards_parse_fully(self):
        if not ALL_CARDS.exists():
            self.skipTest("card database not built")
        db = CardDB()
        for name in ("Inquisition of Kozilek", "Coercion", "Castigate", "Appetite for Brains",
                     "Transgress the Mind", "Lifebane Zombie", "Nimble Larcenist",
                     "Intimidation Tactics", "Lost Hours", "Night Terrors", "Duress"):
            card_def = db.get(name)
            self.assertFalse(card_def.unsupported, (name, card_def.unsupported))


if __name__ == "__main__":
    unittest.main()
