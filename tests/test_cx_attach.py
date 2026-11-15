"""Attach an Aura or Equipment already on the battlefield to another object (#343, mtgsim.cx_attach)."""
import os
import unittest

from mtgsim import auras
from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from mtgsim.engine.policy import ability_worth
from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 5, 5)
BLADE = card("Test Blade", "{1}", "Artifact — Equipment", "Equipped creature gets +2/+0.\nEquip {1}")
MIGHT = card("Test Might", "{1}{G}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2.")
SHACKLE = card("Test Shackle", "{1}{W}", "Enchantment — Aura",
               "Enchant creature\nEnchanted creature can't attack or block.")
LAND_AURA = card("Test Growth", "{G}", "Enchantment — Aura", "Enchant land\nEnchanted land has \"{T}: Add {G}{G}.\"")
WHITE_KNIGHT = card("Test Paladin", "{W}{W}", "Creature — Human Knight", "Protection from artifacts", 2, 2)
HEXED = card("Test Hexer", "{1}", "Creature — Elf", "Hexproof", 1, 1)
SQUIRE = card("Test Squire", "{1}", "Artifact Creature — Squire",
              "{T}: Attach target Equipment you control to target creature you control.", 1, 2)
FINESSE = "Attach target Aura you control to target creature."
CAPTAIN = card("Test Captain", "{2}{W}", "Creature — Human Soldier",
               "At the beginning of combat on your turn, attach up to one target Equipment you control to ~.", 2, 2)
OUTFITTER = card("Test Outfitter", "{1}{W}", "Creature — Human Soldier",
                 "When ~ enters, you may attach target Equipment you control to target creature you control.", 1, 1)


def kinds(text):
    effects, ignored = _parse_effects(text)
    return None if ignored else [e.kind for e in effects]


class Parsing(unittest.TestCase):
    def test_shapes(self):
        for text, want in (
                (FINESSE, ["cx_attach_mark", "cx_attach"]),
                ("Attach target Equipment you control to target creature you control.", ["cx_attach_mark", "cx_attach"]),
                ("Attach target Equipment to target creature.", ["cx_attach_mark", "cx_attach"]),
                ("Attach target Equipment you control to up to one target creature you control.",
                 ["cx_attach_mark", "cx_attach"]),
                ("Attach target Equipment you control to ~.", ["cx_attach"]),
                ("Attach up to one target Equipment you control to that creature.", ["cx_attach"])):
            with self.subTest(text):
                self.assertEqual(kinds(text), want)
        effects, _ = _parse_effects("Attach up to one target Equipment you control to that creature.")
        self.assertEqual((effects[0].data["host"], effects[0].data["optional_target"]), ("prev", True))
        effects, _ = _parse_effects("You may attach target Equipment you control to target creature you control.")
        self.assertTrue(all(e.data.get("optional") for e in effects))

    def test_near_misses_stay_unsupported(self):
        for text in ("Attach target creature to target creature.",              # not an attachment
                     "Attach target artifact you control to target creature.",   # might not be one
                     "Attach target Aura you control to target land.",           # non-creature hosts: not yet
                     "Attach target Aura to target creature or player.",
                     "Attach up to one target Aura to up to one target creature.",
                     "Attach target Aura attached to a creature to another creature."):   # host chosen untargeted
            with self.subTest(text):
                self.assertIsNone(kinds(text))

    @unittest.skipUnless(os.path.exists(DB_FILE), "card database not built")
    def test_cards_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Aura Finesse", "Brass Squire", "Magnetic Theft", "Sokka and Suki", "Kazuul's Toll Collector",
                     "Kor Outfitter", "Iron Hills Stalwart", "Sokka, Swordmaster"):
            with self.subTest(name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


class Engine(Base):
    def go(self, effects, targets, source=None, kind="spell", context=None):
        c = None if source is not None else card("Test Spell", "{1}", "Instant", "")
        item = StackItem(self.a, list(effects), list(targets), card=c, source=source, kind=kind, context=context,
                         name="test")
        self.game.stack.append(item)
        self.game.resolve_top()
        return item

    def setUp(self):
        super().setUp()
        self.x, self.y = self.perm(BEAR, self.a), self.perm(BIG, self.a)

    def test_aura_moves_and_the_bonus_follows(self):
        might = self.perm(MIGHT, self.a)
        auras.attach(self.game, might, self.x)
        stamp = might.attachment_timestamp
        self.assertEqual(self.x.power, 4)
        self.go(_parse_effects(FINESSE)[0], [might, self.y])
        self.assertIs(might.aura_host, self.y)
        self.assertEqual((self.x.power, self.y.power), (2, 7))
        self.assertNotIn(might, self.x.auras)
        self.assertGreater(might.attachment_timestamp, stamp)
        self.assertIs(might.controller, self.a)

    def test_aura_onto_an_opponents_creature_keeps_control(self):
        shackle = self.perm(SHACKLE, self.a)
        theirs = self.perm(BEAR, self.b)
        auras.attach(self.game, shackle, self.x)
        self.go(_parse_effects(FINESSE)[0], [shackle, theirs])
        self.assertIs(shackle.aura_host, theirs)
        self.assertIs(shackle.controller, self.a)

    def test_illegal_destination_leaves_the_aura(self):
        growth = self.perm(LAND_AURA, self.a)
        land = self.perm(ISLAND, self.a)
        auras.attach(self.game, growth, land)
        effects, _ = _parse_effects("Attach target Aura you control to target creature.")
        self.go(effects, [growth, self.y])
        self.assertIs(growth.aura_host, land)            # can't enchant a creature: it stays (701.3b)

    def test_equipment_moves(self):
        blade = self.perm(BLADE, self.a)
        blade.attached_to = self.x
        effects, _ = _parse_effects("Attach target Equipment you control to target creature you control.")
        self.go(effects, [blade, self.y])
        self.assertIs(blade.attached_to, self.y)
        self.assertEqual((self.x.power, self.y.power), (2, 7))

    def test_protection_blocks_equipment_but_not_hexproof(self):
        blade = self.perm(BLADE, self.a)
        blade.attached_to = self.x
        paladin = self.perm(WHITE_KNIGHT, self.a)
        effects, _ = _parse_effects("Attach target Equipment you control to ~.")
        self.go(effects, [blade], source=paladin, kind="ability")
        self.assertIs(blade.attached_to, self.x)         # protection from artifacts: it stays
        hexed = self.perm(HEXED, self.a)
        self.go(effects, [blade], source=hexed, kind="ability")
        self.assertIs(blade.attached_to, hexed)          # attaching doesn't target the host

    def test_another_players_equipment(self):
        blade = self.perm(BLADE, self.b)
        theirs = self.perm(BEAR, self.b)
        blade.attached_to = theirs
        effects, _ = _parse_effects("Attach target Equipment to target creature.")
        self.go(effects, [blade, self.y])
        self.assertIs(blade.attached_to, self.y)
        self.assertIs(blade.controller, self.b)          # control doesn't change
        self.assertEqual(self.y.power, 7)

    def test_no_move_when_the_object_leaves(self):
        blade = self.perm(BLADE, self.a)
        blade.attached_to = self.x
        effects, _ = _parse_effects("Attach target Equipment you control to target creature you control.")
        item = StackItem(self.a, list(effects), [blade, self.y], card=card("Test Spell", "{1}", "Instant", ""),
                         name="test")
        self.game.stack.append(item)
        self.game.leave_battlefield(blade, "graveyard")
        self.game.resolve_top()
        self.assertIsNone(blade.attached_to)
        self.assertEqual(self.y.power, 5)

    def test_host_gone_leaves_the_equipment(self):
        blade = self.perm(BLADE, self.a)
        blade.attached_to = self.x
        effects, _ = _parse_effects("Attach target Equipment you control to target creature you control.")
        item = StackItem(self.a, list(effects), [blade, self.y], card=card("Test Spell", "{1}", "Instant", ""),
                         name="test")
        self.game.stack.append(item)
        self.game.leave_battlefield(self.y, "graveyard")
        self.game.resolve_top()
        self.assertIs(blade.attached_to, self.x)

    def test_no_equip_cost_is_charged(self):
        blade = self.perm(BLADE, self.a)
        land = self.perm(ISLAND, self.a)
        effects, _ = _parse_effects("Attach target Equipment you control to ~.")
        self.go(effects, [blade], source=self.y, kind="ability")
        self.assertIs(blade.attached_to, self.y)
        self.assertFalse(land.tapped)

    def test_that_creature_from_a_trigger(self):
        blade = self.perm(BLADE, self.a)
        effects, _ = _parse_effects("Attach up to one target Equipment you control to that creature.")
        self.go(effects, [blade], source=self.x, kind="trigger", context=self.y)
        self.assertIs(blade.attached_to, self.y)
        self.go(effects, [None], source=self.x, kind="trigger", context=self.x)   # none chosen: nothing happens
        self.assertIs(blade.attached_to, self.y)

    def test_optional_refusal(self):
        blade = self.perm(BLADE, self.a)
        blade.attached_to = self.y
        effects, _ = _parse_effects("You may attach target Equipment you control to target creature you control.")
        self.go(effects, [blade, self.x])               # a worse creature: the AI declines
        self.assertIs(blade.attached_to, self.y)


class AIChoice(Base):
    def test_squire_moves_the_blade_to_the_best_creature(self):
        squire = self.perm(SQUIRE, self.a)
        squire.sick = False
        bear = self.perm(BEAR, self.a)
        blade = self.perm(BLADE, self.a)
        blade.attached_to = bear
        self.assertFalse(ability_worth(self.game, self.a, squire, 0))      # nothing better than the bear yet
        giant = self.perm(BIG, self.a)
        self.assertTrue(ability_worth(self.game, self.a, squire, 0))
        self.assertTrue(self.game.activate_ability(self.a, squire, 0))
        self.game.settle()
        self.assertIs(blade.attached_to, giant)

    def test_finesse_moves_a_shackle_onto_the_opponent(self):
        shackle = self.perm(SHACKLE, self.a)
        bear = self.perm(BEAR, self.a)
        auras.attach(self.game, shackle, bear)
        theirs = self.perm(BIG, self.b)
        spell = self.spell(FINESSE, "Instant")
        plan = self.a.ai.plan_spell(self.game, self.a, spell, True)
        self.assertIsNotNone(plan)
        self.assertEqual(plan[1], [shackle, theirs])

    def test_trigger_picks_the_equipment_for_the_source(self):
        bear = self.perm(card("Test Mite", "", "Creature — Insect", "", 0, 1), self.a)
        blade = self.perm(BLADE, self.a)
        blade.attached_to = bear
        captain = self.perm(CAPTAIN, self.a)
        trig = CAPTAIN.triggers[0]
        targets = self.game.auto_targets(self.a, trig.effects, captain)
        self.assertEqual(targets, [blade])

    def test_may_trigger_declines_a_bad_move(self):
        giant = self.perm(BIG, self.a)
        blade = self.perm(BLADE, self.a)
        blade.attached_to = giant
        outfitter = self.perm(OUTFITTER, self.a)
        targets = self.game.auto_targets(self.a, OUTFITTER.triggers[0].effects, outfitter)
        self.assertIsNone(targets[0])                   # the blade is already on the best creature


@unittest.skipUnless(os.path.exists(DB_FILE), "card database not built")
class RealCards(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)

    def trigger(self, perm, index=0, context=None):
        trig = perm.card.triggers[index]
        targets = self.game.auto_targets(self.a, trig.effects, perm)
        item = StackItem(self.a, list(trig.effects), targets, source=perm, kind="trigger", context=context,
                         name=perm.card.name)
        self.game.stack.append(item)
        self.game.resolve_top()
        return targets

    def test_weapons_vendor_reflexive_attach_moves_the_chosen_equipment(self):
        vendor = self.perm(self.db.get("Weapons Vendor"), self.a)
        land = self.perm(ISLAND, self.a)
        land.sick = False
        mite = self.perm(card("Test Mite", "", "Creature — Insect", "", 0, 1), self.a)
        giant = self.perm(BIG, self.a)
        blade = self.perm(BLADE, self.a)
        blade.attached_to = mite
        trig = next(i for i, t in enumerate(vendor.card.triggers) if "Equipment" in str(t.effects))
        self.trigger(vendor, trig)
        self.game.settle()
        self.assertIs(blade.attached_to, giant)
        self.assertTrue(land.tapped)                     # the {1} was paid

    def test_armory_automaton_takes_every_equipment(self):
        auto = self.perm(self.db.get("Armory Automaton"), self.a)
        bear = self.perm(card("Test Mite", "", "Creature — Insect", "", 0, 1), self.a)
        blades = [self.perm(BLADE, self.a), self.perm(BLADE, self.b)]
        blades[0].attached_to = bear
        targets = self.trigger(auto, 0)
        self.assertEqual({id(x) for x in targets[1]}, {id(x) for x in blades})
        self.assertTrue(all(b.attached_to is auto for b in blades))
        self.assertIs(blades[1].controller, self.b)


if __name__ == "__main__":
    unittest.main()
