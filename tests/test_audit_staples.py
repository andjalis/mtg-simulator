"""Audit 2026-11-16 (opus-cast), round 5 (older staples): "Its controller may search ..." gave the land to the
caster (Path to Exile, Assassin's Trophy, Ghost Quarter), "Destroy target permanent" couldn't hit lands
(Vindicate, Beast Within, Generous Gift)."""
import unittest

from mtgsim.engine import Permanent, StackItem
from mtgsim.engine.policy import default_choose_target
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card, BEAR

PATH = card("Test Path", "{W}", "Instant", "Exile target creature. Its controller may search their library for a basic "
                                           "land card, put that card onto the battlefield tapped, then shuffle.")
VIN = card("Test Vindicate", "{1}{W}{B}", "Sorcery", "Destroy target permanent.")
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
FOREST = card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")
PLAINS = card("Plains", "", "Basic Land — Plains", "({T}: Add {W}.)")


class Staples(Base):
    def resolve(self, c, targets):
        item = StackItem(self.a, list(c.spell_effects), targets + [None] * (len(c.spell_effects) - len(targets)),
                         card=c, name=c.name)
        self.game.stack.append(item)
        self.game.resolve_top()
        self.game.settle()

    def test_parse(self):
        self.assertEqual(PATH.spell_effects[1].target, "that_controller")
        self.assertEqual(VIN.spell_effects[0].target, "permanent")

    def test_path_gives_the_land_to_the_creatures_controller(self):
        ogre = Permanent(OGRE, self.b)
        self.b.battlefield = [ogre]
        self.a.library, self.b.library = [PLAINS] * 3, [FOREST] * 3
        self.resolve(PATH, [ogre])
        self.assertEqual([(p.card.name, p.tapped) for p in self.b.battlefield], [("Forest", True)])
        self.assertFalse(any(p.card.is_land for p in self.a.battlefield))
        self.assertEqual(len(self.a.library), 3)

    def test_vindicate_destroys_a_land(self):
        land = Permanent(FOREST, self.b)
        self.b.battlefield = [land]
        self.resolve(VIN, [land])
        self.assertNotIn(land, self.b.battlefield)

    def test_ai_still_aims_vindicate_at_their_best_permanent(self):
        """HeuristicAI: lands are legal now, but an opposing creature is still the pick."""
        ogre = Permanent(OGRE, self.b)
        self.b.battlefield = [Permanent(FOREST, self.b), ogre]
        self.a.battlefield = [Permanent(BEAR, self.a), Permanent(PLAINS, self.a)]
        with self.game.targeting(VIN):
            self.assertIs(default_choose_target(self.game, self.a, VIN.spell_effects[0]), ogre)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Path to Exile", "Assassin's Trophy"):
            self.assertEqual(db.get(name).spell_effects[1].target, "that_controller", name)
        for name in ("Vindicate", "Beast Within", "Generous Gift"):
            self.assertEqual(db.get(name).spell_effects[0].target, "permanent", name)


if __name__ == "__main__":
    unittest.main()
