"""Targeted graveyard hate ("exile target card from a graveyard", "up to N ... from a single graveyard",
"exile target player's graveyard") and "with different names" returns: targets chosen on cast/activation/trigger,
rechecked on resolution without substituting another card. Uses real cards from the offline card database."""
import random
import unittest

from mtgsim import carddb, graveyards
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, GraveyardTarget, Permanent, Player, default_choose_target

from tests.test_templates import ISLAND


class GraveyardHateTargets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        path = os.path.join(os.path.dirname(carddb.__file__), "data", "cards.sqlite3")
        if not os.path.exists(path):
            raise unittest.SkipTest("card database not built")
        db = carddb.CardDB(offline=True)
        for attr, name in (("cremate", "Cremate"), ("purge", "Coffin Purge"), ("decay", "Rapid Decay"),
                           ("harpy", "Scavenging Harpy"), ("mummy", "Disposal Mummy"),
                           ("angel", "Angel of Finality"), ("scavenger", "Diregraf Scavenger"),
                           ("sinister", "Behold the Sinister Six!"), ("pit", "Pit of Offerings"),
                           ("bears", "Grizzly Bears"), ("elves", "Llanowar Elves"), ("serra", "Serra Angel"),
                           ("swamp", "Swamp"), ("plains", "Plains"), ("shock", "Shock")):
            setattr(cls, attr, db.get(name))
        cls.db = db

    def setUp(self):
        self.a = Player("a", [ISLAND] * 20, HeuristicAI())
        self.b = Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for pl in (self.a, self.b):
            pl.library = [ISLAND] * 20
        self.seen = []

    def lands(self, land, n):
        for _ in range(n):
            self.a.battlefield.append(Permanent(land, self.a))

    def respond_once(self, response, when):
        def respond(game, me):
            if game.stack and not self.seen and when(game.stack[-1]):
                self.seen.append(list(game.stack[-1].targets))
                response()
            return None
        self.b.ai.respond = respond

    def fizzled(self):
        return any("fizzles" in line for line in self.game.events)

    def effects(self, card):
        return (card.spell_effects + [e for t in card.triggers for e in t.effects]
                + [e for a in card.activated for e in a.effects])

    # ------------------------------------------------------------------ templates
    def test_templates_are_supported_and_bound_to_graveyard_cards(self):
        for card in (self.cremate, self.purge, self.decay, self.harpy, self.mummy, self.angel,
                     self.scavenger, self.sinister):
            with self.subTest(card=card.name):
                self.assertEqual(card.unsupported, [])
                self.assertTrue(any(e.target in ("graveyard_card", "player") for e in self.effects(card)))
        self.assertEqual(self.effects(self.angel)[0].target, "player")
        self.assertEqual([(e.kind, e.data["zone"], e.data["single"], e.data["upto"])
                          for e in (self.effects(c)[0] for c in (self.decay, self.harpy, self.cremate))],
                         [("gy_exile", "any", True, True), ("gy_exile", "opp", False, False),
                          ("gy_exile", "any", False, False)])
        self.assertTrue(self.effects(self.sinister)[0].data["distinct"])

    def test_unsupported_wording_stays_visible(self):
        rats = self.db.get("Rats' Feast")
        self.assertIn("Exile X target cards from a single graveyard.", rats.unsupported)
        nightmare = self.db.get("Elspeth's Nightmare")
        self.assertTrue(any("target opponent's graveyard" in u for u in nightmare.unsupported))
        canoptek = self.db.get("Canoptek Scarab Swarm")
        self.assertTrue(any("For each artifact or land card" in u for u in canoptek.unsupported))

    # ------------------------------------------------------------------ cast-time binding
    def test_cast_binds_the_exact_card_and_resolves_it(self):
        self.lands(self.swamp, 1)
        self.a.hand = [self.cremate]
        self.a.graveyard.append(self.elves)
        self.b.graveyard.extend([self.serra, self.bears])
        self.respond_once(lambda: None, lambda item: item.card is self.cremate)
        self.assertTrue(self.game.cast(self.a, self.cremate, [self.bears]))      # not the best card
        self.assertEqual(self.seen[0][0].card, self.bears)
        self.assertEqual((self.b.graveyard, self.b.exile), ([self.serra], [self.bears]))
        self.assertEqual(self.a.graveyard.count(self.elves), 1)

    def test_removed_target_fizzles_and_never_substitutes(self):
        self.lands(self.swamp, 1)
        self.a.hand = [self.cremate]
        self.b.graveyard.extend([self.bears, self.serra])
        self.respond_once(lambda: self.b.exile.append(self.b.graveyard.pop(0)),
                          lambda item: item.card is self.cremate)
        self.assertTrue(self.game.cast(self.a, self.cremate, [self.bears]))
        self.assertTrue(self.fizzled())
        self.assertEqual(self.b.graveyard, [self.serra])

    def test_no_legal_card_means_no_cast_and_no_payment(self):
        self.lands(self.swamp, 1)
        self.a.hand = [self.cremate]
        self.assertFalse(self.game.can_cast_now(self.a, self.cremate))
        self.assertFalse(self.game.cast(self.a, self.cremate))
        self.assertEqual(self.a.hand, [self.cremate])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_explicit_card_not_in_a_graveyard_is_rejected_before_costs(self):
        self.lands(self.swamp, 1)
        self.a.hand = [self.cremate]
        self.b.graveyard.append(self.serra)
        self.assertFalse(self.game.cast(self.a, self.cremate, [self.bears]))
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    # ------------------------------------------------------------------ zones, up to, single graveyard
    def test_opponent_only_hate_rejects_your_own_graveyard(self):
        effect = self.effects(self.mummy)[0]
        self.a.graveyard.append(self.serra)
        self.b.graveyard.append(self.bears)
        mine, theirs = (GraveyardTarget(pl, pl.graveyard[0], pl.graveyard.entries[0]) for pl in (self.a, self.b))
        self.assertFalse(graveyards.legal(self.a, effect, mine))
        self.assertTrue(graveyards.legal(self.a, effect, theirs))
        self.assertEqual([t.card for t in graveyards.candidates(self.game, self.a, effect)], [self.bears])

    def test_enters_trigger_binds_and_exiles_the_opponents_card(self):
        self.lands(self.plains, 3)
        self.a.hand = [self.mummy]
        self.a.graveyard.append(self.serra)
        self.b.graveyard.extend([self.bears, self.elves])
        self.assertTrue(self.game.cast(self.a, self.mummy))
        self.assertEqual(self.a.graveyard, [self.serra])
        self.assertEqual(len(self.b.exile), 1)
        self.assertEqual(len(self.b.graveyard), 1)

    def test_up_to_may_choose_zero_and_ai_never_exiles_its_own_card(self):
        effect = self.effects(self.decay)[0]
        self.a.graveyard.append(self.serra)
        self.assertEqual(graveyards.choose(self.game, self.a, effect), ())
        self.lands(self.swamp, 2)
        self.a.hand = [self.decay]
        self.b.graveyard.append(self.bears)
        self.assertTrue(self.game.cast(self.a, self.decay, [()]))                # explicit zero targets
        self.assertEqual((self.b.graveyard, self.a.graveyard.count(self.serra)), ([self.bears], 1))

    def test_single_graveyard_rejects_cards_from_two_graveyards(self):
        self.lands(self.swamp, 2)
        self.a.hand = [self.decay]
        self.a.graveyard.append(self.serra)
        self.b.graveyard.extend([self.bears, self.elves])
        self.assertFalse(self.game.cast(self.a, self.decay, [(self.serra, self.bears)]))
        self.assertEqual(self.a.hand, [self.decay])
        self.assertTrue(self.game.cast(self.a, self.decay, [(self.bears, self.elves)]))
        self.assertEqual((self.b.graveyard, sorted(c.name for c in self.b.exile)),
                         ([], sorted([self.bears.name, self.elves.name])))

    def test_single_graveyard_auto_choice_stays_in_one_graveyard(self):
        effect = self.effects(self.decay)[0]
        self.a.graveyard.append(self.serra)
        self.b.graveyard.extend([self.bears, self.elves])
        picked = graveyards.choose(self.game, self.a, effect)
        self.assertEqual(len({id(t.controller) for t in picked}), 1)
        self.assertEqual(len(picked), 2)

    def test_partly_removed_batch_exiles_only_the_remaining_chosen_cards(self):
        self.lands(self.swamp, 2)
        self.a.hand = [self.decay]
        self.b.graveyard.extend([self.bears, self.elves, self.serra])
        self.respond_once(lambda: self.b.exile.append(self.b.graveyard.pop(0)),
                          lambda item: item.card is self.decay)
        self.assertTrue(self.game.cast(self.a, self.decay, [(self.bears, self.elves)]))
        self.assertEqual(self.b.graveyard, [self.serra])                         # Serra not substituted
        self.assertEqual(sorted(c.name for c in self.b.exile), sorted([self.bears.name, self.elves.name]))

    # ------------------------------------------------------------------ target player's graveyard
    def test_target_player_graveyard_is_bound_and_exiled_on_resolution(self):
        effect = self.effects(self.angel)[0]
        self.b.graveyard.extend([self.bears, self.elves])
        self.assertIs(default_choose_target(self.game, self.a, effect), self.b)
        self.game.resolve(self.a, effect, self.b)
        self.assertEqual((self.b.graveyard, len(self.b.exile)), ([], 2))
        self.a.graveyard.append(self.serra)
        self.game.resolve(self.a, effect, self.a)                                # the chosen player, not the opponent
        self.assertEqual((self.a.graveyard, self.a.exile), ([], [self.serra]))

    def test_angel_enters_exiling_the_chosen_players_graveyard(self):
        self.lands(self.plains, 4)
        self.a.hand = [self.angel]
        self.b.graveyard.extend([self.bears, self.elves])
        self.assertTrue(self.game.cast(self.a, self.angel))
        self.assertEqual(self.b.graveyard, [])

    # ------------------------------------------------------------------ Diregraf Scavenger
    def test_scavenger_drains_only_when_a_creature_card_was_exiled(self):
        effect = self.effects(self.scavenger)[0]
        self.assertEqual(effect.target, "graveyard_card")
        self.b.graveyard.append(self.bears)
        target = graveyards.choose(self.game, self.a, effect)
        self.game.resolve(self.a, effect, target)
        self.assertEqual((self.a.life, self.b.life, self.b.exile), (22, 18, [self.bears]))
        self.b.graveyard.append(self.shock)
        self.game.resolve(self.a, effect, graveyards.choose(self.game, self.a, effect))
        self.assertEqual((self.a.life, self.b.life), (22, 18))
        self.assertEqual(self.b.exile, [self.bears, self.shock])

    # ------------------------------------------------------------------ different names
    def test_different_names_choice_and_rejection(self):
        self.lands(self.swamp, 7)
        self.a.hand = [self.sinister]
        self.a.graveyard.extend([self.bears, self.bears, self.elves, self.serra])
        effect = self.effects(self.sinister)[0]
        self.assertTrue(effect.data["distinct"])
        picked = graveyards.choose(self.game, self.a, effect)
        self.assertEqual(sorted(t.card.name for t in picked),
                         sorted([self.bears.name, self.elves.name, self.serra.name]))
        self.assertFalse(self.game.cast(self.a, self.sinister, [(self.bears, self.bears)]))
        self.assertEqual(self.a.hand, [self.sinister])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_different_names_resolves_one_of_each_name(self):
        self.lands(self.swamp, 7)
        self.a.hand = [self.sinister]
        self.a.graveyard.extend([self.bears, self.bears, self.elves])
        self.assertTrue(self.game.cast(self.a, self.sinister))
        self.assertEqual(sorted(p.card.name for p in self.a.battlefield if p.is_creature),
                         sorted([self.bears.name, self.elves.name]))
        self.assertEqual(self.a.graveyard.count(self.bears), 1)

    def test_different_names_capacity_counts_names_not_cards(self):
        effect = self.effects(self.sinister)[0]
        two = type(effect)("gy_move", 2, target="graveyard_card", data={**effect.data, "upto": False})
        self.a.graveyard.extend([self.bears, self.bears])
        self.assertFalse(graveyards.can_choose(self.game, self.a, two))
        self.a.graveyard.append(self.elves)
        self.assertTrue(graveyards.can_choose(self.game, self.a, two))


if __name__ == "__main__":
    unittest.main()
