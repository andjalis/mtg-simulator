"""The compositional effect grammar (mtgsim.cx_grammar): subject + verb chain + duration."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards import parse as P
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
WOLF = card("Test Wolf", "{G}", "Creature — Wolf", "", 2, 2)
FLIER = card("Test Flier", "{U}", "Creature — Bird", "Flying", 1, 1)
RED = card("Test Red", "{R}", "Creature — Human", "", 2, 2)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c, targets=None, by=None):
        effects = list(c.spell_effects)
        self.game.stack.append(StackItem(by or self.a, effects, targets or [None] * len(effects), card=c, name=c.name))
        self.game.resolve_top()

    def spell(self, text, types="Instant"):
        c = card("Test Spell", "{1}", types, text)
        self.assertEqual(c.unsupported, [], text)
        return c

    def end_turn(self):
        self.game.expire_continuous_effects()
        for x in self.a.battlefield + self.b.battlefield:
            x.pump_p = x.pump_t = 0
            x.temp_kw.clear()


class Parsing(unittest.TestCase):
    def kinds(self, s):
        effs = parse_sentence(s)
        return None if effs is None else [e.kind for e in effs]

    def test_rejects_what_it_cannot_execute(self):
        for s in ("Those creatures gain trample until end of turn.",       # "those": no referent here
                  "Foo creatures get +1/+1 until end of turn.",            # not a subtype
                  "Target creature gets +2/+2.",                           # a one-shot pump needs a duration
                  "Target creature gains banding until end of turn.",      # not a keyword the engine has
                  "Target creature can't block.",                          # no duration
                  "Target creature gets +1/+1 until end of turn and draws a card.",
                  "Creature gets +1/+1 until end of turn.",                # bare singular subject
                  "Target creature becomes a 3/3 Golem until end of turn."):
            self.assertIsNone(parse_sentence(s), s)

    def test_subjects(self):
        self.assertEqual(self.kinds("Target red or green creature gets -2/-0 until end of turn."), ["debuff_one"])
        self.assertEqual(self.kinds("Up to two target creatures each get +1/+0 and gain menace until end of turn."),
                         ["pump", "grant", "pump", "grant"])
        self.assertEqual(self.kinds("Creatures target player controls get +2/+0 until end of turn."), ["cx_group"])
        self.assertEqual(self.kinds("Other Villains you control gain flying until end of turn."), ["cx_group"])
        self.assertEqual(self.kinds("Equipped creatures you control gain indestructible until end of turn."), ["cx_group"])

    def test_verbs_and_durations(self):
        self.assertEqual(self.kinds("Until end of turn, target creature loses flying and becomes black."),
                         ["cx_lose_kw", "cx_color"])
        self.assertEqual(self.kinds("Target creature becomes white."), ["cx_color"])
        self.assertEqual(self.kinds("Cowards can't block this turn."), ["cx_group"])
        self.assertEqual(self.kinds("It can't be blocked this combat."), ["cx_temp_kw"])
        self.assertEqual(self.kinds("Target creature an opponent controls attacks this turn if able."), ["cx_temp_kw"])

    def test_fallback_runs_after_templates(self):
        effects, bad = P._parse_effects("Target creature gets +2/+0 and gains first strike until end of turn.")
        self.assertEqual([e.kind for e in effects], ["pump"])       # the existing template still wins
        effects, bad = P._parse_effects("You may have target creature gain flying until end of turn.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[-1].kind, "grant")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Canopy Claws", "Rank and File", "Aphotic Wisps", "Cutthroat Maneuver", "Sky Weaver",
                     "How to Start a Riot", "Pyrophobia", "Battle Cry Goblin", "Swarm Surge", "Hold the Line"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


class Resolving(Base):
    def test_lose_flying_until_end_of_turn(self):
        flier = self.perm(FLIER, self.b)
        self.cast(self.spell("Target creature loses flying until end of turn."), [flier])
        self.assertFalse(flier.has("flying"))
        self.end_turn()
        self.assertTrue(flier.has("flying"))

    def test_group_pump_with_subtype_and_controller(self):
        mine, other, theirs = self.perm(GOBLIN, self.a), self.perm(BEAR, self.a), self.perm(GOBLIN, self.b)
        self.cast(self.spell("Goblin creatures you control get +1/+1 and gain haste until end of turn."))
        self.assertEqual((mine.power, mine.toughness), (2, 2))
        self.assertTrue(mine.has("haste"))
        self.assertEqual(other.power, BEAR.power)
        self.assertEqual(theirs.power, 1)
        self.end_turn()
        self.assertEqual(mine.power, 1)

    def test_group_is_fixed_on_resolution(self):
        self.perm(BEAR, self.a)
        self.cast(self.spell("Creatures you control get +1/+0 until end of turn."))
        late = self.perm(BEAR, self.a)
        self.assertEqual(late.power, BEAR.power)

    def test_becomes_color_until_end_of_turn(self):
        bear = self.perm(BEAR, self.b)
        self.cast(self.spell("Target creature becomes black and gains fear until end of turn."), [bear, None])
        self.assertEqual(set(bear.card.colors), {"B"})
        self.assertTrue(bear.has("fear"))
        self.end_turn()
        self.assertEqual(set(bear.card.colors), set(BEAR.colors))

    def test_colour_alternative_target(self):
        spell = self.spell("Target red or green creature gains trample until end of turn.")
        red, blue = self.perm(RED, self.a), self.perm(FLIER, self.a)
        with self.game.targeting(spell):
            legal = self.game.legal_targets(self.a, spell.spell_effects[0])
        self.assertIn(red, legal)
        self.assertNotIn(blue, legal)

    def test_two_targets_each(self):
        x, y = self.perm(BEAR, self.a), self.perm(WOLF, self.a)
        spell = self.spell("Two target creatures each get +2/+2 and gain flying until end of turn.")
        self.cast(spell, [x, None, y, None])
        self.assertEqual((x.power, y.power), (BEAR.power + 2, 4))
        self.assertTrue(x.has("flying") and y.has("flying"))

    def test_creatures_target_player_controls(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.cast(self.spell("Creatures target player controls can't block this turn."), [self.b])
        self.assertTrue(theirs.has("cant_block_now"))
        self.assertFalse(mine.has("cant_block_now"))

    def test_attacking_subtype_group(self):
        wolf, bear = self.perm(WOLF, self.a), self.perm(BEAR, self.a)
        self.game.attackers = [wolf, bear]
        self.cast(self.spell("Attacking Wolves you control gain indestructible until end of turn."))
        self.assertTrue(wolf.has("indestructible"))
        self.assertFalse(bear.has("indestructible"))

    def test_until_your_next_turn_lasts(self):
        from mtgsim.advanced_templates import begin_turn
        flier = self.perm(FLIER, self.b)
        self.cast(self.spell("Target creature loses flying until your next turn."), [flier])
        self.end_turn()
        self.game.turn += 1
        begin_turn(self.game, self.b)
        self.assertFalse(flier.has("flying"))
        self.end_turn()
        self.game.turn += 1
        begin_turn(self.game, self.a)
        self.assertTrue(flier.has("flying"))

    def test_ai_targets_the_opponent_for_a_restriction(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(WOLF, self.b)
        spell = self.spell("Target creature loses trample until end of turn.")
        self.assertIs(self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell), theirs)
        self.assertIsNot(mine, theirs)


if __name__ == "__main__":
    unittest.main()
