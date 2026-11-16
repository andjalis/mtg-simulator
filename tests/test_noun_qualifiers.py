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
        self.assertTrue(self.cast(spell))
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


class Slice3(Base):
    """Relational stats: "with power less than ~'s power", "... than the number of ...", "... than its base power"."""
    BIG = card("Test Big", "{5}{G}", "Creature — Beast", "", 6, 6)

    def test_readings(self):
        self.assertEqual(selector("creature with power less than ~'s power")["stat_rel"],
                         ["power", "<", False, ("q", ("stat", "self", "power"))])
        spec = selector("creature with power less than or equal to the number of creatures you control")
        self.assertNotIn("controller", spec)          # "you control" belongs to the quantity
        self.assertEqual(spec["stat_rel"][:3], ["power", "<", True])
        self.assertEqual(selector("creatures you control with power greater than its base power", plural=True),
                         {"stat_rel": ["power", ">", False, ("base",)], "controller": "mine", "types_all": ["creature"]})

    def test_refusals(self):
        for text in ("creatures with power greater than target creature's power",       # another target's
                     "artifact with mana value less than or equal to the number of rust counters on it",  # "it"
                     "creature with power less than that creature's power",
                     "creature with power less than the frobs you control"):
            with self.subTest(text=text):
                self.assertIsNone(selector(text, plural=text.startswith("creatures")))

    def test_source_power_bound(self):
        psycho = self.perm(card("Test Psycho", "{1}{B}{B}", "Creature — Zombie",
                                "{B}, {T}: Destroy target creature with power less than ~'s power.", 3, 3), self.a)
        bear, big = self.perm(BEAR, self.b), self.perm(self.BIG, self.b)
        eff = psycho.card.activated[0].effects[0]
        with self.g.targeting(psycho):
            self.assertEqual(self.g.legal_targets(self.a, eff), [bear])
        self.perm(SWAMP, self.a)
        self.assertTrue(self.g.activate_ability(self.a, psycho, 0, [bear]))
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(big, self.b.battlefield)

    def test_quantity_is_counted_for_the_controller(self):
        shackles = self.perm(card("Test Shackles", "{3}", "Artifact",
                                  "{2}, {T}: Gain control of target creature with power less than or equal to the "
                                  "number of Islands you control for as long as ~ remains tapped."), self.a)
        bear = self.perm(BEAR, self.b)
        self.perm(self.BIG, self.b)
        self.perm(ISLAND, self.b, 6)          # the opponent's Islands don't count
        self.perm(ISLAND, self.a, 2)
        eff = shackles.card.activated[0].effects[0]
        with self.g.targeting(shackles):
            self.assertEqual(self.g.legal_targets(self.a, eff), [bear])

    def test_static_bound_follows_the_hand(self):
        self.a.hand = [ISLAND] * 2
        self.g.enter_battlefield(self.a, card("Test Bridge", "{3}", "Artifact",
                                              "Creatures with power greater than the number of cards in your hand "
                                              "can't attack."))
        bear, big = self.g.enter_battlefield(self.b, BEAR), self.g.enter_battlefield(self.b, self.BIG)
        bear.sick = big.sick = False
        self.g.settle()
        self.assertTrue(bear.can_attack())
        self.assertFalse(big.can_attack())
        self.a.hand = [ISLAND] * 6
        self.g.settle()
        self.assertTrue(big.can_attack())

    def test_heuristic_ai_aims_the_source_bound_removal_at_the_opponent(self):
        psycho = self.perm(card("Test Psycho", "{1}{B}{B}", "Creature — Zombie",
                                "{B}, {T}: Destroy target creature with power less than ~'s power.", 3, 3), self.a)
        theirs = self.perm(BEAR, self.b)
        self.perm(BEAR, self.a)
        self.perm(SWAMP, self.a)
        self.assertEqual(choose_ability(self.g, self.a, instant=True), ("activate", psycho, "ability:0"))
        self.assertTrue(self.g.activate_ability(self.a, psycho, 0))
        self.assertNotIn(theirs, self.b.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCardsSlice3(unittest.TestCase):
    def test_newly_full_and_refused(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB()
        for name in ("Unliving Psychopath", "Vedalken Shackles", "Ensnaring Bridge", "Beguiler of Wills",
                     "Champion of Lambholt", "Lena, Selfless Champion", "Legacy's Allure", "Dominating Vampire"):
            with self.subTest(name=name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")
        self.assertEqual(card_coverage(db.get("Corrosion")).status, "partial")


class Slice4(Base):
    """"that was dealt damage this turn", "that dealt damage [to you] this turn": a per-turn damage record."""
    def setUp(self):
        super().setUp()
        self.hitter, self.quiet = self.perm(BEAR, self.b), self.perm(BEAR, self.b)
        self.hurt = self.perm(BEAR, self.a)
        self.g.deal_damage(self.a, 2, self.b, source=self.hitter)       # combat-free damage to the player
        self.g.deal_damage(self.hurt, 1, self.b, source=self.quiet)     # and to a creature

    def legal(self, text):
        eff = card("Test", "{W}", "Instant", text).spell_effects[0]
        return self.g.legal_targets(self.a, eff)

    def test_readings_and_refusals(self):
        self.assertEqual(selector("creature that dealt damage to you this turn")["damage_turn"], "dealt_you")
        self.assertEqual(selector("creatures that were dealt damage this turn", plural=True)["damage_turn"], "was_dealt")
        self.assertIsNone(selector("creature that was dealt damage to you this turn"))
        self.assertIsNone(selector("creature that dealt combat damage this turn"))

    def test_who_dealt_and_who_was_dealt(self):
        self.assertEqual(self.legal("Exile target creature that dealt damage to you this turn."), [self.hitter])
        self.assertEqual(set(self.legal("Destroy target creature that dealt damage this turn.")),
                         {self.hitter, self.quiet})
        self.assertEqual(self.legal("Destroy target creature that was dealt damage this turn."), [self.hurt])

    def test_the_record_is_for_this_turn_only(self):
        self.g.turn += 1
        self.hurt.damage = 0            # cleanup removed the marked damage
        self.assertEqual(self.legal("Destroy target creature that dealt damage this turn."), [])
        self.assertEqual(self.legal("Destroy target creature that was dealt damage this turn."), [])

    def test_group_resolves(self):
        spell = card("Test Peace", "{2}", "Instant", "Return each creature that dealt damage this turn to its "
                     "owner's hand.")
        self.assertEqual(spell.unsupported, [])
        self.perm(ISLAND, self.a, 2)
        self.assertTrue(self.cast(spell))
        self.assertNotIn(self.hitter, self.b.battlefield)
        self.assertNotIn(self.quiet, self.b.battlefield)
        self.assertIn(self.hurt, self.a.battlefield)

    def test_heuristic_ai_aims_at_the_attacker_that_hit_it(self):
        self.perm(SWAMP, self.a, 2)
        spell = card("Test Arrow", "{1}{B}", "Sorcery", "Destroy target creature that dealt damage this turn.")
        plan = self.a.ai.plan_spell(self.g, self.a, spell, precombat=True)
        self.assertIsNotNone(plan)
        self.assertIn(plan[1][0], (self.hitter, self.quiet))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCardsSlice4(unittest.TestCase):
    def test_newly_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB()
        for name in ("Avenging Arrow", "Reciprocate", "Giltspire Avenger", "Spear of Heliod", "Jarl of the Forsaken",
                     "Vraska's Finisher", "Death-Rattle Oni", "Retaliate", "Restore the Peace"):
            with self.subTest(name=name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


if __name__ == "__main__":
    unittest.main()
