"""Known quantities on verbs that take literals (#397 slice 2): "deals damage equal to Q to R", "loses / gains life
equal to Q", "draw cards equal to Q", "create a number of ... tokens equal to Q". Read as "<verb> X ..., where X is
Q" only when the engine computes Q as written."""
import random
import unittest
from pathlib import Path
from unittest import mock

from mtgsim import carddb
from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
GIANT = card("Test Giant", "{3}{R}", "Creature — Giant", "", 4, 4)
BIG = card("Test Wall", "{3}", "Creature — Wall", "", 0, 9)


class Parsing(unittest.TestCase):
    def test_positives(self):
        cases = {
            "~ deals damage equal to the number of doom counters on it to each player.": ("counters", "doom"),
            "Its controller loses life equal to the number of creatures that died this turn.":
                ("cxq", "hist", "a creature dies"),
            "Then draw cards equal to the number of creature cards in your graveyard.": ("gy", "creature"),
            "Create a number of 1/1 green Elf Warrior creature tokens equal to the number of creatures you control.":
                ("count", "creature"),
        }
        for text, spec in cases.items():
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertEqual(bad, [])
                self.assertEqual([e.data.get("xq") for e in effects], [spec])

    def test_quantities_the_engine_would_misread_stay_unmatched(self):
        for text in ("~ deals damage equal to the number of Wolves and Werewolves you control to target opponent.",
                     "Draw cards equal to the number of differently named creature tokens you control.",
                     "It deals damage equal to its power to target player.",           # whose power?
                     "~ deals damage equal to that creature's power to target opponent."):
            with self.subTest(text=text):
                self.assertNotEqual(_parse_effects(text)[1], [])


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

    def run_effects(self, effects, source=None, card_=None):
        effs = list(effects)
        targets = self.game.auto_targets(self.a, effs)
        self.game.stack.append(StackItem(self.a, effs, targets, source=source, card=card_, name="test",
                                         kind="spell" if card_ is not None else "trigger"))
        self.game.resolve_top()
        self.game.state_based_actions()

    def test_armageddon_clock_hits_each_player_for_its_doom_counters(self):
        clock = self.perm(self.db.get("Armageddon Clock"))
        clock.counters["doom"] = 3
        trig = next(t for t in clock.card.triggers if t.event == "draw_step")
        self.run_effects(trig.effects, source=clock)
        self.assertEqual((self.a.life, self.b.life), (17, 17))

    def test_time_bomb_counts_its_counters_after_being_sacrificed(self):
        bomb = self.perm(self.db.get("Time Bomb"))
        bomb.counters["time"] = 2
        bear = self.perm(BEAR, self.b)
        wall = self.perm(BIG, self.b)
        self.run_effects([e for e in bomb.card.activated[0].effects], source=bomb)
        self.assertEqual((self.a.life, self.b.life), (18, 18))
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(wall.damage, 2)

    def test_flesh_allergy_counts_the_creatures_that_died(self):
        allergy = self.db.get("Flesh Allergy")
        self.game.destroy(self.perm(BEAR))          # one died earlier this turn
        target = self.perm(BEAR, self.b)
        self.run_effects(allergy.spell_effects, card_=allergy)
        self.assertNotIn(target, self.b.battlefield)
        self.assertEqual(self.b.life, 18)

    def test_thundercloud_shaman_counts_giants_and_spares_them(self):
        shaman = self.db.get("Thundercloud Shaman")
        self.perm(GIANT)
        sh = self.perm(shaman)                       # itself a Giant: two Giants
        bear, wall = self.perm(BEAR, self.b), self.perm(BIG, self.b)
        trig = next(t for t in shaman.triggers if t.event == "etb")
        self.run_effects(trig.effects, source=sh)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(wall.damage, 2)
        self.assertTrue(all(x.damage == 0 for x in self.a.battlefield))

    def test_royal_talon_makes_one_soldier_per_counter(self):
        jet = self.perm(self.db.get("Royal Talon Fighter Jet"))
        jet.counters["+1/+1"] = 3
        trig = next(t for t in jet.card.triggers if t.event == "attacks")
        self.run_effects(trig.effects, source=jet)
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 3)

    def test_hagra_diabolist_drains_the_opponent_by_allies(self):
        hagra = self.perm(self.db.get("Hagra Diabolist"))
        self.perm(card("Test Ally", "{W}", "Creature — Human Ally", "", 1, 1))
        trig = hagra.card.triggers[0]
        self.run_effects(trig.effects, source=hagra)
        self.assertEqual(self.b.life, 18)

    def test_ai_casts_the_quantity_spell(self):
        allergy = self.db.get("Flesh Allergy")
        self.perm(BEAR)
        self.perm(GIANT, self.b)
        for _ in range(4):
            self.perm(self.db.get("Swamp"))
        self.a.hand = [allergy]
        self.a.ai.main_phase(self.game, self.a)
        self.game.run_priority()
        self.assertIn(allergy, self.a.graveyard)
        self.assertEqual(self.b.life, 18)            # the sacrificed Bear and the Giant died this turn


if __name__ == "__main__":
    unittest.main()
