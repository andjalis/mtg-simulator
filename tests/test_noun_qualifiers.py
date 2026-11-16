"""#403: object qualifiers the shared noun-phrase reader knows (mtgsim.cx_noun).

Slice 1: "with mana value X", "with power / toughness X or less", where X is the X paid for the spell or ability."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.policy import choose_ability
from mtgsim.engine.state import Permanent
from mtgsim.permanent_templates import selector

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SWAMP, card

ROCK2 = card("Test Rock", "{2}", "Artifact", "")
ROCK5 = card("Test Monolith", "{5}", "Artifact", "")
FOUR = card("Test Four", "{3}{G}", "Creature — Beast", "", 4, 4)
BIG = card("Test Big", "{5}{G}", "Creature — Beast", "", 6, 6)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner, n=1):
        out = []
        for _ in range(n):
            x = Permanent(c, owner)
            x.sick = False
            owner.battlefield.append(x)
            out.append(x)
        return out[0]

    def cast(self, c, targets=None):
        self.a.hand.append(c)
        return self.g.cast(self.a, c, targets)

    def untapped_lands(self):
        return sum(1 for x in self.a.battlefield if x.card.is_land and not x.tapped)


class Reading(unittest.TestCase):
    def test_x_qualifiers(self):
        self.assertEqual(selector("nonland permanent with mana value X"),
                         {"traits": ["nonland"], "types_all": ["permanent"], "stat_x": ["mana value", "=="]})
        self.assertEqual(selector("creatures with power X or less", plural=True)["stat_x"], ["power", "<="])
        self.assertEqual(selector("artifact or enchantment with mana value X")["stat_x"], ["mana value", "=="])
        self.assertEqual(selector("creature with mana value 3")["stat"], ["mana value", "==", 3])    # unchanged

    def test_refusals(self):
        self.assertIsNone(selector("creature with mana value X or greater"))
        # X that no mana pays: a spell without {X}, a trigger, an ability without {X}
        for cost, types, text in (("{1}{B}", "Instant", "Destroy target creature with mana value X."),
                                  ("{2}", "Artifact", "{T}: Destroy target creature with mana value X."),
                                  ("{2}{B}", "Creature — Horror",
                                   "When this creature enters, destroy target creature with power X or less.")):
            with self.subTest(text=text):
                c = card("Test", cost, types, text, 1 if "Creature" in types else None,
                         1 if "Creature" in types else None)
                self.assertTrue(any("mana value / power / toughness X" in u for u in c.unsupported), c.unsupported)

    def test_spell_with_x_reads(self):
        c = card("Test", "{X}{B}", "Sorcery", "Destroy target creature with mana value X.")
        self.assertEqual(c.unsupported, [])
        c = card("Test", "{2}", "Artifact", "{X}, {T}: Destroy target artifact with mana value X.")
        self.assertEqual(c.unsupported, [])


class ListQualifiers(unittest.TestCase):
    """A qualifier after a list "all A, B, and C <qualifier>" covers the whole list, not only its last item."""
    def group(self, text):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [])
        self.assertEqual(len(effects), 1, effects)
        return effects[0].data["group"]["selector"]

    def test_controller_and_stat_cover_every_item(self):
        self.assertEqual(self.group("Destroy all artifacts and enchantments your opponents control."),
                         {"controller": "opp", "types_any": ["artifact", "enchantment"]})
        spec = self.group("Exile all artifacts and creatures with mana value 3 or less.")
        self.assertEqual(spec["stat"], ["mana value", "<=", 3])
        self.assertEqual(spec["types_any"], ["artifact", "creature"])

    def test_unread_list_qualifier_stays_unread(self):
        text = "Destroy all artifacts and creatures with flanking and frobbing."
        self.assertEqual(_parse_effects(text)[1], [text])


class Spells(Base):
    def test_equal_x_is_paid_as_the_targets_value(self):
        rock, monolith = self.perm(ROCK2, self.b), self.perm(ROCK5, self.b)
        self.perm(ISLAND, self.a, 5)
        repeal = card("Test Repeal", "{X}{U}", "Instant",
                      "Return target nonland permanent with mana value X to its owner's hand. Draw a card.")
        with self.g.targeting(repeal):
            legal = self.g.legal_targets(self.a, repeal.spell_effects[0])
        self.assertIn(rock, legal)
        self.assertNotIn(monolith, legal)       # X = 5 would need six mana with {U}
        self.assertTrue(self.cast(repeal, [rock, None]))
        self.assertNotIn(rock, self.b.battlefield)
        self.assertEqual(self.untapped_lands(), 2)   # X = 2 plus {U}: three of five Islands

    def test_target_must_still_match_the_paid_x(self):
        bear = self.perm(BEAR, self.b)
        self.perm(SWAMP, self.a, 3)
        spell = card("Test Kill", "{X}{B}", "Sorcery", "Destroy target creature with mana value X.")
        self.assertTrue(self.cast(spell, [bear]))
        self.assertNotIn(bear, self.b.battlefield)

    def test_delve_pays_only_the_fixed_x(self):
        bear = self.perm(BEAR, self.b)
        self.perm(SWAMP, self.a, 3)
        self.a.graveyard = [ISLAND] * 5
        spell = card("Test Delve Kill", "{X}{B}", "Sorcery", "Delve\nDestroy target creature with mana value X.")
        self.assertTrue(self.cast(spell, [bear]))
        self.assertNotIn(bear, self.b.battlefield)
        paid = (3 - self.untapped_lands()) + len(self.a.exile)      # lands tapped + cards delved
        self.assertEqual(paid, 3)            # X = 2 plus {B}, not the most delve could pay

    def test_x_or_less_group_uses_the_paid_x(self):
        bears = [self.perm(BEAR, self.b) for _ in range(2)]
        mine = self.perm(BEAR, self.a)
        big = self.perm(BIG, self.b)
        self.perm(SWAMP, self.a, 3)
        march = card("Test March", "{X}{B}{B}{B}", "Sorcery", "Destroy all creatures with mana value X or less.")
        self.assertTrue(self.cast(march))      # all five Swamps' worth? only three: X = 0
        self.assertTrue(all(b in self.b.battlefield for b in bears))
        self.perm(SWAMP, self.a, 2)
        for x in self.a.battlefield:
            x.tapped = False
        self.assertTrue(self.cast(march))      # X = 2
        self.assertFalse(any(b in self.b.battlefield for b in bears))
        self.assertNotIn(mine, self.a.battlefield)
        self.assertIn(big, self.b.battlefield)

    def test_heuristic_ai_casts_x_or_less_sweeper_at_their_creatures(self):
        bears = [self.perm(BEAR, self.b) for _ in range(2)]
        big = self.perm(BIG, self.b)
        self.perm(SWAMP, self.a, 5)
        march = card("Test March", "{X}{B}{B}{B}", "Sorcery", "Destroy all creatures with mana value X or less.")
        self.a.hand = [march]
        self.a.ai.main_phase(self.g, self.a)
        self.assertNotIn(march, self.a.hand)
        self.assertFalse(any(b in self.b.battlefield for b in bears))
        self.assertIn(big, self.b.battlefield)

    def test_heuristic_ai_aims_equal_x_removal_at_the_opponent(self):
        theirs = self.perm(BEAR, self.b)
        self.perm(BEAR, self.a)
        self.perm(SWAMP, self.a, 4)
        spell = card("Test Kill", "{X}{B}", "Sorcery", "Destroy target creature with mana value X.")
        plan = self.a.ai.plan_spell(self.g, self.a, spell, precombat=True)
        self.assertIsNotNone(plan)
        self.assertIs(plan[1][0], theirs)


class Abilities(Base):
    def elemental(self):
        return card("Test Elemental", "{B}{R}", "Creature — Elemental",
                    "{X}{X}{1}: Destroy target artifact or creature with mana value X.", 4, 4)

    def test_ai_chooses_the_x_of_the_best_target(self):
        src = self.perm(self.elemental(), self.a)
        bear, four = self.perm(BEAR, self.b), self.perm(FOUR, self.b)
        self.perm(MOUNTAIN, self.a, 9)
        self.assertEqual(self.g.ability_x(self.a, src, src.activated[0]), 4)
        self.assertEqual(choose_ability(self.g, self.a, instant=True), ("activate", src, "ability:0"))
        self.assertTrue(self.g.activate_ability(self.a, src, 0))
        self.assertNotIn(four, self.b.battlefield)
        self.assertIn(bear, self.b.battlefield)
        self.assertEqual(self.untapped_lands(), 0)      # {X}{X}{1} with X = 4

    def test_resolution_rechecks_the_target_against_x(self):
        src = self.perm(self.elemental(), self.a)
        bear = self.perm(BEAR, self.b)
        self.perm(MOUNTAIN, self.a, 5)
        self.assertTrue(self.g.activate_ability(self.a, src, 0, [bear], x=2))
        self.assertNotIn(bear, self.b.battlefield)
        bear2 = self.perm(BEAR, self.b)
        for x in self.a.battlefield:
            x.tapped = False
        self.assertFalse(self.g.activate_ability(self.a, src, 0, [bear2], x=1))   # mana value 2 isn't X = 1
        self.assertIn(bear2, self.b.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_newly_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB()
        for name in ("Repeal", "Molder", "Detonate", "Disembowel", "Meltdown", "Forced March", "Pernicious Deed",
                     "Deepfire Elemental", "Gorilla Shaman", "Hearth Kami", "Gang Up", "Finale of Eternity",
                     "Blue Sun's Twilight", "Dauntless Dismantler"):
            with self.subTest(name=name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")

    def test_pernicious_deed_reads_one_union_with_x(self):
        from mtgsim.carddb import CardDB
        deed = CardDB().get("Pernicious Deed")
        self.assertEqual(len(deed.activated[0].effects), 1)      # one group: the qualifier covers the whole list
        spec = deed.activated[0].effects[0].data["group"]["selector"]
        self.assertEqual(spec["types_any"], ["artifact", "creature", "enchantment"])
        self.assertEqual(spec["stat_x"], ["mana value", "<="])


class Slice2(Base):
    """non<color>, nonattacking / nonblocking, "that has a <kind> counter on it" (#403 slice 2)."""
    BLACK = card("Test Shade", "{B}", "Creature — Shade", "", 2, 2)

    def test_readings(self):
        self.assertEqual(selector("nonblack creature"), {"not_colors": ["B"], "types_all": ["creature"]})
        self.assertEqual(selector("nonattacking creature")["traits"], ["nonattacking"])
        self.assertEqual(selector("creature that has a -1/-1 counter on it")["counter"], ["-1/-1", True])
        self.assertEqual(selector("creatures that have +1/+1 counters on them", plural=True)["counter"], ["+1/+1", True])
        for text in ("creature that has a +1/+1 counter", "nonpurple creature", "creature that had a counter on it"):
            with self.subTest(text=text):
                self.assertIsNone(selector(text))

    def test_nonblack_excludes_black(self):
        shade, bear = self.perm(self.BLACK, self.b), self.perm(BEAR, self.b)
        eff = card("Test", "{1}{B}", "Instant", "Destroy target nonblack creature.").spell_effects[0]
        with self.g.targeting(None):
            legal = self.g.legal_targets(self.a, eff)
        self.assertIn(bear, legal)
        self.assertNotIn(shade, legal)

    def test_nonattacking_excludes_attackers(self):
        x, y = self.perm(BEAR, self.a), self.perm(BEAR, self.a)
        self.g.attackers = [x]
        eff = card("Test", "{W}", "Instant", "Untap target nonattacking creature.").spell_effects[0]
        legal = self.g.legal_targets(self.a, eff)
        self.assertIn(y, legal)
        self.assertNotIn(x, legal)

    def test_counter_qualifier_resolves(self):
        marked = self.perm(BEAR, self.b)
        marked.counters["-1/-1"] = 1
        plain = self.perm(BEAR, self.b)
        spell = card("Test", "{B}", "Sorcery", "Destroy target creature that has a -1/-1 counter on it.")
        eff = spell.spell_effects[0]
        legal = self.g.legal_targets(self.a, eff)
        self.assertEqual(legal, [marked])
        self.perm(SWAMP, self.a)
        self.assertTrue(self.cast(spell, [marked]))
        self.assertNotIn(marked, self.b.battlefield)
        self.assertIn(plain, self.b.battlefield)

    def test_heuristic_ai_aims_nonblack_removal_at_the_opponent(self):
        theirs = self.perm(BEAR, self.b)
        self.perm(self.BLACK, self.b)
        self.perm(BEAR, self.a)
        self.perm(SWAMP, self.a, 2)
        spell = card("Test", "{1}{B}", "Sorcery", "Destroy target nonblack creature.")
        plan = self.a.ai.plan_spell(self.g, self.a, spell, precombat=True)
        self.assertIsNotNone(plan)
        self.assertIs(plan[1][0], theirs)

    def test_heuristic_ai_casts_the_nonblack_counter_sweep(self):
        bears = [self.perm(BEAR, self.b) for _ in range(2)]
        shade = self.perm(self.BLACK, self.a)
        self.perm(SWAMP, self.a, 3)
        spell = card("Test Banshee", "{2}{B}", "Sorcery", "Put a -1/-1 counter on each nonblack creature.")
        self.assertEqual(spell.unsupported, [])
        self.cast(spell)
        self.assertTrue(all(b.counters.get("-1/-1") == 1 for b in bears))
        self.assertFalse(shade.counters.get("-1/-1"))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCardsSlice2(unittest.TestCase):
    def test_newly_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB()
        for name in ("Alarum", "Banewhip Punisher", "Cradle to Grave", "Midnight Banshee", "Plaguebearer",
                     "Ruthless Instincts", "Throat Slitter", "Triad of Fates", "Hunter's Ambush"):
            with self.subTest(name=name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


if __name__ == "__main__":
    unittest.main()
