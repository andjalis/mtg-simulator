"""Paid and unpaid kicker modes, including real stack/permanent interactions."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import CardDef, card_from_scryfall
from mtgsim.engine import Game, Player


def card(text, *, creature=False):
    return card_from_scryfall({
        "name": "Rider Test", "mana_cost": "{R}", "cmc": 1,
        "type_line": "Creature — Drake" if creature else "Instant",
        "power": "2", "toughness": "2", "oracle_text": "Kicker {4}\n" + text,
    })


def mode(c):
    return next(a for a in c.alt_costs if a.kind == "kicker")


class KickerRiderTests(unittest.TestCase):
    def test_damage_replaces_amount_and_keeps_target(self):
        c = card("Rider Test deals 2 damage to target creature. If this spell was kicked, "
                 "it deals 5 damage to that creature instead.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.spell_effects[0].amount, 2)
        self.assertEqual([(e.kind, e.amount, e.target) for e in mode(c).effects], [("damage", 5, "creature")])
        self.assertEqual(mode(c).cost, {"R": 1, "generic": 4})

    def test_stat_replacement_preserves_other_effects(self):
        for base, kicked, kind, expected in [("+2/+2", "+5/+5", "pump", 5),
                                             ("-2/-2", "-6/-6", "debuff_one", 6)]:
            with self.subTest(base=base):
                c = card(f"Target creature gets {base} until end of turn. Draw a card. "
                         f"If this spell was kicked, that creature gets {kicked} until end of turn instead.")
                self.assertFalse(c.unsupported)
                self.assertEqual(len(c.spell_effects), 2)
                self.assertEqual([(e.kind, e.amount, e.amount2) for e in mode(c).effects],
                                 [(kind, expected, expected), ("draw", 1, 0)])
                self.assertEqual(abs(c.spell_effects[0].amount), 2)

    def test_mismatched_stat_replacement_stays_unsupported(self):
        for base, kicked in [("+2/+2", "-6/-6"), ("-2/-2", "+6/+6"),
                             ("+2/+2", "+6/-6"), ("-2/-2", "-6/+6")]:
            with self.subTest(base=base, kicked=kicked):
                rider = f"that creature gets {kicked} until end of turn instead."
                c = card(f"Target creature gets {base} until end of turn. If this spell was kicked, " + rider)
                self.assertIn("if kicked: " + rider, c.unsupported)
                self.assertEqual(mode(c).effects, c.spell_effects)

    def test_kicked_debuff_policy_targets_opponents_creature(self):
        game, a, b = self.game()
        c = card("Target creature gets -2/-2 until end of turn. If this spell was kicked, "
                 "that creature gets -6/-6 until end of turn instead.")
        body = CardDef("Creature", {}, 0, types=frozenset({"Creature"}), power=4, toughness=4)
        friendly = game.enter_battlefield(a, body)
        enemy = game.enter_battlefield(b, body)
        a.hand.append(c)
        kicked = game._variant(a.hand[0], "kicker", mode(c))
        self.assertEqual([(e.kind, e.amount, e.amount2) for e in kicked.spell_effects], [("debuff_one", 6, 6)])
        self.assertEqual(game.auto_targets(a, kicked.spell_effects), [enemy])
        self.assertTrue(game.cast(a, kicked))
        self.assertNotIn(enemy, b.battlefield)
        self.assertIn(friendly, a.battlefield)
        self.assertEqual((friendly.power, friendly.toughness), (4, 4))

    def test_discard_replacement(self):
        c = card("Target player discards a card. If this spell was kicked, that player discards three cards instead.")
        self.assertFalse(c.unsupported)
        self.assertEqual(c.spell_effects[0].amount, 1)
        self.assertEqual([(e.kind, e.amount, e.target) for e in mode(c).effects], [("discard", 3, "player")])

    def test_whole_effect_replacements(self):
        c = card("Destroy target creature or planeswalker with mana value 2 or less. "
                 "If this spell was kicked, instead destroy target creature or planeswalker.")
        self.assertFalse(c.unsupported)
        self.assertIn("cmc<=2", c.spell_effects[0].filter)
        self.assertEqual([(e.kind, e.target, e.filter) for e in mode(c).effects], [("destroy", "creature_pw", "")])
        c = card("Return target creature card from your graveyard to your hand. "
                 "If this spell was kicked, instead return two target creature cards from your graveyard to your hand.")
        self.assertFalse(c.unsupported)
        self.assertEqual(len(mode(c).effects), 1)
        self.assertEqual((mode(c).effects[0].kind, mode(c).effects[0].amount), ("gy_move", 2))
        self.assertEqual(c.spell_effects[0].amount, 1)

    def test_standalone_counter_rider_has_no_empty_gap(self):
        for number, n in [("a", 1), ("two", 2), ("five", 5)]:
            c = card(f"Flying\nIf this creature was kicked, it enters with {number} +1/+1 counters on it.", creature=True)
            self.assertEqual(c.unsupported, [])
            self.assertEqual(c.etb_counters, 0)
            self.assertEqual(mode(c).counters, n)
            self.assertEqual(mode(c).effects, [])

    def test_unsupported_replacements_stay_visible(self):
        for rider in ["instead create a token that's a copy of Emrakul, the Promised End.",
                      "copy that spell twice instead.",
                      "it enters with X +1/+1 counters on it.",
                      "it enters with two +1/+1 counters on it and with flying."]:
            c = card("Draw a card. If this spell was kicked, " + rider,
                     creature=rider.startswith("it enters"))
            self.assertIn("if kicked: " + rider, c.unsupported)
            self.assertEqual(mode(c).effects, c.spell_effects)

    def test_nonmana_kicker_stays_unsupported(self):
        c = card_from_scryfall({"name": "Rider Test", "mana_cost": "{B}", "type_line": "Sorcery",
            "oracle_text": "Kicker—Sacrifice two lands.\nTarget player discards two cards. "
                           "If this spell was kicked, that player discards three cards instead."})
        self.assertFalse(c.alt_costs)
        self.assertIn("if kicked: that player discards three cards instead.", c.unsupported)

    def game(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0))
        game.turn = 1
        for p in (a, b):
            p.library = [CardDef("Filler", {}, 0, types=frozenset({"Land"})) for _ in range(20)]
        land = CardDef("Mountain", {}, 0, types=frozenset({"Land"}), produces=frozenset({"R"}))
        for _ in range(5):
            game.enter_battlefield(a, land)
        return game, a, b

    def test_real_game_damage_kills_only_when_kicked(self):
        for kicked in (False, True):
            with self.subTest(kicked=kicked):
                game, a, b = self.game()
                c = card("Rider Test deals 2 damage to target creature. If this spell was kicked, "
                         "it deals 5 damage to that creature instead.")
                victim = game.enter_battlefield(b, CardDef("Victim", {}, 0, types=frozenset({"Creature"}), power=4, toughness=4))
                a.hand.append(c)
                chosen = game._variant(a.hand[0], "kicker", mode(c)) if kicked else a.hand[0]
                self.assertTrue(game.cast(a, chosen, [victim]))
                self.assertEqual(victim in b.battlefield, not kicked)
                self.assertEqual(len(b.graveyard), int(kicked))
                self.assertEqual(a.graveyard[0].name, c.name)

    def test_counters_exist_before_entry_sba_and_do_not_follow_reentry(self):
        for kicked in (False, True):
            with self.subTest(kicked=kicked):
                game, a, b = self.game()
                c = card("If this creature was kicked, it enters with two +1/+1 counters on it.", creature=True)
                # A 0/0 survives its entry SBA only when initial kicker counters are present.
                c.power = c.toughness = 0
                a.hand.append(c)
                chosen = game._variant(a.hand[0], "kicker", mode(c)) if kicked else a.hand[0]
                self.assertTrue(game.cast(a, chosen))
                creatures = a.creatures
                self.assertEqual(len(creatures), int(kicked))
                if kicked:
                    perm = creatures[0]
                    self.assertEqual((perm.power, perm.toughness, perm.p1), (2, 2, 2))
                    game.sacrifice(perm)
                    returned = game.enter_battlefield(a, a.graveyard[0])
                    self.assertNotIn(returned, a.battlefield)
                    self.assertEqual(returned.p1, 0)


if __name__ == "__main__":
    unittest.main()
