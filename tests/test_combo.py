"""Compact combo fixture: Kiln Fiend plus a double-strike spell. Oracle text is written out
(from Scryfall/Forge) so these tests don't depend on a card cache."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Permanent, Player

CARDS = {c["name"]: card_from_scryfall(c) for c in [
    {"name": "Kiln Fiend", "mana_cost": "{1}{R}", "cmc": 2, "type_line": "Creature — Elemental Beast",
     "power": "1", "toughness": "2",
     "oracle_text": "Whenever you cast an instant or sorcery spell, Kiln Fiend gets +3/+0 until end of turn."},
    {"name": "Assault Strobe", "mana_cost": "{R}", "cmc": 1, "type_line": "Sorcery",
     "oracle_text": "Target creature gains double strike until end of turn. (It deals both first-strike "
                    "and regular combat damage.)"},
    {"name": "Brute Force", "mana_cost": "{R}", "cmc": 1, "type_line": "Instant",
     "oracle_text": "Target creature gets +3/+3 until end of turn."},
    {"name": "Expedite", "mana_cost": "{R}", "cmc": 1, "type_line": "Instant",
     "oracle_text": "Target creature gains haste until end of turn.\nDraw a card."},
    {"name": "Mountain", "mana_cost": "", "cmc": 0, "type_line": "Basic Land — Mountain", "oracle_text": "({T}: Add {R}.)"},
]}


def perm(name, owner):
    p = Permanent(CARDS[name], owner)
    p.sick = False
    p.tapped = False
    owner.battlefield.append(p)
    return p


class KilnFiendComboTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn = 3
        for p in (self.a, self.b):
            p.library = [CARDS["Mountain"]] * 20

    def test_templates_cover_the_key_cards(self):
        for name in ("Kiln Fiend", "Assault Strobe", "Brute Force", "Expedite"):
            self.assertEqual(CARDS[name].unsupported, [], name)
        self.assertEqual(CARDS["Kiln Fiend"].triggers[0].event, "cast_instant_sorcery")

    def test_rules_key_line_is_exactly_lethal(self):
        fiend = perm("Kiln Fiend", self.a)
        for _ in range(2):
            perm("Mountain", self.a)
        self.a.hand = [CARDS["Assault Strobe"], CARDS["Brute Force"]]
        self.assertTrue(self.game.cast(self.a, CARDS["Assault Strobe"], [fiend]))
        self.game.settle()
        self.assertTrue(fiend.has("double strike"))
        self.assertEqual(fiend.power, 4)
        self.assertTrue(self.game.cast(self.a, CARDS["Brute Force"], [fiend]))
        self.game.settle()
        self.assertEqual((fiend.power, fiend.toughness), (10, 5))   # 1 + 3 + 3 trigger, +3 spell
        self.a.ai.choose_attackers = lambda g, me, opp: [fiend]
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 0)
        self.assertTrue(self.b.lost)

    def test_trigger_ignores_creature_spells_and_grants_target_keyword(self):
        fiend = perm("Kiln Fiend", self.a)
        for _ in range(2):
            perm("Mountain", self.a)
        self.a.hand = [CARDS["Kiln Fiend"]]
        self.game.cast(self.a, CARDS["Kiln Fiend"])
        self.game.settle()
        self.assertEqual(fiend.power, 1)
        self.a.hand = [CARDS["Expedite"]]
        perm("Mountain", self.a)
        self.game.cast(self.a, CARDS["Expedite"], [fiend])
        self.game.settle()
        self.assertEqual(fiend.power, 4)
        self.assertTrue(fiend.has("haste"))

    def test_pilot_finds_two_spell_kill_from_twenty(self):
        perm("Kiln Fiend", self.a)
        for _ in range(2):
            perm("Mountain", self.a)
        self.a.hand = [CARDS["Assault Strobe"], CARDS["Brute Force"]]
        self.game.take_turn(self.a)
        self.assertTrue(self.b.lost)

    def test_fixture_deck_is_sixty_cards(self):
        from mtgsim.decklist import load_deck
        counts = load_deck(Path(__file__).resolve().parents[1] / "decks" / "combo" / "kiln_fiend_strobe.txt")[1]
        self.assertEqual(sum(counts.values()), 60)
        self.assertEqual(counts["Kiln Fiend"], 4)


if __name__ == "__main__":
    unittest.main()
