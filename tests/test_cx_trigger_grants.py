"""Static grants of quoted triggered abilities (#338): host and group recipients, binding and lifecycle."""
import os
import random
import unittest

from mtgsim import auras
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")

PILLORY = card("Test Pillory", "{1}{W}{B}", "Enchantment — Aura",
               "Enchant creature\nEnchanted creature has \"At the beginning of your upkeep, you lose 1 life.\"")
DIES_DRAW = card("Test Last Word", "{1}{U}", "Enchantment — Aura",
                 "Enchant creature\nEnchanted creature has \"When this creature dies, draw a card.\"")
WHIP = card("Test Whip", "{2}", "Artifact — Equipment",
            "Equipped creature gets +2/+0 and has \"At the beginning of your upkeep, you gain 2 life.\"\nEquip {1}")
LORD = card("Test Lord", "{2}{U}", "Creature — Sliver",
            "All Slivers have \"When this permanent enters, draw a card.\"", power=2, toughness=2)
SLIVER = card("Test Sliver", "{1}", "Creature — Sliver", "", power=1, toughness=1)
TAXER = card("Test Taxer", "{2}", "Artifact",
             "Creatures you control have \"Whenever this creature attacks, you gain 1 life.\"")


class Parsing(unittest.TestCase):
    def test_host_group_and_bonus_lines_parse(self):
        for c in (PILLORY, DIES_DRAW, WHIP, LORD, TAXER):
            with self.subTest(c.name):
                self.assertEqual(c.unsupported, [])
                self.assertEqual(len(c.trigger_grants), 1)
        self.assertEqual(WHIP.equip_bonus, (2, 0))
        self.assertEqual(PILLORY.trigger_grants[0][0], {"host": True})
        self.assertEqual(TAXER.trigger_grants[0][0]["controller"], "mine")

    def test_hostile_quote_makes_a_hostile_aura(self):
        self.assertTrue(PILLORY.aura_hostile)
        self.assertFalse(DIES_DRAW.aura_hostile)
        fervor = card("Test Fervor", "{1}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +3/+3 "
                      "and has \"At the beginning of your upkeep, put a -1/-1 counter on this creature.\"")
        self.assertEqual(fervor.unsupported, [])
        self.assertFalse(fervor.aura_hostile)          # the bonus outweighs the drawback

    def test_refusals_stay_visible(self):
        for text, types in (
                # the quoted body isn't matched by the trigger parser
                ("Enchant creature\nEnchanted creature has \"Whenever this creature attacks, frobnicate.\"",
                 "Enchantment — Aura"),
                # anthem plus grant in one group line: not this slice
                ("Creatures you control get +1/+0 and have \"At the beginning of your upkeep, you lose 1 life.\"",
                 "Enchantment"),
                # an Equipment that hurts its holder: the AI only equips its own creatures
                ("Equipped creature has \"At the beginning of your upkeep, you lose 1 life.\"\nEquip {1}",
                 "Artifact — Equipment"),
                # "Enchanted creature" on a card that isn't an Aura
                ("Enchanted creature has \"At the beginning of your upkeep, draw a card.\"", "Enchantment"),
                # an activated quote is another grant family
                ("Creatures you control have \"Whenever this creature attacks, you may draw a card. Then frob.\"",
                 "Enchantment")):
            with self.subTest(text):
                c = card("Test Refusal", "{1}", types, text)
                self.assertTrue(c.unsupported)
                self.assertEqual(c.trigger_grants, ())

    def test_quote_naming_the_source_is_refused(self):
        # "~" would stand for both "this creature" and the Equipment's own name (Spare Dagger)
        c = card("Test Dagger", "{1}", "Artifact — Equipment",
                 "Equipped creature has \"Whenever this creature attacks, you may sacrifice Test Dagger. If you do, "
                 "draw a card.\"\nEquip {1}")
        self.assertTrue(c.unsupported)

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards_are_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Pillory of the Sleepless", "Commander's Authority", "Sunbond", "Thorncaster Sliver",
                     "Dormant Sliver", "Locutus of Borg", "Aura Flux", "Kira, Great Glass-Spinner", "Voltaic Whip",
                     "Verdant Embrace", "Magus of the Tabernacle"):
            with self.subTest(name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")
        self.assertTrue(db.get("Pillory of the Sleepless").aura_hostile)


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def enchant(self, aura, host, by=None):
        self.game._aura_host = host
        perm = self.game.enter_battlefield(by or self.a, aura)
        self.game.settle()
        return perm

    def upkeep(self, p):
        self.game.fire(p, "upkeep")
        self.game.settle()

    def test_you_is_the_recipients_controller(self):
        theirs = self.game.enter_battlefield(self.b, BEAR)
        self.enchant(PILLORY, theirs)                  # a's Aura on b's creature
        life_a, life_b = self.a.life, self.b.life
        self.upkeep(self.a)
        self.assertEqual((self.a.life, self.b.life), (life_a, life_b))   # "your upkeep" is b's upkeep
        self.upkeep(self.b)
        self.assertEqual((self.a.life, self.b.life), (life_a, life_b - 1))

    def test_ai_puts_a_hostile_grant_on_the_opponent(self):
        self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, BEAR)
        self.assertIs(auras.choose_host(self.game, self.a, PILLORY), theirs)

    def test_cleanup_and_multiple_sources(self):
        host = self.game.enter_battlefield(self.b, BEAR)
        first = self.enchant(PILLORY, host)
        self.enchant(PILLORY, host)
        life = self.b.life
        self.upkeep(self.b)
        self.assertEqual(self.b.life, life - 2)        # two Auras, two abilities
        self.game.leave_battlefield(first, "graveyard")
        self.upkeep(self.b)
        self.assertEqual(self.b.life, life - 3)

    def test_suppressed_source_grants_nothing(self):
        host = self.game.enter_battlefield(self.b, BEAR)
        aura = self.enchant(PILLORY, host)
        silencer = self.game.enter_battlefield(self.a, BEAR)
        aura.silenced_by = silencer
        life = self.b.life
        self.upkeep(self.b)
        self.assertEqual(self.b.life, life)
        aura.silenced_by = None
        host.silenced_by = silencer                          # the recipient losing its abilities loses this one too
        self.upkeep(self.b)
        self.assertEqual(self.b.life, life)

    def test_dies_trigger_uses_last_known_abilities(self):
        host = self.game.enter_battlefield(self.a, BEAR)
        self.enchant(DIES_DRAW, host)
        hand = len(self.a.hand)
        self.game.destroy(host)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)
        self.assertFalse(any(x.card is DIES_DRAW for x in self.a.battlefield))   # the Aura went to the graveyard

    def test_blinked_recipient_is_a_new_object_without_the_grant(self):
        host = self.game.enter_battlefield(self.b, BEAR)
        self.enchant(PILLORY, host)
        self.game.leave_battlefield(host, "exile")
        self.game.settle()
        back = self.game.enter_battlefield(self.b, BEAR)
        life = self.b.life
        self.upkeep(self.b)
        self.assertEqual(self.b.life, life)
        self.assertFalse(back.auras)

    def test_group_grant_follows_membership_and_source(self):
        lord = self.game.enter_battlefield(self.a, LORD)
        self.game.settle()
        hand_a, hand_b = len(self.a.hand), len(self.b.hand)
        self.assertEqual(len(self.a.hand), hand_a)
        self.game.enter_battlefield(self.b, SLIVER)    # "All Slivers": the opponent's Sliver draws for its controller
        self.game.settle()
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (hand_a, hand_b + 1))
        self.game.enter_battlefield(self.a, BEAR)      # not a Sliver
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand_a)
        self.game.leave_battlefield(lord, "graveyard")
        self.game.enter_battlefield(self.a, SLIVER)    # source gone: no ability
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand_a)

    def test_lord_gives_itself_the_ability_as_it_enters(self):
        hand = len(self.a.hand)
        self.game.enter_battlefield(self.a, LORD)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_controller_scoped_group_and_equipment_move(self):
        self.game.enter_battlefield(self.a, TAXER)
        mine = self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, BEAR)
        self.assertEqual(sum(t.event == "attacks" for t in mine.triggers), 1)
        self.assertEqual(sum(t.event == "attacks" for t in theirs.triggers), 0)
        whip = self.game.enter_battlefield(self.a, WHIP)
        other = self.game.enter_battlefield(self.a, BEAR)
        whip.attached_to = mine
        self.assertEqual(sum(t.event == "upkeep" for t in mine.triggers), 1)
        self.assertEqual((mine.power, other.power), (4, 2))
        whip.attached_to = other
        self.assertEqual(sum(t.event == "upkeep" for t in mine.triggers), 0)
        self.assertEqual(sum(t.event == "upkeep" for t in other.triggers), 1)
        life = self.a.life
        self.game.fire(self.a, "attacks", source=other)
        self.upkeep(self.a)
        self.assertEqual(self.a.life, life + 3)        # Taxer's 1 and Whip's 2
    def test_it_in_a_self_trigger_is_the_recipient(self):
        rested = card("Test Rested", "{1}{G}", "Enchantment — Aura", "Enchant creature\nEnchanted creature has "
                      "\"Whenever this creature becomes untapped, put two +1/+1 counters on it, then you gain 2 life. "
                      "This ability triggers only once each turn.\"")
        self.assertEqual(rested.unsupported, [])
        host = self.game.enter_battlefield(self.a, BEAR)
        self.enchant(rested, host)
        life = self.a.life
        for _ in range(2):
            self.game.fire(self.a, "becomes_untapped", source=host)
            self.game.settle()
        self.assertEqual((host.p1, self.a.life), (2, life + 2))     # once each turn, counters on the creature

    def test_its_condition_on_the_event_object_is_refused(self):
        c = card("Test Hero", "{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature has \"Whenever this "
                 "creature attacks, if its toughness is 3 or less, put a +1/+1 counter on it.\"")
        self.assertTrue(c.unsupported)

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_first_time_each_turn_is_per_recipient(self):
        from mtgsim.carddb import CardDB
        from mtgsim.engine.state import StackItem
        self.game.enter_battlefield(self.b, CardDB(offline=True).get("Kira, Great Glass-Spinner"))
        bear = self.game.enter_battlefield(self.b, BEAR)
        shock = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to target creature.")
        for alive in (True, False):
            item = StackItem(self.a, list(shock.spell_effects), [bear], card=shock, name=shock.name)
            self.game.stack.append(item)
            self.game.check_ward(item)
            self.game.settle()
            self.assertEqual(bear in self.b.battlefield, alive)


class GrantedEventTriggers(unittest.TestCase):
    """Granted triggers on library (ev:) events fire in real combat; "deals combat damage" fires once per step."""
    def setUp(self):
        from tests.test_combat_triggers import Scripted
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = attackers
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def bloods(self):
        return sum(x.card.name == "Blood" for x in self.a.battlefield)

    def knife(self, host, n=1):
        knife = card("Test Knife", "{1}", "Artifact — Equipment", "Equipped creature gets +1/+0 and has \"Whenever "
                     "this creature deals combat damage, create a Blood token.\"\nEquip {1}")
        self.assertEqual(knife.unsupported, [])
        for _ in range(n):
            self.put(self.a, knife).attached_to = host

    def test_unblocked_and_trample_through_a_blocker_make_one_blood_each(self):
        trampler = self.put(self.a, card("Test Trampler", "{4}{G}", "Creature — Beast", "Trample", 5, 5))
        self.knife(trampler)
        self.fight([trampler])
        self.assertEqual((self.bloods(), self.b.life), (1, 14))
        wall = self.put(self.b, card("Test Wall", "{W}", "Creature — Wall", "", 0, 2))
        trampler.tapped = False
        self.fight([trampler], {trampler: [wall]})
        self.assertEqual(self.bloods(), 2)                       # creature and player hit: one trigger, not two
        self.assertEqual(self.b.life, 10)

    def test_two_sources_are_two_abilities(self):
        bear = self.put(self.a, BEAR)
        self.knife(bear, n=2)
        self.fight([bear])
        self.assertEqual(self.bloods(), 2)

    def test_that_much_is_all_its_combat_damage(self):
        lifelinker = card("Test Charm", "{1}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature has "
                          "\"Whenever this creature deals combat damage, you gain that much life.\"")
        self.assertEqual(lifelinker.unsupported, [])
        trampler = self.put(self.a, card("Test Trampler", "{4}{G}", "Creature — Beast", "Trample", 5, 5))
        self.game._aura_host = trampler
        self.put(self.a, lifelinker)
        wall = self.put(self.b, card("Test Wall", "{W}", "Creature — Wall", "", 0, 2))
        life = self.a.life
        self.fight([trampler], {trampler: [wall]})
        self.assertEqual(self.a.life, life + 5)                  # 2 to the wall and 3 to the player


if __name__ == "__main__":
    unittest.main()
