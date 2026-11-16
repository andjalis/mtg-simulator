"""#646 slice 3: Equip with a non-mana cost ("Equip—Pay 3 life."), read as the activated ability CR 702.6a defines
(mtgsim.kw_lines), and HeuristicAI's value of moving Equipment (auras.attach_value)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, MOUNTAIN, card

LASH = card("Test Lash", "{B}{B}", "Artifact — Equipment", "Equipped creature gets +2/+2.\nEquip—Pay 3 life.")
SWORD = card("Test Greatsword", "{1}{B}", "Artifact — Equipment",
             "Equipped creature gets +1/+1.\nEquip—Pay 3 life. Activate only once each turn.")
TOOLS = card("Test Tools", "{4}", "Artifact — Equipment", "Equipped creature gets +5/+5.\nEquip—Sacrifice a creature.")
GIANT = card("Test Giant", "{4}{R}", "Creature — Giant", "", 5, 5)
TOKEN = card("Spirit", "", "Token Creature — Spirit", "", 1, 1)


def equip_idx(perm):
    return next(i for i, a in enumerate(perm.activated) if any(e.kind == "attach_self" for e in a.effects))


class Parsing(unittest.TestCase):
    def test_positives(self):
        for c, extra in ((LASH, {"life": 3}), (SWORD, {"life": 3}), (TOOLS, {"sacrifice": "creature"})):
            self.assertEqual(c.unsupported, [], c.name)
            (act,) = c.activated
            self.assertEqual(act.extra_costs, extra)
            self.assertTrue(act.sorcery)
            self.assertEqual([e.kind for e in act.effects], ["attach_self"])
            self.assertEqual(act.effects[0].target, "creature_mine")
        self.assertTrue(SWORD.activated[0].once)
        self.assertFalse(LASH.activated[0].once)
        c = card("X", "{1}", "Artifact — Equipment", "Equip—{2}, Pay 2 life.")
        self.assertEqual((c.activated[0].cost.get("generic"), c.activated[0].extra_costs), (2, {"life": 2}))

    def test_refusals(self):
        for text in ("Equip—Pay {3} or discard a card.", "Equip—Pay 3 life. Activate only during combat.",
                     "Equip—Tell a joke."):
            c = card("X", "{1}", "Artifact — Equipment", text)
            self.assertTrue(c.unsupported, text)
            self.assertEqual(c.activated, [], text)
        c = card("X", "{1}", "Artifact — Equipment", "Equip—Pay {3} or discard a card.")
        self.assertEqual(c.unsupported, ["Equip—Pay {3} or discard a card."])       # kept as printed


class Engine(Base):
    def setUp(self):
        super().setUp()
        self.game.step = "main1"

    def test_pay_life_to_attach(self):
        """CR 702.6a: "[Cost]: Attach this permanent to target creature you control. Activate only as a sorcery.\""""
        bear = self.perm(BEAR, self.a)
        lash = self.perm(LASH, self.a)
        self.assertTrue(self.game.activate_ability(self.a, lash, equip_idx(lash), [bear]))
        self.assertIs(lash.attached_to, bear)
        self.assertEqual(self.a.life, 17)
        self.assertEqual((bear.power, bear.toughness), (4, 4))

    def test_only_as_a_sorcery_and_only_your_creatures(self):
        """CR 702.6a: sorcery timing; CR 702.6a "target creature you control"."""
        bear = self.perm(BEAR, self.a)
        lash = self.perm(LASH, self.a)
        self.game.step = "combat"
        self.assertFalse(self.game.activate_ability(self.a, lash, equip_idx(lash), [bear]))
        self.game.step = "main1"
        theirs = self.perm(BEAR, self.b)
        self.assertFalse(self.game.activate_ability(self.a, lash, equip_idx(lash), [theirs]))
        self.assertEqual(self.a.life, 20)

    def test_once_each_turn(self):
        bear, giant = self.perm(BEAR, self.a), self.perm(GIANT, self.a)
        sword = self.perm(SWORD, self.a)
        self.assertTrue(self.game.activate_ability(self.a, sword, equip_idx(sword), [bear]))
        self.assertFalse(self.game.activate_ability(self.a, sword, equip_idx(sword), [giant]))
        self.assertEqual(self.a.life, 17)

    def test_sacrifice_cost(self):
        bear = self.perm(BEAR, self.a)
        token = self.perm(TOKEN, self.a)
        tools = self.perm(TOOLS, self.a)
        self.assertTrue(self.game.activate_ability(self.a, tools, equip_idx(tools), [bear]))
        self.assertNotIn(token, self.a.battlefield)
        self.assertIs(tools.attached_to, bear)
        self.assertEqual(bear.power, 7)


class HeuristicUse(Base):
    def test_ai_equips_once_and_does_not_repay(self):
        self.game.step = "main1"
        bear = self.perm(BEAR, self.a)
        bear.sick = False
        lash = self.perm(LASH, self.a)
        self.a.battlefield.append(Permanent(MOUNTAIN, self.a))
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertIs(lash.attached_to, bear)
        self.assertEqual(self.a.life, 17)
        self.a.ai.use_abilities(self.game, self.a)          # already on the only creature: not paid again
        self.game.settle()
        self.assertEqual(self.a.life, 17)

    def test_ai_moves_it_to_a_better_creature(self):
        self.game.step = "main1"
        bear = self.perm(BEAR, self.a)
        lash = self.perm(LASH, self.a)
        lash.attached_to = bear
        giant = self.perm(GIANT, self.a)
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertIs(lash.attached_to, giant)

    def test_ai_keeps_its_life_when_low(self):
        self.game.step = "main1"
        self.a.life = 6
        self.perm(BEAR, self.a)
        lash = self.perm(LASH, self.a)
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertIsNone(lash.attached_to)
        self.assertEqual(self.a.life, 6)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Demonmail Hauberk", "Dissection Tools", "Inventor's Axe", "Murderer's Axe",
                     "My Precious // Allure of Power", "Nightmare Lash", "Piston Sledge", "Sigil of Distinction",
                     "Dark Knight's Greatsword"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))

    def test_near_miss(self):
        from mtgsim.carddb import CardDB
        self.assertEqual(card_coverage(CardDB(offline=True).get("Bloodthorn Flail")).status, "partial")


if __name__ == "__main__":
    unittest.main()
