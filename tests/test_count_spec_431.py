"""#431: the grammar's "for each <thing>" count (cx_grammar._count_spec) counts what the words say, or refuses the
phrase; it never falls back to a looser count of something else (a first word, or a word copies.fits can't test)."""
import dataclasses
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.counting import count, known
from mtgsim.cx_grammar import _count_spec
from mtgsim.engine import Game, Player

from tests.test_templates import card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


def selector(spec):
    return spec[2]["selector"] if spec and spec[:2] == ("cxq", "perms") else None


class CountSpec(unittest.TestCase):
    def test_the_issue_table(self):
        self.assertEqual(selector(_count_spec("artifact token you control")),
                         {"controller": "mine", "traits": ["token"], "types_all": ["artifact"]})
        self.assertEqual(_count_spec("basic land type among lands you control"), ("domain",))
        self.assertEqual(selector(_count_spec("other legendary creature you control")),
                         {"other": True, "controller": "mine", "traits": ["legendary"], "types_all": ["creature"]})
        self.assertEqual(_count_spec("instant and sorcery card in your graveyard"), ("gy", "instant and sorcery"))
        # no reading counts these yet: refused, not counted as something else
        for desc in ("land you control and each land card in your graveyard", "differently named token you control"):
            self.assertIsNone(_count_spec(desc), desc)

    def test_every_count_spec_is_evaluable(self):
        """A ("count" | "gy", words) spec only ever names words copies.fits can test (else it counts 0)."""
        for desc in ("artifact token you control", "Elf you control", "creature card in your graveyard",
                     "instant and sorcery card in your graveyard", "other legendary creature you control",
                     "attacking creature you control", "commander you control", "Soldier and Warrior you control",
                     "black mana symbol in the mana costs of permanents you control", "card type among cards in your graveyard"):
            spec = _count_spec(desc)
            if spec and spec[0] in ("count", "gy"):
                self.assertTrue(known(spec[1]), (desc, spec))


class Evaluation(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 3, "main1"

    def counted(self, text):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [], text)
        data = effects[0].data          # the older template path keeps a ("per") count
        return self.game.x_quantity(self.a, data["xq"], None, None) if "xq" in data else count(self.game, self.a, data["per"])

    def test_artifact_tokens_only(self):
        token = card("Thopter", "", "Artifact Creature — Thopter", "", 1, 1)
        token = dataclasses.replace(token, is_token=True)
        for c in (token, token, card("Relic", "{1}", "Artifact", ""), card("Bear", "{1}", "Creature — Bear", "", 2, 2)):
            self.game.enter_battlefield(self.a, c)
        self.assertEqual(self.counted("You gain 1 life for each artifact token you control."), 2)

    def test_legendary_creatures(self):
        for c in (card("Legend A", "{1}", "Legendary Creature — Elf", "", 1, 1),
                  card("Legend B", "{1}", "Legendary Creature — Elf", "", 1, 1),
                  card("Plain Elf", "{1}", "Creature — Elf", "", 1, 1),
                  card("Legendary Relic", "{1}", "Legendary Artifact", "")):
            self.game.enter_battlefield(self.a, c)
        self.assertEqual(self.counted("You gain 1 life for each legendary creature you control."), 2)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def ignored(self, name):
        from mtgsim.coverage import card_coverage
        return card_coverage(self.db.get(name)).ignored

    def test_refused_rows_stay_partial(self):
        self.assertTrue(any("each land card" in line for line in self.ignored("Multani, Yavimaya's Avatar")))
        self.assertTrue(any("differently named" in line for line in self.ignored("Grek the Ogre")))

    def test_thorin_counts_artifact_tokens(self):
        """Thorin: other Dwarves get +1/+0 for each artifact TOKEN you control (a nontoken artifact doesn't count)."""
        self.assertEqual(self.ignored("Thorin, King of Durin's Folk"), [])
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0))
        g.turn, g.step = 3, "main1"
        get = self.db.get
        g.enter_battlefield(a, get("Thorin, King of Durin's Folk"))     # its trigger makes a Treasure token
        g.settle()
        dwarf = g.enter_battlefield(a, get("Dwarven Trader"))           # another Dwarf: a second Treasure
        g.settle()
        g.enter_battlefield(a, get("Sol Ring"))                         # not a token
        g.settle()
        treasures = sum(1 for x in a.battlefield if x.card.is_token and x.card.is_artifact)
        self.assertEqual(treasures, 2)
        self.assertEqual(dwarf.power, get("Dwarven Trader").power + 2)

    def test_spec_tags_survive(self):
        """The plural-word renaming touched a spec's tags too: ('cxq', 'cards') -> 'card', 'opponents' -> 'opponent'."""
        self.assertEqual(_count_spec("card named ~ in your graveyard"), ("cxq", "cards", "your_gy", None))
        self.assertEqual(_count_spec("soot counter on ~"), ("counters", "soot"))

    def test_graveyard_and_library_statics_count(self):
        """Full cards whose static count was ('cxq', 'card', ...) and so always 0 (#431)."""
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0))
        get = self.db.get
        a.graveyard = [get(n) for n in ("Sol Ring", "Pacifism", "Shock", "Grizzly Bears")]
        a.library = [get("Grizzly Bears")] * 3 + [get("Island")] * 5
        bot = g.enter_battlefield(a, get("Runaway Trash-Bot"))          # 0/4, +1/+0 per artifact and/or enchantment
        xande = g.enter_battlefield(a, get("Xande, Dark Mage"))         # 3/3, +1/+1 per noncreature, nonland card
        wurm = g.enter_battlefield(a, get("Avoided Stairwurm"))         # 5/5, -1/-1 per creature card in library
        g.settle()
        self.assertEqual((bot.power, bot.toughness), (2, 4))
        self.assertEqual((xande.power, xande.toughness), (6, 6))
        self.assertEqual((wurm.power, wurm.toughness), (2, 2))

    def test_blazing_sunsteel_counts_opponents(self):
        rules = self.db.get("Blazing Sunsteel").advanced_rules["gated"]
        self.assertEqual(rules[0][3][3], ("cxq", "opponents"))

    def test_heroes_podium_counts_other_legends(self):
        self.assertEqual(self.ignored("Heroes' Podium"), [])
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0))
        g.enter_battlefield(a, self.db.get("Heroes' Podium"))
        legends = [g.enter_battlefield(a, card(f"Legend {i}", "{1}", "Legendary Creature — Elf", "", 1, 1)) for i in range(3)]
        g.enter_battlefield(a, card("Plain Elf", "{1}", "Creature — Elf", "", 1, 1))
        g.settle()
        self.assertEqual([x.power for x in legends], [3, 3, 3])         # 1 + two other legends each


if __name__ == "__main__":
    unittest.main()
