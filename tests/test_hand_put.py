"""Qualified hand-to-battlefield puts (#331, mtgsim/hand_put.py): dynamic mana value, chosen type, entry modifiers."""
import os
import random
import unittest

from mtgsim import hand_put
from mtgsim.cards import card_from_scryfall
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from mtgsim.engine.policy import ability_worth
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

VIAL = card("Test Vial", "{1}", "Artifact", "At the beginning of your upkeep, you may put a charge counter on ~.\n"
            "{T}: You may put a creature card with mana value equal to the number of charge counters on ~ from "
            "your hand onto the battlefield.")
PORTAL = card("Test Portal", "{5}", "Artifact", "As ~ enters, choose a creature type.\n"
              "{3}, {T}: You may put a creature card of the chosen type from your hand onto the battlefield.")
LANDSCALE = card("Test Landscale", "{1}", "Artifact", "{T}: You may put a permanent card with mana value less than "
                 "or equal to the number of lands you control from your hand onto the battlefield tapped.")
RAMPAGER = card("Test Rampager", "{1}", "Artifact",
                "{T}: You may put a creature card from your hand onto the battlefield tapped and attacking.")
RESEARCHER = card("Test Researcher", "{1}{U}", "Creature — Human Wizard",
                  "When ~ enters, you may put an Aura card from your hand onto the battlefield attached to ~.", 1, 1)
ACCOMPLICE = card("Test Accomplice", "{2}{R}", "Creature — Human Rogue", "{R}: You may put a planeswalker card "
                  "from your hand onto the battlefield. Sacrifice it at the beginning of the next end step.", 3, 2)
WALKER = card_from_scryfall({"name": "Test Walker", "mana_cost": "{3}{R}", "cmc": 4, "loyalty": "3",
                             "type_line": "Legendary Planeswalker — Testy", "oracle_text": "+1: You gain 1 life."})
RAZER = card("Test Razer", "{1}", "Artifact", "{T}: You may put a creature card from your hand onto the battlefield "
             "tapped and attacking. Return that creature to your hand at the beginning of the next end step.")
SHARED_X = card("Test Feeder", "{1}", "Artifact", "{T}, Sacrifice a creature: Draw X cards, then you may put a "
                "permanent card with mana value X or less from your hand onto the battlefield, where X is the "
                "sacrificed creature's mana value.")
SHADOW = card("Test Shadow", "{2}", "Creature — Horse", "{T}: You may put a creature card with lesser power from your "
              "hand onto the battlefield.", 3, 3)
EITHER = card("Test Either", "{2}", "Artifact", "{T}: You may put a red creature card or an artifact creature card from "
              "your hand onto the battlefield.")
GOLEM = card("Test Golem", "{4}", "Artifact Creature — Golem", "", 4, 4)
ORIGIN = card("Test Origin", "{2}", "Artifact", "{T}: You may put a Goblin creature card from your hand onto the "
              "battlefield. If you don't, draw a card.")
PLASM = card("Test Plasm", "{2}{U}{U}", "Creature — Shapeshifter", "Whenever ~ blocks a creature, you may return ~ "
             "to its owner's hand. If you do, you may put a creature card from your hand onto the battlefield "
             "blocking that creature.", 1, 1)
WALLER = card("Test Waller", "{2}{W}", "Creature — Wall", "Defender\nWhenever ~ blocks, you gain 4 life.", 1, 6)
BEAR2 = card("Two Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
OGRE3 = card("Three Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
GOBLIN = card("Test Goblin", "{1}{R}", "Creature — Goblin", "", 2, 1)
ELF = card("Test Elf", "{1}{G}{G}", "Creature — Elf", "", 2, 2)
HEALER = card("Test Healer", "{1}{W}", "Creature — Human", "When ~ enters, you gain 3 life.", 1, 1)
CHARGER = card("Test Charger", "{3}", "Creature — Beast", "Whenever ~ attacks, you gain 5 life.", 5, 1)
BRUTE = card("Test Brute", "{5}", "Creature — Beast", "", 1, 8)
ROCK = card("Test Rock", "{2}", "Artifact", "", cmc=2)
LEGEND = card("Test Legend", "{2}{G}", "Legendary Creature — Elf", "", 3, 3)
ARMOR = card("Test Armor", "{1}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2.")
RED_ARMOR = card("Red Armor", "{1}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2.")
SHIELDED = card("Shielded Researcher", "{1}{U}", "Creature — Human Wizard",
                "Protection from red\nWhen ~ enters, you may put an Aura card from your hand onto the battlefield "
                "attached to ~.", 1, 1)


def _eff(c, i=0):
    return c.activated[i].effects[-1]


class Parse(unittest.TestCase):
    def test_supported(self):
        for c in (VIAL, PORTAL, LANDSCALE, RAMPAGER, RESEARCHER, SHIELDED, ACCOMPLICE):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(_eff(VIAL).data, {"spec": {"types": ["creature"]}, "mvq": ("==", ("counters", "charge"))})
        self.assertEqual(_eff(PORTAL).data["spec"], {"types": ["creature"], "chosen": True})
        self.assertEqual(_eff(LANDSCALE).data, {"spec": {"types": ["permanent"]}, "mvq": ("<=", ("count", "land")),
                                                "entry": "tapped"})
        self.assertEqual(_eff(RAMPAGER).data["entry"], "attacking")
        self.assertEqual(RESEARCHER.triggers[0].effects[-1].data, {"spec": {"sub": ["Aura"]}, "entry": "attached"})
        self.assertTrue(_eff(ACCOMPLICE).data["sac_eot"])

    def test_where_x_and_descriptions(self):
        jhoira = card("Jho Test", "{1}", "Artifact", "{T}: Put two ingenuity counters on ~, then you may put an artifact card "
                      "with mana value X or less from your hand onto the battlefield, where X is the number of "
                      "ingenuity counters on ~.")
        self.assertEqual(jhoira.unsupported, [])
        self.assertEqual(_eff(jhoira).data["mvq"], ("<=", ("counters", "ingenuity")))
        for desc, spec in (("basic land", {"basic": True, "types": ["land"]}),
                           ("Goblin permanent", {"sub": ["Goblin"], "types": ["permanent"]}),
                           ("Angel, Demon, or Dragon creature", {"types": ["creature"],
                                                                 "any_sub": ["Angel", "Demon", "Dragon"]})):
            c = card("Desc Test", "{1}", "Artifact", f"{{T}}: You may put a {desc} card from your hand onto the battlefield.")
            self.assertEqual(c.unsupported, [], desc)
            self.assertEqual(_eff(c).data["spec"], spec, desc)

    def test_static_either_relative_and_paid_x(self):
        c = card("Desc Test", "{1}", "Artifact", "{T}: You may put an artifact card with mana value 5 or less from "
                 "your hand onto the battlefield.")
        self.assertEqual(_eff(c).data["spec"], {"types": ["artifact"], "mv": ["<=", 5]})
        self.assertEqual(_eff(EITHER).data["spec"], {"either": [{"colors": ["R"], "types": ["creature"]},
                                                                {"types": ["artifact", "creature"]}]})
        self.assertEqual(_eff(SHADOW).data["statq"], ("power", "<", ("stat", "self", "power")))
        spell = card("Desc Test", "{X}{U}{U}", "Sorcery", "Draw X cards. Then you may put a permanent card with mana "
                     "value X or less from your hand onto the battlefield tapped.")
        self.assertEqual(spell.unsupported, [])
        self.assertEqual(spell.spell_effects[-1].data["mvq"], ("<=", ("paid_x",)))

    def test_refusals(self):
        """Unsupported semantics stay visible rather than approximated."""
        for text in (
                # "that damage" is a dynamic referent (#313)
                "Whenever ~ deals combat damage to a player, you may put an artifact card with mana value less "
                "than or equal to that damage from your hand onto the battlefield.",
                # another player's put from "your" hand, and "their" hand without another player
                "When ~ enters, each opponent may put a creature card from your hand onto the battlefield.",
                "When ~ enters, you may put a creature card from their hand onto the battlefield.",
                # counted puts of Auras (host choice) and subtype lists stay out
                "{T}: Put up to two Aura cards from your hand onto the battlefield.",
                "{T}: Put any number of non-Saga permanent cards from your hand onto the battlefield.",
                # combat entry into a block
                "{T}: You may put a creature card from your hand onto the battlefield blocking target creature.",
                # a bare Aura from hand needs a host choice this template doesn't make
                "{T}: You may put an Aura card from your hand onto the battlefield.",
                # a noncreature "attacking"
                "{T}: You may put an artifact card from your hand onto the battlefield tapped and attacking.",
                # "where X" without an X in the card description
                "{T}: You may put a creature card from your hand onto the battlefield, where X is ~'s power.",
                # "that creature" in a dies trigger is a dynamic referent (#313)
                "Whenever another creature you control dies, you may put a permanent card with mana value less "
                "than or equal to that creature's power from your hand onto the battlefield.",
                # an unknown quantity
                "{T}: You may put a creature card with mana value equal to the number of storm clouds overhead "
                "from your hand onto the battlefield."):
            c = card("Refusal Test", "{1}", "Creature — Human", text, 1, 1)
            self.assertTrue(c.unsupported, text)


class Blocking(unittest.TestCase):
    """Aetherplasm: the put creature blocks the attacker the trigger names; no "whenever ~ blocks"."""
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
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

    def test_parse(self):
        self.assertEqual(PLASM.unsupported, [])
        self.assertEqual(PLASM.triggers[0].effects[-1].data["entry"], "blocking")

    def test_put_blocker_takes_over_the_block(self):
        ogre = self.put(self.a, OGRE3)
        plasm = self.put(self.b, PLASM)
        self.b.hand.extend([WALLER, BEAR2])
        life = self.b.life
        self.a.ai.attack = [ogre]
        self.b.ai.block = {ogre: [plasm]}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertIn(PLASM, self.b.hand)                 # returned
        waller = next(x for x in self.b.battlefield if x.card.name == "Test Waller")
        self.assertEqual(waller.damage, 3)                # it blocked the Ogre and took its damage
        self.assertEqual(ogre.damage, 1)
        self.assertEqual(self.b.life, life)               # no combat damage through, no "whenever ~ blocks" life
        self.assertEqual([c.name for c in self.b.hand if c.name == "Two Bear"], ["Two Bear"])

    def test_outside_combat_just_enters(self):
        from types import SimpleNamespace
        eff = PLASM.triggers[0].effects[-1]
        self.b.hand.append(BEAR2)
        perm = hand_put.resolve(self.game, self.b, eff, SimpleNamespace(source=None, context=None, effects=[eff]))
        self.assertIsNotNone(perm)
        self.assertFalse(self.game.blocks)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 2, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
        for _ in range(4):
            land = self.game.enter_battlefield(self.a, card("Mountain", types="Basic Land — Mountain",
                                                            text="({T}: Add {R}.)"))
            land.sick = False

    def put(self, source, *hand):
        self.a.hand.extend(hand)
        perm = self.game.enter_battlefield(self.a, source)
        perm.sick = False
        return perm

    def activate(self, perm, before_resolve=None):
        self.game._action_depth = 1            # hold the ability on the stack (as inside a larger action)
        try:
            self.assertTrue(self.game.activate_ability(self.a, perm, len(perm.activated) - 1))
            self.assertTrue(self.game.stack)
            if before_resolve:
                before_resolve()               # e.g. a charge counter added in response
        finally:
            self.game._action_depth = 0
        self.game.settle()

    def names(self):
        return {x.card.name for x in self.a.battlefield}

    def test_equal_mana_value(self):
        vial = self.put(VIAL, BEAR2, OGRE3)
        vial.counters["charge"] = 2
        self.activate(vial)
        self.assertIn("Two Bear", self.names())
        self.assertNotIn("Three Ogre", self.names())
        self.assertEqual([c.name for c in self.a.hand], ["Three Ogre"])

    def test_counter_added_before_resolution(self):
        vial = self.put(VIAL, BEAR2, OGRE3)
        vial.counters["charge"] = 2
        self.activate(vial, lambda: vial.counters.__setitem__("charge", 3))
        self.assertIn("Three Ogre", self.names())
        self.assertNotIn("Two Bear", self.names())

    def test_no_match_and_empty_hand(self):
        vial = self.put(VIAL, OGRE3)
        vial.counters["charge"] = 1
        self.activate(vial)
        self.assertEqual([c.name for c in self.a.hand], ["Three Ogre"])
        self.a.hand.remove(OGRE3)
        vial.tapped = False
        self.activate(vial)
        self.assertNotIn("Three Ogre", self.names())

    def test_less_or_equal_lands_tapped(self):
        scale = self.put(LANDSCALE, ROCK, BRUTE)          # four lands: Rock (2) fits, Brute (5) doesn't
        self.activate(scale)
        rock = next(x for x in self.a.battlefield if x.card.name == "Test Rock")
        self.assertTrue(rock.tapped)
        self.assertEqual([c.name for c in self.a.hand], ["Test Brute"])

    def test_chosen_type(self):
        portal = self.put(PORTAL, GOBLIN, ELF)
        portal.chosen_type = "Goblin"
        self.activate(portal)
        self.assertIn("Test Goblin", self.names())
        self.assertNotIn("Test Elf", self.names())

    def test_physical_card_and_etb(self):
        vial = self.put(VIAL, HEALER)
        vial.counters["charge"] = 2
        life = self.a.life
        self.activate(vial)
        self.assertNotIn(HEALER, self.a.hand)
        self.assertEqual(self.a.life, life + 3)

    def test_declining(self):
        vial = self.put(VIAL, BEAR2)
        vial.counters["charge"] = 2
        self.a.ai.choose_hand_put = lambda game, me, cards, entry: None
        self.activate(vial)
        self.assertEqual([c.name for c in self.a.hand], ["Two Bear"])
        self.assertNotIn("Two Bear", self.names())

    def test_default_declines_legend_duplicate(self):
        self.game.enter_battlefield(self.a, LEGEND)
        vial = self.put(VIAL, LEGEND)
        vial.counters["charge"] = 3
        self.activate(vial)
        self.assertEqual([c.name for c in self.a.hand], ["Test Legend"])

    def test_tapped_and_attacking_without_attack_trigger(self):
        ramp = self.put(RAMPAGER, CHARGER)
        self.game.step = "declare_attackers"
        life = self.a.life
        self.activate(ramp)
        charger = next(x for x in self.a.battlefield if x.card.name == "Test Charger")
        self.assertTrue(charger.tapped)
        self.assertIn(charger, self.game.attackers)
        self.assertIs(self.game.attack_targets[charger], self.b)
        self.assertEqual(self.a.life, life)          # it was never declared as an attacker

    def test_shared_x_sizes_draw_and_put(self):
        """"Draw X cards, then put ... X or less, where X is ...": one X for both (the parser's where-X rule)."""
        self.assertEqual(SHARED_X.unsupported, [])
        feeder = self.put(SHARED_X, BRUTE, ROCK)
        self.game.enter_battlefield(self.a, OGRE3)       # the creature to sacrifice: mana value 3
        self.activate(feeder)
        self.assertEqual(len(self.a.library), 7)         # drew three
        self.assertIn("Test Rock", self.names())         # 2 <= 3 put; Brute (5) stays
        self.assertNotIn("Test Brute", self.names())
        self.assertNotIn("Three Ogre", self.names())

    def test_either_description(self):
        either = self.put(EITHER, ELF, GOLEM, GOBLIN)
        self.activate(either)
        self.assertIn("Test Golem", self.names())      # the costliest of Goblin (red) and Golem (artifact creature)
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Test Elf", "Test Goblin"])

    def test_lesser_power_than_source(self):
        shadow = self.put(SHADOW, OGRE3, BEAR2)
        self.activate(shadow)
        self.assertIn("Two Bear", self.names())
        self.assertEqual([c.name for c in self.a.hand], ["Three Ogre"])

    def test_paid_x(self):
        from types import SimpleNamespace
        spell = card("Desc Test", "{X}{U}{U}", "Sorcery", "Draw X cards. Then you may put a permanent card with mana "
                     "value X or less from your hand onto the battlefield tapped.")
        self.a.hand.extend([OGRE3, BEAR2])
        perm = hand_put.resolve(self.game, self.a, spell.spell_effects[-1],
                                SimpleNamespace(source=None, card=spell, context=None, x=2))
        self.assertEqual(perm.card.name, "Two Bear")
        self.assertTrue(perm.tapped)

    def test_if_you_dont_follows_the_put(self):
        """"If you don't" asks whether a card was put, not whether the always-taken "may" was."""
        origin = self.put(ORIGIN, ELF)
        self.activate(origin)                         # no Goblin: nothing put, so draw
        self.assertEqual(len(self.a.library), 9)
        self.a.hand.append(GOBLIN)
        origin.tapped = False
        self.activate(origin)
        self.assertIn("Test Goblin", self.names())
        self.assertEqual(len(self.a.library), 9)      # put one: no draw

    def test_returned_at_end_step(self):
        """Ilharg: "that creature" is the card this effect put (the entered-this-resolution fallback)."""
        self.assertEqual(RAZER.unsupported, [])
        razer = self.put(RAZER, CHARGER)
        self.game.step = "declare_attackers"
        self.activate(razer)
        self.assertIn("Test Charger", self.names())
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertNotIn("Test Charger", self.names())
        self.assertEqual([c.name for c in self.a.hand], ["Test Charger"])

    def test_attacking_outside_combat_just_enters_tapped(self):
        ramp = self.put(RAMPAGER, CHARGER)
        self.activate(ramp)
        charger = next(x for x in self.a.battlefield if x.card.name == "Test Charger")
        self.assertTrue(charger.tapped)
        self.assertNotIn(charger, self.game.attackers)

    def test_attacker_choice_prefers_power(self):
        self.assertIs(hand_put.choose(self.game, self.a, [BRUTE, CHARGER], "attacking"), CHARGER)
        self.assertIs(hand_put.choose(self.game, self.a, [BRUTE, CHARGER], ""), BRUTE)

    def test_aura_attached_to_source(self):
        self.a.hand.append(ARMOR)
        researcher = self.game.enter_battlefield(self.a, RESEARCHER)
        self.game.settle()
        armor = next(x for x in self.a.battlefield if x.card.name == "Test Armor")
        self.assertIs(armor.aura_host, researcher)
        self.assertIn(armor, researcher.auras)
        self.assertEqual(researcher.power, 3)

    def test_aura_needs_a_legal_host(self):
        self.a.hand.append(RED_ARMOR)                # protection from red: not a legal host
        self.game.enter_battlefield(self.a, SHIELDED)
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Red Armor"])
        self.a.hand.remove(RED_ARMOR)
        self.a.hand.append(ARMOR)                    # the source left before the trigger resolved
        researcher = self.game.enter_battlefield(self.a, RESEARCHER)
        self.game.leave_battlefield(researcher, "graveyard")
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Test Armor"])
        anthem = card("Test Anything", "{1}", "Artifact", "{T}: You may put a permanent card from your hand onto the "
                      "battlefield.")
        self.assertEqual(hand_put.candidates(self.game, self.a, _eff(anthem), None), [])     # the single put too

    def test_sacrificed_at_next_end_step(self):
        accomplice = self.put(ACCOMPLICE, WALKER)
        self.activate(accomplice)
        walker = next(x for x in self.a.battlefield if x.card.name == "Test Walker")
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertNotIn(walker, self.a.battlefield)
        self.assertIn(accomplice, self.a.battlefield)

    def test_ai_activates_only_with_a_card_to_put(self):
        vial = self.put(VIAL)
        vial.counters["charge"] = 2
        idx = len(vial.activated) - 1
        self.assertFalse(ability_worth(self.game, self.a, vial, idx))
        self.a.hand.append(BEAR2)
        self.assertTrue(ability_worth(self.game, self.a, vial, idx))



GHALTA = card("Test Stampede", "{4}", "Artifact", "{T}: Put any number of creature cards from your hand onto the "
              "battlefield.")
NAIL = card("Test Nail", "{9}", "Sorcery", "Put up to two creature cards from your hand onto the battlefield.")
MICHEL = card("Test Michel", "{3}", "Artifact", "{T}: You may put a creature card and/or a land card from your hand "
              "onto the battlefield.")
SHOW = card("Test Show", "{2}{U}", "Sorcery", "Each player may put an artifact, creature, enchantment, or land card "
            "from their hand onto the battlefield.")
WUMPUS = card("Test Wumpus", "{3}{G}", "Creature — Beast", "When ~ enters, each other player may put a creature card "
              "from their hand onto the battlefield.", 6, 6)
WURM = card("Test Tempting", "{1}{G}", "Creature — Wurm", "When ~ enters, each opponent may put any number of "
            "artifact, creature, enchantment, and/or land cards from their hand onto the battlefield.", 5, 5)
SHOCK = card("Test Shock", "{R}", "Instant", "Test Shock deals 2 damage to any target.")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class Many(unittest.TestCase):
    """Counted puts and other players' puts (#331 slice 4)."""
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def names(self, p):
        return sorted(x.card.name for x in p.battlefield)

    def resolve(self, c, who=None):
        from mtgsim.engine.state import StackItem
        who = who or self.a
        item = StackItem(who, list(c.spell_effects), [None] * len(c.spell_effects), card=c, kind="spell")
        self.game.stack.append(item)
        self.game.settle()

    def test_parse(self):
        for c in (GHALTA, NAIL, MICHEL, SHOW, WUMPUS, WURM):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(_eff(GHALTA).data, {"count": "any", "spec": {"types": ["creature"]}})
        self.assertEqual(NAIL.spell_effects[0].data["count"], 2)
        self.assertEqual(_eff(MICHEL).data["each_of"], [{"types": ["creature"]}, {"types": ["land"]}])
        self.assertEqual(SHOW.spell_effects[0].data, {"who": "each", "spec": {
            "any": ["artifact", "creature", "enchantment", "land"]}})
        self.assertEqual(WUMPUS.triggers[0].effects[-1].data["who"], "each_other")
        self.assertEqual(WURM.triggers[0].effects[-1].data["who"], "each_opp")

    def test_any_number_puts_every_creature_but_one_copy_of_a_legend(self):
        stampede = self.game.enter_battlefield(self.a, GHALTA)
        self.a.hand = [BEAR2, OGRE3, LEGEND, LEGEND, FOREST, SHOCK]
        self.assertTrue(self.game.activate_ability(self.a, stampede, len(stampede.activated) - 1))
        self.game.settle()
        self.assertEqual(self.names(self.a), ["Test Legend", "Test Stampede", "Three Ogre", "Two Bear"])
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Forest", "Test Legend", "Test Shock"])

    def test_up_to_two(self):
        self.a.hand = [BEAR2, OGRE3, BRUTE]
        self.resolve(NAIL)
        self.assertEqual(self.names(self.a), ["Test Brute", "Three Ogre"])     # the two biggest
        self.assertEqual([c.name for c in self.a.hand], ["Two Bear"])

    def test_creature_and_or_land(self):
        michel = self.game.enter_battlefield(self.a, MICHEL)
        self.a.hand = [FOREST, BEAR2, OGRE3, FOREST]
        self.assertTrue(self.game.activate_ability(self.a, michel, len(michel.activated) - 1))
        self.game.settle()
        self.assertEqual(self.names(self.a), ["Forest", "Test Michel", "Three Ogre"])
        self.a.hand = [FOREST]                       # "and/or": the land alone
        michel.tapped = False
        self.assertTrue(self.game.activate_ability(self.a, michel, len(michel.activated) - 1))
        self.game.settle()
        self.assertEqual(self.names(self.a), ["Forest", "Forest", "Test Michel", "Three Ogre"])

    def test_show_and_tell_both_players(self):
        self.a.hand = [BRUTE, SHOCK]
        self.b.hand = [OGRE3, SHOCK]
        self.resolve(SHOW)
        self.assertEqual(self.names(self.a), ["Test Brute"])
        self.assertEqual(self.names(self.b), ["Three Ogre"])
        self.assertEqual([c.name for c in self.b.hand], ["Test Shock"])

    def test_each_other_player_only(self):
        self.a.hand = [BRUTE]
        self.b.hand = [OGRE3, BEAR2]
        self.game.enter_battlefield(self.a, WUMPUS)
        self.game.settle()
        self.assertEqual(self.names(self.a), ["Test Wumpus"])
        self.assertEqual(self.names(self.b), ["Three Ogre"])          # one card, its own pick

    def test_each_opponent_any_number_with_etb_triggers(self):
        self.b.hand = [HEALER, ROCK, FOREST, SHOCK]
        self.game.enter_battlefield(self.a, WURM)
        self.game.settle()
        self.assertEqual(self.names(self.b), ["Forest", "Test Healer", "Test Rock"])
        self.assertEqual(self.b.life, 23)                         # the put creature's own ETB trigger
        self.assertEqual([c.name for c in self.b.hand], ["Test Shock"])

    def test_entries_are_simultaneous(self):
        """A watcher entering with other creatures sees them, within one player and across players."""
        warden = card("Test Warden", "{W}", "Creature — Human Cleric", "Whenever another creature enters, you gain "
                      "1 life.", 1, 1)
        self.a.hand, self.b.hand = [BRUTE], [warden]
        self.resolve(SHOW)
        self.assertEqual((self.b.life, self.a.life), (21, 20))
        stampede = self.game.enter_battlefield(self.a, GHALTA)
        self.a.hand = [warden, OGRE3]
        self.assertTrue(self.game.activate_ability(self.a, stampede, len(stampede.activated) - 1))
        self.game.settle()
        self.assertEqual(self.a.life, 21)

    def test_auras_are_not_put_without_a_host_choice(self):
        self.game.enter_battlefield(self.b, BEAR2)
        self.a.hand = [ARMOR, ROCK]
        self.resolve(SHOW)
        self.assertEqual(self.names(self.a), ["Test Rock"])
        self.assertEqual([c.name for c in self.a.hand], ["Test Armor"])
        anthem = card("Test Anything", "{1}", "Artifact", "{T}: You may put a permanent card from your hand onto the "
                      "battlefield.")
        self.assertEqual(hand_put.candidates(self.game, self.a, _eff(anthem), None), [])     # the single put too

    def test_declined_and_empty(self):
        self.b.ai.choose_hand_put = lambda game, me, cards, entry: None
        self.a.hand, self.b.hand = [BRUTE], [OGRE3]
        self.resolve(SHOW)
        self.assertEqual((self.names(self.a), self.names(self.b)), (["Test Brute"], []))
        self.a.hand = []
        self.resolve(NAIL)
        self.assertEqual(self.names(self.a), ["Test Brute"])

    def test_ai_values(self):
        stampede = self.game.enter_battlefield(self.a, GHALTA)
        stampede.sick = False
        idx = len(stampede.activated) - 1
        self.assertFalse(ability_worth(self.game, self.a, stampede, idx))
        self.a.hand = [BEAR2, OGRE3]
        self.assertTrue(ability_worth(self.game, self.a, stampede, idx))
        self.assertGreater(hand_put.value(self.game, self.a, _eff(GHALTA), stampede), 6)
        self.b.hand = [OGRE3]
        self.assertLess(hand_put.value(self.game, self.a, WUMPUS.triggers[0].effects[-1], None), 0)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class ThatPlayer(unittest.TestCase):
    """'That player / that opponent / its controller / target opponent may put ... from their hand' (#331)."""
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
            for _ in range(5):
                self.game.enter_battlefield(p, ISLAND).sick = False

    def names(self, p):
        return sorted(x.card.name for x in p.battlefield if not x.card.is_land)

    def test_divine_gambit_the_exiled_permanents_controller_puts(self):
        gambit = self.db.get("Divine Gambit")
        self.assertEqual(gambit.unsupported, [])
        for _ in range(2):
            self.game.enter_battlefield(self.a, card("Plains", types="Basic Land — Plains",
                                                     text="({T}: Add {W}.)")).sick = False
        bear = self.game.enter_battlefield(self.b, BEAR2)
        self.a.hand, self.b.hand = [gambit, BRUTE], [OGRE3, SHOCK]
        self.assertTrue(self.game.cast(self.a, gambit, [bear]))
        self.game.settle()
        self.assertEqual((self.names(self.a), self.names(self.b)), ([], ["Three Ogre"]))
        self.assertEqual([c.name for c in self.a.hand], ["Test Brute"])

    def test_metamorphose_that_opponent_puts(self):
        spell = self.db.get("Metamorphose")
        self.assertEqual(spell.unsupported, [])
        rock = self.game.enter_battlefield(self.b, ROCK)
        self.b.hand = [OGRE3]
        self.a.hand = [spell]
        self.assertTrue(self.game.cast(self.a, spell, [rock]))
        self.game.settle()
        self.assertEqual(self.names(self.b), ["Three Ogre"])

    def test_fold_into_aether_only_when_countered(self):
        fold = self.db.get("Fold into Aether")
        self.assertEqual(fold.unsupported, [])
        self.b.hand = [BRUTE, OGRE3]
        self.game._priority_depth = 1
        self.assertTrue(self.game.cast(self.b, BRUTE, []))
        self.a.hand = [fold]
        self.assertTrue(self.game.cast(self.a, fold, [self.game.stack[-1]]))
        self.game._priority_depth = 0
        self.game.settle()
        self.assertEqual(self.names(self.b), ["Three Ogre"])
        self.assertIn("Test Brute", [c.name for c in self.b.graveyard])

    def test_fold_into_aether_counter_fails(self):
        from mtgsim.engine.state import StackItem
        fold = self.db.get("Fold into Aether")
        self.b.hand = [OGRE3]
        gone = StackItem(self.b, [], [], card=BRUTE, kind="spell")      # not on the stack any more
        stays = StackItem(self.b, [], [], card=BRUTE, kind="spell")
        self.game.stack.append(stays)
        eff = fold.spell_effects[-1]
        hand_put.resolve(self.game, self.a, eff, None, None, stays)       # still on the stack: not countered
        self.assertEqual(self.names(self.b), [])
        self.game.stack.remove(stays)
        hand_put.resolve(self.game, self.a, eff, None, None, gone)
        self.assertEqual(self.names(self.b), ["Three Ogre"])

    def test_braids_the_upkeep_player_puts(self):
        braids = self.game.enter_battlefield(self.a, self.db.get("Braids, Conjurer Adept"))
        self.assertEqual(braids.card.unsupported, [])
        self.a.hand, self.b.hand = [BRUTE], [OGRE3]
        self.game.turn += 1
        self.game.begin_upkeep(self.b)
        self.game.settle()
        self.assertEqual(self.names(self.b), ["Three Ogre"])
        self.assertEqual(self.names(self.a), ["Braids, Conjurer Adept"])

    def test_refusals_and_ai_value(self):
        for text in ("If that spell is countered this way, each player may put a creature card from their hand "
                     "onto the battlefield.",
                     "That player may put a creature card from your hand onto the battlefield."):
            c = card("Refusal Test", "{1}", "Instant", text)
            self.assertTrue(c.unsupported, text)
        eff = self.db.get("Divine Gambit").spell_effects[-1]
        self.b.hand = [OGRE3]
        self.assertLess(hand_put.value(self.game, self.a, eff, None), 0)


class UpToX(unittest.TestCase):
    """'Put up to X land cards from your hand onto the battlefield [tapped], where X is ...' and a paid {X}."""
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_where_x(self):
        c = card("Probe Mover", "{1}", "Artifact", "{T}: Put up to X land cards from your hand onto the battlefield "
                 "tapped, where X is the number of creatures you control.")
        self.assertEqual(c.unsupported, [])
        mover = self.game.enter_battlefield(self.a, c)
        for _ in range(2):
            self.game.enter_battlefield(self.a, BEAR2)
        self.a.hand = [ISLAND, ISLAND, ISLAND]
        self.assertTrue(self.game.activate_ability(self.a, mover, len(mover.activated) - 1))
        self.game.settle()
        lands = [x for x in self.a.battlefield if x.card.is_land]
        self.assertEqual(len(lands), 2)
        self.assertTrue(all(x.tapped for x in lands))
        self.assertEqual(len(self.a.hand), 1)

    def test_paid_x(self):
        c = card("Probe Mover", "{1}", "Artifact", "{X}, {T}: Put up to X land cards from your hand onto the battlefield.")
        self.assertEqual(c.unsupported, [])
        mover = self.game.enter_battlefield(self.a, c)
        for _ in range(3):
            self.game.enter_battlefield(self.a, ISLAND).sick = False
        forest = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
        self.a.hand = [forest, forest, forest]
        self.assertTrue(self.game.activate_ability(self.a, mover, len(mover.activated) - 1, x=2))
        self.game.settle()
        self.assertEqual(sum(x.card.name == "Forest" for x in self.a.battlefield), 2)
