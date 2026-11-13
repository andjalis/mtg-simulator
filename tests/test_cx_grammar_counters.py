"""cx_grammar_counters.py: counter placement composed with selectors, conditions and coordinated clauses."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from mtgsim.engine.state import Permanent
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

import dataclasses
PW = dataclasses.replace(card("Test Walker", "{2}{U}", "Planeswalker — Test", ""), loyalty=5)
EQUIP = card("Test Ring", "{2}", "Artifact — Equipment", "Equip {1}")


def effects(text):
    effs, bad = _parse_effects(text)
    assert not bad, bad
    return effs


def refuses(text):
    effs, bad = _parse_effects(text)
    assert bad and not effs, (text, effs)
    return bad


class Parsing(unittest.TestCase):
    def test_conditional_placement_on_the_source(self):
        # "if ~ has fewer than three charge counters on it, put a charge counter on it"
        effs = effects("If ~ has fewer than three charge counters on it, put a charge counter on it.")
        self.assertEqual([(e.kind, e.amount, e.target) for e in effs], [("add_counter", 1, "self")])
        self.assertEqual(effs[0].cond, 'lib:["counters","charge","<",3]')
        self.assertEqual(effs[0].data["counter"], "charge")
        # "if ~ didn't attack this turn, put a +1/+1 counter on it"
        effs = effects("If ~ didn't attack this turn, put a +1/+1 counter on it.")
        self.assertEqual([(e.kind, e.target) for e in effs], [("p1_counters", "self")])
        self.assertEqual(effs[0].cond, '!lib:["src_attacked_turn"]')
        # "if ~ dealt damage to an opponent this turn, put a +1/+1 counter on it"
        effs = effects("If ~ dealt damage to an opponent this turn, put a +1/+1 counter on it.")
        self.assertEqual(effs[0].cond, 'lib:["src_damaged_opp"]')

    def test_trailing_condition(self):
        effs = effects("Put a +1/+1 counter on equipped creature if it's blue.")
        self.assertEqual([(e.kind, e.target) for e in effs], [("add_counter", "host")])
        self.assertEqual(effs[0].cond, 'lib:["host_is",{"colors":["U"]}]')
        effs = effects("Then put two +1/+1 counters on that permanent if you control an artifact and an enchantment.")
        self.assertEqual([(e.kind, e.amount, e.target) for e in effs], [("add_counter", 2, "prev")])
        self.assertTrue(effs[0].cond.startswith('lib:["and"'))
        # "it" is the object just named, not the trigger's referent
        effs = effects("Put a +1/+1 counter on it if it's a creature.")
        self.assertEqual(effs[0].cond, 'lib:["prev_is",{"types":["creature"]}]')
        effs = effects("Put a loyalty counter on it if it's a planeswalker.")
        self.assertEqual(effs[0].cond, 'lib:["prev_is",{"types":["planeswalker"]}]')
        self.assertEqual(effs[0].data["counter"], "loyalty")

    def test_coordinated_clauses(self):
        effs = effects("Put a +1/+1 counter on that creature and a +1/+1 counter on ~.")
        self.assertEqual([(e.kind, e.target, e.data["counter"]) for e in effs],
                         [("add_counter", "prev", "+1/+1"), ("add_counter", "self", "+1/+1")])
        # group placement with coordinated clauses and distinct counter kinds
        effs = effects("Put five +1/+1 counters on each creature you control and five loyalty counters on "
                       "each other planeswalker you control.")
        self.assertEqual([(e.kind, e.data["effect"].kind, e.data["effect"].amount, e.data["effect"].data["counter"])
                          for e in effs],
                         [("permanent_group", "add_counter", 5, "+1/+1"),
                          ("permanent_group", "add_counter", 5, "loyalty")])
        self.assertEqual(effs[1].data["selector"]["other"], True)
        # a list of targets with their own amounts; the ordinal is "another"
        effs = effects("Put a +1/+1 counter on target creature, two +1/+1 counters on another target creature, "
                       "and three +1/+1 counters on a third target creature.")
        self.assertEqual([(e.amount, e.target, e.data.get("distinct")) for e in effs],
                         [(1, "permanent", True), (2, "permanent", True), (3, "permanent", True)])
        self.assertTrue(all(e.data["selector"].get("other") for e in effs[1:]))
        # a placement next to another verb: the compound split keeps both effects
        effs = effects("Put a +1/+1 counter on it and tap up to one target creature.")
        self.assertEqual([(e.kind, e.target) for e in effs], [("p1_counters", "prev"), ("tap", "creature")])
        self.assertTrue(effs[1].data["optional_target"])

    def test_single_choice_from_a_group(self):
        effs = effects("Put a vigilance counter on a creature you control.")
        self.assertEqual([(e.kind, e.amount, e.target) for e in effs], [("add_counter", 1, "permanent")])
        self.assertEqual(effs[0].data["selector"], {"controller": "mine", "types_all": ["creature"]})
        self.assertEqual(effs[0].data["counter"], "vigilance")

    def test_chained_then(self):
        effs = effects("Create a 2/1 white Cat Warrior creature token, then put a vigilance counter on a creature "
                       "you control.")
        self.assertEqual([e.kind for e in effs], ["token", "add_counter"])

    def test_near_misses_stay_unmatched(self):
        # referent groups ("each of them") are the target-list lane, referent quantities the #313 lane
        refuses("Put a +1/+1 counter on each of them.")
        refuses("Put a +1/+1 counter on a creature you control if you feel lucky.")
        # an unknown trailing condition is not guessed
        refuses("Put a +1/+1 counter on ~ if you feel lucky.")
        # quoted ability grants are a separate dependency: a counter phrase inside the quote is not ours
        refuses('Commander creatures you own have "Whenever ~ attacks a player, if no opponent has more life than '
                'that player, put a +1/+1 counter on ~."')


class Engine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def resolve(self, text, source=None, context=None, targets=None, card_def=None):
        effs = effects(text)
        c = card_def or card("Test Spell", "{1}", "Sorcery", text)
        item = StackItem(self.a, effs, [None] * len(effs), card=None if source else c,
                         source=source, context=context, kind="trigger" if source else "spell", name=c.name)
        if targets is None:
            targets = self.game.auto_targets(self.a, effs, source=item)
        item.targets = targets
        self.game.stack.append(item)
        self.game.resolve_top()
        return effs

    def test_counters_condition_true_and_false(self):
        post = self.perm(card("Test Post", "{2}", "Artifact",
                              "Whenever you cast an instant or sorcery spell, if ~ has fewer than three charge "
                              "counters on it, put a charge counter on it."), self.a)
        self.resolve("If ~ has fewer than three charge counters on it, put a charge counter on it.", source=post)
        self.assertEqual(post.counters.get("charge", 0), 1)
        post.counters["charge"] = 3
        self.resolve("If ~ has fewer than three charge counters on it, put a charge counter on it.", source=post)
        self.assertEqual(post.counters["charge"], 3)          # the condition is false: nothing is put
        # the placed counter is a real counter: proliferate adds another of the same kind
        self.game.proliferate(self.a)
        self.assertEqual(post.counters["charge"], 4)

    def test_did_not_attack_condition(self):
        bird = self.perm(card("Test Bird", "{1}{U}", "Creature — Bird", "Flying", "", 1, 1), self.a)
        self.resolve("If ~ didn't attack this turn, put a +1/+1 counter on it.", source=bird)
        self.assertEqual(bird.counters.get("+1/+1", 0), 1)
        bird.counters["+1/+1"] = 0
        bird.attack_count = (self.game.turn, 1)               # it attacked this turn
        self.resolve("If ~ didn't attack this turn, put a +1/+1 counter on it.", source=bird)
        self.assertEqual(bird.counters.get("+1/+1", 0), 0)

    def test_dealt_damage_condition(self):
        outlaw = self.perm(card("Test Outlaw", "{1}{B}", "Creature — Human", "", "", 2, 1), self.a)
        self.resolve("If ~ dealt damage to an opponent this turn, put a +1/+1 counter on it.", source=outlaw)
        self.assertEqual(outlaw.counters.get("+1/+1", 0), 0)  # no damage yet
        self.game.deal_damage(self.b, 2, self.a, source=outlaw)
        self.resolve("If ~ dealt damage to an opponent this turn, put a +1/+1 counter on it.", source=outlaw)
        self.assertEqual(outlaw.counters.get("+1/+1", 0), 1)

    def test_group_placement_distinct_kinds(self):
        pw = self.perm(PW, self.a)
        other_pw = self.perm(PW, self.a)
        pw.counters["loyalty"] = other_pw.counters["loyalty"] = 5   # planeswalkers enter with loyalty
        bears = [self.perm(BEAR, self.a) for _ in range(2)]
        [self.perm(BEAR, self.b)]
        self.resolve("Put five +1/+1 counters on each creature you control and five loyalty counters on each "
                     "other planeswalker you control.", source=pw)
        self.assertEqual([b.counters.get("+1/+1", 0) for b in bears], [5, 5])
        self.assertEqual(other_pw.counters.get("loyalty", 0), 10)
        self.assertEqual(pw.counters.get("loyalty", 0), 5)      # ~ is not "each other"
        self.assertEqual(sum(b.counters.get("+1/+1", 0) for b in self.b.battlefield), 0)

    def test_coordinated_previous_object(self):
        ranger = self.perm(card("Test Ranger", "{3}{G}", "Creature — Human Ranger", "", 2, 2), self.a)
        entering = self.perm(BEAR, self.a)
        self.resolve("Put a +1/+1 counter on that creature and a +1/+1 counter on ~.",
                     source=ranger, context=entering)
        self.assertEqual(entering.counters.get("+1/+1", 0), 1)
        self.assertEqual(ranger.counters.get("+1/+1", 0), 1)

    def test_three_targets_get_their_own_amounts(self):
        bears = [self.perm(BEAR, self.a) for _ in range(4)]
        effs = effects("Put a +1/+1 counter on target creature, two +1/+1 counters on another target creature, "
                       "and three +1/+1 counters on a third target creature.")
        targets = self.game.auto_targets(self.a, effs, source=StackItem(self.a, effs, [None] * 3))
        self.assertEqual(len({id(t) for t in targets}), 3)     # distinct targets
        for e, t in zip(effs, targets):
            self.game.resolve(self.a, e, t)
        self.assertEqual(sorted(b.counters.get("+1/+1", 0) for b in bears), [0, 1, 2, 3])

    def test_host_condition_color(self):
        ring = self.perm(EQUIP, self.a)
        blue = self.perm(card("Test Blue", "{U}", "Creature — Human", "", 1, 1), self.a)
        red = self.perm(card("Test Red", "{R}", "Creature — Human", "", 1, 1), self.a)
        ring.attached_to = blue
        self.resolve("Put a +1/+1 counter on equipped creature if it's blue.", source=ring)
        self.assertEqual((blue.counters.get("+1/+1", 0), red.counters.get("+1/+1", 0)), (1, 0))
        ring.attached_to = red
        self.resolve("Put a +1/+1 counter on equipped creature if it's blue.", source=ring)
        self.assertEqual((blue.counters.get("+1/+1", 0), red.counters.get("+1/+1", 0)), (1, 0))

    def test_trailing_condition_on_the_previous_object(self):
        bear = self.perm(BEAR, self.a)
        rock = self.perm(card("Test Rock", "{1}", "Artifact", "", ), self.a)
        for obj in (bear, rock):
            effs = effects("Target permanent you control gains hexproof until end of turn. "
                           "Put a +1/+1 counter on it if it's a creature.")
            item = StackItem(self.a, effs, [None] * len(effs), kind="trigger")
            targets = self.game.auto_targets(self.a, effs, source=item)
            targets[0] = obj
            self.game.stack.append(StackItem(self.a, effs, targets, kind="trigger"))
            self.game.resolve_top()
        self.assertEqual(bear.counters.get("+1/+1", 0), 1)
        self.assertEqual(rock.counters.get("+1/+1", 0), 0)      # not a creature: no counter

    def test_chained_then_places_on_my_creature(self):
        bear = self.perm(BEAR, self.a)
        [self.perm(BEAR, self.b)]
        c = card("Test Saga", "{2}{W}", "Enchantment — Saga",
                 "II — Create a 2/1 white Cat Warrior creature token, then put a vigilance counter on a creature "
                 "you control.")
        self.assertEqual(c.unsupported, [])
        self.resolve("Create a 2/1 white Cat Warrior creature token, then put a vigilance counter on a creature "
                     "you control.")
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((token.power, token.toughness), (2, 1))
        self.assertEqual(bear.counters.get("vigilance", 0), 1)
        self.assertEqual(sum(x.counters.get("vigilance", 0) for x in self.b.battlefield), 0)


class AiChoice(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [ISLAND] * 20, HeuristicAI()), Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0
        for _ in range(4):
            self.a.battlefield.append(Permanent(ISLAND, self.a))

    def test_single_choice_aims_at_my_creature(self):
        mine = [Permanent(BEAR, self.a) for _ in range(2)]
        self.a.battlefield.extend(mine)
        theirs = [Permanent(BEAR, self.b) for _ in range(2)]
        self.b.battlefield.extend(theirs)
        c = card("Test Gift", "{1}{U}", "Sorcery", "Put a vigilance counter on a creature you control.")
        self.assertEqual(c.unsupported, [])
        self.a.hand.append(c)
        self.game.main_phase(self.a)
        self.assertEqual([x.counters.get("vigilance", 0) for x in mine], [1, 0])
        self.assertEqual([x.counters.get("vigilance", 0) for x in theirs], [0, 0])


if __name__ == "__main__":
    unittest.main()
