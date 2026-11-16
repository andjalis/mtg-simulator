"""Blink, the rest of #318: type lists ("creatures and/or lands"), any number of targets, a return under an
opponent's control, with no control clause, or tapped and attacking; the default AI's blink targets."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.policy import default_choose_target
from mtgsim.cx_multi_target import choose_list

from tests.test_templates import BEAR, ISLAND, PLAINS, card

DB = Path(__file__).resolve().parents[1] / "mtgsim/data/cards.sqlite3"
ETB = card("Test Etb", "{2}", "Creature — Goblin", "When ~ enters, you gain 2 life.", 1, 1)
ETB_LAND = card("Test Etb Land", "", "Land", "When ~ enters, you gain 1 life.")
TOKEN = card("Test Token", "", "Token Creature — Soldier", "", 1, 1)
TOKEN.is_token = True
FLICKER2 = card("Test Ghostly", "{2}{U}", "Instant",
                "Exile two target artifacts, creatures, and/or lands you control, then return those cards to the "
                "battlefield under your control.")
PASS = card("Test Pass", "{2}{B}", "Creature — Demon",
            "{1}: Exile ~, then return it to the battlefield under an opponent's control.", 2, 2)
ATTACK = card("Test Attack", "{3}", "Creature — Elf",
              "Whenever ~ attacks, exile up to one target creature you own, then return it to the battlefield "
              "under your control tapped and attacking.", 2, 2)
MANY = card("Test Many", "{3}{W}", "Instant",
            "Exile any number of target nonland permanents you control, then return those cards to the "
            "battlefield under their owner's control.")


def unparsed(text):
    return _parse_effects(text)[1]


class Parse(unittest.TestCase):
    def test_written_cards(self):
        for c in (FLICKER2, PASS, ATTACK, MANY):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_shapes(self):
        effs, bad = _parse_effects("Exile ~, then return it to the battlefield.")
        self.assertEqual((bad, [(e.kind, e.target) for e in effs]), ([], [("blink", "self")]))
        self.assertFalse(effs[0].data["yours"] or effs[0].data["transformed"])
        effs, _ = _parse_effects("Exile ~, then return him to the battlefield under an opponent's control.")
        self.assertTrue(effs[0].data["opponent"])
        effs, _ = _parse_effects("Exile two target creatures and/or lands you control, then return them to the "
                                 "battlefield under their owner's control.")
        self.assertEqual([e.kind for e in effs], ["blink", "blink"])
        self.assertEqual(effs[0].data["selector"], {"controller": "mine", "types_any": ["creature", "land"]})
        self.assertTrue(all(e.data["distinct"] for e in effs))
        effs, _ = _parse_effects(MANY.oracle_text if hasattr(MANY, "oracle_text") else
                                 "Exile any number of target nonland permanents you control, then return those "
                                 "cards to the battlefield under their owner's control.")
        self.assertEqual((effs[0].kind, effs[0].data["probe"].kind), ("cx_multi", "blink"))

    def test_refusals(self):
        for text in (
                "Exile ~, then return it to the battlefield face down under its owner's control.",
                "Exile target creature, then return it to the battlefield under its owner's control with X +1/+1 "
                "counters on it, where X is the number of lands you control.",
                "Exile ~, then return it to the battlefield attached to target creature.",
                "Exile two target creatures and/or players you control, then return them to the battlefield "
                "under their owner's control."):
            with self.subTest(text=text):
                self.assertTrue(unparsed(text))

    @unittest.skipUnless(DB.exists(), "card database not built")
    def test_real_cards(self):
        db = CardDB(offline=True)
        for name in ("Ghostly Flicker", "Brago, King Eternal", "The Neutrinos", "Sol'Kanar the Tainted"):
            with self.subTest(name=name):
                self.assertEqual(db.get(name).unsupported, [])
        fishing = db.get("Lake-town Mariners // Gone Fishing").adventure
        self.assertEqual(fishing.unsupported, [])
        self.assertEqual([e.kind for e in fishing.spell_effects], ["blink", "blink"])
        # still partial: "face down"
        self.assertTrue(db.get("Shorecrasher Elemental").unsupported)
        # "exile it, then return it": the creature the ally trigger is about, ~ under a self head (#458)
        for name in ("Gossip's Talent", "Jecht, Reluctant Guardian // Braska's Final Aeon"):
            self.assertEqual(db.get(name).unsupported, [], name)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 20, HeuristicAI())
        self.b = Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main1"
        for land in (PLAINS, PLAINS, PLAINS, ISLAND, ISLAND, ISLAND):
            self.perm(land, self.a)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def named(self, player, name):
        return [x for x in player.battlefield if x.card.name == name]


class Resolve(Base):
    def test_two_targets_of_a_type_list_return_as_new_objects(self):
        creature, land = self.perm(ETB, self.a), self.perm(ETB_LAND, self.a)
        creature.counters["+1/+1"] = 2
        life = self.a.life
        self.a.hand = [FLICKER2]
        self.assertTrue(self.game.cast(self.a, FLICKER2, [creature, land]))
        self.game.settle()
        new_creature, new_land = self.named(self.a, "Test Etb"), self.named(self.a, "Test Etb Land")
        self.assertEqual((len(new_creature), len(new_land)), (1, 1))
        self.assertIsNot(new_creature[0], creature)
        self.assertEqual(new_creature[0].counters.get("+1/+1", 0), 0)
        self.assertEqual(self.a.life, life + 3)          # both enters abilities

    def test_return_under_an_opponents_control(self):
        demon = self.perm(PASS, self.a)
        self.assertTrue(self.game.activate(self.a, demon, "ability:0"))
        self.game.settle()
        self.assertEqual(self.named(self.a, "Test Pass"), [])
        new = self.named(self.b, "Test Pass")
        self.assertEqual(len(new), 1)
        self.assertIs(new[0].owner, self.a)

    def test_bare_return_puts_a_back_face_back_front_face_up(self):
        front = card("Test Saga Front", "{3}", "Creature — Human", "", 3, 3)
        front.back = card("Test Saga Back", "", "Enchantment — Saga",
                          "III — Exile ~, then return it to the battlefield.")
        self.assertEqual(front.back.unsupported, [])
        perm = self.game.enter_battlefield(self.a, front.back, physical_card=front)
        effs, _ = _parse_effects("Exile ~, then return it to the battlefield.")
        self.game.stack.append(StackItem(self.a, effs, [None], source=perm))
        self.game.settle()
        self.assertEqual(self.named(self.a, "Test Saga Back"), [])
        back = self.named(self.a, "Test Saga Front")
        self.assertEqual(len(back), 1)
        self.assertIs(back[0].front, perm.front)        # the same physical card, front face up
        self.assertIs(back[0].controller, self.a)

    def test_tapped_and_attacking_only_in_combat(self):
        elf, bear = self.perm(ATTACK, self.a), self.perm(ETB, self.a)
        trig = ATTACK.triggers[0]
        self.game.step = "declare_attackers"
        self.game.attackers.append(elf)
        self.game.stack.append(StackItem(self.a, list(trig.effects), [bear], source=elf))
        self.game.settle()
        new = self.named(self.a, "Test Etb")[0]
        self.assertIsNot(new, bear)
        self.assertTrue(new.tapped)
        self.assertIn(new, self.game.attackers)
        # outside combat it just enters tapped
        self.game.step = "main1"
        self.game.stack.append(StackItem(self.a, list(trig.effects), [new], source=elf))
        self.game.settle()
        newer = self.named(self.a, "Test Etb")[0]
        self.assertIsNot(newer, new)
        self.assertTrue(newer.tapped)
        self.assertNotIn(newer, self.game.attackers)

    def test_a_token_is_gone(self):
        token = self.perm(TOKEN, self.a)
        effs, _ = _parse_effects("Exile two target creatures and/or lands you control, then return them to the "
                                 "battlefield under their owner's control.")
        self.game.stack.append(StackItem(self.a, effs[:1], [token], source=None))
        self.game.settle()
        self.assertEqual(self.named(self.a, "Test Token"), [])

    def test_optional_blink_declines_to_lose_a_token_or_a_stolen_permanent(self):
        effs, _ = _parse_effects("You may exile target nonland permanent you control, then return it to the "
                                 "battlefield under its owner's control.")
        self.assertEqual([e.kind for e in effs], ["blink"])
        self.assertTrue(effs[0].data["optional"])
        token = self.perm(TOKEN, self.a)
        stolen = self.perm(ETB, self.a)
        stolen.owner = self.b
        for target in (token, stolen):
            self.game.stack.append(StackItem(self.a, effs, [target], source=None))
            self.game.settle()
            self.assertIn(target, self.a.battlefield)
        mine = self.perm(ETB, self.a)
        self.game.stack.append(StackItem(self.a, effs, [mine], source=None))
        self.game.settle()
        self.assertNotIn(mine, self.a.battlefield)
        self.assertEqual(len(self.named(self.a, "Test Etb")), 2)


class AIChoices(Base):
    def flicker(self, text="Exile target creature, then return it to the battlefield under its owner's control."):
        return _parse_effects(text)[0][0]

    def test_blinks_its_own_creature_with_an_enters_ability(self):
        mine = self.perm(ETB, self.a)
        self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        self.assertIs(default_choose_target(self.game, self.a, self.flicker()), mine)

    def test_exiles_an_opponents_token_when_nothing_of_its_own_gains(self):
        self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        token = self.perm(TOKEN, self.b)
        self.assertIs(default_choose_target(self.game, self.a, self.flicker()), token)

    def test_no_target_when_nothing_gains(self):
        self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        self.perm(TOKEN, self.a)
        self.assertIsNone(default_choose_target(self.game, self.a, self.flicker()))

    def test_return_under_your_control_steals(self):
        self.perm(ETB, self.a)
        theirs = self.perm(BEAR, self.b)
        eff = self.flicker("Exile target creature, then return it to the battlefield under your control.")
        self.assertIs(default_choose_target(self.game, self.a, eff), theirs)

    def test_any_number_skips_tokens_and_what_gains_nothing(self):
        one, two = self.perm(ETB, self.a), self.perm(ETB, self.a)
        self.perm(BEAR, self.a)
        self.perm(TOKEN, self.a)
        eff = MANY.spell_effects[0]
        self.assertEqual(set(map(id, choose_list(self.game, self.a, eff))), {id(one), id(two)})

    def test_ai_plans_ghostly_flicker_on_its_own_creatures(self):
        one, two = self.perm(ETB, self.a), self.perm(ETB, self.a)
        self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        plan = self.a.ai.plan_spell(self.game, self.a, FLICKER2)
        self.assertIsNotNone(plan)
        self.assertEqual({id(t) for t in plan[1]}, {id(one), id(two)})
        life = self.a.life
        self.a.hand = [FLICKER2]
        self.assertTrue(self.game.cast(self.a, FLICKER2, plan[1]))
        self.game.settle()
        self.assertEqual(self.a.life, life + 4)

    def test_second_required_target_is_a_harmless_one(self):
        one = self.perm(ETB, self.a)
        bear = self.perm(BEAR, self.a)
        self.perm(TOKEN, self.a)
        plan = self.a.ai.plan_spell(self.game, self.a, FLICKER2)
        self.assertIs(plan[1][0], one)
        second = plan[1][1]
        self.assertIs(second.controller, self.a)
        self.assertFalse(second.card.is_token)
        self.assertIsNot(second, one)
        self.assertIn(second.card.name, ("Plains", "Island", bear.card.name))

    @unittest.skipUnless(DB.exists(), "card database not built")
    def test_giving_itself_away_is_the_last_mode_chosen(self):
        from mtgsim import modal
        solkanar = CardDB(offline=True).get("Sol'Kanar the Tainted")
        source = self.perm(solkanar, self.a)
        self.perm(BEAR, self.b)
        modes = solkanar.triggers[0].modes
        order = []
        for _ in range(len(modes)):
            effects = modal.pick(self.game, self.a, modes, source, least=0)
            order.append(next(i for i, m in enumerate(modes) if m and effects and m[0] is effects[0]))
        self.assertEqual(order[-1], 3)          # "Exile ~, then return it under an opponent's control"
        self.assertEqual(sorted(order), [0, 1, 2, 3])


BATCH = card("Test Batch", "{1}", "Enchantment", "Whenever one or more creatures you control enter, you gain 1 life.")


class Simultaneous(Base):
    def test_counted_targets_return_together(self):
        self.perm(BATCH, self.a)
        one, two = self.perm(ETB, self.a), self.perm(ETB, self.a)
        life = self.a.life
        self.a.hand = [FLICKER2]
        self.assertTrue(self.game.cast(self.a, FLICKER2, [one, two]))
        self.game.settle()
        # two enters abilities (+4), one "one or more creatures enter" batch (+1), not two
        self.assertEqual(self.a.life, life + 5)
        self.assertEqual(len(self.named(self.a, "Test Etb")), 2)

    def test_any_number_return_together(self):
        self.perm(BATCH, self.a)
        one, two = self.perm(ETB, self.a), self.perm(ETB, self.a)
        life = self.a.life
        self.game.stack.append(StackItem(self.a, list(MANY.spell_effects), [(one, two)], card=MANY, name=MANY.name))
        self.game.settle()
        self.assertEqual(self.a.life, life + 5)

    def test_an_illegal_slot_does_not_stop_the_other(self):
        one, two = self.perm(ETB, self.a), self.perm(ETB, self.a)
        life = self.a.life
        self.game.stack.append(StackItem(self.a, list(FLICKER2.spell_effects), [one, two], card=FLICKER2,
                                         name=FLICKER2.name))
        self.a.battlefield.remove(two)            # gone before resolution
        self.game.settle()
        self.assertEqual(self.a.life, life + 2)


@unittest.skipUnless(DB.exists(), "card database not built")
class ExileIt(unittest.TestCase):
    """"Exile it, then return it": the ally creature (Gossip's Talent), or ~ itself (Jecht)."""
    def setUp(self):
        from tests.test_combat_triggers import Scripted
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
            p.ai.attack, p.ai.block = (), {}

    def put(self, c):
        perm = self.game.enter_battlefield(self.a, c)
        perm.sick = False
        self.game.settle()
        return perm

    def attack(self, *attackers):
        self.a.ai.attack = list(attackers)
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_gossips_talent_blinks_the_creature_that_hit(self):
        talent = self.put(self.db.get("Gossip's Talent"))
        talent.counters["level"] = 3
        goblin = self.put(ETB)
        life = self.a.life
        self.attack(goblin)
        new = [x for x in self.a.battlefield if x.card.name == "Test Etb"]
        self.assertEqual(len(new), 1)
        self.assertIsNot(new[0], goblin)
        self.assertEqual(self.a.life, life + 2)

    def test_gossips_talent_keeps_a_token(self):
        talent = self.put(self.db.get("Gossip's Talent"))
        talent.counters["level"] = 3
        token = self.put(TOKEN)
        self.attack(token)
        self.assertIn(token, self.a.battlefield)

    def test_jecht_blinks_itself_transformed(self):
        jecht = self.put(self.db.get("Jecht, Reluctant Guardian // Braska's Final Aeon"))
        self.attack(jecht)
        new = [x for x in self.a.battlefield if x.front is jecht.front]
        self.assertEqual(len(new), 1)
        self.assertIsNot(new[0], jecht)
        self.assertEqual(new[0].card.name, "Braska's Final Aeon")


if __name__ == "__main__":
    unittest.main()
