"""#313: real Oracle text and last-known statistics of cards and permanents."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

ELF = card("Referent Elf", "{3}{G}", "Creature — Elf", "", 4, 6)


class ReferentStats(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(13))
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 30
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        self.db = CardDB(offline=True)
        if self.db._all is not None:
            self.addCleanup(self.db._all.close)

    def resolve(self, effects, targets=None, source=None, context=None, controller=None):
        item = StackItem(controller or self.a, effects, targets or [None] * len(effects),
                         source=source, context=context, kind="trigger")
        self.g.stack.append(item)
        self.g.resolve_top()
        return item

    def test_mirkwood_elk_returns_elf_and_gains_its_power(self):
        elk = self.db.get("Mirkwood Elk")
        self.assertFalse(elk.unsupported)
        self.a.graveyard.append(ELF)
        self.resolve(elk.triggers[0].effects)
        self.assertIn(ELF, self.a.hand)
        self.assertEqual(self.a.life, 24)

    def test_failed_return_gains_nothing_and_clears_previous_card(self):
        effects = self.db.get("Mirkwood Elk").triggers[0].effects
        self.a.graveyard.append(ELF)
        item = self.resolve(effects)
        self.assertEqual(self.a.life, 24)
        for eff in effects:
            self.g.resolve(self.a, eff, None, item)
        self.assertEqual(self.a.life, 24)

    def test_rotfeaster_can_exile_from_own_graveyard_and_reads_toughness(self):
        maggot = self.db.get("Rotfeaster Maggot")
        self.assertFalse(maggot.unsupported)
        self.a.graveyard.append(ELF)
        target = self.a.graveyard[-1]
        effects = maggot.triggers[0].effects
        self.assertIn(target, self.g.legal_targets(self.a, effects[0]))
        self.resolve(effects, [target, None])
        self.assertIn(target, self.a.exile)
        self.assertEqual(self.a.life, 26)

    def test_rotfeaster_does_not_replace_illegal_target_with_same_name_copy(self):
        effects = self.db.get("Rotfeaster Maggot").triggers[0].effects
        self.b.graveyard.extend([ELF, ELF])
        gone = self.b.graveyard.pop()
        self.b.hand.append(gone)
        self.resolve(effects, [gone, None])
        self.assertEqual(self.a.life, 20)
        self.assertEqual(len(self.b.graveyard), 1)

    def test_daxos_uses_damaged_players_top_card_and_keeps_permission_unmatched(self):
        daxos = self.db.get("Daxos of Meletis")
        self.assertEqual(len(daxos.unsupported), 1)
        self.assertIn("you may cast that card", daxos.unsupported[0])
        self.b.library.append(ELF)
        self.resolve(daxos.triggers[0].effects, context=self.b)
        self.assertIn(ELF, self.b.exile)
        self.assertEqual(self.a.life, 24)
        self.assertEqual(len(self.a.exile), 0)

    def test_card_stats_are_frozen_before_reanimation(self):
        effects, bad = _parse_effects("Return target Elf card from your graveyard to the battlefield. "
                                    "You gain life equal to that card's power.")
        self.assertFalse(bad)
        self.a.graveyard.append(ELF)
        item = StackItem(self.a, effects, [None, None])
        self.g.resolve(self.a, effects[0], None, item)
        self.a.creatures[-1].pump_p = 10
        self.g.resolve(self.a, effects[1], None, item)
        self.assertEqual(self.a.life, 24)

    def test_unlinked_card_power_stays_unmatched(self):
        effects, bad = _parse_effects("You gain life equal to that card's power.")
        self.assertFalse(effects)
        self.assertTrue(bad)

    def test_negative_card_power_gains_zero(self):
        negative = card("Negative Elf", "{G}", "Creature — Elf", "", -2, 3)
        self.a.graveyard.append(negative)
        self.resolve(self.db.get("Mirkwood Elk").triggers[0].effects)
        self.assertEqual(self.a.life, 20)

    def test_later_reveal_replaces_earlier_card_reference(self):
        effects, bad = _parse_effects("Return target Elf card from your graveyard to your hand. "
                                    "Reveal the top card of your library. You gain life equal to that card's mana value.")
        self.assertFalse(bad)
        self.a.graveyard.append(ELF)
        self.resolve(effects)
        self.assertEqual(self.a.life, 20)  # the revealed land, not the four-mana Elf
