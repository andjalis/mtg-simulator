"""#329 slice: "create <tokens> for each <thing>" reads the thing through the grammar's count reader
(cx_grammar._count_spec) when the token template's own quantities don't know it: domain ("basic land type among
lands you control"), converge ("color of mana spent to cast this spell"), "card named ~ in your graveyard" and
"<thing> sacrificed this way"."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


class Parse(unittest.TestCase):
    def xq(self, text):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [], text)
        self.assertEqual(effects[0].kind, "cx_token")
        return effects[0].data.get("xq")

    def test_positives(self):
        self.assertEqual(self.xq("Create a 1/1 green Saproling creature token for each basic land type among lands "
                                 "you control."), ("domain",))
        self.assertEqual(self.xq("Create a 2/2 black Zombie creature token for each card named ~ in your graveyard."),
                         ("cxq", "cards", "your_gy", None))
        self.assertEqual(self.xq("Create a Food token for each creature sacrificed this way."),
                         ("this_way", "sacrificed", "creature"))

    def test_refusals(self):
        for text in ("Create a 1/1 green Saproling creature token for each frob you control.",
                     "Create a 2/2 white Cat creature token for each Equipment attached to it.",
                     "Create a 1/1 green Saproling creature token for each differently named token you control.",
                     "Create a 1/1 green Saproling creature token for each land you control and each land card in "
                     "your graveyard."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [text], text)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Games(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [self.db.get("Island")] * 20

    def lands(self, *names):
        for n in names:
            self.game.enter_battlefield(self.a, self.db.get(n)).sick = False

    def tokens(self, p, name):
        return [x for x in p.battlefield if x.card.is_token and name in x.card.name]

    def cast(self, name, **kw):
        spell = self.db.get(name)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, **kw), name)
        self.game.settle()

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Herd Migration", "Spore Burst", "Ordered Migration", "Sweep the Skies", "Unified Front",
                     "Undead Servant", "Syphon Flesh", "Voracious Fell Beast"):
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_spore_burst_counts_basic_land_types(self):
        self.lands("Forest", "Forest", "Island", "Plains")         # three types (two Forests count once)
        self.cast("Spore Burst")
        self.assertEqual(len(self.tokens(self.a, "Saproling")), 3)

    def test_unified_front_counts_colors_spent(self):
        self.lands("Plains", "Island", "Swamp", "Mountain")           # {3}{W} from four colours: all four spent
        self.cast("Unified Front")
        self.assertEqual(len(self.tokens(self.a, "Kor Ally")), 4)

    def test_undead_servant_counts_its_namesakes(self):
        self.a.graveyard = [self.db.get("Undead Servant"), self.db.get("Undead Servant"), self.db.get("Shock")]
        self.lands("Swamp", "Swamp", "Swamp", "Swamp")
        self.cast("Undead Servant")
        self.assertEqual(len(self.tokens(self.a, "Zombie")), 2)

    def test_syphon_flesh_counts_the_opponents_sacrifice(self):
        self.game.enter_battlefield(self.b, self.db.get("Grizzly Bears"))
        self.game.settle()
        self.lands("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")
        self.cast("Syphon Flesh")
        self.assertEqual(self.b.creatures, [])
        self.assertEqual(len(self.tokens(self.a, "Zombie")), 1)

    def test_syphon_flesh_with_nothing_to_sacrifice(self):
        self.lands("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")
        self.cast("Syphon Flesh")
        self.assertEqual(self.tokens(self.a, "Zombie"), [])

    def test_ai_casts_spore_burst(self):
        self.lands("Forest", "Island", "Plains", "Swamp")
        self.a.hand = [self.db.get("Spore Burst")]
        self.game.main_phase(self.a)
        self.game.settle()
        self.assertEqual(self.a.hand, [])
        self.assertEqual(len(self.tokens(self.a, "Saproling")), 4)


if __name__ == "__main__":
    unittest.main()
