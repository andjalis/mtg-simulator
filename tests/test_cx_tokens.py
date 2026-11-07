"""Token descriptions as a sub-grammar (mtgsim/cx_tokens.py): real cards parse fully and their tokens enter."""
import random
import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.coverage import card_coverage
from mtgsim.cx_tokens import describe, parse_create
from mtgsim.cards.model import NO_MATCH
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND

DB_FILE = Path(__file__).resolve().parent.parent / "mtgsim" / "data" / "cards.sqlite3"


def token_effects(card):
    effects = list(card.spell_effects) + list(card.etb_effects)
    effects += [e for t in card.triggers for e in t.effects] + [e for a in card.activated for e in a.effects]
    return [e for e in effects if e.kind == "cx_token"]


class Grammar(unittest.TestCase):
    def test_parts(self):
        spec = describe('1/1 colorless Phyrexian Mite artifact creature token with toxic 1 and "~ can\'t block."')
        card = spec["card"]
        self.assertEqual((card.power, card.toughness, card.toxic, card.cant_block), (1, 1, 1, True))
        self.assertEqual(card.types, frozenset({"Artifact", "Creature"}))
        self.assertTrue(card.is_token)
        spec = describe("4/4 red and white Dragon creature token with flying named Big One that's tapped and attacking")
        self.assertEqual(spec["card"].name, "Big One")
        self.assertEqual(spec["card"].color_override, frozenset({"R", "W"}))
        self.assertTrue(spec["tapped"] and spec["attacking"])
        self.assertEqual(describe("tapped Treasure token"), {"kind": "treasure", "tapped": True, "attacking": False})

    def test_rejects(self):
        self.assertIsNone(describe("2/2 green Bear creature token with frobnicate"))     # unknown keyword
        self.assertIsNone(describe('1/1 Spirit creature token with "Zorb the glorb."'))  # ability the parser ignores
        self.assertIsNone(describe("Frobnium token"))                                     # unknown predefined token
        self.assertIsNone(describe("Vibranium token"))       # its mana restriction isn't parsed yet
        heartwood = describe("Heartwood token")["card"]
        self.assertEqual((heartwood.produces, heartwood.color_override), ({"R", "G"}, {"R", "G"}))
        self.assertIs(parse_create("", "that many 1/1 green Saproling creature tokens"), NO_MATCH)
        self.assertIs(parse_create("target creature", "a Food token"), NO_MATCH)

    def test_lists_and_counts(self):
        effs = parse_create("", "a 3/3 colorless Wurm artifact creature token with deathtouch and a 3/3 colorless "
                                "Wurm artifact creature token with lifelink")
        self.assertEqual([sorted(e.data["card"].keywords) for e in effs], [["deathtouch"], ["lifelink"]])
        effs = parse_create("", "a number of Food tokens equal to the number of creatures you control")
        self.assertEqual((len(effs), effs[0].data["kind"]), (1, "food"))
        self.assertIn("xq", effs[0].data)
        effs = parse_create("", "a 2/2 black Zombie creature token for each creature card in your graveyard")
        self.assertIn("xq", effs[0].data)
        self.assertEqual(parse_create("each player", "a Food token")[0].data["who"], "each")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB()

    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_full(self):
        for name in ("Beast Within", "Pongify", "Wurmcoil Engine", "Crawling Chorus", "Gaseous Anomaly", "Belonging",
                     "Elephant-Mandrill", "Curse of Opulence", "Fire Navy Trebuchet", "Pinnacle Emissary",
                     "Generous Gift", "Rapid Hybridization"):
            cov = card_coverage(self.db.get(name))
            self.assertEqual(cov.ignored, [], name)

    def test_beast_within_gives_the_token_to_the_controller(self):
        card = self.db.get("Beast Within")
        bear = self.game.enter_battlefield(self.b, BEAR)
        destroy, make = card.spell_effects
        self.game.resolve(self.a, destroy, bear)
        self.game.resolve(self.a, make, None, prev=bear)
        beasts = [x for x in self.b.battlefield if "Beast" in x.card.subtypes]
        self.assertEqual(len(beasts), 1)
        self.assertEqual((beasts[0].power, beasts[0].toughness), (3, 3))
        self.assertFalse(any("Beast" in x.card.subtypes for x in self.a.battlefield))

    def test_owner_of_the_exiled_card_gets_the_token(self):
        for name in ("Funeral Pyre",):
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)
        pyre = self.db.get("Funeral Pyre")
        self.b.graveyard = [BEAR]
        self.game.stack.append(StackItem(self.a, list(pyre.spell_effects), [None] * len(pyre.spell_effects), card=pyre))
        self.game.resolve_top()
        self.assertEqual(self.b.exile, [BEAR])
        spirits = [x for x in self.b.battlefield if "Spirit" in x.card.subtypes]
        self.assertEqual([(x.power, x.has("flying")) for x in spirits], [(1, True)])
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))

    def test_owner_of_the_source(self):
        eff = parse_create("its owner", "a 1/1 white Soldier creature token")[0]
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.b.battlefield.append(mine)          # the opponent controls it; a still owns it
        self.a.battlefield.remove(mine)
        mine.controller = self.b
        self.game.resolve(self.a, eff, None, StackItem(self.b, [eff], [None], card=BEAR, source=mine))
        self.assertTrue(any("Soldier" in x.card.subtypes for x in self.a.battlefield))

    def test_mite_planet_and_gold(self):
        mite = token_effects(self.db.get("Crawling Chorus"))[0]
        self.game.resolve(self.a, mite, None)
        tok = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual(tok.card.toxic, 1)
        self.assertTrue(tok.card.cant_block)
        planet = token_effects(self.db.get("Gaseous Anomaly"))[0]
        self.game.resolve(self.a, planet, None)
        land = next(x for x in self.a.battlefield if x.card.name == "New Planet")
        self.assertTrue(land.tapped and land.card.is_land and len(land.card.produces) == 5)
        gold = token_effects(self.db.get("Curse of Opulence"))[0]
        self.game.resolve(self.a, gold, None)
        self.assertTrue(any(x.card.name == "Gold" and x.card.is_artifact for x in self.a.battlefield))

    def test_each_player_food_and_changeling(self):
        food = token_effects(self.db.get("Elephant-Mandrill"))[0]
        self.game.resolve(self.a, food, None)
        for p in (self.a, self.b):
            self.assertEqual(sum(x.card.token_kind == "food" for x in p.battlefield), 1)
        shapes = token_effects(self.db.get("Belonging"))[0]
        self.game.resolve(self.a, shapes, None)
        changelings = [x for x in self.a.battlefield if x.card.changeling]
        self.assertEqual(len(changelings), shapes.amount)

    def test_for_each_count(self):
        eff = parse_create("", "a 1/1 white Soldier creature token for each creature you control")[0]
        for _ in range(2):
            self.game.enter_battlefield(self.a, BEAR)
        self.game.resolve(self.a, eff, None)
        self.assertEqual(sum("Soldier" in x.card.subtypes for x in self.a.battlefield), 2)

    def test_x_sized_token(self):
        eff = token_effects(self.db.get("Formless Genesis"))[0]
        self.a.graveyard = [self.db.get("Forest")] * 3
        self.game.resolve(self.a, eff, None)
        tok = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((tok.power, tok.toughness, tok.card.changeling), (3, 3, True))

    def test_dies_count_uses_last_counters(self):
        mouser = self.game.enter_battlefield(self.a, self.db.get("Big Mother Mouser"))
        self.game.destroy(mouser)
        self.game.settle()
        self.assertEqual(sum(x.card.name == "Robot token" for x in self.a.battlefield), 2)

    def test_counts_of_the_triggering_object_are_left_alone(self):
        self.assertIs(parse_create("", "a Mutagen token for each +1/+1 counter on it"), NO_MATCH)
        self.assertFalse(token_effects(self.db.get("The Ooze")))


class GameCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB()

    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def effects(self, text):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [], text)
        return effects


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Riders(GameCase):
    """Sentences about the tokens just created: end-of-combat and end-step removal, haste until end of turn."""

    def test_full(self):
        for name in ("Kavaron Harrier", "Geist of Saint Traft", "Gluttonous Troll"):
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)

    def test_sacrifice_at_end_of_combat(self):
        eff = token_effects(self.db.get("Kavaron Harrier"))[0]
        self.assertEqual(eff.data["leave"], ("end_combat", "sacrifice"))
        self.game.resolve(self.a, eff, None)
        robot = next(x for x in self.a.battlefield if x.card.is_token)
        self.game.end_combat(self.a)
        self.assertNotIn(robot, self.a.battlefield)

    def test_exile_at_next_end_step(self):
        eff, = self.effects("Create two 1/1 red Goblin creature tokens. Exile them at the beginning of the next end step.")
        self.game.resolve(self.a, eff, None)
        goblins = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(goblins), 2)
        self.assertEqual([how for _, how in self.game.end_cleanup], ["exile", "exile"])

    def test_haste_until_end_of_turn(self):
        eff, = self.effects("Create a 4/4 red Dragon creature token with flying. It gains haste until end of turn.")
        self.game.resolve(self.a, eff, None)
        dragon = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertTrue(dragon.has("haste") and dragon.has("flying"))
        self.game.expire_continuous_effects()
        self.assertFalse(dragon.has("haste"))

    def test_one_token_per_opponent(self):
        eff = token_effects(self.db.get("Gluttonous Troll"))[0]
        self.game.resolve(self.a, eff, None)
        self.assertEqual(sum(x.card.token_kind == "food" for x in self.a.battlefield), 1)

    def test_rider_without_a_token_stays_unmatched(self):
        _, bad = _parse_effects("Draw a card. Sacrifice that token at end of combat.")
        self.assertEqual(len(bad), 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Subjects(GameCase):
    """"they / that player creates" and "a Food token or a Treasure token"."""
    def test_full(self):
        for name in ("Pain Distributor", "Ant-Man's Army", "Tireless Provisioner", "Vraska, the Cutting Glare"):
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)

    def test_trigger_player(self):
        eff = token_effects(self.db.get("Pain Distributor"))[0]
        self.game.resolve(self.a, eff, None, StackItem(self.a, [eff], [None], context=self.b))
        self.assertEqual([x.card.token_kind for x in self.b.battlefield], ["treasure"])
        self.assertFalse(self.a.battlefield)

    def test_previous_targets_controller(self):
        destroy, treasure = self.db.get("Vraska, the Cutting Glare").triggers[0].effects
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.resolve(self.a, destroy, bear)
        self.game.resolve(self.a, treasure, bear.controller, prev=bear)
        self.assertEqual([x.card.token_kind for x in self.b.battlefield], ["treasure"])

    def test_choice(self):
        eff = token_effects(self.db.get("Ant-Man's Army"))[0]
        self.a.hand = [self.db.get("Wurmcoil Engine")]          # a spell the lands can't pay for: Treasure
        self.game.resolve(self.a, eff, None)
        self.a.hand = []
        self.game.resolve(self.a, eff, None)
        self.assertEqual(sorted(x.card.token_kind for x in self.a.battlefield), ["food", "treasure"])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class CopyTokens(GameCase):
    """"Create a token that's a copy of that creature / it": the object the previous effect or the trigger acted on."""
    def test_full(self):
        for name in ("Necroduality", "Supplant Form", "Mirrorworks", "Riku of Two Reflections", "Impostor Syndrome",
                     "Replication Specialist"):
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)

    def test_trigger_subject(self):
        self.game.enter_battlefield(self.a, self.db.get("Necroduality"))
        self.game.enter_battlefield(self.a, self.db.get("Gravecrawler"))
        self.game.settle()
        copies = [x for x in self.a.battlefield if x.card.name == "Gravecrawler" and x.card.is_token]
        self.assertEqual(len(copies), 1)

    def test_previous_target_after_it_left(self):
        bounce, make = self.db.get("Supplant Form").spell_effects
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.resolve(self.a, bounce, bear)
        self.game.resolve(self.a, make, bear, prev=bear)
        self.assertIn(BEAR, self.b.hand)
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((token.card.name, token.power), ("Grizzly Bears", 2))

    def test_except_and_riders(self):
        make, = self.effects("Create a token that's a copy of it, except it's a 1/1 Spirit in addition to its other "
                             "types. Exile it at the beginning of the next end step.")
        self.assertEqual(make.target, "prev")
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.resolve(self.a, make, bear, prev=bear)
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((token.power, "Spirit" in token.card.subtypes), (1, True))
        self.assertEqual([how for _, how in self.game.end_cleanup], ["exile"])



@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class HeuristicAIGames(unittest.TestCase):
    """The default AI casts the cards itself and the tokens land on the right side."""
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB()

    def setup(self, spell, land, step, active):
        from mtgsim.ai import HeuristicAI
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 3, step, active
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        for _ in range(4):
            self.game.enter_battlefield(self.a, self.db.get(land)).sick = False
        self.a.hand = [self.db.get(spell)]

    def test_beast_within_at_the_opponents_end_step(self):
        self.setup("Beast Within", "Forest", "end_step", 1)
        self.game.enter_battlefield(self.b, self.db.get("Wurmcoil Engine"))
        play = self.a.ai.respond(self.game, self.a)
        self.assertEqual(play[0].name, "Beast Within")
        self.assertTrue(self.game.cast(self.a, *play))
        self.game.settle()
        self.assertEqual(sorted(x.card.name for x in self.b.battlefield),
                         ["Beast token", "Phyrexian Wurm token", "Phyrexian Wurm token"])
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))

    def test_attacking_token_is_sacrificed_at_end_of_combat(self):
        self.setup("Kavaron Harrier", "Plains", "main1", 0)
        self.a.hand = []
        self.game.enter_battlefield(self.a, self.db.get("Kavaron Harrier")).sick = False
        tokens_at_end_of_combat = []
        end_combat = self.game.end_combat

        def watch(p):
            tokens_at_end_of_combat.append([x.card.name for x in self.a.battlefield if x.card.is_token])
            end_combat(p)
        self.game.end_combat = watch
        self.game.combat(self.a, self.b)
        self.assertEqual(tokens_at_end_of_combat, [["Robot token"]])    # paid {2}; the Robot attacked
        self.assertEqual(self.b.life, 16)
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))

    def test_each_player_creates_a_food(self):
        self.setup("Elephant-Mandrill", "Forest", "main1", 0)
        self.game.main_phase(self.a)
        self.game.settle()
        self.assertIn("Elephant-Mandrill", [x.card.name for x in self.a.battlefield])
        for p in (self.a, self.b):
            self.assertEqual(sum(x.card.token_kind == "food" for x in p.battlefield), 1, p.name)
    def test_they_create_a_treasure_after_vraska_destroys_their_permanent(self):
        self.setup("Vraska, the Cutting Glare", "Forest", "main1", 0)
        for land in ("Swamp", "Swamp", "Forest"):          # seven lands: {B}{B}{G}, and six for the trigger
            self.game.enter_battlefield(self.a, self.db.get(land)).sick = False
        self.game.enter_battlefield(self.b, self.db.get("Wurmcoil Engine"))
        self.game.main_phase(self.a)
        self.game.settle()
        self.assertIn("Vraska, the Cutting Glare", [x.card.name for x in self.a.battlefield])
        self.assertEqual(sum(x.card.token_kind == "treasure" for x in self.b.battlefield), 1)
        self.assertFalse(any(x.card.token_kind == "treasure" for x in self.a.battlefield))

if __name__ == "__main__":
    unittest.main()
