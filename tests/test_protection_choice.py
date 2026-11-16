"""#643 slice 3: "gains protection from [artifacts / colorless or from] the color of your choice" for any subject
(mtgsim.protection_choice; protection from colorless in protection_qualities)."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.coverage import card_coverage
from mtgsim.engine import StackItem, protected_from
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, SHOCK, card

RAZOR = card("Test Razor Barrier", "{1}{W}", "Instant", "Target permanent you control gains protection from artifacts "
             "or from the color of your choice until end of turn.")
GIVER = card("Test Giver", "{W}", "Creature — Kor Cleric", "{T}: Another target creature you control gains protection "
             "from colorless or from the color of your choice until end of turn.", 1, 2)
ROD = card("Test Rod", "{3}", "Artifact", "{T}: ~ deals 1 damage to any target.")
SHATTER = card("Test Shatter", "{1}{R}", "Instant", "Destroy target artifact.")


class Parsing(unittest.TestCase):
    def test_subjects(self):
        for text, target, kw in (
                ("Target permanent you control gains protection from artifacts or from the color of your choice "
                 "until end of turn.", "permanent", "protection_choice|artifacts"),
                ("Target creature or enchantment you control gains protection from the color of your choice until "
                 "end of turn.", "permanent", "protection_choice"),
                ("Another target creature you control gains protection from colorless or from the color of your "
                 "choice until end of turn.", "permanent", "protection_choice|colorless"),     # selector + "other"
                ("~ gains protection from artifacts or from the color of your choice until end of turn.", "self",
                 "protection_choice|artifacts")):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertEqual((effects[0].kind, effects[0].target, effects[0].data["keyword"]), ("grant", target, kw))

    def test_refusals(self):
        for text in ("Target creature gains protection from the color of its controller's choice until end of turn.",
                     "Target creature gains protection from the card type of your choice until end of turn.",
                     "Target creature gains protection from lands or from the color of your choice until end of turn."):
            effects, bad = _parse_effects(text)
            self.assertTrue(bad, text)


class Engine(Base):
    def resolve(self, c, target, threat=None):
        if threat is not None:
            self.game.stack.append(threat)
        item = StackItem(self.a, list(c.spell_effects), [target], card=c, name=c.name)
        self.game.stack.append(item)
        self.game.resolve_top()

    def test_chooses_artifacts_against_an_artifact_threat(self):
        """CR 702.16: the choice is made on resolution; against the opponent's artifact source, "artifacts"."""
        bear = self.perm(BEAR, self.a)
        rod = self.perm(ROD, self.b)
        threat = StackItem(self.b, list(rod.card.activated[0].effects), [bear], source=rod, name="Rod", kind="ability")
        self.resolve(RAZOR, bear, threat)
        self.assertTrue(bear.has("protection from artifacts"))
        self.assertTrue(protected_from(bear, rod))

    def test_chooses_the_colour_of_a_coloured_threat(self):
        bear = self.perm(BEAR, self.a)
        threat = StackItem(self.b, list(SHOCK.spell_effects), [bear], card=SHOCK, name="Shock")
        self.resolve(RAZOR, bear, threat)
        self.assertTrue(bear.has("protection from red"))
        self.assertFalse(bear.has("protection from artifacts"))

    def test_protection_from_colorless(self):
        bear = self.perm(BEAR, self.a)
        rod = self.perm(ROD, self.b)
        threat = StackItem(self.b, list(rod.card.activated[0].effects), [bear], source=rod, name="Rod", kind="ability")
        giver = self.perm(GIVER, self.a)
        item = StackItem(self.a, list(giver.card.activated[0].effects), [bear], source=giver, kind="ability")
        self.game.stack += [threat, item]
        self.game.resolve_top()
        self.assertTrue(bear.has("protection from colorless"))
        self.assertTrue(protected_from(bear, rod))
        self.assertFalse(protected_from(bear, SHOCK))


class HeuristicUse(Base):
    def test_ai_saves_its_creature_from_an_artifact_source(self):
        """The AI's protective response uses the alternative when it stops the threat."""
        from mtgsim.engine.policy import protective_ability
        giver = self.perm(GIVER, self.a)
        giver.sick = False
        bear = self.perm(BEAR, self.a)
        rod = self.perm(ROD, self.b)
        threat = StackItem(self.b, list(rod.card.activated[0].effects), [bear], source=rod, name="Rod", kind="ability")
        self.game.stack.append(threat)
        action = protective_ability(self.game, self.a, threat, bear)
        self.assertIsNotNone(action)
        self.assertIs(action[1], giver)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Alseid of Life's Bounty", "Apostle's Blessing", "Borg Incursion", "Giver of Runes",
                     "Jeweled Spirit", "Razor Barrier", "Sygg, River Guide", "Mother of Runes"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))
        self.assertEqual(card_coverage(db.get("Pale Wayfarer")).status, "partial")


if __name__ == "__main__":
    unittest.main()
