"""#625: conditional free casts and the Traps' conditions (mtgsim.cx_altcost, mtgsim.cx_condlib).

    If an opponent controls a Swamp and you control a Plains, you may cast ~ without paying its mana cost.
    If three or more creatures are attacking, you may pay {U} rather than pay ~'s mana cost.
    If an opponent cast a blue spell this turn, you may pay {R} rather than pay ~'s mana cost.
"""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.cx_condlib import parse
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, PLAINS, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
LEGATE = card("Test Legate", "{2}{W}", "Creature — Human Cleric",
              "If an opponent controls a Swamp and you control a Plains, you may cast ~ without paying its mana cost.",
              1, 2)
WRATH = card("Test Massacre", "{2}{B}{B}", "Sorcery",
             "If an opponent controls a Plains and you control a Swamp, you may cast ~ without paying its mana cost.\n"
             "All creatures get -2/-2 until end of turn.")


def trap(cond, cost="{U}"):
    return card("Test Trap", "{3}{U}{U}", "Instant — Trap",
                f"If {cond}, you may pay {cost} rather than pay ~'s mana cost.\nDraw two cards.")


class Parsing(unittest.TestCase):
    def test_free_cast_line_is_a_conditional_alt_cost(self):
        self.assertEqual(LEGATE.unsupported, [])
        alt = [a for a in LEGATE.alt_costs if a.kind.startswith("cond_alt_")]
        self.assertEqual(len(alt), 1)
        self.assertEqual(alt[0].cost, {"generic": 0})
        code, parts = LEGATE.advanced_rules["alt_if"][0]
        self.assertTrue(code.startswith('lib:["and"'))
        self.assertEqual(parts, ())

    def test_conditions(self):
        self.assertEqual(parse("three or more creatures are attacking"), 'lib:["attackers",">=",3]')
        self.assertIn("attacker_kind", parse("a black creature with flying is attacking"))
        self.assertEqual(parse("an opponent drew three or more cards this turn"), 'lib:["drawn_opp",3]')
        self.assertEqual(parse("an opponent cast three or more spells this turn"), 'lib:["opp_spells",">=",3]')
        self.assertEqual(parse("an opponent had two or more lands enter the battlefield under their control this "
                               "turn"), 'lib:["hist","a land an opponent controls enters",2]')

    def test_refusals(self):
        for text in ("If you control a commander, you may cast ~ without paying its mana cost.",
                     "You may cast ~ without paying its mana cost.",                 # no condition: not this line
                     "If you control a Forest, you may cast ~ without paying its mana cost and as though it had "
                     "flash."):
            c = card("Test Refused", "{1}{G}", "Instant", text + "\nDraw a card.")
            self.assertTrue(c.unsupported, text)
            self.assertFalse(c.advanced_rules.get("alt_if"), text)
        for cond in ("a creature is attacking",            # plain: not a Trap wording this reads
                     "you've been dealt damage by two or more creatures this turn"):
            self.assertEqual(parse(cond), "", cond)


class Engine(Base):
    def options(self, p, name):
        return [c for c in self.game.spell_options(p) if c.name.startswith(name)]

    def free_option(self, p, name):
        return [c for c in self.options(p, name) if "cond_alt" in c.name]

    def test_legate_needs_both_lands_and_costs_nothing(self):
        self.a.hand = [LEGATE]
        self.a.battlefield = [Permanent(PLAINS, self.a)]
        self.assertFalse(self.free_option(self.a, "Test Legate"))          # no Swamp on their side
        self.b.battlefield = [Permanent(SWAMP, self.b)]
        free = self.free_option(self.a, "Test Legate")
        self.assertEqual(len(free), 1)
        self.a.battlefield[0].tapped = True                                 # no mana at all
        self.assertTrue(self.game.cast(self.a, free[0]))
        self.assertEqual([x.card.name for x in self.a.creatures], ["Test Legate"])

    def test_ai_casts_the_free_sweeper(self):
        self.a.hand = [WRATH]
        self.a.battlefield = [Permanent(SWAMP, self.a)]
        self.b.battlefield = [Permanent(PLAINS, self.b)] + [Permanent(BEAR, self.b) for _ in range(3)]
        for x in self.b.battlefield:
            x.sick = False
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn("Test Massacre", [c.name for c in self.a.graveyard])
        self.assertEqual(self.b.creatures, [])

    def test_attacking_count(self):
        t = trap("three or more creatures are attacking")
        self.a.hand = [t]
        attackers = [self.perm(BEAR, self.b) for _ in range(3)]
        self.game.attackers = attackers[:2]
        self.assertFalse(self.free_option(self.a, "Test Trap"))
        self.game.attackers = attackers
        self.assertTrue(self.free_option(self.a, "Test Trap"))

    def test_attacking_kind(self):
        t = trap("a black creature with flying is attacking", "{G}")
        self.a.hand = [t]
        bat = card("Test Bat", "{B}", "Creature — Bat", "Flying", 1, 1)
        self.game.attackers = [self.perm(BEAR, self.b)]
        self.assertFalse(self.free_option(self.a, "Test Trap"))
        self.game.attackers.append(self.perm(bat, self.b))
        self.assertTrue(self.free_option(self.a, "Test Trap"))

    def test_opponent_cast_a_blue_spell_this_turn(self):
        t = trap("an opponent cast a blue spell this turn", "{R}")
        red = card("Test Red", "{R}", "Instant", "Draw a card.")
        blue = card("Test Blue", "{U}", "Instant", "Draw a card.")
        self.a.hand = [t]
        self.b.hand = [red, blue]
        self.b.battlefield = [Permanent(ISLAND, self.b), Permanent(card("Mountain", types="Basic Land — Mountain",
                                                                         text="({T}: Add {R}.)"), self.b)]
        self.game.cast(self.b, red)
        self.assertFalse(self.free_option(self.a, "Test Trap"))
        self.game.cast(self.b, blue)
        self.assertTrue(self.free_option(self.a, "Test Trap"))
        self.game.turn += 1
        self.assertFalse(self.free_option(self.a, "Test Trap"))              # this turn only

    def test_opponent_had_creatures_enter(self):
        t = trap("an opponent had two or more creatures enter the battlefield under their control this turn")
        self.a.hand = [t]
        self.game.enter_battlefield(self.b, BEAR)
        self.game.enter_battlefield(self.a, BEAR)                             # mine don't count
        self.assertFalse(self.free_option(self.a, "Test Trap"))
        self.game.enter_battlefield(self.b, BEAR)
        self.assertTrue(self.free_option(self.a, "Test Trap"))

    def test_opponent_drew_three(self):
        t = trap("an opponent drew three or more cards this turn", "{R}")
        self.a.hand = [t]
        self.game.draw(self.b, 2)
        self.game.draw(self.a, 3)
        self.assertFalse(self.free_option(self.a, "Test Trap"))
        self.game.draw(self.b, 1)
        self.assertTrue(self.free_option(self.a, "Test Trap"))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Cho-Arrim Legate", "Massacre", "Refreshing Rain", "Submerge", "Sivvi's Ruse", "Mogg Salvage",
                     "Deepwood Legate", "Kyren Legate", "Rushwood Legate", "Saprazzan Legate", "Arrow Volley Trap",
                     "Baloth Cage Trap", "Nemesis Trap", "Slingbow Trap", "Whiplash Trap", "Lavaball Trap",
                     "Permafrost Trap", "Lethargy Trap", "Ricochet Trap", "Runeflare Trap"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))

    def test_near_misses_stay_partial(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Patrician's Scorn", "Inferno Trap", "Fierce Guardianship"):
            self.assertNotEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
