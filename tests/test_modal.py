"""Modal spells, triggers and abilities (mtgsim/modal.py). Card text is written out."""
import random
import unittest

from mtgsim import modal
from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.coverage import card_coverage
from mtgsim.engine import Game, Player


def card(name, cost, types, text, power=None, toughness=None):
    d = {"name": name, "mana_cost": cost, "type_line": types, "oracle_text": text,
         "cmc": sum(int(x) if x.isdigit() else 1 for x in cost.strip("{}").split("}{") if x)}
    if power is not None:
        d.update(power=str(power), toughness=str(toughness))
    return card_from_scryfall(d)


class Parse(unittest.TestCase):
    def test_headers(self):
        cases = {"Choose one —": (1, 1), "Choose two —": (2, 2), "Choose one or both —": (2, 1),
                 "Choose one or more —": (modal.ANY, 1), "Choose up to two.": (2, 0),
                 "Choose any number —": (modal.ANY, 0), "Descend 8 — Choose one.": (1, 1)}
        for line, (most, least) in cases.items():
            spec, _ = modal.parse_header(line)
            self.assertEqual((spec.most, spec.least), (most, least), line)

    def test_unique_and_repeat(self):
        spec, _ = modal.parse_header("choose one that hasn't been chosen this turn —")
        self.assertEqual(spec.unique, "turn")
        spec, _ = modal.parse_header("Choose three. You may choose the same mode more than once.")
        self.assertTrue(spec.repeat)
        self.assertEqual(spec.most, 3)

    def test_card_parses_fully(self):
        c = card("Overwhelming Surge", "{2}{R}", "Instant", "Choose one or both —\n• ~ deals 3 damage to target "
                 "creature.\n• You gain 2 life.")
        self.assertEqual(len(c.modes), 2)
        self.assertEqual(card_coverage(c).status, "full")
        named = card("Test", "{1}{W}", "Instant", "Choose one —\n• Puff Piece — You gain 3 life.\n• Draw a card.")
        self.assertEqual(len(named.modes), 2)
        self.assertEqual(card_coverage(named).status, "full")

    def test_etb_and_activated_modes(self):
        c = card("Stomper", "{3}{G}", "Creature — Beast", "When this creature enters, choose one —\n• You gain 4 "
                 "life.\n• Draw a card.", 3, 3)
        self.assertEqual(len(c.triggers[0].modes), 2)
        a = card("Fungus", "{1}", "Creature — Fungus", "{2}, Sacrifice ~: Choose one —\n• You gain 2 life.\n• "
                 "Draw a card.", 1, 1)
        self.assertEqual(len(a.activated[0].modes), 2)

    def test_pawprint(self):
        c = card("Season", "{3}{W}{W}", "Sorcery", "Choose up to five {P} worth of modes. You may choose the same "
                 "mode more than once.\n{P} — You gain 1 life.\n{P}{P} — Draw a card.\n{P}{P}{P} — Each opponent "
                 "loses 3 life.")
        self.assertEqual(c.modes.spec.budget, 5)
        self.assertEqual(c.modes.spec.costs, [1, 2, 3])


class Play(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main1"

    def test_both_modes_chosen_when_both_useful(self):
        c = card("Both", "{2}{R}", "Instant", "Choose one or both —\n• You gain 3 life.\n• Draw a card.")
        chosen = modal.select(self.game, self.a, c.modes)
        self.assertEqual(len(chosen), 2)

    def test_unique_mode_not_repeated_in_turn(self):
        c = card("Tri", "{1}", "Creature — Rat", "Whenever you attack, choose one that hasn't been chosen this "
                 "turn —\n• You gain 1 life.\n• Draw a card.\n• Each opponent loses 1 life.", 1, 1)
        modes = c.triggers[0].modes
        src = type("S", (), {"ability_turns": {}})()
        seen = set()
        for _ in range(3):
            seen.update(i for i in modal.select(self.game, self.a, modes, src, least=0))
            modal.pick(self.game, self.a, modes, src, least=0)
        self.assertEqual(modal.select(self.game, self.a, modes, src, least=0), [])

    def test_pawprint_spends_budget(self):
        c = card("Season", "{3}{W}{W}", "Sorcery", "Choose up to five {P} worth of modes. You may choose the "
                 "same mode more than once.\n{P} — You gain 1 life.\n{P}{P} — Draw a card.\n{P}{P}{P} — Each "
                 "opponent loses 3 life.")
        self.b.life = 20
        chosen = modal.select(self.game, self.a, c.modes)
        self.assertTrue(chosen)
        self.assertLessEqual(sum(c.modes.spec.costs[i] for i in chosen), 5)


class Upgrades(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))

    def test_parsed_without_notes(self):
        c = card("Gnash", "{1}{G}", "Instant", "Choose one. If you have no cards in hand, choose one or more "
                 "instead.\n- You gain 2 life.\n- Draw a card.".replace("- ", "• "))
        self.assertEqual(c.modes.spec.upgrades, [("no_hand", modal.ANY)])
        self.assertEqual(card_coverage(c).status, "full")

    def test_conditions(self):
        g, me = self.game, self.a
        self.assertTrue(modal.upgrade_active(g, me, "no_hand"))
        self.assertFalse(modal.upgrade_active(g, me, "teamwork"))
        self.assertTrue(modal.upgrade_active(g, me, "teamwork", {"teamwork"}))
        self.assertFalse(modal.upgrade_active(g, me, "delirium"))
        me.graveyard = [card("A", "", "Artifact", ""), card("C", "", "Creature — Elf", "", 1, 1),
                        card("I", "{1}", "Instant", ""), card("L", "", "Land", "")]
        self.assertTrue(modal.upgrade_active(g, me, "delirium"))

    def test_teamwork_chooses_both(self):
        c = card("Go Nuts", "{1}{G}", "Instant", "Teamwork 3 (As an additional cost to cast this spell, you may tap "
                 "any number of creatures you control with total power 3 or more.)\nChoose one. If this spell was "
                 "cast using teamwork, choose both instead.\n• You gain 2 life.\n• Draw a card.")
        self.assertEqual(c.teamwork, 3)
        self.assertEqual(c.unsupported, [])
        spec = modal._upgraded(self.game, self.a, c.modes.spec, {"teamwork"})
        self.assertEqual(spec.most, 2)
        self.assertEqual(modal._upgraded(self.game, self.a, c.modes.spec, ()).most, 1)


if __name__ == "__main__":
    unittest.main()
