"""Rules fixes: #266 named activation bans on ability variants, #267 divided damage to a hexproof player,
#270 hexproof from <colour> vs recoloured sources, #272 simultaneous untap with tap-locks."""
import random
import unittest

from mtgsim import continuous
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

BOLT = card("Test Forked Bolt", "{R}", "Sorcery", "Test Forked Bolt deals 2 damage divided as you choose among one "
            "or two targets.")
AEGIS = card("Test Aegis", "{2}{W}", "Enchantment", "You have hexproof.")
NEEDLE = card("Test Needle", "{1}", "Artifact",
              "As ~ enters, choose a card name.\nActivated abilities of sources with the chosen name can't be "
              "activated unless they're mana abilities.")
CHANNELER = card("Test Channeler", "{3}{G}", "Creature — Spirit",
                 "Channel — {1}{G}, Discard ~: You gain 3 life.", 2, 2)
PINGER = card("Test Pinger", "{1}", "Creature — Human", "{T}: ~ deals 1 damage to any target.", 1, 1)


def new_game():
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 2, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 10
    return g, a, b



class NamedActivationBan(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.g, self.a, self.b = new_game()

    def needle(self, name):
        n = self.g.enter_battlefield(self.b, NEEDLE)
        self.g.settle()
        n.chosen_name = name
        return n

    def test_parse(self):
        self.assertEqual(NEEDLE.unsupported, [])
        self.assertTrue(NEEDLE.chosen_land_lock)

    def test_ban_applies_to_permanent_abilities(self):
        pinger = self.g.enter_battlefield(self.a, PINGER)
        pinger.sick = False
        self.assertTrue(self.g.can_activate(self.a, pinger, 0))
        self.needle(PINGER.name)
        self.assertFalse(self.g.can_activate(self.a, pinger, 0))

    def test_other_names_unaffected(self):
        pinger = self.g.enter_battlefield(self.a, PINGER)
        pinger.sick = False
        self.needle("Something Else")
        self.assertTrue(self.g.can_activate(self.a, pinger, 0))

    def castable_abilities(self):
        return [v for v in self.g.spell_options(self.a) if v.is_ability and self.g.can_cast_now(self.a, v)]

    def _channel_variant(self):
        card_ = CHANNELER
        self.assertEqual(card_.unsupported, [])
        self.a.hand.append(card_)
        for land in ("Forest", "Forest"):
            self.g.enter_battlefield(self.a, self.db.get(land))
        return card_, self.castable_abilities()

    def test_channel_blocked_by_named_ban(self):
        card_, opts = self._channel_variant()
        self.assertTrue(opts, "channel variant is offered without the ban")
        self.needle(card_.name)
        self.assertFalse(self.castable_abilities())

    def test_channel_not_blocked_by_other_name(self):
        _, opts = self._channel_variant()
        self.needle("Something Else")
        self.assertEqual(len(self.castable_abilities()), len(opts))

    def test_unearth_blocked_by_named_ban(self):
        card_ = self.db.get("Dregscape Zombie")
        self.a.graveyard.append(card_)
        for _ in range(3):
            self.g.enter_battlefield(self.a, self.db.get("Swamp"))
        self.assertTrue(self.castable_abilities())
        self.needle(card_.name)
        self.assertFalse(self.castable_abilities())


class DividedDamageHexproof(unittest.TestCase):
    def setUp(self):
        self.g, self.a, self.b = new_game()

    def cast_resolve(self, hexproof_after_cast):
        item = StackItem(self.a, list(BOLT.spell_effects), [None], card=BOLT, name=BOLT.name)
        self.g.stack.append(item)
        if hexproof_after_cast:
            self.g.enter_battlefield(self.b, AEGIS)
        self.g.resolve_top()

    def test_player_loses_nothing_after_gaining_hexproof(self):
        self.cast_resolve(True)
        self.assertEqual(self.b.life, 20)

    def test_player_takes_share_without_hexproof(self):
        self.cast_resolve(False)
        self.assertEqual(self.b.life, 18)

    def test_not_planned_against_hexproof_player(self):
        self.g.enter_battlefield(self.b, AEGIS)
        self.cast_resolve(False)
        self.assertEqual(self.b.life, 20)

    def test_permanent_share_still_lost_when_illegal(self):
        bear = self.g.enter_battlefield(self.b, BEAR)
        item = StackItem(self.a, list(BOLT.spell_effects), [None], card=BOLT, name=BOLT.name)
        self.g.stack.append(item)
        self.b.battlefield.remove(bear)
        self.g.resolve_top()
        self.assertEqual(bear.damage, 0)


if __name__ == "__main__":
    unittest.main()
