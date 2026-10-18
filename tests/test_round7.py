"""Cheap generic lines: keyword pumps, lords, second-spell discount, removal variants."""
import unittest

from tests.test_templates import BEAR, MOUNTAIN, card
from tests.test_empower_discover import Base

LINES = {
    "pump": card("T1", "{1}", "Creature — Cat", "{1}: ~ gets +2/+0 and gains lifelink until end of turn.", 1, 1),
    "aura": card("T2", "{1}", "Enchantment — Aura", "Enchant creature\nWhen ~ enters, enchanted creature gains hexproof until end of turn."),
    "ce": card("T3", "{1}", "Instant", "Destroy target creature or enchantment."),
    "tap": card("T4", "{1}", "Instant", "Tap target permanent."),
    "each": card("T5", "{1}", "Sorcery", "Each player draws a card."),
    "block": card("T6", "{1}", "Sorcery", "Target creature can't block this turn."),
    "exile": card("T7", "{1}", "Sorcery", "Target opponent exiles a card from their hand."),
    "reanimate": card("T8", "{1}", "Sorcery", "Return target creature card from your graveyard to the battlefield."),
    "regrow": card("T9", "{1}", "Sorcery", "Return up to one target permanent card from your graveyard to your hand."),
    "damaged": card("T10", "{1}", "Instant", "Destroy target creature an opponent controls that was dealt damage this turn."),
    "lord": card("T11", "{1}", "Creature — Elf", "Other Elf creatures you control get +1/+1.", 1, 1),
    "counters": card("T12", "{1}", "Creature — Cat", "Creatures you control with +1/+1 counters on them have trample.", 1, 1),
    "second": card("T13", "{1}", "Creature — Cat", "The second spell you cast each turn costs {1} less to cast.", 1, 1),
    "lands": card("T14", "{1}", "Creature — Cat", "As long as you control seven or more lands, ~ gets +2/+2.", 1, 1),
    "kwlord": card("T15", "{1}", "Creature — Bird", "Creatures you control with flying get +1/+1.", 1, 1),
    "sublord": card("T16", "{1}", "Creature — Cat", "Other Cats you control get +1/+1.", 1, 1),
    "subkw": card("T17", "{1}", "Creature — Rhino", "Rhinos you control have menace.", 1, 1),
    "discount": card("T18", "{3}", "Sorcery", "~ costs {1} less to cast if you control a Wizard.\nDraw a card."),
    "shrink": card("T19", "{1}", "Sorcery", "Put two -1/-1 counters on target creature."),
    "gy": card("T20", "{1}", "Sorcery", "Exile target player's graveyard."),
    "ping": card("T21", "{1}", "Sorcery", "~ deals 2 damage to each player."),
    "two": card("T22", "{1}", "Sorcery", "One or two target creatures each get +2/+2 until end of turn."),
    "ae": card("T23", "{1}", "Instant", "Counter target artifact or enchantment spell."),
}


class Round7(Base):
    def test_templates(self):
        for k, c in LINES.items():
            self.assertEqual(c.unsupported, [], k)

    def test_lord_counts_other_elves_only(self):
        lord = self.perm(LINES["lord"])
        elf = self.perm(card("Elf", "{1}", "Creature — Elf", "", 1, 1))
        self.assertEqual((lord.power, elf.power), (1, 2))
        self.assertEqual(self.perm(BEAR).power, 2)

    def test_counter_team_trample(self):
        self.perm(LINES["counters"])
        bear = self.perm(BEAR)
        self.assertFalse(bear.has("trample"))
        bear.counters["+1/+1"] = 1
        self.assertTrue(bear.has("trample"))

    def test_second_spell_discount(self):
        self.perm(LINES["second"])
        spell = card("Spell", "{2}", "Sorcery", "Draw a card.")
        self.assertEqual(self.game.cost_of(self.a, spell).get("generic"), 2)
        self.game.spells_cast = {"turn": self.game.turn, self.a.name: 1}
        self.assertEqual(self.game.cost_of(self.a, spell).get("generic"), 1)

    def test_seven_lands_bonus(self):
        cat = self.perm(LINES["lands"])
        for _ in range(7):
            self.perm(MOUNTAIN)
        self.assertEqual(cat.power, 3)

    def test_cant_block_and_damaged_destroy(self):
        bear = self.perm(BEAR, self.b)
        self.game.resolve(self.a, LINES["block"].spell_effects[0], bear)
        from mtgsim.engine import can_block
        self.assertFalse(can_block(bear, self.perm(BEAR)))
        self.assertFalse(self.game.legal_target(self.a, LINES["damaged"].spell_effects[0], bear))
        bear.damage = 1
        self.assertTrue(self.game.legal_target(self.a, LINES["damaged"].spell_effects[0], bear))

    def test_reanimate_and_each_draws(self):
        self.a.graveyard.append(BEAR)
        self.game.resolve(self.a, LINES["reanimate"].spell_effects[0], None)
        self.assertEqual(len(self.a.creatures), 1)
        self.game.resolve(self.a, LINES["each"].spell_effects[0], None)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 1))

    def test_second_batch_templates(self):
        for k in ("kwlord", "sublord", "subkw", "discount", "shrink", "gy", "ping", "two", "ae"):
            self.assertEqual(LINES[k].unsupported, [], k)

    def test_keyword_and_subtype_lords(self):
        self.perm(LINES["kwlord"])
        flyer = self.perm(card("Bird", "{1}", "Creature — Bird", "Flying", 1, 1))
        self.assertEqual(flyer.power, 2)
        self.assertEqual(self.perm(BEAR).power, 2)
        self.perm(LINES["subkw"])
        rhino = self.perm(card("Rhino", "{1}", "Creature — Rhino", "", 1, 1))
        self.assertTrue(rhino.has("menace"))

    def test_conditional_discount(self):
        self.assertEqual(self.game.cost_of(self.a, LINES["discount"]).get("generic"), 3)
        self.perm(card("Wiz", "{1}", "Creature — Wizard", "", 1, 1))
        self.assertEqual(self.game.cost_of(self.a, LINES["discount"]).get("generic"), 2)

    def test_shrink_ping_and_graveyard_exile(self):
        bear = self.perm(BEAR, self.b)
        self.game.resolve(self.a, LINES["shrink"].spell_effects[0], bear)
        self.assertEqual(bear.power, 0)
        self.game.resolve(self.a, LINES["ping"].spell_effects[0], None)
        self.assertEqual((self.a.life, self.b.life), (18, 18))
        self.b.graveyard.append(BEAR)
        self.game.resolve(self.a, LINES["gy"].spell_effects[0], None)
        self.assertEqual(self.b.graveyard, [])


if __name__ == "__main__":
    unittest.main()
