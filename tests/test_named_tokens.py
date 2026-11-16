"""#525: "create <Name>, a legendary P/T ... creature token" makes a token with that name that is legendary, and
"if you don't control a creature named <Name>" checks for it (Jiang Yanggu, Rufus Shinra, Tolsimir)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 20
    return g, a, b


def run(g, p, effects):
    g.stack.append(StackItem(p, list(effects), [None] * len(effects), kind="ability"))
    g.resolve_top()
    g.settle()


class Parse(unittest.TestCase):
    def test_shapes(self):
        effects, bad = _parse_effects("Create Voja, Friend to Elves, a legendary 3/3 green and white Wolf creature "
                                      "token.")
        self.assertEqual(bad, [])
        d = effects[0].data
        self.assertEqual((d["token_name"], d["legendary"], d["power"], d["name"]), ("Voja, Friend to Elves", True, 3,
                                                                                     "Wolf"))
        effects, bad = _parse_effects("Create Boo, a legendary 1/1 red Hamster creature token with trample and haste.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["keywords"], frozenset({"trample", "haste"}))

    def test_near_misses(self):
        for text in ("Create ~ Twin, a legendary 3/4 red and green Human Warrior creature token.",   # own name
                     "Create The Blackjack, a legendary 3/3 colorless Vehicle artifact token with flying and crew 2.",
                     "Create Mowu, a legendary 3/3 green Dog creature token and a 1/1 white Soldier creature token."):
            _, bad = _parse_effects(text)
            self.assertTrue(bad, text)

    def test_dont_control_condition(self):
        effects, bad = _parse_effects("If you don't control a creature named Mowu, create Mowu, a legendary 3/3 green "
                                      "Dog creature token.")
        self.assertEqual(bad, [])
        self.assertIn('"name":"Mowu"', effects[0].cond.replace(" ", ""))


class Engine(unittest.TestCase):
    def test_named_legendary_and_legend_rule(self):
        g, a, b = game()
        effects, _ = _parse_effects("Create Voja, a legendary 2/2 green and white Wolf creature token.")
        run(g, a, effects)
        vojas = [x for x in a.battlefield if x.card.name == "Voja"]
        self.assertEqual(len(vojas), 1)
        self.assertTrue(vojas[0].card.legendary and vojas[0].card.is_token)
        self.assertIn("Wolf", vojas[0].card.subtypes)
        self.assertEqual(vojas[0].card.colors, frozenset({"G", "W"}))
        run(g, a, effects)
        self.assertEqual(sum(x.card.name == "Voja" for x in a.battlefield), 1)    # legend rule: one stays

    def test_only_if_you_dont_control_one(self):
        g, a, b = game()
        effects, _ = _parse_effects("If you don't control a creature named Mowu, create Mowu, a legendary 3/3 green "
                                    "Dog creature token.")
        run(g, a, effects)
        run(g, a, effects)
        self.assertEqual(sum(x.card.name == "Mowu" for x in a.battlefield), 1)
        self.assertEqual(len(a.graveyard), 0)                                     # the second one was never made


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Jiang Yanggu", "Jiang Yanggu, Never Alone", "Rufus Shinra", "Tolsimir Wolfblood",
                     "Tolsimir, Friend to Wolves", "Rinoa Heartilly", "Sophia, Dogged Detective",
                     "Rok-Tahk, Budding Scientist", "Verix Bladewing", "Kiora, the Rising Tide", "The Spear of Leonidas",
                     "Venser, Corpse Puppet"):
            self.assertEqual(db.get(name).unsupported, [], name)

    def test_tolsimir_ability_in_game(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        g, a, b = game()
        t = g.enter_battlefield(a, db.get("Tolsimir Wolfblood"))
        t.sick = False
        self.assertTrue(g.activate_ability(a, t, next(i for i, x in enumerate(t.activated) if x.effects)))
        g.settle()
        voja = next(x for x in a.battlefield if x.card.name == "Voja")
        self.assertEqual((voja.power, voja.toughness), (4, 4))      # Tolsimir: +1/+1 for green and +1/+1 for white


if __name__ == "__main__":
    unittest.main()
