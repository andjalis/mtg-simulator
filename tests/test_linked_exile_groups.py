"""Linked exile for filtered targets, counted targets, one target per opponent and opponents' groups (#347), and
the exact-object return: each source brings back only its own cards that are still in exile, under their owners'
control."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.policy import default_choose_target

from tests.test_templates import BEAR, ISLAND, card

DB = Path(__file__).resolve().parents[1] / "mtgsim/data/cards.sqlite3"
WRAP = card("Test Wrap", "{1}{W}", "Enchantment", "When ~ enters, exile target creature with mana value 3 or less an "
            "opponent controls until ~ leaves the battlefield.")
GRASP = card("Test Grasp", "{1}{W}{W}", "Enchantment", "When ~ enters, for each opponent, exile up to one target "
             "nonland permanent that player controls until ~ leaves the battlefield.")
CRACKDOWN = card("Test Crackdown", "{3}{W}{W}", "Artifact", "When ~ enters, exile all artifacts your opponents "
                 "control until ~ leaves the battlefield.")
PETRA = card("Test Petra", "{5}{R}", "Creature — Dinosaur", "When ~ enters, exile two target lands until ~ leaves "
             "the battlefield.", 5, 6)
OGRE = card("Big Ogre", "{4}{R}", "Creature — Ogre", "", 5, 5)
ROCK = card("Test Rock", "{2}", "Artifact", "")
TOKEN = card("Test Token", "", "Token Creature — Soldier", "", 1, 1)
TOKEN.is_token = True


class Parse(unittest.TestCase):
    def test_written(self):
        for c in (WRAP, GRASP, CRACKDOWN, PETRA):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual([e.kind for e in PETRA.triggers[0].effects], ["oring", "oring"])
        self.assertEqual(GRASP.triggers[0].effects[0].data["selector"]["controller"], "opp")

    def test_for_each_player_is_one_slot_per_player(self):
        effs, bad = _parse_effects("For each player, exile up to one target creature that player controls until ~ "
                                   "leaves the battlefield.")
        self.assertEqual(bad, [])
        self.assertEqual([e.data["selector"]["controller"] for e in effs], ["mine", "opp"])
        self.assertTrue(all(e.data["optional_target"] for e in effs))

    def test_refusals(self):
        for text in ("Exile all creatures with power 5 or greater until ~ leaves the battlefield.",   # may hit ~ itself
                     "Exile each nonland permanent with mana value 2 or less until ~ leaves the battlefield.",
                     "For each opponent, exile target nonland permanent that player controls until ~ leaves the "
                     "battlefield.",
                     "Exile target non-Saga, nonland permanent until ~ leaves the battlefield.",
                     "Exile any number of other target creatures controlled by different players until ~ leaves "
                     "the battlefield."):
            with self.subTest(text=text):
                self.assertTrue(_parse_effects(text)[1])

    @unittest.skipUnless(DB.exists(), "card database not built")
    def test_real_cards(self):
        db = CardDB(offline=True)
        for name in ("Silkwrap", "Petradon", "Grasp of Fate", "Celebrate the Mountain-king", "Consulate Crackdown",
                     "Suspension Field"):
            with self.subTest(name=name):
                self.assertEqual(db.get(name).unsupported, [])
        for name in ("Aligned Hedron Network", "Temporary Lockdown"):
            self.assertTrue(db.get(name).unsupported, name)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 20, HeuristicAI())
        self.b = Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main1"

    def perm(self, c, owner, controller=None):
        p = Permanent(c, controller or owner)
        p.owner = owner
        p.sick = p.tapped = False
        (controller or owner).battlefield.append(p)
        return p

    def enter(self, c, targets=None):
        """Put source c onto a's battlefield and resolve its enters trigger with the given targets (AI's if None)."""
        src = self.perm(c, self.a)
        effects = list(c.triggers[0].effects)
        if targets is None:
            targets = self.game.auto_targets(self.a, effects, src)
        self.game.stack.append(StackItem(self.a, effects, targets, source=src))
        self.game.settle()
        return src

    def names(self, player):
        return sorted(x.card.name for x in player.battlefield)


class Resolve(Base):
    def test_silkwrap_filter_and_return(self):
        small, big = self.perm(BEAR, self.b), self.perm(OGRE, self.b)
        eff = WRAP.triggers[0].effects[0]
        legal = self.game.legal_targets(self.a, eff)
        self.assertIn(small, legal)
        self.assertNotIn(big, legal)
        src = self.enter(WRAP)
        self.assertEqual(self.names(self.b), [OGRE.name])
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertEqual(self.names(self.b), sorted([BEAR.name, OGRE.name]))

    def test_stolen_creature_returns_under_its_owners_control(self):
        stolen = self.perm(BEAR, self.b, controller=self.a)
        effs, _ = _parse_effects("Exile target creature until ~ leaves the battlefield.")
        src = self.perm(WRAP, self.b)            # the opponent's O-Ring takes back "their" creature from a
        self.game.stack.append(StackItem(self.b, effs, [stolen], source=src))
        self.game.settle()
        self.assertEqual(self.a.battlefield, [])
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertIn(BEAR.name, self.names(self.b))
        self.assertNotIn(BEAR.name, self.names(self.a))

    def test_a_token_is_gone(self):
        token = self.perm(TOKEN, self.b)
        src = self.enter(GRASP, [token])
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertEqual(self.b.battlefield, [])

    def test_a_card_that_left_exile_stays_where_it_went(self):
        bear = self.perm(BEAR, self.b)
        src = self.enter(WRAP, [bear])
        card = bear.front
        self.game.move_card(card, self.b.exile, self.b.hand, reason="test")
        self.game.move_card(card, self.b.hand, self.b.exile, reason="test")     # a new object in exile
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertEqual(self.b.battlefield, [])
        self.assertIn(card, self.b.exile)

    def test_each_copy_returns_only_its_own(self):
        one, two = self.perm(BEAR, self.b), self.perm(BEAR, self.b)
        first, second = self.enter(WRAP, [one]), self.enter(WRAP, [two])
        self.game.leave_battlefield(first, "graveyard")
        self.game.settle()
        self.assertEqual(len(self.b.battlefield), 1)
        self.assertIn(two.front, self.b.exile)
        self.game.leave_battlefield(second, "graveyard")
        self.game.settle()
        self.assertEqual(len(self.b.battlefield), 2)

    def test_source_gone_before_resolution_exiles_nothing(self):
        bear = self.perm(BEAR, self.b)
        src = self.perm(WRAP, self.a)
        effects = list(WRAP.triggers[0].effects)
        self.game.stack.append(StackItem(self.a, effects, [bear], source=src))
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertEqual(self.names(self.b), [BEAR.name])

    def test_crackdown_takes_only_opponents_artifacts_and_gives_them_back(self):
        mine, theirs = self.perm(ROCK, self.a), self.perm(ROCK, self.b)
        self.perm(BEAR, self.b)
        src = self.enter(CRACKDOWN, [None])
        self.assertIn(mine, self.a.battlefield)
        self.assertIn(src, self.a.battlefield)
        self.assertEqual(self.names(self.b), [BEAR.name])
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertEqual(self.names(self.b), sorted([BEAR.name, ROCK.name]))
        self.assertIsNotNone(theirs)

    def test_petradon_two_lands(self):
        one, two = self.perm(ISLAND, self.b), self.perm(ISLAND, self.b)
        src = self.enter(PETRA, [one, two])
        self.assertEqual(self.b.battlefield, [])
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertEqual(len(self.b.battlefield), 2)


class AI(Base):
    def test_grasp_aims_at_the_opponents_best_nonland_permanent(self):
        self.perm(BEAR, self.a)
        self.perm(ISLAND, self.b)
        self.perm(BEAR, self.b)
        ogre = self.perm(OGRE, self.b)
        self.assertIs(default_choose_target(self.game, self.a, GRASP.triggers[0].effects[0]), ogre)

    def test_for_each_player_leaves_its_own_slot_empty(self):
        effs, _ = _parse_effects("For each player, exile up to one target creature that player controls until ~ "
                                 "leaves the battlefield.")
        self.perm(BEAR, self.a)
        ogre = self.perm(OGRE, self.b)
        targets = self.game.auto_targets(self.a, effs)
        self.assertEqual(targets, [None, ogre])


NEWT = card("Test Newt", "{1}{U}", "Creature — Newt",
            "When ~ enters, exile a land you control.\n"
            "When ~ leaves the battlefield, return the exiled card to the battlefield under its owner's control.", 1, 1)
PROTECTOR = card("Test Protector", "{2}{W}{W}", "Creature — Angel", "Flying\n"
                 "When ~ enters, you may exile any number of non-Angel creatures you control until ~ leaves the "
                 "battlefield.", 2, 2)
ADRIAN = card("Test Adrian", "{4}{W}", "Creature — Human Noble",
              "When ~ enters, exile any number of other nonland permanents you control until ~ leaves the "
              "battlefield. Create a 1/1 white Soldier creature token for each permanent exiled this way.", 3, 3)
ETB_BEAR = card("Test Etb Bear", "{1}{G}", "Creature — Bear", "When ~ enters, you gain 2 life.", 2, 2)


class NonTargeted(Base):
    def test_parse_shapes(self):
        for c in (NEWT, PROTECTOR, ADRIAN):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(NEWT.triggers[0].effects[0].kind, "oring_pick")
        self.assertEqual(PROTECTOR.triggers[0].effects[-1].kind, "oring_any")
        self.assertEqual(ADRIAN.triggers[0].effects[0].kind, "oring_any")
        self.assertEqual(ADRIAN.triggers[0].effects[0].data["for_each_token"].kind, "token")
        self.assertTrue(ADRIAN.triggers[0].effects[0].data["reward_each"])

    def test_oring_pick_exiles_the_least_valuable_and_returns_it(self):
        self.perm(ISLAND, self.a)
        self.perm(ROCK, self.a)
        src = self.enter(NEWT)
        self.assertEqual([x.name for x in self.a.exile], ["Island"])
        self.assertEqual(self.names(self.a), ["Test Newt", "Test Rock"])   # the artifact stayed (selector: land)
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertIn("Island", self.names(self.a))

    def test_oring_any_exiles_etb_creatures_and_they_retrigger_on_return(self):
        self.perm(BEAR, self.a)          # no ETB: not worth exiling
        self.perm(ETB_BEAR, self.a)
        life = self.a.life
        src = self.enter(PROTECTOR)
        self.assertEqual([x.name for x in self.a.exile], [ETB_BEAR.name])
        self.assertIn(BEAR.name, self.names(self.a))
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertEqual(self.a.life, life + 2)      # the ETB fired again on the return
        self.assertIn(ETB_BEAR.name, self.names(self.a))

    def test_for_each_token_rider_counts_the_exiled(self):
        self.perm(BEAR, self.a)
        self.perm(ROCK, self.a)
        src = self.enter(ADRIAN)
        soldiers = [x for x in self.a.battlefield if "Soldier" in x.card.name]
        self.assertEqual(len(soldiers), 2)           # both nonland permanents were exiled (reward_each)
        self.assertEqual(self.names(self.a), ["Soldier token", "Soldier token", "Test Adrian"])
        self.game.leave_battlefield(src, "graveyard")
        self.game.settle()
        self.assertIn(BEAR.name, self.names(self.a))
        self.assertIn("Test Rock", self.names(self.a))


if __name__ == "__main__":
    unittest.main()
