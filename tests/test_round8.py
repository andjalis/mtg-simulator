"""Speed, threaten, Mercenary tokens, Job select and small keyword lines."""
import unittest

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card
from tests.test_empower_discover import Base

RACER = card("Test Racer", "{1}{R}", "Creature — Goblin",
             "Start your engines!\nMax speed — ~ gets +1/+1 and has menace.", 2, 2)
THREAT = card("Test Threaten", "{2}{R}", "Sorcery",
              "Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.")
POSSE = card("Test Posse", "{X}{R}", "Sorcery",
             "Create X 1/1 red Mercenary creature tokens with \"{T}: Target creature you control gets +1/+0 until end of "
             "turn. Activate only as a sorcery.\"")
SWORD = card("Test Sword", "{2}", "Artifact — Equipment",
             "Job select\nEquipped creature gets +2/+2.\nEquip {2}")
GHOST = card("Test Ghost", "{1}{U}", "Creature — Spirit",
             "~ can't be blocked.\nYou have no maximum hand size.", 1, 1)
HUSK = card("Test Husk", "{2}", "Creature — Treefolk", "~ enters with two -1/-1 counters on it.", 4, 4)


class Round8(Base):
    def test_templates(self):
        for c in (RACER, THREAT, POSSE, SWORD, GHOST, HUSK):
            self.assertEqual(c.unsupported, [], c.name)

    def test_speed_starts_rises_and_gates_max_speed(self):
        racer = self.game.enter_battlefield(self.a, RACER)
        self.assertEqual(self.a.speed, 1)
        self.assertEqual(racer.power, 2)
        for turn in range(2, 5):
            self.game.turn = turn
            self.game.change_life(self.b, -1, "test")
        self.assertEqual(self.a.speed, 4)
        self.assertEqual((racer.power, racer.has("menace")), (3, True))

    def test_threaten_steals_until_cleanup(self):
        bear = self.perm(BEAR, self.b)
        self.game.resolve(self.a, THREAT.spell_effects[0], bear)
        self.assertIn(bear, self.a.battlefield)
        self.assertFalse(bear.sick)
        self.game.take_turn(self.b)
        self.assertIn(bear, self.b.battlefield)

    def test_mercenary_tokens_have_the_ability(self):
        from mtgsim.engine import StackItem
        item = StackItem(self.a, [], [], card=POSSE, kind="spell")
        item.x = 2
        self.game.resolve(self.a, POSSE.spell_effects[0], None, item)
        mercs = [x for x in self.a.battlefield if x.card.name == "Mercenary token"]
        self.assertEqual(len(mercs), 2)
        self.assertEqual(len(mercs[0].card.activated), 1)

    def test_job_select_makes_hero_and_attaches(self):
        sword = self.game.enter_battlefield(self.a, SWORD)
        self.game.settle()
        hero = next(x for x in self.a.battlefield if "Hero" in x.card.subtypes)
        self.assertIs(sword.attached_to, hero)
        self.assertEqual(hero.power, 3)

    def test_small_keywords(self):
        ghost = self.perm(GHOST)
        self.assertTrue(ghost.has("unblockable"))
        husk = self.game.enter_battlefield(self.a, HUSK)
        self.assertEqual(husk.power, 2)

    def test_optional_costs_that_draw(self):
        loot = card("Test Loot", "{1}", "Sorcery", "You may discard a card. If you do, draw two cards.")
        swarm = card("Test Swarm", "{1}", "Creature — Rat",
                     "When ~ enters, you may sacrifice another creature or artifact. If you do, draw a card.", 1, 1)
        for c in (loot, swarm):
            self.assertEqual(c.unsupported, [], c.name)
        self.a.hand = [ISLAND]
        self.a.library = [BEAR] * 5
        self.game.resolve(self.a, loot.spell_effects[0], None)
        self.assertEqual(len(self.a.hand), 2)
        token = self.game.enter_battlefield(self.a, __import__("mtgsim.cards", fromlist=["x"]).make_token("Food", 0, 0, (), None, "food", True))
        self.game.enter_battlefield(self.a, swarm)
        self.game.settle()
        self.assertNotIn(token, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 3)

    def test_pay_gate_follow_up_runs_only_when_paid(self):
        pup = card("Test Pangolin", "{1}", "Creature — Rat",
                   "Whenever ~ attacks, you may pay {1}. If you do, put a +1/+1 counter on ~.", 1, 1)
        self.assertEqual(pup.unsupported, [])
        from mtgsim.engine import StackItem
        src = self.perm(pup)
        effs = pup.triggers[0].effects
        self.assertEqual([e.kind for e in effs], ["pay_gate", "p1_counters"])
        self.perm(MOUNTAIN)
        item2 = StackItem(self.a, list(effs), [None, src], kind="trigger", source=src)
        for eff, tgt in zip(effs, item2.targets):
            if self.game.check_cond(self.a, eff, item2, None):
                self.game.resolve(self.a, eff, src if eff.kind != "pay_gate" else None, item2)
        self.assertEqual(src.p1, 1)


if __name__ == "__main__":
    unittest.main()
