import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player

DB = CardDB(offline=True)


def perm(name, owner, sick=False):
    p = Permanent(DB.get(name), owner)
    p.sick = sick
    p.tapped = False
    owner.battlefield.append(p)
    return p


class AITests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        for p in (self.a, self.b):
            p.library = [DB.get("Island")] * 20

    def test_no_attack_into_bigger_blocker(self):
        bears = perm("Grizzly Bears", self.a)
        perm("Kalonian Tusker", self.b)
        self.assertEqual(self.a.ai.choose_attackers(self.game, self.a, self.b), [])
        self.b.battlefield[0].tapped = True
        self.assertEqual(self.a.ai.choose_attackers(self.game, self.a, self.b), [bears])

    def test_alpha_strike_for_lethal(self):
        self.b.life = 5
        attackers = [perm("Grizzly Bears", self.a) for _ in range(3)]
        perm("Kalonian Tusker", self.b)
        self.assertEqual(set(self.a.ai.choose_attackers(self.game, self.a, self.b)), set(attackers))

    def test_stays_home_when_crack_back_is_lethal(self):
        self.a.life = 6
        perm("Grizzly Bears", self.a)
        perm("Kalonian Tusker", self.b)
        perm("Kalonian Tusker", self.b)
        self.b.battlefield[0].tapped = True   # the bear could attack past one, but not leave us dead
        self.assertEqual(self.a.ai.choose_attackers(self.game, self.a, self.b), [])

    def test_lethal_tie_adds_redundancy_against_open_mana(self):
        # Any two bears are lethal; the third costs nothing and survives one removal spell.
        self.b.life = 4
        bears = [perm("Grizzly Bears", self.a) for _ in range(3)]
        perm("Mountain", self.b)
        self.assertEqual(set(self.a.ai.choose_attackers(self.game, self.a, self.b)), set(bears))

    def test_lethal_tie_keeps_blocker_when_failed_kill_means_crack_back(self):
        self.b.life, self.a.life = 4, 3
        [perm("Grizzly Bears", self.a) for _ in range(3)]
        perm("Kalonian Tusker", self.b).tapped = True
        self.assertEqual(len(self.a.ai.choose_attackers(self.game, self.a, self.b)), 2)

    def test_reach_lethal_adds_costless_attack_but_not_into_blocker(self):
        self.b.life = 3
        perm("Mountain", self.a)
        self.a.hand = [DB.get("Lightning Bolt")]
        bear = perm("Grizzly Bears", self.a)
        self.assertEqual(self.a.ai.choose_attackers(self.game, self.a, self.b), [bear])
        perm("Kalonian Tusker", self.b)
        self.assertEqual(self.a.ai.choose_attackers(self.game, self.a, self.b), [])

    def test_blocks_trade_and_chumps_only_when_needed(self):
        tusker = perm("Kalonian Tusker", self.a)
        bears = perm("Grizzly Bears", self.b)
        self.assertEqual(self.b.ai.choose_blocks(self.game, self.b, self.a, [tusker]), {})
        self.b.life = 3
        self.assertEqual(self.b.ai.choose_blocks(self.game, self.b, self.a, [tusker]), {tusker: [bears]})

    def test_double_block_kills_big_attacker(self):
        baloth = perm("Rumbling Baloth", self.a)
        b1, b2 = perm("Kalonian Tusker", self.b), perm("Centaur Courser", self.b)
        blocks = self.b.ai.choose_blocks(self.game, self.b, self.a, [baloth])
        self.assertEqual(set(blocks.get(baloth, [])), {b1, b2})

    def test_burn_goes_face_for_lethal_else_kills_creature(self):
        perm("Mountain", self.a)
        bolt = DB.get("Lightning Bolt")
        self.a.hand = [bolt]
        tusker = perm("Kalonian Tusker", self.b)
        eff = bolt.spell_effects[0]
        self.assertIs(self.a.ai.best_damage_target(self.game, self.a, eff, bolt, False)[0], tusker)
        self.b.life = 3
        self.assertIs(self.a.ai.best_damage_target(self.game, self.a, eff, bolt, False)[0], self.b)

    def test_counters_big_threat_not_a_tax_they_can_pay(self):
        for _ in range(6):
            perm("Forest", self.a)
        for _ in range(2):
            perm("Island", self.b)
        self.b.hand = [DB.get("Counterspell")]
        self.a.hand = [DB.get("Colossal Dreadmaw")]
        self.game.cast(self.a, DB.get("Colossal Dreadmaw"))
        self.assertEqual(self.a.creatures, [])
        perm("Forest", self.a)
        for p in self.a.battlefield + self.b.battlefield:
            p.tapped = False
        self.b.hand = [DB.get("Jwari Disruption")]
        self.a.hand = [DB.get("Colossal Dreadmaw")]
        self.game.cast(self.a, DB.get("Colossal Dreadmaw"))
        self.assertEqual(len(self.a.creatures), 1)
        self.assertEqual(self.b.hand, [DB.get("Jwari Disruption")])

    def test_main_phase_uses_mana_fully(self):
        for _ in range(3):
            perm("Forest", self.a)
        self.a.hand = [DB.get("Colossal Dreadmaw"), DB.get("Kalonian Tusker"), DB.get("Llanowar Elves")]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertEqual(sorted(c.card.name for c in self.a.creatures), ["Kalonian Tusker", "Llanowar Elves"])

    def test_hexproof_answers_removal(self):
        troll = perm("Old-Growth Troll", self.b)
        perm("Forest", self.b)
        self.b.hand = [DB.get("Snakeskin Veil")]
        for _ in range(3):
            perm("Swamp", self.a)
        self.a.hand = [DB.get("Murder")]
        self.game.cast(self.a, DB.get("Murder"), [troll])
        self.assertIn(troll, self.b.battlefield)
        self.assertEqual(self.b.hand, [])

    def test_plays_mdfc_land_side_when_out_of_lands(self):
        perm("Forest", self.a)
        self.a.hand = [DB.get("Kazandu Mammoth")]
        self.game.step = "main1"
        self.a.ai.play_land(self.game, self.a)
        self.assertEqual(self.a.hand, [])
        self.assertIn("Kazandu Valley", [p.card.name for p in self.a.battlefield])

    def test_cantrip_at_end_step(self):
        perm("Island", self.b)
        self.b.hand = [DB.get("Consider")]
        self.game.active_idx = 0
        self.game.step = "end_step"
        choice = self.b.ai.respond(self.game, self.b)
        self.assertEqual(choice[0].name, "Consider")

    def test_sweeper_waits_for_more_than_one_creature(self):
        perm("Grizzly Bears", self.a)
        for _ in range(4):
            perm("Plains", self.b)
        sweep = DB.get("Depopulate")
        self.assertIsNone(self.b.ai.plan_spell(self.game, self.b, sweep))
        perm("Kalonian Tusker", self.a)
        perm("Centaur Courser", self.a)
        self.assertIsNotNone(self.b.ai.plan_spell(self.game, self.b, sweep))

    def test_run_match_gives_each_game_fresh_ai_state(self):
        from mtgsim.runner import fresh_ai
        shared = HeuristicAI()
        shared._idle_turns = 3
        copy = fresh_ai(shared)
        self.assertIsNot(copy, shared)
        self.assertEqual(copy._idle_turns, 0)
        self.assertEqual(shared._idle_turns, 3)

    def test_planeswalker_makes_blocker_instead_of_plus_that_gets_it_killed(self):
        emperor = perm("The Wandering Emperor", self.a)
        emperor.counters["loyalty"] = 2
        perm("Grizzly Bears", self.a)
        perm("Kalonian Tusker", self.b)
        perm("Kalonian Tusker", self.b)
        # +1 leaves 3 loyalty against two 3/3s and one blocker; -1 makes a second blocker.
        cost = emperor.card.loyalty_abilities[self.a.ai.choose_loyalty(self.game, self.a, emperor)][0]
        self.assertEqual(cost, -1)

    def test_planeswalker_plus_when_it_keeps_the_walker_safe(self):
        emperor = perm("The Wandering Emperor", self.a)
        emperor.counters["loyalty"] = 3
        perm("Grizzly Bears", self.a)
        perm("Grizzly Bears", self.b)
        cost = emperor.card.loyalty_abilities[self.a.ai.choose_loyalty(self.game, self.a, emperor)][0]
        self.assertEqual(cost, 1)

    def test_taps_counter_mana_for_a_threat_while_they_are_tapped_out(self):
        for _ in range(5):
            perm("Island", self.a)
        lands = [perm("Island", self.b) for _ in range(3)]
        self.a.hand = [DB.get("Counterspell"), DB.get("Air Elemental")]
        self.b.hand = [DB.get("Grizzly Bears")]
        self.assertTrue(self.a.ai._reserve(self.game, self.a))
        for land in lands:
            land.tapped = True
        self.assertEqual(self.a.ai._reserve(self.game, self.a), {})

    def test_removal_skips_ward_it_cannot_pay(self):
        terror = perm("Tolarian Terror", self.b)     # ward {2}
        swamps = [perm("Swamp", self.a) for _ in range(5)]
        murder = DB.get("Murder")
        self.a.hand = [murder]
        for s in swamps[3:]:
            s.tapped = True
        eff = murder.spell_effects[0]
        self.assertIsNone(self.a.ai.choose_target(self.game, self.a, eff, murder))
        for s in swamps[3:]:
            s.tapped = False
        self.assertIs(self.a.ai.choose_target(self.game, self.a, eff, murder), terror)

    def test_new_effects_have_value(self):
        from mtgsim.cards import card_from_scryfall
        rally = card_from_scryfall({"name": "Rally Test", "mana_cost": "{1}{W}", "cmc": 2, "type_line": "Sorcery",
                                    "oracle_text": "Creatures you control get +2/+1 until end of turn."})
        tutor = card_from_scryfall({"name": "Tutor Test", "mana_cost": "{1}{G}", "cmc": 2, "type_line": "Sorcery",
                                    "oracle_text": "Search your library for a creature card, reveal it, put it "
                                                   "into your hand, then shuffle."})
        self.assertEqual([e.kind for e in rally.spell_effects], ["pump_all"])
        self.assertEqual([e.kind for e in tutor.spell_effects], ["tutor"])
        for _ in range(2):
            perm("Grizzly Bears", self.a)
        self.assertGreater(self.a.ai.plan_spell(self.game, self.a, rally, precombat=True)[0], 2)
        self.assertIsNone(self.a.ai.plan_spell(self.game, self.a, rally, precombat=False))
        self.assertGreater(self.a.ai.plan_spell(self.game, self.a, tutor)[0], 0)


if __name__ == "__main__":
    unittest.main()
