"""Quantity-based "Add mana" sentences (mtgsim.cx_grammar_addmana, #332): "Add {R} for each Goblin on the
battlefield", "add {B} for each charge counter on ~", "{2}, {T}: Add {B} for each black creature card in
your graveyard", "... for each ... removed/destroyed this way". Exact colours and amounts for 0/1/many,
source scope, filtered graveyards, battlefield counts, and the resolved event result for "this way"."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, StackItem

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
ZOMBIE = card("Test Zombie", "{B}", "Creature — Zombie", "", 2, 2)
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 2, 2)
TRINKET = card("Test Trinket", "{1}", "Artifact", "", cmc=1)
BIG_RED = card("Big Red Thing", "{3}{R}{R}", "Creature — Dragon", "", 6, 6)


def spell(text, types="Instant", cost="{R}"):
    c = card("Test Spell", cost, types, text)
    assert c.unsupported == [], (text, c.unsupported)
    return c


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner=None, sick=False):
        owner = owner or self.a
        x = self.game.enter_battlefield(owner, c)
        x.sick = sick
        return x

    def cast(self, c, by=None):
        self.a.pool.clear()
        effs = list(c.spell_effects)
        self.game.stack.append(StackItem(by or self.a, effs, [None] * len(effs), card=c, name=c.name))
        self.game.resolve_top()

    def resolve_trigger(self, perm, event=0, by=None):
        self.a.pool.clear()
        trig = perm.card.triggers[event]
        item = StackItem(by or perm.controller, list(trig.effects), [None] * len(trig.effects),
                         source=perm, name="trigger", kind="trigger")
        self.game.stack.append(item)
        self.game.resolve_top()

    def resolve_ability(self, perm, index=0, by=None):
        self.a.pool.clear()
        act = perm.card.activated[index]
        item = StackItem(by or perm.controller, list(act.effects), [None] * len(act.effects),
                         source=perm, name="ability", kind="ability")
        self.game.stack.append(item)
        self.game.resolve_top()

    def mana(self, p=None):
        return sorted(tuple(sorted(m.card.produces)) for m in (p or self.a).pool)


class Parsing(unittest.TestCase):
    def test_positive_sentences(self):
        cases = {
            "Add {R} for each Goblin on the battlefield.":
                ("add_mana", {"colors": ["R"], "xq": ("cxq", "perms", {"selector": {"subtypes": ["goblin"],
                                                                                      "types_any": ["permanent"]}})}),
            "add {B} for each charge counter on ~.": ("add_mana", {"colors": ["B"], "xq": ("counters", "charge")}),
            "Add {B} for each black creature card in your graveyard.":
                ("add_mana", {"colors": ["B"], "xq": ("cxq", "cards", "your_gy", {"colors": ["B"], "types": ["creature"]})}),
            "Add one mana of any color for each charge counter removed this way.":
                ("add_mana", {"colors": [], "choice": ["W", "U", "B", "R", "G"], "xq": ("this_way", "removed", "charge")}),
            "Add {B} or {G} for each permanent destroyed this way.":
                ("add_mana", {"colors": [], "choice": ["B", "G"], "xq": ("this_way", "destroyed", "permanent")}),
            "Add {R} for each card in your hand.":
                ("add_mana", {"colors": ["R"], "xq": ("cxq", "cards", "your_hand", {})}),
        }
        for text, (kind, data) in cases.items():
            c = spell(text)
            self.assertEqual(len(c.spell_effects), 1, text)
            e = c.spell_effects[0]
            self.assertEqual(e.kind, kind, text)
            self.assertEqual(e.data, data, text)

    def test_activated_ability_sentence(self):
        c = card("Test Crypt", types="Land — Swamp", text="{T}: Add {B}.\n{2}, {T}: Add {B} for each black creature "
                                                          "card in your graveyard.")
        self.assertEqual(c.unsupported, [])
        act = c.activated[0]
        self.assertEqual(act.cost, {"generic": 2})
        self.assertEqual(act.extra_costs, {"tap": True})
        self.assertEqual([e.kind for e in act.effects], ["add_mana"])
        self.assertEqual(act.effects[0].data["xq"], ("cxq", "cards", "your_gy", {"colors": ["B"], "types": ["creature"]}))

    def test_refusals_stay_visible(self):
        """Quantities with no fixed referent (or not this family's verbs) must not match."""
        for text in ("Add {R} for each card in target opponent's hand.",
                     "Add {C} for each {S} spent to cast this spell.",
                     "Add {R} for each card revealed this way.",
                     "Add {R} for each card discarded this way.",
                     "Add {R} for each card named Rite of Flame in each graveyard.",
                     "Add {R} for each 1 life your opponents have lost this turn.",
                     "Add {R} for each creature that died this way."):
            c = card("Test Spell", "{R}", "Instant", text)
            self.assertEqual(len(c.unsupported), 1, text)      # stays unmatched and visible
            self.assertIn("for each", c.unsupported[0])


class BattlefieldCount(Base):
    def test_brightstone_ritual_0_1_many_and_both_players(self):
        ritual = spell("Add {R} for each Goblin on the battlefield.")
        self.cast(ritual)
        self.assertEqual(self.mana(), [])                                    # 0 goblins: no mana
        self.perm(GOBLIN)
        self.cast(ritual)
        self.assertEqual(self.mana(), [("R",)])                              # 1
        self.perm(GOBLIN)
        self.perm(GOBLIN, self.b)                                            # an opponent's Goblin counts too
        self.cast(ritual)
        self.assertEqual(self.mana(), [("R",), ("R",), ("R",)])              # 3

    def test_other_subtypes_do_not_count(self):
        self.perm(BEAR)
        self.perm(BEAR, self.b)
        self.cast(spell("Add {R} for each Goblin on the battlefield."))
        self.assertEqual(self.mana(), [])


class SourceCounters(Base):
    def test_charge_counters_on_the_source_only(self):
        relic = card("Test Relic", "{3}", "Artifact",
                     "At the beginning of your first main phase, add {B} for each charge counter on ~.")
        self.assertEqual(relic.unsupported, [])
        perm = self.perm(relic)
        other = self.perm(card("Test Other", "{3}", "Artifact",
                               "At the beginning of your first main phase, add {B} for each charge counter on ~."))
        other.counters["charge"] = 5
        self.resolve_trigger(perm)
        self.assertEqual(self.mana(), [])                                    # 0 counters on the source
        perm.counters["charge"] = 1
        self.resolve_trigger(perm)
        self.assertEqual(self.mana(), [("B",)])                              # 1
        perm.counters["charge"] = 3
        self.resolve_trigger(perm)
        self.assertEqual(self.mana(), [("B",), ("B",), ("B",)])              # 3 (the other's 5 ignored)

    def test_non_charge_counters_do_not_count(self):
        relic = card("Test Relic", "{3}", "Artifact",
                     "At the beginning of your first main phase, add {B} for each charge counter on ~.")
        perm = self.perm(relic)
        perm.counters["+1/+1"] = 4
        self.resolve_trigger(perm)
        self.assertEqual(self.mana(), [])


class GraveyardCount(Base):
    def test_filtered_graveyard_0_1_many(self):
        land = card("Test Crypt", types="Land — Swamp", text="{T}: Add {B}.\n{2}, {T}: Add {B} for each black creature "
                                                             "card in your graveyard.")
        self.assertEqual(land.unsupported, [])
        perm = self.perm(land)
        self.resolve_ability(perm)
        self.assertEqual(self.mana(), [])                                    # empty graveyard
        self.a.graveyard += [ZOMBIE, ELF, TRINKET]                           # only black creature cards count
        self.resolve_ability(perm)
        self.assertEqual(self.mana(), [("B",)])
        self.a.graveyard += [ZOMBIE, ZOMBIE]
        self.resolve_ability(perm)
        self.assertEqual(self.mana(), [("B",)] * 3)

    def test_spell_version_counts_own_graveyard_only(self):
        self.b.graveyard += [ZOMBIE, ZOMBIE]
        self.a.graveyard += [ZOMBIE]
        self.cast(spell("Add {B} for each black creature card in your graveyard."))
        self.assertEqual(self.mana(), [("B",)])


class ThisWayRemoved(Base):
    def test_removed_this_way_uses_the_resolved_result(self):
        relic = card("Test Relic", "{3}", "Artifact",
                     "At the beginning of your first main phase, remove all charge counters from ~. "
                     "Add one mana of any color for each charge counter removed this way.")
        self.assertEqual(relic.unsupported, [])
        perm = self.perm(relic)
        self.resolve_trigger(perm)
        self.assertEqual(self.mana(), [])                                    # nothing to remove
        perm.counters["charge"] = 4
        self.resolve_trigger(perm)
        mana = self.mana()
        self.assertEqual(len(mana), 4)                                       # 4 removed -> 4 mana
        self.assertEqual(len(set(mana)), 1)                                  # one color, chosen once
        self.assertEqual(perm.counters["charge"], 0)

    def test_cost_removed_counter_counts_too(self):
        battery = card("Test Battery", "{2}", "Artifact",
                       "{T}, Remove a charge counter from ~: Add one mana of any color for each charge counter "
                       "removed this way.")
        self.assertEqual(battery.unsupported, [])
        perm = self.perm(battery)
        perm.counters["charge"] = 2
        self.a.pool.clear()
        self.assertTrue(self.game.activate_ability(self.a, perm, 0))
        self.game.settle()
        self.assertEqual(len(self.mana()), 1)          # one counter removed as the cost -> one mana
        self.assertEqual(perm.counters["charge"], 1)


class ThisWayDestroyed(Base):
    def test_destroyed_this_way_counts_only_what_died(self):
        c = spell("Destroy each nonland permanent with mana value 2 or less. "
                  "Add {B} or {G} for each permanent destroyed this way.", types="Sorcery", cost="{2}{B}")
        self.assertEqual(c.unsupported, [])
        cheap_creature = card("Cheap Beast", "{2}", "Creature — Beast", "", 2, 2, cmc=2)
        pricey = card("Pricey Beast", "{5}", "Creature — Beast", "", 5, 5, cmc=5)
        indestructible = card("Sturdy Beast", "{1}", "Creature — Beast", "Indestructible", 2, 2, cmc=1)
        self.perm(TRINKET)                       # artifact, mv 1: destroyed
        self.perm(cheap_creature)                # mv 2: destroyed
        pricey = self.perm(card("Pricey Beast", "{5}", "Creature — Beast", "", 5, 5, cmc=5))   # mv 5: survives
        sturdy = self.perm(indestructible)      # mv 1 but indestructible: not destroyed
        self.cast(c)
        mana = self.mana()
        self.assertEqual(len(mana), 2)            # 2 destroyed this way, not 3 and not a global count
        self.assertEqual(len(set(mana)), 1)       # one {B} or {G} choice, repeated
        self.assertIn(mana[0], (("B",), ("G",)))
        self.assertTrue(any(x is pricey for x in self.a.battlefield))
        self.assertTrue(any(x is sturdy for x in self.a.battlefield))

    def test_nothing_destroyed_no_mana_even_after_other_deaths(self):
        c = spell("Destroy each nonland permanent with mana value 2 or less. "
                  "Add {B} or {G} for each permanent destroyed this way.", types="Sorcery", cost="{2}{B}")
        self.game.destroy(self.perm(BEAR))       # a global "died this turn" count must not leak in
        self.perm(card("Pricey Beast", "{5}", "Creature — Beast", "", 5, 5, cmc=5))
        self.cast(c)
        self.assertEqual(self.mana(), [])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def test_issue_examples_parse_full(self):
        for name in ("Altar of Shadows", "Black Market", "Brightstone Ritual", "Coalition Relic",
                     "Crypt of Agadeem", "Culling Ritual"):
            c = self.db.get(name)
            self.assertEqual(c.unsupported, [], name)
            self.assertEqual(c.approximations, [], name)

    def test_altar_of_shadows_trigger_makes_black_per_charge_counter(self):
        altar = self.perm(self.db.get("Altar of Shadows"))
        altar.counters["charge"] = 3
        self.resolve_trigger(altar)
        self.assertEqual(self.mana(), [("B",)] * 3)

    def test_crypt_of_agadeem_ability(self):
        crypt = self.perm(self.db.get("Crypt of Agadeem"))
        self.a.graveyard += [ZOMBIE, ELF]
        self.resolve_ability(crypt)
        self.assertEqual(self.mana(), [("B",)])

    def test_coalition_relic_trigger(self):
        relic = self.perm(self.db.get("Coalition Relic"))
        relic.counters["charge"] = 2
        self.resolve_trigger(relic)
        self.assertEqual(len(self.mana()), 2)
        self.assertEqual(relic.counters["charge"], 0)

    def test_culling_ritual_spell(self):
        self.perm(TRINKET)          # artifact, mana value 1: destroyed
        self.perm(BEAR)             # creature, mana value 2: destroyed
        self.perm(card("Pricey Beast", "{5}", "Creature — Beast", "", 5, 5, cmc=5))
        self.cast(self.db.get("Culling Ritual"))
        mana = self.mana()
        self.assertEqual(len(mana), 2)               # two permanents destroyed this way
        self.assertEqual(len(set(mana)), 1)          # one {B} or {G} choice, repeated
        self.assertIn(mana[0], (("B",), ("G",)))

    def test_ai_uses_ritual_only_when_it_makes_mana(self):
        ritual = self.db.get("Brightstone Ritual")
        for _ in range(3):
            self.perm(GOBLIN)
        for _ in range(3):
            self.perm(MOUNTAIN)
        self.a.hand = [ritual, BIG_RED]
        self.assertFalse(self.game.can_cast_now(self.a, BIG_RED))     # no future mana is invented
        self.game.take_turn(self.a)
        self.assertIn("Big Red Thing", [x.card.name for x in self.a.battlefield])

    def test_ai_holds_ritual_that_makes_nothing(self):
        ritual = self.db.get("Brightstone Ritual")
        for _ in range(3):
            self.perm(MOUNTAIN)
        self.a.hand = [ritual, BIG_RED]
        self.game.take_turn(self.a)
        self.assertNotIn("Big Red Thing", [x.card.name for x in self.a.battlefield])
        self.assertIn(ritual, self.a.hand)


if __name__ == "__main__":
    unittest.main()
