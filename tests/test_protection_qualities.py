"""#643 slice 2: protection / hexproof from each colour, mana value, legendary and modified creatures, card types
(mtgsim.protection_qualities; comma lists via kw_lines)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, StackItem, can_block, protected_from
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, SHOCK, card

ANGEL = card("Test Iridescent", "{5}{W}{W}", "Creature — Angel", "Flying, protection from each color", 4, 4)
SKULK = card("Test Skulk", "{1}{W}", "Creature — Kithkin Rogue", "Lifelink, protection from mana value 3 or greater",
             1, 1)
TITAN = card("Test Titan", "{8}", "Artifact Creature — Robot",
             "Void Shields — Protection from mana value 3 or less", 16, 16)
TSABO = card("Test Tsabo", "{5}{B}{R}", "Legendary Creature — Bird Horror",
             "First strike, protection from legendary creatures", 7, 4)
LOUVAQ = card("Test Louvaq", "{2}{U}", "Legendary Creature — Horror", "Protection from modified creatures", 3, 3)
OVERSOUL = card("Test Oversoul", "{G/W}{G/W}{G/W}{G/W}{G/W}", "Creature — Spirit Avatar",
                "Protection from blue, from black, and from red", 5, 5)
BREAKER = card("Test Breaker", "{5}{B}{B}", "Creature — Eldrazi", "Hexproof from each color", 6, 6)
NEVINYRRAL = card("Test Nevinyrral", "{3}{U}{B}{R}", "Legendary Creature — Zombie Wizard",
                  "Hexproof from artifacts, creatures, and enchantments", 4, 6)
LEGEND = card("Test Legend", "{2}{R}", "Legendary Creature — Human", "", 3, 3)
DOOM = card("Test Doom Blade", "{1}{B}", "Instant", "Destroy target creature.")
GROWTH = card("Test Growth", "{G}", "Instant", "Target creature gets +3/+3 until end of turn.")
ROD = card("Test Rod", "{3}", "Artifact", "{T}: ~ deals 1 damage to any target.")
BOLT_6 = card("Test Fireball", "{5}{R}", "Sorcery", "~ deals 6 damage to any target.")


class Parsing(unittest.TestCase):
    def test_keywords(self):
        self.assertIn("protection from each color", ANGEL.keywords)
        self.assertEqual(SKULK.advanced_rules["protection_mv"], (3, "greater"))
        self.assertIn("lifelink", SKULK.keywords)
        self.assertEqual(TITAN.advanced_rules["protection_mv"], (3, "less"))
        self.assertTrue({"protection from blue", "protection from black", "protection from red"} <= OVERSOUL.keywords)
        self.assertTrue({"hexproof from artifacts", "hexproof from creatures",
                         "hexproof from enchantments"} <= NEVINYRRAL.keywords)
        for c in (ANGEL, SKULK, TITAN, TSABO, LOUVAQ, OVERSOUL, BREAKER, NEVINYRRAL):
            self.assertEqual(c.unsupported, [], c.name)

    def test_refusals(self):
        for text in ("Protection from blue, from black, and from plaid", "Hexproof from artifacts and lands",
                     "Protection from mana value X or greater", "Protection from each colour"):
            c = card("X", "{1}", "Creature — Spirit", text, 1, 1)
            self.assertTrue(c.unsupported, text)


class Rules(Base):
    def test_each_color_covers_all_four_parts(self):
        """CR 702.16 (DEBT): damage, enchanting, blocking and targeting by coloured sources; colourless isn't."""
        angel = self.perm(ANGEL, self.a)
        bear = Permanent(BEAR, self.b)                  # green
        self.assertTrue(protected_from(angel, SHOCK))
        self.assertFalse(can_block(bear, angel))
        self.assertFalse(self.game.targetable(angel, self.b, SHOCK))
        self.assertFalse(protected_from(angel, ROD))
        self.game.deal_damage(angel, 3, by=self.b, cause="shock", source=SHOCK)
        self.assertEqual(angel.damage, 0)

    def test_mana_value(self):
        skulk, titan = self.perm(SKULK, self.a), self.perm(TITAN, self.a)
        self.assertFalse(protected_from(skulk, DOOM))                   # mana value 2
        self.assertTrue(protected_from(skulk, BOLT_6))
        self.assertTrue(protected_from(titan, SHOCK))
        self.assertFalse(protected_from(titan, BOLT_6))

    def test_legendary_and_modified_creatures(self):
        tsabo, louvaq = self.perm(TSABO, self.a), self.perm(LOUVAQ, self.a)
        legend, bear = Permanent(LEGEND, self.b), Permanent(BEAR, self.b)
        self.assertFalse(can_block(legend, tsabo))
        self.assertTrue(can_block(bear, tsabo))
        self.assertTrue(can_block(bear, louvaq))
        bear.counters["+1/+1"] = 1                      # modified (CR 700.9)
        self.assertFalse(can_block(bear, louvaq))

    def test_color_list(self):
        over = self.perm(OVERSOUL, self.a)
        self.assertTrue(protected_from(over, SHOCK) and protected_from(over, DOOM))
        self.assertFalse(protected_from(over, GROWTH))


class Hexproof(Base):
    def spell(self, c, by):
        return StackItem(by, list(c.spell_effects), [None], card=c, name=c.name)

    def test_each_color_both_sides(self):
        """Hexproof from each color: the opponent's coloured spells can't target it; its controller's can."""
        breaker = self.perm(BREAKER, self.a)
        self.assertFalse(self.game.targetable(breaker, self.b, self.spell(DOOM, self.b)))
        self.assertTrue(self.game.targetable(breaker, self.b, self.perm(ROD, self.b)))       # colourless
        self.assertTrue(self.game.targetable(breaker, self.a, self.spell(GROWTH, self.a)))   # its controller

    def test_card_types(self):
        nev = self.perm(NEVINYRRAL, self.a)
        self.assertFalse(self.game.targetable(nev, self.b, self.perm(ROD, self.b)))          # artifact source
        self.assertFalse(self.game.targetable(nev, self.b, self.perm(BEAR, self.b)))         # creature source
        self.assertTrue(self.game.targetable(nev, self.b, self.spell(SHOCK, self.b)))        # an instant
        self.assertTrue(self.game.targetable(nev, self.a, self.perm(ROD, self.a)))           # its controller's


class HeuristicUse(Base):
    def test_ai_cannot_aim_at_it(self):
        self.perm(BREAKER, self.a)
        bear = self.perm(BEAR, self.a)
        eff = DOOM.spell_effects[0]
        with self.game.targeting(DOOM):
            self.assertIs(self.b.ai.choose_target(self.game, self.b, eff, DOOM), bear)

    def test_its_owner_still_can(self):
        breaker = self.perm(BREAKER, self.a)
        eff = GROWTH.spell_effects[0]
        with self.game.targeting(GROWTH):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, eff, GROWTH), breaker)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Iridescent Angel", "Tsabo Tavoc", "Louvaq, the Aberrant", "Breaker of Creation",
                     "Eradicator Valkyrie", "Nevinyrral, Urborg Tyrant", "Mistmeadow Skulk", "Reaver Titan",
                     "Oversoul of Dusk", "Elite Inquisitor", "Etched Champion", "Pristine Angel"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))
        self.assertEqual(card_coverage(db.get("Favor of the Mighty")).status, "partial")


if __name__ == "__main__":
    unittest.main()
