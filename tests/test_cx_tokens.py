"""Token descriptions as a sub-grammar (mtgsim/cx_tokens.py): real cards parse fully and their tokens enter."""
import random
import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.coverage import card_coverage
from mtgsim.cx_tokens import describe, parse_create
from mtgsim.cards.model import NO_MATCH
from mtgsim.cards.parse import _parse_effects, _parse_trigger_line
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
        # "on that creature" names a different object than the counts can bind: still refused
        self.assertIs(parse_create("", "a Mutagen token for each +1/+1 counter on that creature"), NO_MATCH)
        # "on it" binds the trigger's object (read as an LKI snapshot when it queued)
        eff = parse_create("", "a Mutagen token for each +1/+1 counter on it")[0]
        self.assertEqual(eff.data["xq"], ("subj_counters", "+1/+1"))
        self.assertIsNotNone(token_effects(self.db.get("The Ooze"))[0])


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
class Counts(GameCase):
    """Devotion, the previous object's stats, leading "for each", and tokens whose P/T a quoted ability defines."""
    def test_full(self):
        for name in ("Master of Waves", "Evangel of Heliod", "Artifact Mutation", "Brass's Bounty", "Bladewing, Deathless Tyrant",
                     "Vernal Sovereign", "Kalonian Twingrove", "Jacked Rabbit", "Termagant Swarm"):
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)

    def test_devotion(self):
        eff = token_effects(self.db.get("Master of Waves"))[0]
        self.game.enter_battlefield(self.a, self.db.get("Master of Waves"))       # {3}{U}: devotion 1
        self.game.enter_battlefield(self.a, self.db.get("Delver of Secrets"))                 # {U}: devotion 2
        self.game.resolve(self.a, eff, None)
        self.assertEqual(sum("Elemental" in x.card.subtypes and x.card.is_token for x in self.a.battlefield), 2)

    def test_previous_objects_mana_value(self):
        destroy, make = self.db.get("Artifact Mutation").spell_effects
        rock = self.game.enter_battlefield(self.b, self.db.get("Mind Stone"))
        self.game.resolve(self.a, destroy, rock)
        self.game.resolve(self.a, make, None, prev=rock)
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 2)

    def test_count_written_first(self):
        eff = token_effects(self.db.get("Brass's Bounty"))[0]
        for _ in range(3):
            self.game.enter_battlefield(self.a, self.db.get("Island"))
        self.game.resolve(self.a, eff, None)
        self.assertEqual(sum(x.card.token_kind == "treasure" for x in self.a.battlefield), 3)

    def test_defining_ability_token(self):
        eff = token_effects(self.db.get("Vernal Sovereign"))[0]
        for _ in range(2):
            self.game.enter_battlefield(self.a, BEAR)
        self.game.resolve(self.a, eff, None)
        elemental = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((elemental.power, elemental.toughness), (3, 3))     # two Bears and itself

    def test_devotion_counts_hybrid_pips_for_each_colour(self):
        from mtgsim.engine.kinds.cx_tokens import devotion
        finks = self.db.get("Kitchen Finks")                       # {1}{G/W}{G/W}
        self.assertEqual((devotion(finks, ("W",)), devotion(finks, ("G",)), devotion(finks, ("G", "W"))), (2, 2, 2))
        self.assertEqual(devotion(self.db.get("Spectral Procession"), ("W",)), 3)    # {2/W}{2/W}{2/W}
        self.assertEqual(devotion(self.db.get("Master of Waves"), ("U",)), 1)

    def test_old_doubling_wording_and_populate_tail(self):
        for name in ("Anointed Procession", "Parallel Lives", "Eyes in the Skies", "Horncaller's Chant"):
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)
        self.assertTrue(self.db.get("Anointed Procession").token_double)
        self.assertEqual([e.kind for e in self.db.get("Eyes in the Skies").spell_effects], ["cx_token", "populate"])

    def test_parent_name_in_a_quoted_ability_is_refused(self):
        self.assertIsNone(describe('green Ooze creature token with "~\'s power and toughness are each equal to the '
                                   'number of slime counters on ~."'))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class FilteredCounts(GameCase):
    """#329: counts from a zone set union, counters on the bound object, nontoken death history and the
    triggering event's amount ("that many")."""

    def test_full(self):
        for name in ("Aatchik, Emerald Radian", "Asmira, Holy Avenger", "Boss's Chauffeur", "Broodhatch Nantuko",
                     "Caller of the Claw", "Darien, King of Kjeldor", "Druid's Call", "Eumidian Hatchery",
                     "Fresh Meat", "Hornet Nest", "Lulu, Inspiring Hollyphant", "Olivia's Attendants",
                     "Rise from the Nether", "Saber Ants", "The Ooze", "Urborg Justice"):
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)

    def test_andor_zone_counts_each_card_once(self):
        # an artifact, a creature and an artifact creature (counted once), plus a land that counts nothing
        self.a.graveyard = [self.db.get("Mind Stone"), BEAR, self.db.get("Ornithopter"), self.db.get("Forest")]
        eff = token_effects(self.db.get("Aatchik, Emerald Radian"))[0]
        self.game.resolve(self.a, eff, None)
        self.assertEqual(sum("Insect" in x.card.subtypes for x in self.a.battlefield), 3)
        self.a.graveyard = []                       # count 0: no tokens
        self.game.resolve(self.a, eff, None)
        self.assertEqual(sum("Insect" in x.card.subtypes for x in self.a.battlefield), 3)

    def test_token_doubling_still_applies_to_a_counted_creation(self):
        self.a.graveyard = [self.db.get("Mind Stone"), BEAR]
        self.game.enter_battlefield(self.a, self.db.get("Parallel Lives"))
        eff = token_effects(self.db.get("Aatchik, Emerald Radian"))[0]
        self.game.resolve(self.a, eff, None)
        self.assertEqual(sum("Insect" in x.card.subtypes for x in self.a.battlefield), 4)

    def test_counters_on_the_dying_creature_read_lki(self):
        chauffeur = self.game.enter_battlefield(self.a, self.db.get("Boss's Chauffeur"))
        chauffeur.counters["+1/+1"] = 3
        self.game.destroy(chauffeur)
        self.game.settle()
        citizens = [x for x in self.a.battlefield if "Citizen" in x.card.subtypes and x.card.is_token]
        self.assertEqual([(x.power, x.toughness) for x in citizens], [(1, 1)] * 3)

    def test_counters_on_the_leaving_creature(self):
        self.game.enter_battlefield(self.a, self.db.get("The Ooze"))
        bear = self.game.enter_battlefield(self.a, BEAR)
        bear.counters["+1/+1"] = 2
        self.game.leave_battlefield(bear, "hand")
        self.game.settle()
        self.assertEqual(sum(x.card.token_kind == "mutagen" for x in self.a.battlefield), 2)

    def test_that_many_from_the_damage_actually_dealt(self):
        ants = self.game.enter_battlefield(self.a, self.db.get("Saber Ants"))        # 2/3: survives two hits
        self.game.deal_damage(ants, 2, by=self.b)
        self.game.settle()
        insects = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(insects), 2)
        self.assertTrue(all((x.power, x.toughness) == (1, 1) for x in insects))
        ants.prevent_next = 1                       # 1 damage gets through: one more ("you may" is taken)
        self.game.deal_damage(ants, 2, by=self.b)
        self.game.settle()
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 3)
        ants.prevent_next = 9                       # fully prevented: the trigger doesn't fire at all
        self.game.deal_damage(ants, 2, by=self.b)
        self.game.settle()
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 3)

    def test_that_many_outside_an_amount_event_stays_unmatched(self):
        self.assertIs(parse_create("", "that many 1/1 green Insect creature tokens"), NO_MATCH)
        _, bad = _parse_effects("Each player discards all the cards in their hand, then creates that many 2/2 black "
                                "Zombie creature tokens.")
        self.assertEqual(len(bad), 1)               # a discard carries no event amount
        triggers, bad, _ = _parse_trigger_line("Whenever a creature you control dies, create that many Treasure tokens.")
        self.assertEqual((triggers, bad), ([], ["create that many Treasure tokens."]))

    def test_that_many_token_abilities_run(self):
        nest = self.game.enter_battlefield(self.a, self.db.get("Hornet Nest"))       # 0/2: one hit is survivable
        self.game.deal_damage(nest, 1, by=self.b)
        self.game.settle()
        bug = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertTrue(bug.has("flying") and bug.has("deathtouch"))

    def test_nontoken_death_history(self):
        for _ in range(2):
            self.game.destroy(self.game.enter_battlefield(self.a, BEAR))
        bug = parse_create("", "a 1/1 green Insect creature token")[0]
        self.game.resolve(self.a, bug, None)        # a token dying must not count
        self.game.destroy(next(x for x in self.a.battlefield if x.card.is_token))
        self.game.settle()
        self.game.enter_battlefield(self.a, self.db.get("Caller of the Claw"))
        self.game.settle()
        bears = [x for x in self.a.battlefield if "Bear" in x.card.subtypes and x.card.is_token]
        self.assertEqual([(x.power, x.toughness) for x in bears], [(2, 2)] * 2)

    def test_nontoken_death_history_zero(self):
        self.game.enter_battlefield(self.a, self.db.get("Caller of the Claw"))
        self.game.settle()
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))


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

    def test_populate_and_doubling(self):
        self.setup("Horncaller's Chant", "Forest", "main1", 0)
        for _ in range(4):
            self.game.enter_battlefield(self.a, self.db.get("Forest")).sick = False
        self.game.enter_battlefield(self.a, self.db.get("Parallel Lives"))
        self.game.main_phase(self.a)
        self.game.settle()
        rhinos = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(rhinos), 4)          # two Rhinos, then the populated copy twice
        self.assertTrue(all(x.has("trample") and x.power == 4 for x in rhinos))

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

    def test_broodhatch_damage_trigger_makes_that_many_insects(self):
        self.setup("Broodhatch Nantuko", "Forest", "main1", 0)
        self.game.main_phase(self.a)                # the AI casts the newly playable creature itself
        self.game.settle()
        brood = next(x for x in self.a.battlefield if x.card.name == "Broodhatch Nantuko")
        self.game.deal_damage(brood, 3, by=self.b)
        self.game.settle()
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 3)

    def test_broodhatch_blocks_and_creates_insects_for_combat_damage(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        brood = self.game.enter_battlefield(self.a, self.db.get("Broodhatch Nantuko"))
        bear = self.game.enter_battlefield(self.b, BEAR)
        bear.sick = False
        self.b.ai.attack = (bear,)
        self.a.ai.block = {bear: [brood]}
        self.game.combat(self.b, self.a)
        self.game.settle()
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 2)     # the Bear's 2 damage

if __name__ == "__main__":
    unittest.main()
