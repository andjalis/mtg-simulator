"""Cards-lane triggers: tap-and-stun on cast, damage riders, two-card hand discard, entered-this-turn hexproof."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card

DEEP_FIEND = card("Test Deep-Fiend", "{3}{U}{U}", "Creature — Eldrazi", "When you cast this spell, tap up to four "
                  "target permanents.", 5, 6)
BEHEMOTH = card("Test Behemoth", "{4}{U}", "Creature — Elemental", "Test Behemoth has hexproof as long as it entered "
                "this turn.", 4, 4)
VEINS = card("Test Veins", "{B}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature is dealt damage, "
             "its controller loses that much life.")
AGONY = card("Test Agony", "{R}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature is dealt damage, "
             "Test Agony deals that much damage to that creature's controller.")
PURPOSE = card("Test Purpose", "{1}{W}", "Enchantment", "Whenever a creature you control deals combat damage, you "
               "gain that much life.")
MINDBENDER = card("Test Mindbender", "{5}{B}", "Creature — Eldrazi", "When you cast this spell, target opponent reveals "
                  "their hand. You choose from it a nonland card with mana value 3 or less and a card with mana value "
                  "4 or greater. That player discards those cards.", 4, 4)
CRAB = card("Test Crab", "{5}{B}", "Creature — Eldrazi", "When ~ enters, target opponent exiles the top card of their "
            "library, a card at random from their graveyard, and a card at random from their hand. You may cast a "
            "spell from among cards exiled this way without paying its mana cost.", 5, 5)
RIDDLE = card("Test Riddlekeeper", "{5}{U}", "Creature — Eldrazi", "When you cast this spell, tap up to two target "
              "permanents. Put a stun counter on each of them.", 3, 3)
ARRESTER = card("Test Arrester", "{3}{W}", "Creature — Human", "When ~ enters, detain target creature an opponent "
                "controls.", 2, 2)
DECREE = card("Test Decree", "{1}{W}{U}", "Sorcery", "Detain up to two target creatures your opponents control.")
SMALL = card("Test Small", "{2}", "Artifact", "")
BIG = card("Test Big", "{4}", "Artifact", "")


class CxTriggers(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def resolve_effects(self, effects, targets):
        self.game.stack.append(StackItem(self.a, list(effects), targets, name="test", kind="trigger"))
        self.game.resolve_top()

    def test_all_parse(self):
        for c in (DEEP_FIEND, BEHEMOTH, VEINS, AGONY, PURPOSE, MINDBENDER, CRAB):
            self.assertEqual(c.unsupported, [], c.name)

    def test_tap_up_to_four_permanents(self):
        theirs = [self.perm(BEAR, self.b) for _ in range(5)]
        eff = DEEP_FIEND.cast_self_triggers[0].effects[0]
        self.assertEqual((eff.kind, eff.amount), ("tap", 4))
        self.resolve_effects([eff], [theirs[0]])
        self.assertEqual(sum(t.tapped for t in theirs), 4)

    def test_tap_and_stun_each(self):
        theirs = [self.perm(BEAR, self.b) for _ in range(3)]
        self.assertEqual(RIDDLE.unsupported, [])
        self.resolve_effects(RIDDLE.cast_self_triggers[0].effects, [theirs[0]])
        self.assertEqual([t.tapped for t in theirs].count(True), 2)
        self.assertEqual(sum(t.counters.get("stun", 0) for t in theirs), 2)

    def test_detain(self):
        from mtgsim.engine import can_block
        self.assertEqual(ARRESTER.unsupported + DECREE.unsupported, [])
        theirs = [self.perm(BEAR, self.b) for _ in range(2)]
        mine = self.perm(BEAR, self.a)
        self.resolve_effects(DECREE.spell_effects, [theirs[0]])
        self.assertEqual([t.detained_by for t in theirs], [self.a, self.a])
        self.assertFalse(theirs[0].can_attack())
        self.assertFalse(can_block(theirs[1], mine))
        self.game.take_turn(self.a)
        self.assertEqual([t.detained_by for t in theirs], [None, None])

    def test_hexproof_only_the_turn_it_entered(self):
        mon = self.game.enter_battlefield(self.a, BEHEMOTH)
        self.assertTrue(mon.has("hexproof"))
        self.game.turn += 2
        self.assertFalse(mon.has("hexproof"))

    def test_ragged_veins_drains_controller(self):
        theirs = self.perm(DRAGON3, self.b)
        self.a.hand = [VEINS]
        for _ in range(2):
            self.perm(MOUNTAIN, self.a)
        host = self.perm(BEAR, self.b)
        aura = self.game.enter_battlefield(self.a, VEINS)
        host.auras.append(aura)
        aura.attached_to = host
        before = self.b.life
        self.game.deal_damage(host, 2, by=self.a, source=None)
        self.assertEqual(self.b.life, before - 2)
        del theirs

    def test_binding_agony_deals_damage_to_controller(self):
        host = self.perm(DRAGON3, self.b)
        aura = self.game.enter_battlefield(self.a, AGONY)
        host.auras.append(aura)
        aura.attached_to = host
        before = self.b.life
        self.game.deal_damage(host, 3, by=self.a, source=None)
        self.assertEqual(self.b.life, before - 3)

    def test_noble_purpose_gains_on_combat_damage(self):
        self.perm(PURPOSE, self.a)
        bear = self.perm(BEAR, self.a)
        before = self.a.life
        self.game.deal_damage(self.b, 2, by=self.a, source=bear, combat=True)
        self.assertEqual(self.a.life, before + 2)
        self.game.deal_damage(self.b, 2, by=self.a, source=bear, combat=False)
        self.assertEqual(self.a.life, before + 2)

    def test_mindbender_discards_two_cards(self):
        self.b.hand = [SMALL, BIG, ISLAND, BEAR]
        effs = MINDBENDER.cast_self_triggers[0].effects
        self.assertEqual(len(effs), 2)
        self.resolve_effects(effs, [self.b, None])
        self.assertEqual(len(self.b.hand), 2)
        self.assertIn(BIG, self.b.graveyard)

    def test_crabomination_exiles_three_zones(self):
        self.b.hand = [SMALL]
        self.b.graveyard = [BIG]
        top = self.b.library[-1]
        effs = CRAB.triggers[0].effects
        self.assertEqual(effs[0].kind, "exile_three_zones")
        self.resolve_effects(effs, [self.b])
        self.assertFalse(self.b.hand or self.b.graveyard)
        self.assertEqual(len(self.b.library), 19)
        self.assertIn(top, self.b.exile + [p.card for p in self.a.battlefield] + self.a.exile)


if __name__ == "__main__":
    unittest.main()
