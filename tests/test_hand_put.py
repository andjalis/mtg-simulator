"""Qualified hand-to-battlefield puts (#331, mtgsim/hand_put.py): dynamic mana value, chosen type, entry modifiers."""
import random
import unittest

from mtgsim import hand_put
from mtgsim.cards import card_from_scryfall
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

    def test_refusals(self):
        """Unsupported semantics stay visible rather than approximated."""
        for text in (
                # "that damage" is a dynamic referent (#313)
                "Whenever ~ deals combat damage to a player, you may put an artifact card with mana value less "
                "than or equal to that damage from your hand onto the battlefield.",
                # another player's decision
                "When ~ enters, each opponent may put a creature card from their hand onto the battlefield.",
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
                # X also sizes the draw: the where-clause can't be bound to the put alone
                "{T}, Sacrifice another creature: Draw X cards, then you may put a permanent card with mana value "
                "X or less from your hand onto the battlefield, where X is the sacrificed creature's mana value.",
                # an unknown quantity
                "{T}: You may put a creature card with mana value equal to the number of storm clouds overhead "
                "from your hand onto the battlefield."):
            c = card("Refusal Test", "{1}", "Creature — Human", text, 1, 1)
            self.assertTrue(c.unsupported, text)


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


if __name__ == "__main__":
    unittest.main()
