"""smol-chonk-7 batch 8, priority 1: initiative / dungeon-completion gates.

The engine conds landed in le-batch8 (stack.check_cond): "initiative" (the resolving
player holds the initiative) and "dungeon_complete" (any completed dungeon), plus the
"!" negation prefix. These tests pin the gate templates that read them:

- "if you have the initiative" / "if you've completed a dungeon" gates in trigger bodies
  and as sentence-level "If X, Y" gates (Passageway Seer, White Plume Adventurer,
  Rilsa Rael, Caves of Chaos Adventurer);
- the negative variant "if you haven't completed Tomb of Annihilation" -> cond
  "!dungeon_complete" (Acererak), with the any-dungeon narrowing recorded as an
  approximation note;
- Undercellar Sweep's "you or a player you're attacking has the initiative" narrows to
  the same "initiative" cond (approximation note), and its "that are tapped and
  attacking" tokens / "you create" bodies parse.
"""
import unittest

from mtgsim.cards.parse import _parse_effects, _parse_trigger
from tests.test_templates import card

UNDERCELLAR = card("Undercellar Sweep", "{2}{W}", "Enchantment",
                   "When this enchantment enters, you take the initiative.\n"
                   "Whenever you attack, if you or a player you're attacking has the "
                   "initiative, you create two 1/1 white Soldier creature tokens that are "
                   "tapped and attacking.")
PASSAGEWAY = card("Passageway Seer", "{1}{B}", "Creature — Human Peasant",
                  "Lifelink\nWhen this creature enters, you take the initiative.\n"
                  "At the beginning of your end step, if you have the initiative, put a "
                  "+1/+1 counter on this creature.", 1, 3)
ACERERAK = card("Acererak the Archlich", "{2}{B}", "Legendary Creature — Zombie Wizard",
                "When Acererak enters, if you haven't completed Tomb of Annihilation, "
                "return Acererak to its owner's hand and venture into the dungeon.\n"
                "Whenever Acererak attacks, for each opponent, you create a 2/2 black Zombie "
                "creature token unless that player sacrifices a creature of their choice.", 5, 5)
WHITE_PLUME = card("White Plume Adventurer", "{2}{W}", "Creature — Human Bard",
                   "When this creature enters, you take the initiative.\n"
                   "At the beginning of each opponent's upkeep, untap a creature you control. "
                   "If you've completed a dungeon, untap all creatures you control instead.", 3, 3)
RILSA = card("Rilsa Rael, Kingpin", "{1}{B}{B}", "Legendary Creature — Human Rogue",
             "Deathtouch\nWhen Rilsa Rael enters, you take the initiative.\n"
             "Whenever you attack, target attacking creature gains deathtouch until end of "
             "turn. If you've completed a dungeon, that creature also gets +5/+0 and gains "
             "first strike and menace until end of turn.", 3, 3)
CAVES = card("Caves of Chaos Adventurer", "{2}{R}", "Creature — Dragon Bard",
             "Trample\nWhen this creature enters, you take the initiative.\n"
             "Whenever this creature attacks, exile the top card of your library. If you've "
             "completed a dungeon, you may play that card this turn without paying its mana "
             "cost. Otherwise, you may play that card this turn.", 3, 3)


class InitiativeGates(unittest.TestCase):
    def test_trigger_gate_initiative(self):
        triggers, bad, _ = _parse_trigger(
            "At the beginning of your end step, if you have the initiative, "
            "put a +1/+1 counter on ~.")
        self.assertEqual(bad, [])
        t, = triggers
        self.assertEqual(t.event, "end_step")
        self.assertEqual([(e.kind, e.cond) for e in t.effects], [("p1_counters", "initiative")])

    def test_trigger_gate_dungeon_complete_rider(self):
        triggers, bad, _ = _parse_trigger(
            "At the beginning of each opponent's upkeep, untap a creature you control. "
            "If you've completed a dungeon, untap all creatures you control instead.")
        self.assertEqual(bad, [])
        t, = triggers
        self.assertEqual(t.event, "opp_upkeep")
        self.assertEqual([(e.kind, e.cond, e.target) for e in t.effects],
                         [("untap_target", "", "creature_mine"), ("untap_all", "dungeon_complete", "none")])

    def test_dungeon_complete_pump_rider(self):
        triggers, bad, _ = _parse_trigger(
            "Whenever you attack, target attacking creature gains deathtouch until end of "
            "turn. If you've completed a dungeon, that creature also gets +5/+0 and gains "
            "first strike and menace until end of turn.")
        self.assertEqual(bad, [])
        t, = triggers
        self.assertEqual([e.kind for e in t.effects], ["grant", "pump", "grant", "grant"])
        self.assertEqual(t.effects[1].cond, "dungeon_complete")
        self.assertEqual(t.effects[1].target, "prev")

    def test_accererak_negative_gate(self):
        triggers, bad, _ = _parse_trigger(
            "When ~ enters, if you haven't completed Tomb of Annihilation, "
            "return ~ to its owner's hand and venture into the dungeon.")
        self.assertEqual(bad, [])
        t, = triggers
        self.assertEqual(t.event, "etb")
        self.assertEqual([(e.kind, e.cond) for e in t.effects],
                         [("bounce_self", "!dungeon_complete"), ("venture", "!dungeon_complete")])

    def test_undercellar_attack_gate_and_tokens(self):
        triggers, bad, _ = _parse_trigger(
            "Whenever you attack, if you or a player you're attacking has the initiative, "
            "you create two 1/1 white Soldier creature tokens that are tapped and attacking.")
        self.assertEqual(bad, [])
        t, = triggers
        self.assertEqual(t.event, "you_attack")
        [e] = t.effects
        self.assertEqual(e.kind, "token")
        self.assertEqual(e.cond, "initiative")
        self.assertEqual(e.amount, 2)
        self.assertTrue(e.data["attacking"])

    def test_you_create_body_is_imperative(self):
        effects, bad = _parse_effects("You create a treasure token.")
        self.assertEqual(bad, [])
        self.assertEqual([e.kind for e in effects], ["token"])

    def test_card_wordings_parse(self):
        for c in (UNDERCELLAR, PASSAGEWAY, WHITE_PLUME, RILSA, CAVES):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(len(ACERERAK.unsupported), 1)       # the per-opponent Zombie attack line
        self.assertIn("for each opponent", ACERERAK.unsupported[0])

    def test_approximation_notes(self):
        def has_note(card_def, note):
            return any(note in a for a in card_def.approximations)
        self.assertTrue(has_note(UNDERCELLAR, "the gate counts only your own initiative"))
        self.assertTrue(has_note(ACERERAK, "any completed dungeon stands in for Tomb of "
                                           "Annihilation"))
        self.assertTrue(has_note(CAVES, "the may-play riders are played as the impulse draw"))

    def test_cards_parse_clean_without_notes(self):
        for c in (PASSAGEWAY, WHITE_PLUME, RILSA):
            self.assertEqual(c.approximations, [], c.name)


if __name__ == "__main__":
    unittest.main()
