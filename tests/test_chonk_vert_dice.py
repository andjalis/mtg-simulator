"""Die rolls: outcome tables, "the result" amounts and threshold triggers (chonk/vert)."""
import random
import unittest

from mtgsim import dungeon_mechanics
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

THUNDERWAVE = card("Thunderwave", "{3}{R}", "Sorcery",
                   "Roll a d20.\n1—9 | Thunderwave deals 3 damage to each creature.\n"
                   "10—19 | You may choose a creature.\n"
                   "20 | Thunderwave deals 6 damage to each creature your opponents control.")
HOARDING_OGRE = card("Hoarding Ogre", "{3}{R}", "Creature — Ogre",
                     "Trample\nWhenever this creature attacks, roll a d20.\n"
                     "1—9 | Create a Treasure token.\n10—19 | Create two Treasure tokens.\n"
                     "20 | Create three Treasure tokens.", 3, 3)
DJINNI = card("Djinni Windseer", "{4}{U}", "Creature — Djinni",
              "Flying\nWhen this creature enters, roll a d20.\n"
              "1—9 | Scry 1.\n10—19 | Scry 2.\n20 | Scry 3.", 3, 3)
BRAZEN_DWARF = card("Brazen Dwarf", "{1}{R}", "Creature — Dwarf Shaman",
                    "Whenever you roll one or more dice, this creature deals 1 damage to each opponent.", 1, 1)
STEEL_SQUIRREL = card("Steel Squirrel", "{2}", "Artifact Creature — Squirrel",
                      "Whenever you roll a 5 or higher on a die, this creature gets +X/+X until end of "
                      "turn, where X is the result.\n{6}: Roll a six-sided die.", 1, 1)
CHICKEN_EGG = card("Chicken Egg", "{1}{W}", "Creature — Egg",
                   "At the beginning of your upkeep, roll a six-sided die. If you roll a 6, sacrifice "
                   "this creature and create a 4/4 red Giant Bird creature token.", 0, 1)
DIJINN_TABLE = ("1—9 | Scry 1.\n10—19 | Scry 2.\n20 | Scry 3.")


class ParseDice(unittest.TestCase):
    def test_roll_spell_effect(self):
        self.assertEqual([(e.kind, e.data.get("sides")) for e in THUNDERWAVE.spell_effects],
                         [("die_roll", 20)])

    def test_outcome_table_becomes_die_triggers(self):
        self.assertEqual([t.event for t in THUNDERWAVE.triggers], ["die:1-9", "die:20-20"])
        ogre = [(t.event, [e.kind for e in t.effects]) for t in HOARDING_OGRE.triggers]
        self.assertIn(("die:1-9", ["token"]), ogre)
        self.assertIn(("die:10-19", ["token"]), ogre)
        self.assertIn(("die:20-20", ["token"]), ogre)
        djinni = [t.event for t in DJINNI.triggers]
        self.assertEqual(djinni, ["etb", "die:1-9", "die:10-19", "die:20-20"])

    def test_roll_and_result_in_one_line(self):
        c = card("Box of Free-Range Goblins", "{1}{R}", "Sorcery",
                 "Roll a six-sided die. Create a number of 1/1 red Goblin creature tokens equal to the result.")
        self.assertEqual([e.kind for e in c.spell_effects], ["die_roll", "die_amount"])

    def test_result_pump(self):
        c = card("Growth Spurt", "{1}{G}", "Instant",
                 "Roll a six-sided die. Target creature gets +X/+X until end of turn, where X is the result.")
        self.assertEqual([(e.kind, e.target) for e in c.spell_effects],
                         [("die_roll", "none"), ("die_amount", "creature")])

    def test_die_check_and_otherwise(self):
        c = card("Poultrygeist", "{1}{B}", "Creature — Bird Spirit",
                 "Flying\nWhenever a creature dies, you may roll a six-sided die. If you roll a 1, "
                 "sacrifice this creature. Otherwise, put a +1/+1 counter on this creature.", 1, 1)
        checks = [e for t in c.triggers for e in t.effects if e.kind == "die_check"]
        self.assertEqual([(e.data["lo"], e.data["hi"]) for e in checks], [(1, 1), (2, 99)])

    def test_roll_event_listeners(self):
        self.assertEqual([(t.event, [e.kind for e in t.effects]) for t in BRAZEN_DWARF.triggers],
                         [("you_roll", ["damage"])])
        self.assertEqual([t.event for t in STEEL_SQUIRREL.triggers], ["you_roll>=5"])

    def test_five_treasure_tokens(self):
        effs, bad = _parse_effects("Create five Treasure tokens.")
        self.assertFalse(bad)
        self.assertEqual((effs[0].kind, effs[0].amount, effs[0].data.get("kind")),
                         ("token", 5, "treasure"))

    def test_un_sets_stay_partial_without_raising(self):
        for name, text in (("Urza's Project", "{2}: Roll a six-sided die. This creature gets the "
                            "indicated result.\n1 — It gets -2/-2 until end of turn."),
                           ("Chaos Dragon", "This creature attacks each combat if able.\nAt the "
                            "beginning of combat on your turn, each player rolls a d20.")):
            card(name, "{2}{R}", "Creature", text, 2, 2)   # must not raise


class DiceEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def put(self, definition, p=None):
        perm = self.g.enter_battlefield(p or self.a, definition)
        perm.sick = False
        self.g.settle()
        return perm

    def apply(self, text, targets=()):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets)
        prev = None
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item, prev=prev)
            prev = target
        return item

    def rolled(self):
        return dungeon_mechanics._last_die(self.g, self.a)

    def treasures(self, p=None):
        return [x for x in (p or self.a).battlefield if x.card.token_kind == "treasure"]

    def test_roll_stores_the_result(self):
        self.apply("Roll a d20.")
        self.assertTrue(1 <= self.rolled() <= 20)

    def test_outcome_table_dispatches_in_range(self):
        ogre = self.put(HOARDING_OGRE)
        state = self.g.rng.getstate()               # peek at the next roll
        n = self.g.rng.randint(1, 20)
        self.g.rng.setstate(state)
        self.g.resolve(self.a, ogre.triggers[0].effects[0], None,
                       StackItem(self.a, [], [], source=ogre))
        self.g.settle()
        expected = 1 if n <= 9 else 2 if n <= 19 else 3
        self.assertEqual(len(self.treasures()), expected)

    def test_result_amount_creates_that_many_tokens(self):
        self.apply("Roll a six-sided die. Create a number of 1/1 red Goblin creature tokens "
                   "equal to the result.")
        self.g.settle()
        goblins = [x for x in self.a.battlefield if "Goblin" in x.card.subtypes]
        self.assertEqual(len(goblins), self.rolled())

    def test_result_amount_pumps_by_the_result(self):
        bear = self.put(BEAR)
        self.apply("Roll a six-sided die. Target creature gets +X/+X until end of turn, where X is "
                   "the result.", (None, bear))
        self.assertEqual(bear.power, 2 + self.rolled())
        self.assertEqual(bear.toughness, 2 + self.rolled())

    def test_die_check_only_fires_in_range(self):
        egg = self.put(CHICKEN_EGG)
        effects = egg.triggers[0].effects
        for eff in effects:
            self.g.resolve(self.a, eff, None, StackItem(self.a, [], [], source=egg))
        self.g.settle()
        birds = [x for x in self.a.battlefield if "Bird" in x.card.subtypes and x.power == 4]
        if self.rolled() == 6:
            self.assertEqual(len(birds), 1)
            self.assertNotIn(egg, self.a.battlefield)
        else:
            self.assertEqual(birds, [])

    def test_you_roll_listener_fires(self):
        self.put(BRAZEN_DWARF)
        life = self.b.life
        self.apply("Roll a d20.")
        self.g.settle()
        self.assertEqual(self.b.life, life - 1)

    def test_threshold_listener_checks_the_roll(self):
        squirrel = self.put(STEEL_SQUIRREL)
        self.apply("Roll a six-sided die.")
        self.g.settle()
        if self.rolled() >= 5:
            self.assertEqual(squirrel.power, 1 + self.rolled())
        else:
            self.assertEqual(squirrel.power, 1)

    def test_djinni_table_etb(self):
        djinni = self.put(DJINNI)
        self.g.settle()
        self.assertTrue(djinni in self.a.battlefield)
        self.assertTrue(1 <= self.rolled() <= 20)

    def test_roll_without_outcomes_does_nothing_harmless(self):
        life = self.b.life
        self.apply("Roll a d20.")
        self.g.settle()
        self.assertEqual(self.b.life, life)

    def test_modified_roll_adds_hand(self):
        self.a.hand = [ISLAND, ISLAND, ISLAND]
        self.apply("Roll a d20 and add the number of cards in your hand.")
        self.assertGreaterEqual(self.rolled(), 4)
