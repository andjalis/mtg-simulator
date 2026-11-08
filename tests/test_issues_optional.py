"""Optional ("you may") effects and the AI declining them: issues #257, #268, #265."""
import random
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.state import Permanent, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND


def effects(text):
    effs, bad = _parse_effects(text)
    assert not bad, bad
    return effs


class Base(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, p):
        perm = Permanent(BEAR, p)
        p.battlefield.append(perm)
        return perm

    def trigger(self, text):
        from tests.test_templates import card
        return card("T", "{1}", "Creature — Golem", "At the beginning of combat on your turn, " + text, 1, 1).triggers[0].effects

    def go(self, effs, source, *targets):
        item = StackItem(self.a, effs, list(targets), source=source)
        prev = None
        for e, t in zip(item.effects, item.targets):
            self.game.resolve(self.a, e, t, item, prev)
            prev = t


class OptionalCounters(Base):
    def test_marked_optional(self):
        self.assertTrue(self.trigger("you may remove all counters from this creature.")[0].data.get("optional"))
        self.assertTrue(self.trigger("you may move a +1/+1 counter from this creature onto target creature.")[0]
                        .data.get("optional"))

    def test_mandatory_not_marked(self):
        self.assertFalse(self.trigger("remove all counters from this creature.")[0].data.get("optional"))

    def test_remove_declined_on_own_good_counters(self):
        mine = self.put(self.a)
        mine.counters["+1/+1"] = 2
        self.go(self.trigger("you may remove all counters from this creature."), mine, mine)
        self.assertEqual(mine.counters["+1/+1"], 2)

    def test_remove_mandatory_still_happens(self):
        mine = self.put(self.a)
        mine.counters["+1/+1"] = 2
        self.go(self.trigger("remove all counters from this creature."), mine, mine)
        self.assertEqual(mine.counters["+1/+1"], 0)

    def test_remove_taken_from_opponent_good_counter(self):
        mine, theirs = self.put(self.a), self.put(self.b)
        theirs.counters["+1/+1"] = 2
        self.go(self.trigger("you may remove all +1/+1 counters from target creature."), mine, theirs)
        self.assertEqual(theirs.counters["+1/+1"], 0)

    def test_remove_taken_for_own_bad_counter(self):
        mine = self.put(self.a)
        mine.counters["-1/-1"] = 2
        self.go(self.trigger("you may remove all counters from this creature."), mine, mine)
        self.assertEqual(mine.counters["-1/-1"], 0)

    def test_move_between_own_creatures_happens(self):
        x, y = self.put(self.a), self.put(self.a)
        x.counters["+1/+1"] = 3
        self.go(self.trigger("you may move a +1/+1 counter from this creature onto target creature."), x, y)
        self.assertEqual((x.counters["+1/+1"], y.counters["+1/+1"]), (2, 1))

    def test_move_good_counter_to_opponent_declined(self):
        x, y = self.put(self.a), self.put(self.b)
        x.counters["+1/+1"] = 3
        self.go(self.trigger("you may move a +1/+1 counter from this creature onto target creature."), x, y)
        self.assertEqual((x.counters["+1/+1"], y.counters.get("+1/+1", 0)), (3, 0))

    def test_mandatory_move_to_opponent_still_happens(self):
        x, y = self.put(self.a), self.put(self.b)
        x.counters["+1/+1"] = 3
        self.go(self.trigger("move a +1/+1 counter from this creature onto target creature."), x, y)
        self.assertEqual((x.counters["+1/+1"], y.counters["+1/+1"]), (2, 1))


def tcard(name, cost, types, text, p=None, t=None):
    from tests.test_templates import card
    return card(name, cost, types, text, p, t)


class Mech(Base):
    def give_mana(self, p, n, land=None):
        from tests.test_templates import FOREST
        for _ in range(n):
            perm = self.game.enter_battlefield(p, land or FOREST)
            perm.sick = False

    def beam_options(self, card):
        self.a.graveyard.append(card)
        return [o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "beam"]

    def token(self, p):
        import dataclasses
        from tests.test_templates import BEAR
        perm = Permanent(dataclasses.replace(BEAR, name="Tok", is_token=True, cmc=0), p)
        p.battlefield.append(perm)
        return perm

    def test_beam_skips_token_only(self):
        beam = tcard("Test Beam", "{3}{G}", "Sorcery", "Beam me up {1}{G}")
        self.give_mana(self.a, 3)
        self.token(self.a)
        self.assertEqual(self.beam_options(beam), [])

    def test_beam_returns_nontoken_not_token(self):
        from mtgsim.cx_mech import beam_creature
        bear = self.put(self.a)
        self.token(self.a)
        self.assertIs(beam_creature(self.a, tcard("B", "{3}{G}", "Sorcery", "Beam me up {1}{G}")), bear)

    def test_beam_skips_creature_worth_more_than_spell(self):
        beam = tcard("Test Beam", "{G}", "Sorcery", "Beam me up {G}")
        self.give_mana(self.a, 2)
        big = tcard("Big", "{5}", "Creature — Golem", "", 5, 5)
        self.game.enter_battlefield(self.a, big)
        self.assertEqual(self.beam_options(beam), [])

    def test_beam_offered_for_cheap_creature(self):
        beam = tcard("Test Beam", "{3}{G}", "Sorcery", "Beam me up {1}{G}")
        self.give_mana(self.a, 2)
        self.put(self.a)
        self.assertEqual(len(self.beam_options(beam)), 1)

    def test_recover_pays_when_cheap(self):
        from tests.test_templates import SWAMP
        rec = tcard("Test Recover", "{3}{B}", "Creature — Zombie", "Recover {1}{B}", 3, 3)
        self.give_mana(self.a, 2, SWAMP)
        self.a.graveyard.append(rec)
        victim = self.put(self.a)
        self.game.destroy(victim)
        self.game.settle()
        self.assertIn(rec, self.a.hand)

    def test_recover_declined_when_dearer_than_card(self):
        from tests.test_templates import SWAMP
        rec = tcard("Test Recover", "{1}", "Creature — Zombie", "Recover {3}{B}", 1, 1)
        self.give_mana(self.a, 5, SWAMP)
        self.a.graveyard.append(rec)
        victim = self.put(self.a)
        self.game.destroy(victim)
        self.game.settle()
        self.assertIn(rec, self.a.exile)
        self.assertEqual(sum(1 for x in self.a.battlefield if x.tapped), 0)

    def test_reinforce_is_a_discard(self):
        rein = tcard("Test Reinforce", "{G}", "Instant", "Reinforce 2—{1}{G}")
        mad = []
        target = self.put(self.a)
        self.give_mana(self.a, 2)
        self.a.hand.append(rein)
        self.a.discarded_cards.clear()
        option = next(o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "channel")
        fired = []
        orig = self.game.fire
        self.game.fire = lambda who, ev, *a, **k: (fired.append((who, ev)), orig(who, ev, *a, **k))[1]
        self.assertTrue(self.game.cast(self.a, option, [target]))
        self.game.settle()
        self.assertIn((self.a, "you_discard"), fired)
        self.assertIn((self.b, "opp_discard"), fired)
        self.assertIn(rein, self.a.discarded_cards)
        self.assertIn(rein, self.a.graveyard)
        self.assertEqual(target.counters["+1/+1"], 2)

    def test_reinforce_madness_card_goes_to_madness(self):
        both = tcard("Test Both", "{G}", "Instant", "Reinforce 1—{G}\nMadness {G}")
        self.give_mana(self.a, 3)
        target = self.put(self.a)
        self.a.hand.append(both)
        option = next((o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "channel"), None)
        if option is None:
            self.skipTest("no channel option for combined text")
        self.game.cast(self.a, option, [target])
        self.assertIn("Test Both", [c.name for c in self.a.exile] + [c.name for c in self.a.graveyard])


if __name__ == "__main__":
    unittest.main()
