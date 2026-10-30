"""smol-chonk batch 2: wording-template generalizations (unclassified bucket + trigger wordings).

Covers substitutions (targeted discard filters, "return this card", "you may have ~ deal",
copy-spell wording), new trigger templates (host damage, targeted by spell, "when you cast a
<type> spell", +1/+1 counters you put), "Do this only once each turn" flags, edict wordings,
reveal-dig, token-haste riders, and the O-ring two-sentence rewrite.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")


class SmolBatch2Parse(unittest.TestCase):
    def clean(self, c):
        self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(c.approximations, [], c.name)

    def test_targeted_discard_filters(self):
        for text in ("Target player reveals their hand. You choose an artifact or creature card from it. "
                     "That player discards that card.",
                     "Target opponent reveals their hand. You choose a nonland permanent card from it. "
                     "That player discards that card.",
                     "Target player reveals their hand. You choose a nonland card from it. "
                     "That player discards that card."):
            c = card("Divest", "{1}{B}", "Sorcery", text)
            self.clean(c)
            self.assertEqual([e.kind for e in c.spell_effects], ["discard_choice"])

    def test_return_this_card_from_graveyard(self):
        c = card("Eternal Idea", "{3}{U}", "Creature — Elemental",
                 "Whenever you cast an instant or sorcery spell, you may return this card from your "
                 "graveyard to your hand.")
        self.clean(c)
        self.assertEqual(c.gy_triggers[0].event, "cast_instant_sorcery")
        self.assertEqual([e.kind for e in c.gy_triggers[0].effects], ["pay_gate", "return_self_gy"])
        self.assertEqual(c.gy_triggers[0].effects[1].data["to"], "hand")

    def test_you_may_have_deal_damage(self):
        c = card("Goblin Shrine", "{1}{R}", "Enchantment",
                 "Whenever another Goblin you control enters, you may have Goblin Shrine deal 1 damage "
                 "to target player or planeswalker.")
        self.clean(c)
        self.assertEqual([e.kind for e in c.triggers[0].effects], ["damage"])
        self.assertEqual(c.triggers[0].effects[0].amount, 1)

    def test_copy_target_spell(self):
        for text in ("Copy target instant or sorcery spell.",
                     "Copy target instant spell.",
                     "Copy target sorcery spell. You may choose new targets for the copy."):
            c = card("Echo", "{R}{R}", "Instant", text)
            self.clean(c)

    def test_host_damages_player(self):
        c = card("Nosiness", "{U}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature "
                 "deals damage to an opponent, you may draw a card.")
        self.clean(c)
        self.assertEqual(c.host_triggers[0].event, "damages_player")

    def test_host_dealt_damage(self):
        c = card("Blight", "{2}{B}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature "
                 "is dealt damage, destroy it.")
        self.clean(c)
        self.assertEqual(c.host_triggers[0].event, "dealt_damage")
        self.assertEqual(c.host_triggers[0].effects[0].kind, "destroy")

    def test_targeted_by_spell_sacrifice(self):
        c = card("Shy Illusion", "{1}{U}", "Creature — Illusion",
                 "When Shy Illusion becomes the target of a spell, sacrifice it.", 2, 2)
        self.clean(c)
        self.assertEqual(c.triggers[0].event, "targeted_by_spell")
        self.assertEqual(c.triggers[0].effects[0].kind, "sacrifice_self")

    def test_combat_damage_player_or_planeswalker(self):
        c = card("Zealous Sprite", "{1}{W}", "Creature — Spirit",
                 "Whenever Zealous Sprite deals combat damage to a player or planeswalker, proliferate.", 1, 1)
        self.clean(c)
        self.assertEqual(c.triggers[0].event, "combat_damage_player")
        self.assertEqual(c.triggers[0].effects[0].kind, "proliferate")

    def test_when_you_cast_type_spell(self):
        c = card("Skittering Watcher", "{1}{B}", "Creature — Horror",
                 "When you cast a creature spell, sacrifice Skittering Watcher.", 2, 1)
        self.clean(c)
        self.assertEqual(c.triggers[0].event, "cast_spell")
        self.assertEqual(c.triggers[0].filter, "spell:creature")

    def test_put_counters_trigger(self):
        c = card("Counter Sage", "{2}{G}", "Creature — Druid",
                 "Whenever you put one or more +1/+1 counters on Counter Sage, you may draw that many cards.",
                 1, 3)
        self.clean(c)
        self.assertEqual(c.triggers[0].event, "p1_added")

    def test_do_this_once_each_turn(self):
        trig = card("Once Troll", "{2}{R}", "Creature — Troll",
                    "Whenever Once Troll attacks, draw a card. Do this only once each turn.", 2, 2)
        self.clean(trig)
        self.assertTrue(trig.triggers[0].once)
        act = card("Once Machine", "{3}", "Artifact",
                   "{T}: Scry 1. Do this only once each turn.")
        self.clean(act)
        self.assertTrue(act.activated[0].once)

    def test_edict_wordings(self):
        each = card("Deathpact", "{1}{B}", "Sorcery", "Each player sacrifices a creature of their choice.")
        self.clean(each)
        self.assertEqual([e.kind for e in each.spell_effects], ["edict_each"])
        target = card("Deathpact", "{1}{B}", "Sorcery", "Target player sacrifices a creature of their choice.")
        self.clean(target)
        self.assertEqual([e.kind for e in target.spell_effects], ["edict"])

    def test_reveal_top_card_to_hand(self):
        c = card("Insight Pulse", "{2}{U}", "Instant",
                 "Reveal the top card of your library and put that card into your hand.")
        self.clean(c)
        self.assertEqual(c.spell_effects[0].kind, "dig")

    def test_token_haste_rider(self):
        c = card("Rabble Rouser", "{3}{R}", "Sorcery",
                 "Create three 1/1 red Devil creature tokens with \"When this token dies, it deals 1 damage "
                 "to any target.\" They gain haste until end of turn.")
        self.clean(c)
        self.assertIn("haste", c.spell_effects[0].data["keywords"])

    def test_oring_two_sentence_wording(self):
        c = card("Snatch Away", "{2}{W}", "Creature — Human",
                 "When Snatch Away enters, exile target creature an opponent controls. When Snatch Away "
                 "leaves the battlefield, return the exiled card to the battlefield under its owner's "
                 "control.", 1, 1)
        self.clean(c)

    def test_exile_another_target(self):
        c = card("Loyal Guard", "{2}{W}", "Creature — Human",
                 "{W}, Sacrifice Loyal Guard: Exile another target creature an opponent controls.", 1, 1)
        self.clean(c)
        self.assertEqual(c.activated[0].effects[0].kind, "exile_permanent")

    def test_sac_stat_amounts(self):
        c = card("Grand Throw", "{1}{R}", "Instant",
                 "As an additional cost to cast this spell, sacrifice a creature.\n"
                 "Grand Throw deals damage equal to the sacrificed creature's power to any target.")
        self.clean(c)
        self.assertEqual(c.spell_effects[0].data["xq"], ("sac", "power"))


class SmolBatch2Play(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [BEAR] * 20

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def test_edict_each_player_hits_opponent(self):
        spell = card("Pact", "{B}", "Sorcery", "Each player sacrifices a creature of their choice.")
        self.perm(SWAMP)
        victim = self.perm(BEAR, self.b)
        self.a.hand.append(spell)
        self.game.cast(self.a, spell, [])
        self.game.settle()
        self.assertNotIn(victim, self.b.battlefield)

    def test_host_damages_player_draws(self):
        aura = card("Nosy Aura", "{U}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted "
                    "creature deals damage to an opponent, you may draw a card.")
        host = self.perm(BEAR)
        a = Permanent(aura, self.a)
        a.aura_host = host
        host.auras.append(a)
        self.a.battlefield.append(a)
        hand = len(self.a.hand)
        self.game.deal_damage(self.b, 1, by=self.a, cause="test", source=host)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_targeted_by_spell_sacrifices(self):
        c = card("Shy Illusion", "{1}{U}", "Creature — Illusion",
                 "When Shy Illusion becomes the target of a spell, sacrifice it.", 2, 2)
        perm = self.perm(c, self.b)
        self.game.fire(self.b, "targeted_by_spell", perm, context=self.a)
        self.game.settle()
        self.assertNotIn(perm, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()
