"""#443 follow-ups: 'up to one target creature gets -N/-N' may aim at any creature (or none), and 'another target
creature gets -N/-N' can't take the creature an earlier target of the same spell took (Leeching Bite)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

TWO = card("Mine", "{1}", "Creature — Human", "", 2, 2)
FOE = card("Foe", "{1}", "Creature — Ogre", "", 2, 2)
BITE = card("Test Bite", "{1}{G}", "Instant", "Target creature gets +1/+1 until end of turn. Another target "
            "creature gets -1/-1 until end of turn.")
RAT = card("Test Rat", "{B}", "Sorcery", "Up to one target creature gets -1/-1 until end of turn.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class UpToOne(unittest.TestCase):
    def test_parse(self):
        effects, bad = _parse_effects("Up to one target creature gets -2/-2 until end of turn.")
        self.assertEqual(bad, [])
        self.assertEqual((effects[0].kind, effects[0].filter), ("debuff_one", ""))
        self.assertTrue(effects[0].data["optional_target"])

    def test_any_creature_or_none_is_legal(self):
        g, a, b = game()
        mine, foe = g.enter_battlefield(a, TWO), g.enter_battlefield(b, FOE)
        eff = RAT.spell_effects[0]
        self.assertEqual(set(g.legal_targets(a, eff)), {mine, foe})
        self.assertTrue(g.valid_action_targets(a, RAT.spell_effects, [None], RAT))
        self.assertTrue(g.valid_action_targets(a, RAT.spell_effects, [mine], RAT))

    def test_ai_aims_at_the_opponent(self):
        g, a, b = game()
        g.enter_battlefield(a, card("Mine1", "{1}", "Creature — Human", "", 1, 1))
        self.assertEqual(g.auto_targets(a, RAT.spell_effects, RAT), [None])     # only its own X/1: none
        foe = g.enter_battlefield(b, card("Foe1", "{1}", "Creature — Elf", "", 1, 1))
        self.assertEqual(g.auto_targets(a, RAT.spell_effects, RAT), [foe])


class Another(unittest.TestCase):
    def test_parse_flag_only_for_another(self):
        self.assertTrue(BITE.spell_effects[1].data.get("not_earlier"))
        effects, _ = _parse_effects("Target creature gets -2/-2 until end of turn.")
        self.assertNotIn("not_earlier", effects[0].data)

    def test_same_creature_twice_is_not_a_legal_choice(self):
        g, a, b = game()
        mine, foe = g.enter_battlefield(a, TWO), g.enter_battlefield(b, FOE)
        self.assertFalse(g.valid_action_targets(a, BITE.spell_effects, [mine, mine], BITE))
        self.assertFalse(g.valid_action_targets(a, BITE.spell_effects, [foe, foe], BITE))
        self.assertTrue(g.valid_action_targets(a, BITE.spell_effects, [mine, foe], BITE))
        self.assertTrue(g.valid_action_targets(a, BITE.spell_effects, [foe, mine], BITE))

    def test_cast_and_resolve(self):
        g, a, b = game()
        for _ in range(2):
            g.enter_battlefield(a, card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)"))
        mine, foe = g.enter_battlefield(a, TWO), g.enter_battlefield(b, card("Foe1", "{1}", "Creature — Elf", "", 1, 1))
        a.hand = [BITE]
        self.assertFalse(g.cast(a, BITE, [mine, mine]))
        self.assertIn(BITE, a.hand)
        self.assertTrue(g.cast(a, BITE, [mine, foe]))
        g.settle()
        self.assertEqual(mine.power, 3)
        self.assertNotIn(foe, b.battlefield)

    def test_ai_picks_two_different_creatures(self):
        g, a, b = game()
        mine, foe = g.enter_battlefield(a, TWO), g.enter_battlefield(b, card("Foe1", "{1}", "Creature — Elf", "", 1, 1))
        self.assertEqual(g.auto_targets(a, BITE.spell_effects, BITE), [mine, foe])

    @unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Leeching Bite", "Consume Strength", "Steal Strength", "Rites of Reaping", "Schismotivate"):
            c = db.get(name)
            self.assertEqual(c.unsupported, [], name)
            self.assertTrue(c.spell_effects[-1].data.get("not_earlier"), name)
        self.assertTrue(db.get("Drooling Groodion").activated[0].effects[-1].data.get("not_earlier"))
        for name in ("Rat Out", "Bleeding Edge", "Dubious Delicacy", "Zulaport Duelist", "Ant-Man's Air Force"):
            c = db.get(name)
            self.assertEqual(c.unsupported, [], name)
            effs = [e for t in c.triggers for e in t.effects] + list(c.spell_effects)
            d = next(e for e in effs if e.kind == "debuff_one")
            self.assertEqual(d.filter, "", name)
            self.assertTrue(d.data.get("optional_target"), name)


if __name__ == "__main__":
    unittest.main()
