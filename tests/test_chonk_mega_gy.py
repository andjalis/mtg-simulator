"""Graveyard, exile and sacrifice templates of the mega-chonk batch: dig-to-graveyard,
Fact-or-Fiction splits, self-return riders, optional self-sacrifice / self-exile payoffs,
hand-exile O-rings and temporary reanimation."""
import unittest

from mtgsim.cards import Effect, _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_combat_triggers import BEAR
from tests.test_templates import ISLAND, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)
SPIKE = card("Test Spike", "{2}", "Creature — Spike", "", 3, 1)
SPELL = card("Test Spell", "{1}", "Sorcery", "")


class MegaChonkGraveyard(Batch1):
    def apply_effects(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def setUp(self):
        super().setUp()
        self.a.library = [ISLAND, SPELL, BIG, SPIKE, SPELL, ISLAND, SPELL, ISLAND]

    def test_dig_keep_one_rest_to_graveyard(self):
        self.apply("Look at the top five cards of your library. Put one of them into your hand and the rest into your graveyard.")
        self.assertEqual((len(self.a.hand), len(self.a.graveyard)), (1, 4))
        self.assertEqual(len(self.a.library), 3)

    def test_dig_keep_two_of_two(self):
        self.apply("Look at the top two cards of your library. Put one of them into your hand and the other into your graveyard.")
        self.assertEqual((len(self.a.hand), len(self.a.graveyard)), (1, 1))

    def test_dig_filter_keeps_a_creature_or_land(self):
        self.apply("Reveal the top five cards of your library. You may put a creature or land card from among them into your hand. Put the rest into your graveyard.")
        self.assertEqual(len(self.a.hand), 1)
        self.assertIn(self.a.hand[0].types & {"Creature", "Land"}, ({"Creature"}, {"Land"}))

    def test_dig_types_keeps_one_of_each(self):
        self.a.library = [ISLAND, SPELL, BIG, SPELL, SPELL]
        self.apply("Reveal the top five cards of your library. You may put a creature card and/or a land card from among them into your hand. Put the rest into your graveyard.")
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual({c.types & {"Creature", "Land"} for c in self.a.hand}, {frozenset({"Creature"}), frozenset({"Land"})})
        self.assertEqual(len(self.a.graveyard), 3)

    def test_dig_top_back(self):
        top = [SPELL, SPELL, SPIKE]
        self.a.library = [ISLAND] * 5 + list(top)
        self.apply("Look at the top three cards of your library. You may put one of those cards back on top of your library. Put the rest into your graveyard.")
        self.assertEqual((len(self.a.graveyard), len(self.a.library)), (2, 6))
        self.assertEqual(self.a.library[-1].name, "Test Spike")

    def test_fact_or_fiction(self):
        self.apply("Reveal the top five cards of your library. An opponent separates those cards into two piles. Put one pile into your hand and the other into your graveyard.")
        self.assertEqual((len(self.a.hand), len(self.a.graveyard)), (3, 2))
        self.assertEqual(len(self.a.library), 3)

    def test_return_this_card_from_graveyard_to_hand(self):
        effects = self.apply_effects("You may return this card from your graveyard to your hand.")
        self.assertIn("return_self_gy", [e.kind for e in effects])
        self.assertEqual(effects[-1].data["to"], "hand")

    def test_reanimate_temp_exiles_at_end_step(self):
        self.a.graveyard.append(SPIKE)
        effects = self.apply_effects("Return target creature card from your graveyard to the battlefield. That creature gains haste until end of turn. Exile it at the beginning of the next end step.")
        self.assertEqual([e.kind for e in effects], ["reanimate_temp"])
        item = StackItem(self.a, effects, [])
        self.g.resolve(self.a, effects[0], None, item)
        self.assertEqual([p.card.name for p in self.a.creatures], ["Test Spike"])
        self.assertTrue(self.a.creatures[0].has("haste"))
        self.g.begin_end_step(self.a)
        self.g.settle()
        self.assertEqual([p.card.name for p in self.a.creatures], [])
        self.assertIn(SPIKE, self.a.exile)

    def test_reanimate_temp_top_of_graveyard(self):
        self.a.graveyard.extend([BIG, SPIKE])
        effects = self.apply_effects("Return the top creature card of your graveyard to the battlefield. That creature gains haste until end of turn. Exile it at the beginning of the next end step.")
        item = StackItem(self.a, effects, [])
        self.g.resolve(self.a, effects[0], None, item)
        self.assertEqual([p.card.name for p in self.a.creatures], ["Test Spike"])

    def test_may_exile_self_payoff(self):
        reanimator = card("Test Looter", "{2}", "Creature — Rogue",
                          "When this creature dies, you may exile it. If you do, draw a card.", 1, 1)
        perm = self.put(reanimator)
        hand = len(self.a.hand)
        self.g.destroy(perm)
        self.g.settle()
        self.assertIn(reanimator, self.a.exile)
        self.assertNotIn(reanimator, self.a.graveyard)
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_sac_self_payoff(self):
        perm = self.put(BEAR)
        hand = len(self.a.hand)
        effect = Effect("sac_self_payoff", data={"effects": [Effect("draw", 1)]})
        item = StackItem(self.a, [effect], [], source=perm)
        self.g.resolve(self.a, effect, None, item)
        self.g.settle()
        self.assertNotIn(perm, self.a.battlefield)
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_sac_self_parse(self):
        effects, ignored = _parse_effects("You may sacrifice this creature. If you do, search your library "
                                          "for a Demon card, reveal that card, put it into your hand, then shuffle.")
        self.assertFalse(ignored, ignored)
        self.assertEqual([e.kind for e in effects], ["sac_self_payoff"])

    def test_exile_hand_permanent(self):
        self.b.hand[:] = [SPELL, SPELL, SPELL]
        self.apply("Target player reveals their hand. You choose a nonland card from it. Exile that card.", [self.b])
        self.assertEqual((len(self.b.hand), len(self.b.exile)), (2, 1))

    def test_hand_exile_oring(self):
        fiend = card("Test Fiend", "{1}{B}", "Creature — Human Rogue",
                     "When this creature enters, target opponent reveals their hand and you choose a nonland card "
                     "from it. Exile that card. When this creature leaves the battlefield, return the exiled card "
                     "to its owner's hand.", 1, 1)
        self.b.hand[:] = [SPELL, SPELL]
        perm = self.put(fiend)
        self.g.settle()
        self.assertEqual(len(self.b.exile), 1)
        self.assertEqual(len(self.b.hand), 1)
        self.g.leave_battlefield(perm, "graveyard")
        self.g.settle()
        self.assertEqual((len(self.b.exile), len(self.b.hand)), (0, 2))

    def test_edict_of_their_choice(self):
        weak, strong = self.put(BEAR, self.b), self.put(BIG, self.b)
        self.apply("Each player sacrifices a creature of their choice.")
        self.assertNotIn(weak, self.b.battlefield)
        self.assertIn(strong, self.b.battlefield)



    def test_process_payoff(self):
        stranded = card("Test Stranded", "{2}", "Creature", "", 2, 2)
        self.b.exile.append(stranded)
        victim = self.put(BEAR, self.b)
        effects = self.apply_effects("You may put a card an opponent owns from exile into that "
                                     "player's graveyard. If you do, target creature gets -3/-3 until end of turn.")
        item = StackItem(self.a, effects, [None, victim])
        self.g.resolve(self.a, effects[0], None, item)
        self.g.settle()
        self.assertIn(stranded, self.b.graveyard)
        self.assertNotIn(stranded, self.b.exile)
        self.assertEqual(victim.toughness, 2 - 3)

    def test_process_nothing_in_exile(self):
        victim = self.put(BEAR, self.b)
        effects = self.apply_effects("You may put a card an opponent owns from exile into that "
                                     "player's graveyard. If you do, target creature gets -3/-3 until end of turn.")
        item = StackItem(self.a, effects, [None, victim])
        self.g.resolve(self.a, effects[0], None, item)
        self.g.settle()
        self.assertEqual(victim.toughness, 2)

    def test_sac_unless_discard_pays(self):
        masticore = self.put(card("Test Masticore", "{4}", "Artifact Creature — Masticore", "", 4, 4))
        self.a.hand[:] = [SPELL, SPELL]
        effect = self.apply_effects("Sacrifice ~ unless you discard a card.")[0]
        self.g.resolve(self.a, effect, None, StackItem(self.a, [effect], [], source=masticore))
        self.assertEqual((len(self.a.hand), masticore in self.a.battlefield), (1, True))

    def test_sac_unless_discard_sacrifices_when_empty(self):
        masticore = self.put(card("Test Masticore", "{4}", "Artifact Creature — Masticore", "", 4, 4))
        self.a.hand.clear()
        effect = self.apply_effects("Sacrifice ~ unless you discard a card.")[0]
        self.g.resolve(self.a, effect, None, StackItem(self.a, [effect], [], source=masticore))
        self.assertNotIn(masticore, self.a.battlefield)

    def test_junk_token_parse(self):
        from mtgsim.cards.tokens import make_token
        junk = make_token("", 0, 0, kind="junk")
        self.assertEqual(junk.token_kind, "junk")
        self.assertTrue(junk.activated)
        effects, ignored = _parse_effects("Create a Junk token.")
        self.assertFalse(ignored, ignored)
        self.assertEqual([(e.kind, e.amount, e.data.get("kind")) for e in effects], [("token", 1, "junk")])


if __name__ == "__main__":
    unittest.main()
