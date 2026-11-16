"""#628: "If a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield
[with N +1/+1 counters on it] instead of putting it into your graveyard." (mtgsim.cx_discard_bf)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Loxodon Smiter", "Nullhide Ferox", "Obstinate Baloth", "Wilt-Leaf Liege", "Dodecapod")
RULE = ("If a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield{} "
        "instead of putting it into your graveyard.")
SMITER = card("Test Smiter", "{1}{G}{W}", "Creature — Elephant Soldier", RULE.format(""), 4, 4)
POD = card("Test Pod", "{4}", "Artifact Creature — Golem", RULE.format(" with two +1/+1 counters on it"), 3, 3)
ROT = card("Test Rot", "{2}{B}", "Sorcery", "Target player discards a card.")
LOOT = card("Test Loot", "{R}", "Sorcery", "Discard a card.")


class Parse(unittest.TestCase):
    def test_rule(self):
        self.assertEqual(SMITER.unsupported, [])
        self.assertEqual(SMITER.advanced_rules["discard_to_bf"], {"p1": 0})
        self.assertEqual(POD.advanced_rules["discard_to_bf"], {"p1": 2})

    def test_refusals(self):
        for text in (RULE.format("").replace("an opponent controls", "you control"),
                     RULE.format(" tapped"),
                     RULE.format("").replace("into your graveyard", "into exile")):
            self.assertTrue(card("Test Odd", "{G}", "Creature — Elf", text, 1, 1).unsupported, text)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def resolve(self, controller, spell, targets):
        effects = list(spell.spell_effects)
        self.g.stack.append(StackItem(controller, effects, targets, card=spell, name=spell.name))
        self.g.resolve_top()

    def test_opponents_spell_puts_it_onto_the_battlefield(self):
        self.a.hand = [SMITER]
        self.resolve(self.b, ROT, [self.a])
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Test Smiter"])
        self.assertEqual(self.a.hand, [])
        self.assertFalse(any(c.name == "Test Smiter" for c in self.a.graveyard))
        self.assertEqual(len(self.a.discarded_cards), 1)          # still a discard

    def test_with_counters(self):
        self.a.hand = [POD]
        self.resolve(self.b, ROT, [self.a])
        pod = next(x for x in self.a.battlefield if x.card.name == "Test Pod")
        self.assertEqual((pod.p1, pod.power), (2, 5))

    def test_own_discard_goes_to_the_graveyard(self):
        self.a.hand = [SMITER]
        self.resolve(self.a, LOOT, [None])
        self.assertEqual(self.a.battlefield, [])
        self.assertTrue(any(c.name == "Test Smiter" for c in self.a.graveyard))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full_and_baloth_enters_with_its_trigger(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        a.hand = [db.get("Obstinate Baloth")]
        g.stack.append(StackItem(b, list(ROT.spell_effects), [a], card=ROT, name=ROT.name))
        g.resolve_top()
        g.settle()
        self.assertEqual([x.card.name for x in a.battlefield], ["Obstinate Baloth"])
        self.assertEqual(a.life, 24)                              # "When ~ enters, you gain 4 life."


if __name__ == "__main__":
    unittest.main()
