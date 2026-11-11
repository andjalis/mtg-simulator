"""Battles / Sieges (#254): defense counters, protector, attacking battles, defeat and cast transformed."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.battles import defending_player
from mtgsim.cards import CardDef, Effect
from mtgsim.cards.parse import card_from_scryfall as parse_card
from mtgsim.coverage import card_coverage
from mtgsim.engine import Game, Player, StackItem


def siege(defense=4, back_types=("Creature",), etb=()):
    """A Siege like the March of the Machine ones: a creature back face with power 3."""
    back = CardDef(name="Siege Back", mana_cost={}, cmc=0, types=frozenset(back_types),
                   power=3 if "Creature" in back_types else 0, toughness=3 if "Creature" in back_types else 0)
    return CardDef(name="Test Siege", mana_cost={"generic": 2, "R": 1}, cmc=3, types=frozenset({"Battle"}),
                   subtypes=frozenset({"Siege"}), defense=defense, back=back, etb_effects=list(etb))


def bear(power=2, **kw):
    return CardDef(name=f"Bear {power}", mana_cost={}, cmc=2, types=frozenset({"Creature"}),
                   power=power, toughness=2, **kw)


class _Pass(HeuristicAI):
    """Never acts with priority, so tests control the stack."""
    def respond(self, game, me):
        return None


class BattleTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], _Pass())
        self.b = Player("b", [], _Pass())
        self.game = Game(self.a, self.b, random.Random(0))

    def enter(self, card=None, player=None):
        return self.game.enter_battlefield(player or self.a, card or siege())

    def drain(self):
        """Put pending triggers on the stack and resolve everything, with state-based actions between."""
        game = self.game
        for _ in range(20):
            game.state_based_actions()
            game.flush_triggers()
            if not game.stack:
                return
            game.resolve_top()

    # ------------------------------------------------------------- entering

    def test_enters_with_defense_and_opponent_protects(self):
        perm = self.enter()
        self.assertEqual(perm.counters["defense"], 4)
        self.assertIs(perm.protector, self.b)
        self.assertTrue(perm.is_battle)

    def test_protector_reassigned_when_controller_protects(self):
        perm = self.enter()
        perm.protector = self.a
        self.game.state_based_actions()
        self.assertIs(perm.protector, self.b)

    # ------------------------------------------------------------- defeat

    def test_damage_defeats_and_casts_transformed_keeping_the_physical_card(self):
        perm = self.enter()
        front = perm.front
        self.game.deal_damage(perm, 2, by=self.a)
        self.assertEqual(perm.counters["defense"], 2)
        self.assertEqual(perm.damage, 0)
        self.game.deal_damage(perm, 5, by=self.a)
        self.assertEqual(perm.counters.get("defense", 0), 0)
        self.game.state_based_actions()
        self.assertIn(perm, self.a.battlefield)         # its defeat trigger is pending: not put into the graveyard
        self.drain()
        self.assertNotIn(perm, self.a.battlefield)
        backs = [x for x in self.a.battlefield if x.card.name == "Siege Back"]
        self.assertEqual(len(backs), 1)
        self.assertIs(backs[0].front, front)
        self.assertTrue(backs[0].is_creature)
        self.assertNotIn(front, self.a.exile)

    def test_counter_removal_defeats(self):
        perm = self.enter()
        self.game.resolve(self.b, Effect("cx_remove_counters", 4, target="permanent",
                                         data={"counter": "defense"}), perm)
        self.drain()
        self.assertTrue(any(x.card.name == "Siege Back" for x in self.a.battlefield))

    def test_pop_of_last_counter_defeats(self):
        perm = self.enter()
        perm.counters.pop("defense")
        self.assertTrue(any(e[2] is perm and e[1][0].kind == "siege_defeat" for e in self.game.pending))

    def test_partial_removal_does_not_trigger(self):
        perm = self.enter()
        perm.counters["defense"] = 1
        self.assertFalse(self.game.pending)
        self.game.state_based_actions()
        self.assertIn(perm, self.a.battlefield)

    def test_response_bounces_battle_trigger_does_nothing(self):
        perm = self.enter()
        self.game.deal_damage(perm, 4, by=self.a)
        self.game.state_based_actions()
        self.game.flush_triggers()
        self.assertEqual(self.game.stack[-1].effects[0].kind, "siege_defeat")
        self.game.leave_battlefield(perm, "hand")        # in response
        self.drain()
        self.assertIn(perm.front, self.a.hand)
        self.assertFalse(any(x.card.name == "Siege Back" for x in self.a.battlefield))

    def test_countered_trigger_puts_battle_into_graveyard(self):
        perm = self.enter()
        self.game.deal_damage(perm, 4, by=self.a)
        self.game.state_based_actions()
        self.game.flush_triggers()
        trigger = self.game.stack[-1]
        self.game.state_based_actions()
        self.assertIn(perm, self.a.battlefield)          # source of a trigger on the stack
        self.game.stack.remove(trigger)                  # "counter target triggered ability"
        self.game.state_based_actions()
        self.assertNotIn(perm, self.a.battlefield)
        self.assertIn(perm.front, self.a.graveyard)

    def test_failed_cast_stays_in_exile(self):
        self.game.enter_battlefield(self.b, CardDef(name="Ban", mana_cost={}, cmc=0, types=frozenset({"Enchantment"}),
                                                    advanced_rules={"no_cast": ["creature"]}))
        perm = self.enter()
        front = perm.front
        self.game.deal_damage(perm, 4, by=self.a)
        self.drain()
        self.assertIn(front, self.a.exile)
        self.assertNotIn(front, self.a.hand)
        self.assertFalse(any(x.card.name == "Siege Back" for x in self.a.battlefield))

    def test_countered_transformed_spell_goes_to_graveyard(self):
        perm = self.enter()
        front = perm.front
        self.game.deal_damage(perm, 4, by=self.a)
        self.game.state_based_actions()
        self.game.flush_triggers()
        self.game._priority_depth += 1                   # inside a priority loop: the cast spell waits on the stack
        self.game.resolve_top()                          # exile, then cast transformed
        self.game._priority_depth -= 1
        spell = self.game.stack[-1]
        self.assertTrue(spell.is_spell)
        self.assertEqual(spell.card.cmc, 3)              # the front face's mana value
        self.game.counter(self.b, Effect("counter", target="spell"), spell)
        self.assertIn(front, self.a.graveyard)
        self.assertNotIn(front, self.a.exile)

    def test_lost_abilities_no_trigger_graveyard(self):
        perm = self.enter()
        perm.silenced_by = self.game.enter_battlefield(self.b, bear(1))     # Tishana's Tidebinder-style
        self.game.deal_damage(perm, 4, by=self.a)
        self.assertFalse(self.game.pending)
        self.game.state_based_actions()
        self.assertIn(perm.front, self.a.graveyard)

    # ------------------------------------------------------------- combat

    def attack(self, attackers, targets, blocks=None):
        game = self.game
        game.hook = lambda p, name, _orig=game.hook: (
            (lambda *a: targets) if name == "choose_attack_targets" else _orig(p, name))
        self.a.ai.choose_attackers = lambda g, me, opp: list(attackers)
        self.b.ai.choose_blocks = lambda g, me, opp, atk: dict(blocks or {})
        game.combat(self.a, self.b)

    def test_attack_own_siege_damage_removes_defense(self):
        perm = self.enter()
        attacker = self.game.enter_battlefield(self.a, bear(3))
        attacker.sick = False
        self.attack([attacker], {attacker: perm})
        self.assertEqual(perm.counters["defense"], 1)
        self.assertEqual(self.b.life, 20)

    def test_attack_defeats_siege(self):
        perm = self.enter(siege(defense=2))
        attacker = self.game.enter_battlefield(self.a, bear(3))
        attacker.sick = False
        self.attack([attacker], {attacker: perm})
        self.assertNotIn(perm, self.a.battlefield)
        self.assertTrue(any(x.card.name == "Siege Back" for x in self.a.battlefield))

    def test_protector_blocks_for_battle(self):
        perm = self.enter()
        attacker = self.game.enter_battlefield(self.a, bear(3))
        attacker.sick = False
        blocker = self.game.enter_battlefield(self.b, bear(1))
        self.attack([attacker], {attacker: perm}, {attacker: [blocker]})
        self.assertEqual(perm.counters["defense"], 4)
        self.assertNotIn(blocker, self.b.battlefield)

    def test_cannot_attack_battle_you_protect(self):
        theirs = self.enter(player=self.b)               # b's Siege, protected by a
        self.assertIs(theirs.protector, self.a)
        attacker = self.game.enter_battlefield(self.a, bear(3))
        attacker.sick = False
        self.attack([attacker], {attacker: theirs})
        self.assertEqual(theirs.counters["defense"], 4)
        self.assertEqual(self.b.life, 17)

    def test_defending_player_is_protector(self):
        perm = self.enter()
        attacker = self.game.enter_battlefield(self.a, bear(3))
        self.game.attack_targets[attacker] = perm
        item = StackItem(self.a, [], [], source=attacker)
        self.assertIs(defending_player(self.game, item), self.b)
        from mtgsim.cx_grammar import players
        self.assertEqual(players(self.game, self.a, "defending", item, None), [self.b])

    def test_attacking_a_battle_is_not_attacking_you(self):
        perm = self.enter()
        attacker = self.game.enter_battlefield(self.a, bear(3))
        attacker.sick = False
        fired, fire = [], self.game.fire
        self.game.fire = lambda p, event, *a, **k: (fired.append(event), fire(p, event, *a, **k))[1]
        self.attack([attacker], {attacker: perm})
        self.assertIn("attacks", fired)
        self.assertNotIn("opp_creature_attacks", fired)

    def test_ai_values_defending_player_as_protector(self):
        from mtgsim.ai import HeuristicAI
        perm = self.enter()
        attacker = self.game.enter_battlefield(self.a, bear(3))
        self.game.attack_targets[attacker] = perm
        eff = Effect("cx_players", data={"who": "defending", "effects": [Effect("lose_life", 2)]})
        card = CardDef(name="Player effect", mana_cost={}, cmc=0, types=frozenset({"Sorcery"}), spell_effects=[eff])
        self.game.resolving_item = StackItem(self.a, [eff], [], source=attacker)
        self.assertGreater(HeuristicAI()._players_plan(self.game, self.a, eff, card, False)[1], 0)

    def test_ai_sends_unblockable_attackers_at_defeatable_battle(self):
        from mtgsim.engine.policy import choose_attack_targets
        perm = self.enter(siege(defense=3))
        flyer = self.game.enter_battlefield(self.a, bear(3, keywords=frozenset({"flying"})))
        ground = self.game.enter_battlefield(self.a, bear(2))
        self.game.enter_battlefield(self.b, bear(1))
        out = choose_attack_targets(self.game, self.a, [flyer, ground])
        self.assertEqual(out, {flyer: perm})
        perm.counters["defense"] = 4                     # can't be defeated by the flyer alone: no change
        self.assertEqual(choose_attack_targets(self.game, self.a, [flyer, ground]), {})


class SiegeParseTests(unittest.TestCase):
    def test_defense_and_this_siege(self):
        card = parse_card({"name": "Invasion of Test // Back", "layout": "transform", "card_faces": [
            {"name": "Invasion of Test", "mana_cost": "{1}{R}", "type_line": "Battle — Siege", "defense": "4",
             "oracle_text": "(As a Siege enters, choose an opponent to protect it. You and others can attack it. "
                            "When it's defeated, exile it, then cast it transformed.)\n"
                            "When this Siege enters, it deals 2 damage to target creature."},
            {"name": "Back", "mana_cost": "", "type_line": "Creature — Goblin", "power": "3", "toughness": "3",
             "oracle_text": ""}]})
        self.assertEqual(card.defense, 4)
        self.assertTrue(card.is_battle)
        self.assertEqual(card_coverage(card).status, "full")

    def test_non_siege_battle_unsupported(self):
        card = parse_card({"name": "Occupation of Test", "mana_cost": "{R}", "type_line": "Battle — Control Point",
                           "defense": "2", "oracle_text": "{T}: Add {R}."})
        self.assertEqual(card_coverage(card).status, "partial")


if __name__ == "__main__":
    unittest.main()
