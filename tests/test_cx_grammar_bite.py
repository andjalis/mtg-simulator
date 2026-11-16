"""#313 referent damage: "<creature> deals damage equal to its power to <recipient>" (mtgsim.cx_grammar_bite)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, MOUNTAIN, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


def spell(text, types="Instant", cost="{R}"):
    return card("Test Bite", cost, types, text)


class Parsing(unittest.TestCase):
    def kinds(self, s):
        effs = parse_sentence(s)
        return None if effs is None else [e.kind for e in effs]

    def test_shapes(self):
        self.assertEqual(self.kinds("Target creature you control deals damage equal to its power to any target."),
                         ["bite_src", "ref_bite"])
        self.assertEqual(self.kinds("Up to two target creatures you control each deal damage equal to their power "
                                    "to another target creature."), ["bite_src", "bite_src", "ref_bite"])
        self.assertEqual(self.kinds("Target creature you control and up to one other target legendary creature you "
                                    "control each deal damage equal to their power to target creature you don't "
                                    "control."), ["bite_src", "bite_src", "ref_bite"])
        self.assertEqual(self.kinds("Each creature deals damage to itself equal to its power."), ["cx_group"])
        self.assertEqual(self.kinds("Each other Bird you control deals damage equal to its power to target creature "
                                    "an opponent controls."), ["ref_bite"])
        twice = parse_sentence("Target creature you control deals damage equal to twice its power to target "
                               "creature you don't control.")
        self.assertEqual(twice[-1].data["mult"], 2)
        rel = parse_sentence("Target creature an opponent controls deals damage equal to its power to another "
                             "target creature that player controls.")
        self.assertEqual(rel[-1].data["bite_rel"], "not_src_same_ctrl")

    def test_existing_parses_are_kept(self):
        # "~ deals damage equal to its power to any target": the damage verb's own parse, not this rider's
        self.assertEqual(self.kinds("~ deals damage equal to its power to any target."), ["damage"])

    def test_rejects(self):
        for s in ("They each deal damage equal to their power to target creature an opponent controls.",
                  "Target creature you control deals damage equal to its toughness to any target.",
                  "Target creature you control deals damage equal to its power to you and any target.",
                  "Target creature you control deals damage equal to its power to target creature the chosen player "
                  "controls.",
                  "Target creature you control deals damage equal to its power to another target creature that "
                  "player controls.",           # "that player": no player in the sentence
                  "Each creature target player controls deals damage equal to its power to itself.",
                  "Target creature you control deals damage equal to its power divided as you choose among any "
                  "number of target creatures."):
            self.assertIsNone(parse_sentence(s), s)


class Resolving(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def creature(self, owner, p, t, name="Beast", types="Creature — Beast"):
        x = self.g.enter_battlefield(owner, card(name, "{1}", types, "", p, t))
        x.sick = False
        return x

    def cast(self, c, targets, by=None):
        self.g.stack.append(StackItem(by or self.a, list(c.spell_effects), targets, card=c, name=c.name))
        self.g.resolve_top()

    def test_target_creature_hits_any_target(self):
        mine = self.creature(self.a, 4, 4)
        c = spell("Target creature you control deals damage equal to its power to any target.")
        self.cast(c, [mine, self.b])
        self.assertEqual(self.b.life, 16)
        theirs = self.creature(self.b, 3, 3)
        self.cast(c, [mine, theirs])
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertEqual(mine.damage, 0)            # a bite, not a fight

    def test_power_is_read_on_resolution_and_twice(self):
        mine = self.creature(self.a, 2, 2)
        theirs = self.creature(self.b, 5, 5)
        c = spell("Target creature you control deals damage equal to twice its power to target creature you don't "
                  "control.")
        mine.pump_p = 1                             # 3 power as it resolves: 6 damage
        self.cast(c, [mine, theirs])
        self.assertNotIn(theirs, self.b.battlefield)

    def test_illegal_source_deals_no_damage(self):
        mine = self.creature(self.a, 4, 4)
        theirs = self.creature(self.b, 3, 3)
        c = spell("Target creature you control deals damage equal to its power to another target creature.")
        self.g.leave_battlefield(mine, "hand")
        self.cast(c, [mine, theirs])
        self.assertIn(theirs, self.b.battlefield)
        self.assertEqual(theirs.damage, 0)

    def test_two_sources_each_deal_their_damage(self):
        x, y = self.creature(self.a, 2, 2), self.creature(self.a, 3, 3)
        theirs = self.creature(self.b, 4, 5)
        c = spell("Up to two target creatures you control each deal damage equal to their power to another target "
                  "creature.")
        self.cast(c, [x, y, theirs])
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertEqual(self.g.legal_targets(self.a, c.spell_effects[2]).count(x), 1)   # nobody chosen yet

    def test_another_target_excludes_the_source(self):
        mine = self.creature(self.a, 4, 4)
        theirs = self.creature(self.b, 3, 3)
        c = spell("Target creature you control deals damage equal to its power to another target creature.")
        bite = c.spell_effects[1]
        self.g._choosing_targets, self.g._choosing_effects = [mine], c.spell_effects
        try:
            with self.g.targeting(c):
                legal = self.g.legal_targets(self.a, bite)
        finally:
            self.g._choosing_targets, self.g._choosing_effects = [], ()
        self.assertNotIn(mine, legal)
        self.assertIn(theirs, legal)

    def test_that_player_controls(self):
        big, small = self.creature(self.b, 4, 4), self.creature(self.b, 2, 2)
        mine = self.creature(self.a, 1, 1)
        c = spell("Target creature an opponent controls deals damage equal to its power to another target creature "
                  "that player controls.")
        bite = c.spell_effects[1]
        self.g._choosing_targets, self.g._choosing_effects = [big], c.spell_effects
        try:
            with self.g.targeting(c):
                legal = self.g.legal_targets(self.a, bite)
        finally:
            self.g._choosing_targets, self.g._choosing_effects = [], ()
        self.assertEqual(legal, [small])
        self.assertNotIn(mine, legal)
        self.cast(c, [big, small])
        self.assertNotIn(small, self.b.battlefield)
        self.assertIn(big, self.b.battlefield)

    def test_itself_and_its_controller(self):
        theirs = self.creature(self.b, 3, 3)
        self.cast(spell("Target creature deals damage equal to its power to itself."), [theirs, None])
        self.assertNotIn(theirs, self.b.battlefield)
        other = self.creature(self.b, 4, 4)
        c = spell("Tap target creature. That creature deals damage equal to its power to its controller.")
        self.assertEqual(c.unsupported, [])
        self.cast(c, [other] + [None] * (len(c.spell_effects) - 1))
        self.assertEqual(self.b.life, 16)

    def test_group_members_hit_themselves(self):
        big, small = self.creature(self.b, 4, 3), self.creature(self.a, 1, 3)
        self.cast(spell("Each creature deals damage to itself equal to its power.", "Sorcery"), [None])
        self.assertNotIn(big, self.b.battlefield)
        self.assertIn(small, self.a.battlefield)
        self.assertEqual(small.damage, 1)

    def test_group_sources_hit_one_target(self):
        birds = [self.creature(self.a, 2, 2, "Bird", "Creature — Bird") for _ in range(2)]
        theirs = self.creature(self.b, 4, 4)
        c = spell("Each Bird you control deals damage equal to its power to target creature an opponent controls.")
        self.assertEqual([e.kind for e in c.spell_effects], ["ref_bite"])
        self.cast(c, [theirs])
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertTrue(all(b in self.a.battlefield for b in birds))


class AI(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10
        for _ in range(3):
            self.g.enter_battlefield(self.a, MOUNTAIN).sick = False

    def creature(self, owner, p, t, name="Beast"):
        x = self.g.enter_battlefield(owner, card(name, "{1}", "Creature — Beast", "", p, t))
        x.sick = False
        return x

    def test_ai_aims_its_creature_at_theirs(self):
        mine = self.creature(self.a, 4, 4, "Mine")
        theirs = self.creature(self.b, 3, 3, "Theirs")
        self.a.hand.append(spell("Target creature you control deals damage equal to its power to another target "
                                 "creature.", "Sorcery"))
        self.g.main_phase(self.a)
        self.g.settle()
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)
        self.assertEqual(mine.damage, 0)

    def test_ai_turns_their_creature_on_their_other_creature(self):
        big = self.creature(self.b, 4, 4, "Big")
        small = self.creature(self.b, 3, 3, "Small")
        self.a.hand.append(spell("Target creature an opponent controls deals damage equal to its power to another "
                                 "target creature that player controls.", "Sorcery"))
        self.g.main_phase(self.a)
        self.g.settle()
        self.assertNotIn(small, self.b.battlefield)
        self.assertIn(big, self.b.battlefield)

    def test_ai_goes_face_with_any_target(self):
        self.creature(self.a, 5, 5, "Mine")
        self.b.life = 5
        self.a.hand.append(spell("Target creature you control deals damage equal to its power to any target.",
                                 "Sorcery"))
        self.g.main_phase(self.a)
        self.g.settle()
        self.assertLessEqual(self.b.life, 0)

    def test_ai_casts_a_self_damage_sweep_when_it_hurts_them(self):
        big = self.creature(self.b, 5, 5, "Big")
        small = self.creature(self.a, 1, 3, "Small")
        self.a.hand.append(spell("Each creature deals damage to itself equal to its power.", "Sorcery"))
        self.g.main_phase(self.a)
        self.g.settle()
        self.assertNotIn(big, self.b.battlefield)
        self.assertIn(small, self.a.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCardReferents(unittest.TestCase):
    """"It" in a trigger or an ability: the creature the trigger fired on, the enchanted creature for an Aura's own
    enters trigger, the source itself after "Sacrifice ~"."""
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def test_bind_the_monster_hurts_you_by_the_enchanted_creature(self):
        for _ in range(2):
            self.g.enter_battlefield(self.a, ISLAND).sick = False
        beast = self.g.enter_battlefield(self.b, card("Beast", "{1}", "Creature — Beast", "", 5, 5))
        self.a.hand.append(self.db.get("Bind the Monster"))
        self.g.main_phase(self.a)
        self.g.settle()
        self.assertTrue(beast.tapped)
        self.assertEqual(self.a.life, 15)

    def test_stalking_vengeance_reads_the_dead_creatures_last_power(self):
        self.g.enter_battlefield(self.a, self.db.get("Stalking Vengeance"))
        mine = self.g.enter_battlefield(self.a, card("Mine", "{1}", "Creature — Beast", "", 4, 4))
        mine.counters["+1/+1"] = 1
        self.g.deal_damage(mine, 9, by=self.b)
        self.g.state_based_actions()
        self.g.settle()
        self.assertEqual(self.b.life, 15)

    def test_hellhole_flailer_sacrificed_still_deals_its_power(self):
        flailer = self.g.enter_battlefield(self.a, self.db.get("Hellhole Flailer"))
        ability, power = flailer.card.activated[0], flailer.power
        self.g.sacrifice(flailer)
        item = StackItem(self.a, list(ability.effects), [None, self.b], source=flailer, name="Flailer")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(self.b.life, 20 - power)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in ("Soul's Fire", "Band Together", "Backlash", "Friendly Rivalry", "Bartz and Boko",
                     "Itzquinth, Firstborn of Gishath", "Traitor's Roar", "Wave of Reckoning", "Cosmic Hunger",
                     "Fall of the Hammer", "Mutiny", "Common Goal", "Wisecrack", "Allies at Last", "Polliwallop",
                     "Wing Puncture", "Gravitic Punch", "Punishing Punch", "Solar Blaze", "Bind the Monster",
                     "Combo Attack", "Hellhole Flailer", "Pain for All"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
