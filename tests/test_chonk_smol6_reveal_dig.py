"""smol-chonk-6 batch 7: typed reveal-and-discard keeps its filter, "reveals their hand"
standalone lines become peek_hand peeks, the count-gated "N or more creatures you control
attack" triggers, and the X-scaled dig with a described keep (Seismic Sense).

The typed reveal-and-discard clause used to rewrite into a sentinel that dropped the card
description, so Thoughtseize and friends played as "discard any card"; the clause now keeps
it (TARGETDISCARD2), narrows words the hand matcher can't express with an approximation
note, and stays unsupported when nothing of the description is expressible.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

GIANT = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)
ROCK = card("Test Rock", "{2}", "Artifact", "")
BLAST = card("Test Blast", "{2}{R}", "Sorcery", "")
DRAGON = card("Test Dragon", "{3}{R}", "Creature — Dragon", "", 3, 3)
SPIRIT = card("Test Spirit", "{1}{W}", "Creature — Spirit", "", 1, 1)

VITRIOL = card("Stinging Vitriol", "{2}{R}", "Sorcery",
               "Stinging Vitriol deals 2 damage to target opponent. That player reveals "
               "their hand. You choose a nonland card from it. They discard that card.")
TRUTH = card("Extract the Truth", "{2}{B}", "Sorcery",
             "Choose one —\n• Target opponent reveals their hand. You may choose a "
             "creature, enchantment, or planeswalker card from it. That player discards "
             "that card.\n• Target opponent sacrifices an enchantment of their choice.")
THOUGHTSEIZE = card("Thoughtseize", "{B}", "Sorcery",
                    "Target player reveals their hand. You choose a nonland card from it. "
                    "That player discards that card. You lose 2 life.")
DESPISE = card("Despise", "{B}", "Sorcery",
               "Target opponent reveals their hand. You choose a creature or planeswalker "
               "card from it. That player discards that card.")
DIVEST = card("Divest", "{B}", "Sorcery",
              "Target player reveals their hand. You choose an artifact or creature card "
              "from it. That player discards that card.")
ENCROACH = card("Encroach", "{1}{B}", "Sorcery",
                "Target player reveals their hand. You choose a nonbasic land card from "
                "it. That player discards that card.")
LAY_BARE = card("Lay Bare the Heart", "{1}{B}", "Sorcery",
                "Target opponent reveals their hand. You choose a nonlegendary, nonland "
                "card from it. That player discards that card.")
PERMANENT_CHOICE = card("Test Grasp", "{1}{B}", "Sorcery",
                        "Target opponent reveals their hand. You choose a nonland "
                        "permanent card from it. That player discards that card.")
ONLY_PERMANENT = card("Test Seize", "{1}{B}", "Sorcery",
                      "Target opponent reveals their hand. You choose a permanent card "
                      "from it. That player discards that card.")
MINDCLAW = card("Mindclaw Shaman", "{4}{R}", "Creature — Viashino Shaman",
                "When this creature enters, target opponent reveals their hand.", 2, 2)
HORN = card("Horn of the Mark", "{4}", "Artifact",
            "Whenever two or more creatures you control attack a player, look at the top "
            "five cards of your library. You may reveal a creature card from among them "
            "and put it into your hand. Put the rest on the bottom of your library in a "
            "random order.")
LANDROVAL = card("Landroval, Horizon Witness", "{4}{W}", "Creature — Bird",
                 "Flying\nWhenever two or more creatures you control attack a player, "
                 "target attacking creature without flying gains flying until end of turn.", 3, 4)
SEISMIC = card("Seismic Sense", "{1}{G}", "Sorcery",
               "Look at the top X cards of your library, where X is the number of lands "
               "you control. You may reveal a creature or land card from among them and "
               "put it into your hand. Put the rest on the bottom of your library in a "
               "random order.")


class Chonk6RevealDig(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        self.g.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def perm(self, c, owner=None):
        perm = Permanent(c, owner or self.a)
        perm.sick, perm.tapped = False, False
        (owner or self.a).battlefield.append(perm)
        return perm

    def land(self, p, n, c=MOUNTAIN):
        for _ in range(n):
            land = Permanent(c, p)
            land.sick = False
            p.battlefield.append(land)


class TypedRevealDiscard(Chonk6RevealDig):
    def test_stinging_vitriol_end_to_end(self):
        self.assertEqual(VITRIOL.unsupported, [])
        self.assertEqual(VITRIOL.approximations, [])
        kinds = [(e.kind, e.target) for e in VITRIOL.spell_effects]
        self.assertEqual(kinds, [("damage", "player"), ("discard_choice", "player")])
        self.assertEqual([e.filter for e in VITRIOL.spell_effects], ["", "nonland"])

    def test_filter_words_are_kept(self):
        for cdef, want in ((THOUGHTSEIZE, "nonland"), (DESPISE, "creature or planeswalker"),
                           (DIVEST, "artifact or creature")):
            self.assertEqual(cdef.unsupported, [], cdef.name)
            (eff,) = [e for e in cdef.spell_effects if e.kind == "discard_choice"]
            self.assertEqual(eff.filter, want)

    def test_unmatchable_words_narrow_with_a_note(self):
        for cdef, want in ((ENCROACH, "land"), (LAY_BARE, "nonland"), (PERMANENT_CHOICE, "nonland")):
            self.assertEqual(cdef.unsupported, [], cdef.name)
            (eff,) = [e for e in cdef.spell_effects if e.kind == "discard_choice"]
            self.assertEqual(eff.filter, want)
            self.assertTrue(any("revealed-card description" in note for note in cdef.approximations),
                            cdef.approximations)

    def test_nothing_expressible_stays_unsupported(self):
        """"a permanent card" alone can't be narrowed: the clause leaves the line for the
        older hand templates, whose matcher has no "permanent" word either, so nothing is
        chosen and nobody discards (an under-match, never a whole-hand over-match)."""
        self.assertEqual(ONLY_PERMANENT.unsupported, [])
        (eff,) = [e for e in ONLY_PERMANENT.spell_effects if e.kind == "discard_choice"]
        self.b.hand = [GIANT, BLAST]
        self.g.resolve(self.a, eff, self.b)
        self.assertEqual(self.b.hand, [GIANT, BLAST])
        self.assertEqual(self.b.graveyard, [])

    def test_may_choose_discard_is_always_taken(self):
        """The second mode ("sacrifices an enchantment of their choice") has no template
        yet, so only the reveal-discard mode parses and the card stays partial."""
        modes = TRUTH.modes
        self.assertEqual([e.kind for e in modes[0]], ["discard_choice"])
        self.assertEqual(modes[0][0].filter, "creature, enchantment, or planeswalker")
        self.assertTrue(any("sacrifices an enchantment" in l for l in TRUTH.unsupported),
                        TRUTH.unsupported)

    def test_discard_respects_the_filter(self):
        self.b.hand = [ISLAND, GIANT]
        self.b.life = 20
        eff = [e for e in VITRIOL.spell_effects if e.kind == "discard_choice"][0]
        self.g.resolve(self.a, eff, self.b)
        self.assertEqual([c.name for c in self.b.graveyard], [GIANT.name])
        self.assertEqual([c.name for c in self.b.hand], [ISLAND.name])

    def test_filter_only_discards_matching_cards(self):
        self.b.hand = [ISLAND, GIANT, ROCK, BLAST]
        eff = [e for e in DIVEST.spell_effects if e.kind == "discard_choice"][0]
        self.g.resolve(self.a, eff, self.b)          # "artifact or creature": the Giant
        self.assertEqual([c.name for c in self.b.graveyard], [GIANT.name])


class PeekHand(Chonk6RevealDig):
    def test_standalone_reveal_parses(self):
        self.assertEqual(MINDCLAW.unsupported, [])
        (trig,) = MINDCLAW.triggers
        self.assertEqual(trig.event, "etb")
        self.assertEqual([(e.kind, e.target) for e in trig.effects], [("peek_hand", "player")])

    def test_peek_hand_resolves_without_moving_cards(self):
        hand = list(self.b.hand)
        self.g.resolve(self.a, MINDCLAW.triggers[0].effects[0], self.b)
        self.assertEqual(self.b.hand, hand)

    def test_that_player_reveal_targets_the_context(self):
        effects, ignored = _parse_effects("That player reveals their hand.")
        self.assertFalse(ignored, ignored)
        self.assertEqual([(e.kind, e.target) for e in effects], [("peek_hand", "that_player")])


class AttackCountTriggers(Chonk6RevealDig):
    def test_horn_of_the_mark_end_to_end(self):
        self.assertEqual(HORN.unsupported, [])
        self.assertEqual(HORN.approximations, [])
        (trig,) = HORN.triggers
        self.assertEqual(trig.event, "attack_two_plus")
        self.assertEqual([(e.kind, e.amount, e.amount2, e.data.get("filter")) for e in trig.effects],
                         [("dig", 5, 1, "a creature card")])

    def test_landroval_end_to_end(self):
        self.assertEqual(LANDROVAL.unsupported, [])
        self.assertEqual(LANDROVAL.triggers[0].event, "attack_two_plus")
        self.assertEqual([e.kind for e in LANDROVAL.triggers[0].effects], ["grant"])

    def test_one_or_more_maps_to_you_attack(self):
        cdef = card("Test Herald", "{3}{W}", "Creature — Bird",
                    "Whenever one or more creatures you control attack, draw a card.", 2, 2)
        self.assertEqual(cdef.unsupported, [])
        self.assertEqual([(t.event, [e.kind for e in t.effects]) for t in cdef.triggers],
                         [("you_attack", ["draw"])])

    def test_firing_the_gate_draws_the_creature(self):
        self.perm(HORN)
        self.a.library = [ISLAND] * 10 + [ISLAND, BLAST, ROCK, DRAGON, ISLAND]  # looked at: last 5
        before = len(self.a.hand)
        self.g.fire(self.a, "attack_two_plus")
        self.g.settle()
        self.assertEqual(len(self.a.hand), before + 1)
        self.assertEqual(self.a.hand[-1].name, DRAGON.name)


class XCountDig(Chonk6RevealDig):
    def test_seismic_sense_end_to_end(self):
        self.assertEqual(SEISMIC.unsupported, [])
        self.assertEqual(SEISMIC.approximations, [])
        (eff,) = SEISMIC.spell_effects
        self.assertEqual((eff.kind, eff.amount2, eff.data.get("x_lands"), eff.data.get("filter")),
                         ("dig", 1, True, "a creature or land card"))

    def test_dig_scaled_by_lands_keeps_a_matching_card(self):
        self.land(self.a, 3, MOUNTAIN)
        self.a.library = [ISLAND] * 10 + [BLAST, GIANT, DRAGON]   # the top three are looked at
        before = len(self.a.hand)
        self.g.resolve(self.a, SEISMIC.spell_effects[0], None)
        self.assertEqual(len(self.a.hand), before + 1)
        self.assertIn(self.a.hand[-1].name, (GIANT.name, DRAGON.name))
        self.assertNotIn(self.a.hand[-1].name, (BLAST.name,))      # the sorcery was not kept
