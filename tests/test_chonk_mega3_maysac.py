"""The remaining "you may sacrifice it. If you do, <payoff>" cards: multi-card
"that player discards", "defending player discards" (Mindstab Thrull) and
"destroy target creature that player controls" (Blind Zealot).
"""
import unittest

from mtgsim.cards import _parse_effects, card_from_scryfall
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import BEAR, DRAGON3, card

CADAVER = card("Test Cadaver", "{3}{B}", "Creature — Zombie", "", 2, 2)
THRULL = card("Test Thrull", "{1}{B}{B}", "Creature — Thrull", "", 2, 2)
ZEALOT = card("Test Zealot", "{1}{B}{B}", "Creature — Human Cleric", "", 2, 2)


def face(text):
    return card_from_scryfall({"name": "Test Card", "mana_cost": "{2}{B}", "type_line": "Creature — Test",
                               "oracle_text": text, "power": "2", "toughness": "2"})


class MaySacParse(unittest.TestCase):
    def trigger_effects(self, text, event):
        c = face(text)
        (trig,) = c.triggers
        self.assertEqual(trig.event, event)
        return trig.effects

    def test_that_player_discards_three(self):
        (eff,) = self.trigger_effects("Whenever ~ deals combat damage to a player, you may "
                                      "sacrifice it. If you do, that player discards three cards.",
                                      "combat_damage_player")
        self.assertEqual(eff.kind, "sac_self_payoff")
        (discard,) = eff.data["effects"]
        self.assertEqual((discard.kind, discard.amount, discard.target),
                         ("discard", 3, "that_player"))

    def test_defending_player_discards_three(self):
        (eff,) = self.trigger_effects("Whenever ~ attacks and isn't blocked, you may "
                                      "sacrifice it. If you do, defending player discards three cards.",
                                      "unblocked")
        (discard,) = eff.data["effects"]
        self.assertEqual((discard.kind, discard.amount), ("discard_defender", 3))

    def test_destroy_that_player_controls(self):
        (eff,) = self.trigger_effects("Whenever ~ deals combat damage to a player, you may "
                                      "sacrifice it. If you do, destroy target creature that "
                                      "player controls.", "combat_damage_player")
        (destroy,) = eff.data["effects"]
        self.assertEqual((destroy.kind, destroy.data.get("type")), ("destroy_that_player", "creature"))

    def test_equipment_subject_gate(self):
        (eff,) = self.trigger_effects("Whenever ~ deals combat damage to a player, you may "
                                      "sacrifice this Equipment. If you do, draw a card.",
                                      "combat_damage_player")
        self.assertEqual(eff.kind, "sac_self_payoff")


class MaySacBehavior(Batch1):
    def sac_payoff(self, payoff_text, source=None, context=None):
        effects, ignored = _parse_effects(f"SACSELF {payoff_text}")
        self.assertFalse(ignored, ignored)
        item = StackItem(self.a, effects, [None], source=source, context=context)
        for eff in item.effects:
            self.g.resolve(self.a, eff, None, item)
        self.g.settle()               # resolve the queued payoff trigger
        return item

    def test_sacrifices_and_that_player_discards_three(self):
        cadaver = self.put(CADAVER)
        self.b.hand = [BEAR, BEAR, BEAR, BEAR]
        self.sac_payoff("That player discards three cards.", source=cadaver, context=self.b)
        self.assertNotIn(cadaver, self.a.battlefield)      # sacrificed
        self.assertEqual(len(self.b.hand), 1)              # the damaged player discarded 3
        self.assertEqual(len(self.b.graveyard), 3)

    def test_defending_player_discards(self):
        thrull = self.put(THRULL)
        self.b.hand = [BEAR, BEAR, BEAR]
        self.sac_payoff("Defending player discards three cards.", source=thrull)
        self.assertEqual(self.b.hand, [])
        self.assertEqual(self.a.hand, [])

    def test_destroy_that_player_best_creature(self):
        zealot = self.put(ZEALOT)
        weak = self.put(BEAR, self.b)
        strong = self.put(DRAGON3, self.b)
        self.sac_payoff("Destroy target creature that player controls.",
                         source=zealot, context=self.b)
        self.assertNotIn(strong, self.b.battlefield)
        self.assertIn(weak, self.b.battlefield)


class MaySacDatabase(unittest.TestCase):
    def test_cards_fully_parse(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        for name in ("Blind Zealot", "Haunted Cadaver", "Mindstab Thrull", "Cacophony Scamp"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored, row.simplified))


if __name__ == "__main__":
    unittest.main()
