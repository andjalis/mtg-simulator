"""Exchange of control between two permanents (#334, mtgsim.cx_exchange)."""
import unittest

from mtgsim import counter_mechanics
from mtgsim.cards import _parse_effects
from mtgsim.engine import Permanent, StackItem
from mtgsim.engine.policy import ability_worth
from mtgsim.cx_exchange import pair_ok
from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 5, 5)
ROCK = card("Test Rock", "{2}", "Artifact", "")
AURA = card("Test Shell", "{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.")
TOTEM = card("Test Totem", "{2}", "Artifact", "{5}: Exchange control of ~ and target nonland permanent.")
CRAB = card("Test Crab", "{3}{U}", "Creature — Crab", "When ~ enters, you may exchange control of target creature "
            "you control and target creature an opponent controls.", 3, 3)
PLOTTER = card("Test Plotter", "{2}{U}", "Creature — Vedalken", "When ~ enters, exchange control of target land you "
               "control and target land an opponent controls.", 1, 1)


def kinds(text):
    effects, ignored = _parse_effects(text)
    return None if ignored else [e.kind for e in effects]


class Parsing(unittest.TestCase):
    def test_shapes(self):
        for text, want in (
                ("Exchange control of ~ and target nonland permanent.", ["cx_exchange"]),
                ("Exchange control of target creature you control and target creature an opponent controls.",
                 ["cx_exchange_mark", "cx_exchange"]),
                ("Exchange control of two target creatures.", ["cx_exchange_mark", "cx_exchange"]),
                ("Exchange control of two target permanents that share a card type.",
                 ["cx_exchange_mark", "cx_exchange"]),
                ("You may exchange control of two other target creatures controlled by different players.",
                 ["cx_exchange_mark", "cx_exchange"]),
                ("You may exchange control of ~ and target permanent you neither own nor control.", ["cx_exchange"])):
            self.assertEqual(kinds(text), want, text)

    def test_relations_and_options(self):
        effects, _ = _parse_effects("You may exchange control of target nonland permanent you control and target "
                                    "permanent an opponent controls that shares a card type with it.")
        self.assertEqual(effects[1].data["cx_pair"], ["share_card"])
        self.assertTrue(all(e.data["optional"] for e in effects))
        effects, _ = _parse_effects("Exchange control of target artifact or creature and another target permanent "
                                    "that shares one of those types with it.")
        self.assertEqual(effects[1].data["cx_pair"], ["share:artifact,creature"])
        effects, _ = _parse_effects("You may exchange control of target creature you control and target creature "
                                    "with power less than or equal to that creature's power an opponent controls.")
        self.assertEqual(effects[1].data["cx_pair"], ["power_le"])
        effects, _ = _parse_effects("Exchange control of ~ and target permanent you neither own nor control.")
        self.assertEqual(effects[0].data["selector"]["owner"], "opp")
        self.assertNotIn("optional", effects[0].data)

    def test_near_misses_stay_unsupported(self):
        for text in ("Exchange control of ~ and up to one target creature an opponent controls.",   # Gilded Drake
                     "Exchange control of target noncreature spell and target creature.",
                     "You may exchange control of ~ and that spell.",
                     "Exchange control of target creature and another target creature.",           # "another" alone
                     "Exchange control of up to two target creatures.",
                     "Exchange control of ~ and target creature that shares one of those types with it."):
            self.assertIsNone(kinds(text), text)

    @unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
    def test_cards_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Avarice Totem", "Chromeshell Crab", "Daring Thief", "Conjured Currency", "Switcheroo",
                     "Kitsune, Dragon's Daughter", "Shifting Loyalties", "Vedalken Plotter", "Spawnbroker"):
            self.assertEqual(db.get(name).unsupported, [], name)
        self.assertTrue(db.get("Gilded Drake").unsupported)


class Engine(Base):
    def item(self, effects, targets, source=None, kind="ability"):
        return StackItem(self.a, list(effects), list(targets), source=source, kind=kind)

    def go(self, item):
        self.game.stack.append(item)
        self.game.resolve_top()

    def test_source_and_target_swap_and_last(self):
        totem, giant = self.perm(TOTEM, self.a), self.perm(BIG, self.b)
        giant.sick = False
        self.go(self.item(totem.activated[0].effects, [giant], totem))
        self.assertIs(giant.controller, self.a)
        self.assertIs(totem.controller, self.b)
        self.assertIs(giant.owner, self.b)          # owner unchanged
        self.assertTrue(giant.sick)                 # summoning sick under its new controller
        counter_mechanics.expire_source_control(self.game, cleanup=True)
        self.assertIs(giant.controller, self.a)     # indefinite, survives cleanup

    def test_two_explicit_targets(self):
        switch = self.spell("Exchange control of two target creatures.", "Sorcery")
        bear, giant = self.perm(BEAR, self.a), self.perm(BIG, self.b)
        self.cast(switch, [bear, giant])
        self.assertIs(bear.controller, self.b)
        self.assertIs(giant.controller, self.a)

    def test_same_controller_does_nothing(self):
        switch = self.spell("Exchange control of two target creatures.", "Sorcery")
        bear, giant = self.perm(BEAR, self.b), self.perm(BIG, self.b)
        self.cast(switch, [bear, giant])
        self.assertIs(bear.controller, self.b)
        self.assertIs(giant.controller, self.b)

    def test_no_half_exchange_when_an_object_leaves(self):
        switch = self.spell("Exchange control of two target creatures.", "Sorcery")
        for gone in (0, 1):
            bear, giant = self.perm(BEAR, self.a), self.perm(BIG, self.b)
            pair = [bear, giant]
            self.game.leave_battlefield(pair[gone], "graveyard")
            self.cast(switch, pair)
            stay = pair[1 - gone]
            self.assertIs(stay.controller, stay.owner, gone)
            stay.controller.battlefield.remove(stay)

    def test_first_target_illegal_on_resolution(self):
        trade = self.spell("Exchange control of target creature you control and target creature an opponent "
                           "controls.", "Sorcery")
        bear, giant = self.perm(BEAR, self.a), self.perm(BIG, self.b)
        counter_mechanics.add_control(self.game, bear, self.b)      # no longer "a creature you control"
        self.cast(trade, [bear, giant])
        self.assertIs(bear.controller, self.b)
        self.assertIs(giant.controller, self.b)

    def test_source_gone_no_exchange(self):
        totem, giant = self.perm(TOTEM, self.a), self.perm(BIG, self.b)
        item = self.item(totem.activated[0].effects, [giant], totem)
        self.game.leave_battlefield(totem, "graveyard")
        self.go(item)
        self.assertIs(giant.controller, self.b)

    def test_shared_card_type(self):
        loyal = self.spell("Exchange control of two target permanents that share a card type.", "Sorcery")
        rock, giant, bear = self.perm(ROCK, self.a), self.perm(BIG, self.b), self.perm(BEAR, self.a)
        with self.game.targeting(loyal):
            self.game._choosing_targets = [rock]
            legal = self.game.legal_targets(self.a, loyal.spell_effects[1])
            self.game._choosing_targets = []
        self.assertNotIn(giant, legal)
        self.cast(loyal, [rock, giant])             # no shared type: the second target is illegal
        self.assertIs(rock.controller, self.a)
        self.assertIs(giant.controller, self.b)
        self.cast(loyal, [bear, giant])
        self.assertIs(bear.controller, self.b)
        self.assertIs(giant.controller, self.a)
        self.assertTrue(pair_ok(bear, giant, ["share_perm"]))
        self.assertFalse(pair_ok(rock, giant, ["share:artifact,creature"]))

    def test_different_players(self):
        effects, _ = _parse_effects("Exchange control of two other target creatures controlled by different players.")
        bear, wolf = self.perm(BEAR, self.b), self.perm(BIG, self.b)
        self.go(self.item(effects, [bear, wolf], None, "trigger"))
        self.assertIs(bear.controller, self.b)
        self.assertIs(wolf.controller, self.b)
        mine = self.perm(BEAR, self.a)
        self.go(self.item(effects, [mine, wolf], None, "trigger"))
        self.assertIs(mine.controller, self.b)
        self.assertIs(wolf.controller, self.a)

    def test_attachments_stay(self):
        totem, giant = self.perm(TOTEM, self.a), self.perm(BIG, self.b)
        aura = self.perm(AURA, self.b)
        aura.attached_to = giant
        self.go(self.item(totem.activated[0].effects, [giant], totem))
        self.assertIs(giant.controller, self.a)
        self.assertIs(aura.attached_to, giant)
        self.assertIs(aura.controller, self.b)

    def test_later_control_effect_wins_by_timestamp(self):
        totem, giant = self.perm(TOTEM, self.a), self.perm(BIG, self.b)
        self.go(self.item(totem.activated[0].effects, [giant], totem))
        counter_mechanics.add_control(self.game, giant, self.b, until_eot=True)   # a later threaten
        self.assertIs(giant.controller, self.b)
        counter_mechanics.expire_source_control(self.game, cleanup=True)
        self.assertIs(giant.controller, self.a)

    def test_optional_refusal(self):
        trig = CRAB.triggers[0].effects
        giant, bear = self.perm(BIG, self.a), self.perm(BEAR, self.b)
        self.assertEqual(self.game.auto_targets(self.a, trig), [None, None])   # nothing worth taking: declined
        self.go(self.item(trig, [giant, bear], None, "trigger"))            # a bad pair on resolution: declined
        self.assertIs(giant.controller, self.a)
        self.assertIs(bear.controller, self.b)

    def test_optional_favourable_trade(self):
        trig = CRAB.triggers[0].effects
        bear, giant = self.perm(BEAR, self.a), self.perm(BIG, self.b)
        targets = self.game.auto_targets(self.a, trig)
        self.assertEqual(targets, [bear, giant])
        self.go(self.item(trig, targets, None, "trigger"))
        self.assertIs(giant.controller, self.a)

    def test_mandatory_trigger_still_exchanges(self):
        trig = PLOTTER.triggers[0].effects
        mine, theirs = self.perm(ISLAND, self.a), self.perm(ISLAND, self.b)
        targets = self.game.auto_targets(self.a, trig)
        self.assertEqual(targets, [mine, theirs])
        self.go(self.item(trig, targets, None, "trigger"))
        self.assertIs(mine.controller, self.b)
        self.assertIs(theirs.controller, self.a)


class AIChoice(Base):
    def lands(self, n):
        for _ in range(n):
            land = self.perm(ISLAND, self.a)
            land.sick = False

    def test_activates_only_for_a_favourable_trade(self):
        self.lands(5)
        totem = self.perm(TOTEM, self.a)
        bear = self.perm(card("Test Mite", "", "Artifact Creature — Insect", "", 0, 1), self.b)
        self.assertFalse(ability_worth(self.game, self.a, totem, 0))
        giant = self.perm(BIG, self.b)
        self.assertTrue(ability_worth(self.game, self.a, totem, 0))
        self.assertTrue(self.game.activate_ability(self.a, totem, 0))
        self.game.settle()
        self.assertIs(giant.controller, self.a)
        self.assertIs(bear.controller, self.b)

    def test_casts_switch_giving_the_worst_for_the_best(self):
        switch = self.spell("Exchange control of two target creatures.", "Sorcery")
        bear, own_giant = self.perm(BEAR, self.a), self.perm(BIG, self.a)
        dragon = self.perm(card("Test Dragon", "{6}", "Creature — Dragon", "Flying", 6, 6), self.b)
        plan = self.a.ai.plan_spell(self.game, self.a, switch, True)
        self.assertIsNotNone(plan)
        self.assertEqual(plan[1], [bear, dragon])
        self.assertIsInstance(own_giant, Permanent)
        self.b.battlefield.remove(dragon)
        self.assertIsNone(self.a.ai.plan_spell(self.game, self.a, switch, True))   # nothing better to take


if __name__ == "__main__":
    unittest.main()
