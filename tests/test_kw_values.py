"""#633: granted keywords with a number: ward {N} and toxic N (mtgsim.cx_grammar_kwvalue, mtgsim.kw_values)."""
import unittest

from mtgsim.cards.parse import _parse_effects
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

GUARDIAN = card("Test Guardian", "{4}{W}", "Artifact Creature — Golem", "Other artifacts you control have ward {2}.",
                2, 5)
VANGUARD = card("Test Vanguard", "{1}{W}", "Creature — Human Warrior",
                "Each other Human you control gets +1/+0 and has ward {1}.", 2, 2)
COMMUNION = card("Test Communion", "{1}{B}", "Enchantment — Aura", "Enchant creature\nEnchanted creature has toxic 2.")
INJECTOR = card("Test Injector", "{2}", "Artifact — Equipment",
                "Equipped creature gets +0/+2 and has toxic 1.\nEquip {1}")
RESEARCH = card("Test Research", "{B}", "Enchantment — Aura",
                "Enchant creature\nAs long as enchanted creature is legendary, it gets +1/+1 and has ward {1}.")
HUMAN = card("Test Human", "{W}", "Creature — Human", "", 1, 1)
RELIC = card("Test Relic", "{1}", "Artifact", "")


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (GUARDIAN, VANGUARD, COMMUNION, INJECTOR, RESEARCH):
            self.assertEqual(c.unsupported, [], c.name)
        # main's static_ward reader (permanent_templates) takes the plain "<group> you control have ward {N}" first
        self.assertTrue(GUARDIAN.advanced_rules.get("static_ward") or
                        GUARDIAN.static_keyword_grants[0][1] == ("ward:2",))
        self.assertIn("toxic:2", COMMUNION.equip_keywords)

    def test_temporary(self):
        effects, bad = _parse_effects("Target creature you control gains ward {2} until end of turn.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data.get("keyword"), "ward:2")

    def test_refusals(self):
        for text in ("Other artifacts you control have ward—Pay 2 life.",          # a non-mana ward cost
                     "Creatures you control with a counter on them have ward {1}.",   # no counter kind (yet)
                     "Creatures you control have ward {X}."):
            c = card("Test Refused", "{3}", "Artifact", text)
            self.assertTrue(c.unsupported, text)
        effects, bad = _parse_effects("Target creature gains ward {2}.")         # no duration
        self.assertTrue(bad)


class Engine(Base):
    def test_group_ward(self):
        guardian = self.perm(GUARDIAN, self.a)
        relic = self.perm(RELIC, self.a)
        theirs = self.perm(RELIC, self.b)
        self.assertEqual(relic.ward, 2)
        self.assertEqual(guardian.ward, 0)                       # "other"
        self.assertEqual(theirs.ward, 0)                         # "you control"
        self.a.battlefield.remove(guardian)
        self.assertEqual(relic.ward, 0)

    def test_ward_counters_an_unpaid_opponents_spell(self):
        self.perm(GUARDIAN, self.a)
        relic = self.perm(RELIC, self.a)
        shatter = card("Test Shatter", "{1}", "Instant", "Destroy target artifact.")
        self.b.hand = [shatter]
        self.b.battlefield.append(Permanent(card("Wastes", types="Basic Land", text="{T}: Add {C}."), self.b))
        self.assertTrue(self.game.cast(self.b, shatter, [relic]))
        self.game.settle()
        self.assertIn(relic, self.a.battlefield)                 # ward {2} unpaid: the spell is countered
        self.assertIn("Test Shatter", [c.name for c in self.b.graveyard])

    def test_pump_and_ward_compound(self):
        self.perm(VANGUARD, self.a)
        human = self.perm(HUMAN, self.a)
        self.assertEqual((human.power, human.ward), (2, 1))
        self.assertEqual(self.perm(BEAR, self.a).ward, 0)

    def test_aura_toxic_adds_poison(self):
        bear = self.perm(BEAR, self.a)
        aura = self.perm(COMMUNION, self.a)
        aura.aura_host = bear
        bear.auras.append(aura)
        self.game.deal_damage(self.b, 2, source=bear, combat=True)
        self.assertEqual(self.b.counters.get("poison", 0), 2)
        self.game.deal_damage(self.b, 2, source=bear)            # noncombat: no toxic
        self.assertEqual(self.b.counters.get("poison", 0), 2)

    def test_equipment_toxic_and_pump(self):
        bear = self.perm(BEAR, self.a)
        injector = self.perm(INJECTOR, self.a)
        injector.attached_to = bear
        bear.equipment.append(injector)
        self.assertEqual(bear.toughness, 4)
        self.game.deal_damage(self.b, 2, source=bear, combat=True)
        self.assertEqual(self.b.counters.get("poison", 0), 1)

    def test_gains_toxic_only_with_toxic(self):
        nurse = card("Test Nurse", "{3}{G}", "Creature — Elf Cleric",
                     "Toxic 2\n{2}{G}: Each other creature you control with toxic gains toxic 1 until end of turn.", 3, 3)
        self.assertEqual(nurse.unsupported, [])
        source = self.perm(nurse, self.a)
        rat = self.perm(card("Test Rat", "{1}", "Creature — Rat", "Toxic 1", 1, 1), self.a)
        bear = self.perm(BEAR, self.a)
        self.assertTrue(rat.has("toxic"))                         # printed toxic counts for "with toxic"
        self.assertFalse(bear.has("toxic"))
        effects = nurse.activated[0].effects
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects), name="nurse", kind="ability",
                                         source=source))
        self.game.resolve_top()
        self.game.deal_damage(self.b, 1, source=rat, combat=True)
        self.assertEqual(self.b.counters.get("poison", 0), 2)      # toxic 1 printed + toxic 1 gained
        self.game.deal_damage(self.b, 2, source=bear, combat=True)
        self.assertEqual(self.b.counters.get("poison", 0), 2)

    def test_conditional_host_ward(self):
        bear = self.perm(BEAR, self.a)
        aura = self.perm(RESEARCH, self.a)
        aura.aura_host = bear
        bear.auras.append(aura)
        self.assertEqual(bear.ward, 0)                           # not legendary
        legend = self.perm(card("Test Legend", "{2}", "Legendary Creature — Human", "", 2, 2), self.a)
        aura.aura_host = legend
        bear.auras.remove(aura)
        legend.auras.append(aura)
        self.assertEqual(legend.ward, 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Coppercoat Vanguard", "Necrogen Communion", "Bronze Guardian", "Combat Research", "K-9, Mark I",
                     "Karumonix, the Rat King", "Prosthetic Injector",
                     "Gold-Forged Thopteryx", "Star Whale", "Flowering of the White Tree", "Elder Owyn Lyons",
                     "Storvald, Frost Giant Jarl"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))
        # Matt Murdock ("with a counter on it has ward {1}") waits for #700's any-kind counter selector
        self.assertEqual(card_coverage(db.get("Matt Murdock, Justice Seeker")).status, "partial")


if __name__ == "__main__":
    unittest.main()
