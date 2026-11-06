"""smol-chonk-3 batch 4: {X} ability costs, X-sized tokens, mana restrictions and X-quantities.

- {X} in an activated ability's mana cost parses (Cinder Elemental, engine chose the payable X
  since le-chonk-3); driven end to end off the parsed card.
- "Create an X/X ... creature token, where X is <known quantity>" parses to a token effect with
  the xq/xq_size data resolve.py scales (Abzan Monument).
- _mana_restriction grows the "legendary" / "x_cost" / "c_cost" kinds (Untaidake, Anina), and
  _xq the ("greatest_perm", ...), ("tapped_any", (...)) and ("defenders",) spec tuples.
"""
import random
import unittest

from mtgsim.cards.clauses import _xq
from mtgsim.cards.parse import _mana_restriction, _parse_effects
from mtgsim.engine import Game, Permanent, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, MOUNTAIN, card

CINDER = card("Cinder Elemental", "{3}{R}", "Creature — Elemental",
              "{X}{R}, {T}, Sacrifice Cinder Elemental: It deals X damage to any target.", 0, 2)
ABZAN = card("Abzan Monument", "{3}", "Artifact",
             "{1}{W}{B}{G}, {T}, Sacrifice Abzan Monument: Create an X/X white Spirit creature "
             "token, where X is the greatest toughness among creatures you control. "
             "Activate only as a sorcery.")
TOME = card("Test Tome", "{2}", "Artifact", "{X}: Draw X cards.")
UNTAIDAKE = card("Untaidake, the Cloud Keeper", "", "Legendary Land",
                 "{T}, Pay 2 life: Add {C}{C}. Spend this mana only to cast legendary spells.")
ANINA = card("Anina, Natural Parallelist", "{1}{G}{U}", "Creature — Human",
             "{T}: Add {G}{U}. Spend this mana only to cast spells with {X} in their mana costs.",
             2, 1)
ROSHEEN = card("Rosheen, Roaring Prophet", "{4}{R}{G}", "Creature — Giant",
               "{T}: Reveal any number of cards with {X} in their mana cost in your hand. Add {C}{C} "
               "for each card revealed this way. Spend this mana only on costs that contain {X}.",
               4, 5)
MOUNTAINS = [MOUNTAIN] * 10


class XAbilityCosts(unittest.TestCase):
    def test_x_cost_parses(self):
        self.assertEqual(CINDER.unsupported, [])
        act = CINDER.activated[0]
        self.assertEqual(act.cost, {"generic": 0, "X": 1, "R": 1})
        self.assertEqual(act.extra_costs, {"tap": True, "sac_self": True})
        self.assertEqual([(e.kind, e.target, e.data.get("x")) for e in act.effects],
                         [("damage", "any", True)])
        self.assertEqual(TOME.unsupported, [])
        self.assertEqual(TOME.activated[0].cost, {"generic": 0, "X": 1})

    def test_cinder_elemental_end_to_end(self):
        a, b = Player("a", [BEAR] * 20, Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 2, "main1", 0
        cinder = Permanent(CINDER, a)
        cinder.sick = False
        a.battlefield.append(cinder)
        for cdef in MOUNTAINS[:5]:
            land = Permanent(cdef, a)
            land.sick = False
            a.battlefield.append(land)
        self.assertEqual(game.ability_x(a, cinder, CINDER.activated[0]), 4)   # {X}{R}: 4 + 1
        self.assertTrue(game.can_activate(a, cinder, 0))
        self.assertTrue(game.activate(a, cinder, "ability:0", target=[b]))
        game.settle()
        self.assertEqual(b.life, 20 - 4)
        self.assertNotIn(cinder, a.battlefield)          # sacrificed as part of the cost


class XSizedToken(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(ABZAN.unsupported, [])
        eff = ABZAN.activated[0].effects[0]
        self.assertEqual(eff.kind, "token")
        self.assertEqual(eff.data["name"], "Spirit")
        self.assertEqual(eff.data["xq"], ("greatest", "toughness"))
        self.assertTrue(eff.data["xq_size"])

    def test_token_size_end_to_end(self):
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 2, "main1", 0
        mon = Permanent(ABZAN, a)
        mon.sick = False
        a.battlefield.append(mon)
        big = Permanent(card("Test Big", "{5}{G}", "Creature — Beast", "", 6, 5), a)
        big.sick = False
        a.battlefield.append(big)
        for name, t in (("p", "Basic Land — Plains"), ("s", "Basic Land — Swamp"),
                        ("f", "Basic Land — Forest"), ("f2", "Basic Land — Forest")):
            land = Permanent(card(name, types=t), a)
            land.sick = False
            a.battlefield.append(land)
        self.assertTrue(game.activate(a, mon, "ability:0"))
        game.settle()
        spirits = [t for t in a.battlefield if t.card.is_token]
        self.assertEqual([(s.power, s.toughness) for s in spirits], [(5, 5)])   # Big's toughness


class ManaRestrictions(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(_mana_restriction("to cast legendary spells"), "legendary")
        self.assertEqual(_mana_restriction("to cast spells with {X} in their mana costs"), "x_cost")
        self.assertEqual(_mana_restriction("on costs that contain {X}"), "x_cost")
        self.assertEqual(_mana_restriction("on costs that contain {C}"), "c_cost")

    def test_lines(self):
        self.assertEqual(UNTAIDAKE.unsupported, [])
        self.assertEqual(UNTAIDAKE.mana_restriction, "legendary")
        self.assertEqual(UNTAIDAKE.restricted_amount, 2)
        self.assertEqual(UNTAIDAKE.approximations, ["the 2 life for restricted mana isn't paid"])
        self.assertEqual(ANINA.unsupported, [])
        self.assertEqual(ANINA.mana_restriction, "x_cost")


class XQuantities(unittest.TestCase):
    def test_specs(self):
        self.assertEqual(_xq("the greatest mana value among permanents you control"),
                         ("greatest_perm", "mana value"))
        self.assertEqual(_xq("the greatest power among permanents you control"),
                         ("greatest_perm", "power"))
        self.assertEqual(_xq("the number of tapped artifacts and/or creatures you control"),
                         ("tapped_any", ("artifact", "creature")))
        self.assertEqual(_xq("the number of creatures you control with defender"), ("defenders",))

    def test_where_x_is_phrase(self):
        effects, bad = _parse_effects("Put a number of +1/+1 counters on ~ equal to the greatest "
                                      "mana value among permanents you control.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].kind, "p1_counters")
        self.assertEqual(effects[0].data["xq"], ("greatest_perm", "mana value"))


if __name__ == "__main__":
    unittest.main()
