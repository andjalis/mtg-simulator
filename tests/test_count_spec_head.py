"""#373: the grammar's "for each <thing>" count reads the head noun of the phrase ("basic land TYPE among lands you
control", "tapped ARTIFACT you control"), not the first word that makes a quantity match."""
import unittest

from mtgsim.cx_grammar import _count_spec

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
RELIC = card("Test Relic", "{1}", "Artifact", "")
LEGEND = card("Test Legend", "{2}", "Legendary Creature — Human", "", 2, 2)
LEGEND_RELIC = card("Test Crown", "{2}", "Legendary Artifact", "")


class Specs(unittest.TestCase):
    def test_head_noun(self):
        self.assertEqual(_count_spec("basic land type among lands you control"), ("domain",))
        self.assertEqual(_count_spec("tapped artifact you control"), ("tapped_any", ("artifact",)))
        self.assertEqual(_count_spec("legendary creature you control"),
                         ("cxq", "perms", {"selector": {"controller": "mine", "traits": ["legendary"], "types_all": ["creature"]}}))
        self.assertEqual(_count_spec("other creature you control")[1], "other creature")
        self.assertEqual(_count_spec("artifact token you control")[:2], ("cxq", "perms"))     # Thorin, King of Durin's Folk

    def test_unchanged(self):
        self.assertEqual(_count_spec("creature you control"), ("count", "creature"))
        self.assertEqual(_count_spec("Elf you control"), ("count", "Elf"))
        self.assertEqual(_count_spec("creature card in your graveyard"), ("gy", "creature"))
        self.assertEqual(_count_spec("card in your hand"), ("hand",))

    def test_unknown_phrase_is_refused(self):
        self.assertIsNone(_count_spec("permanent of the chosen type you control"))


class Behaviour(Base):
    def resolve(self, text, target):
        from mtgsim.engine import StackItem
        c = self.spell(text)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [target], card=c, name=c.name))
        self.game.resolve_top()

    def test_domain_counts_types_not_lands(self):
        for land in (FOREST, FOREST, ISLAND):
            self.perm(land, self.a)
        bear = self.perm(BEAR, self.a)
        self.resolve("Target creature gets +1/+1 until end of turn for each basic land type among lands you control.",
                     bear)
        self.assertEqual((bear.power, bear.toughness), (4, 4))      # Forest and Island: two types

    def test_legendary_creatures_only(self):
        self.perm(LEGEND, self.a)
        self.perm(LEGEND_RELIC, self.a)
        bear = self.perm(BEAR, self.a)
        self.resolve("Creatures you control get +1/+0 until end of turn for each legendary creature you control.",
                     None)
        self.assertEqual(bear.power, 3)

    def test_tapped_artifacts_only(self):
        self.perm(RELIC, self.a).tapped = True
        self.perm(RELIC, self.a)
        self.perm(FOREST, self.a).tapped = True
        bear = self.perm(BEAR, self.a)
        self.resolve("Creatures you control get +1/+0 until end of turn for each tapped artifact you control.", None)
        self.assertEqual(bear.power, 3)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_might_of_alara(self):
        from mtgsim.carddb import CardDB
        from mtgsim.engine import StackItem
        might = CardDB(offline=True).get("Might of Alara")
        for land in (FOREST, FOREST):
            self.perm(land, self.a)
        bear = self.perm(BEAR, self.a)
        self.game.stack.append(StackItem(self.a, list(might.spell_effects), [bear], card=might, name=might.name))
        self.game.resolve_top()
        self.assertEqual(bear.power, 3)     # one basic land type


if __name__ == "__main__":
    unittest.main()
