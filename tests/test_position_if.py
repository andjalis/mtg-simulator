"""Conditions the shared library already reads, in more sentence positions (#397 slice 1): "Then if C, B" and the
suffix "B if C". C is checked as B resolves (so "Then if" sees the effects before it); "it" in a suffix condition
is B's own target; unknown conditions and unclear referents keep the sentence unmatched."""
import random
import unittest
from pathlib import Path
from unittest import mock

from mtgsim import carddb
from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_templates import BEAR, DRAGON3, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


def parsed(text):
    effects, bad = _parse_effects(text)
    return [(e.kind, e.target, e.cond) for e in effects], bad


class Parsing(unittest.TestCase):
    def test_positions(self):
        cases = {
            "Then if you're the monarch, double the number of +1/+1 counters on each creature you control.":
                [("double_counters", "my_creatures", 'lib:["monarch"]')],
            "Counter target instant spell if it's blue.": [("counter", "spell", 'lib:["prev_is",{"colors":["U"]}]')],
            "Then create a Treasure token if you weren't the starting player.": [("token", "none", 'lib:["not_starting"]')],
            "Draw a card if that creature's power is 2 or less.": [("draw", "none", 'lib:["prev_is",{"power":["<=",2]}]')],
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parsed(text), (want, []))

    def test_refusals(self):
        for text in ("Counter target spell if it was kicked.",       # "it" is the target, not this spell
                     "You gain 3 life if it's tapped.",              # no target: whose "it"?
                     "Draw a card if you control a frobnicator.",    # unknown condition
                     "Then if you control a frobnicator, draw a card."):
            with self.subTest(text=text):
                self.assertNotEqual(parsed(text)[1], [])

    def test_other_if_wordings_are_left_alone(self):
        self.assertEqual(parsed("Target creature attacks this turn if able.")[0][0][2], "")

    def test_a_condition_already_on_the_body_is_kept(self):
        effects, bad = _parse_effects("You may pay {1}. If you do, draw a card if you control an artifact.")
        self.assertEqual(bad, [])
        self.assertIn("ctl:artifact>=1", effects[-1].cond)
        self.assertIn("paid", effects[-1].cond)

    def test_plural_subtypes_ending_in_es(self):
        from mtgsim import cx_condlib
        self.assertEqual(cx_condlib.parse("you control no Leeches"), 'lib:["ctl","you",{"sub":["Leech"]},"==",0]')
        self.assertEqual(cx_condlib.parse("you control two or more Foxes"), 'lib:["ctl","you",{"sub":["Fox"]},">=",2]')


@unittest.skipUnless(DB_FILE.exists(), "needs the card database")
class Games(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(carddb, "CACHE", Path("/nonexistent/mtgsim-cache.json")):
            cls.db = carddb.CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner=None):
        x = self.game.enter_battlefield(owner or self.a, c)
        x.sick = False
        return x

    def resolve(self, c, targets, by=None, effects=None):
        effs = list(effects if effects is not None else c.spell_effects)
        self.game.stack.append(StackItem(by or self.a, effs, targets, card=c if effects is None else None,
                                         name=c.name, kind="spell" if effects is None else "trigger"))
        self.game.resolve_top()

    def test_burnout_counters_only_a_blue_instant(self):
        burnout = self.db.get("Burnout")
        for colour, cost, countered in (("blue", "{U}", True), ("red", "{R}", False)):
            with self.subTest(colour=colour):
                self.setUp()
                spell = card(f"Test {colour}", cost, "Instant", "Draw a card.")
                target = StackItem(self.b, list(spell.spell_effects), [None], card=spell, name=spell.name)
                self.game.stack.append(target)
                effs = [e for e in burnout.spell_effects if e.kind == "counter"]
                self.game.stack.append(StackItem(self.a, effs, [target], name="Burnout"))
                self.game.resolve_top()
                self.assertEqual(target not in self.game.stack, countered)

    def test_depressurize_checks_power_after_the_debuff(self):
        dep = self.db.get("Depressurize")
        big = card("Test Giant", "{4}", "Creature — Giant", "", 4, 4)
        for creature, dies in ((BEAR, True), (big, False)):
            with self.subTest(creature=creature.name):
                self.setUp()
                x = self.perm(creature, self.b)
                self.resolve(dep, [x, None])
                self.game.state_based_actions()
                self.assertEqual(x not in self.b.battlefield, dies)

    def test_hour_of_promise_zombies_need_three_deserts(self):
        desert = card("Test Desert", "", "Land — Desert", "{T}: Add {C}.")
        hour = self.db.get("Hour of Promise")
        for deserts, zombies in ((1, 0), (3, 2)):
            with self.subTest(deserts=deserts):
                self.setUp()
                self.a.library = [desert] * 2 + [ISLAND] * 10
                for _ in range(deserts - 2 if deserts > 2 else 0):
                    self.perm(desert)
                if deserts == 1:
                    self.a.library = [desert] + [ISLAND] * 10
                self.resolve(hour, [None] * len(hour.spell_effects))
                self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), zombies)

    def test_eagle_of_deliverance_reads_the_targeted_creature(self):
        eagle = self.db.get("Eagle of Deliverance")
        trig = next(t for t in eagle.triggers if t.event == "etb")
        for creature, draws in ((BEAR, 1), (DRAGON3, 0)):
            with self.subTest(creature=creature.name):
                self.setUp()
                x = self.perm(creature)
                hand = len(self.a.hand)
                self.resolve(eagle, [x, None], effects=trig.effects)
                self.assertEqual(len(self.a.hand) - hand, draws)

    def test_furgul_counts_leeches(self):
        furgul = self.db.get("Furgul, Quag Nurturer")
        trig = next(t for t in furgul.triggers if t.event == "end_step")
        leech = card("Test Leech", "{B}", "Creature — Leech", "", 1, 1)
        x = self.perm(leech)
        self.resolve(furgul, [None] * len(trig.effects), effects=trig.effects)
        self.assertEqual(x.counters.get("+1/+1"), 1)
        self.assertEqual([y.card.name for y in self.a.battlefield], ["Test Leech"])     # no Slimy Dualleech

    def test_ai_casts_feudkillers_verdict_and_gets_the_giant_when_ahead(self):
        verdict = self.db.get("Feudkiller's Verdict")
        for _ in range(6):
            self.perm(self.db.get("Plains"))
        self.a.hand = [verdict]
        self.a.ai.main_phase(self.game, self.a)
        self.game.run_priority()
        self.assertEqual(self.a.life, 30)
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 1)


if __name__ == "__main__":
    unittest.main()
