"""Quantities read by mtgsim.cx_grammar_quantity: devotion, noun-phrase counts, turn history, greatest / total."""
import unittest

from mtgsim.cards.clauses import _xq

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, card

ZOMBIE = card("Test Zombie", "{B}{B}", "Creature — Zombie", "", 2, 2)
HYBRID = card("Test Hybrid", "{B/G}", "Creature — Elf", "", 1, 1)
RELIC = card("Test Relic", "{4}", "Artifact", "", cmc=4)
TRINKET = card("Test Trinket", "{1}", "Artifact", "", cmc=1)


class Parsing(unittest.TestCase):
    def test_specs(self):
        self.assertEqual(_xq("your devotion to white and black"), ("cxq", "devotion", "WB"))
        self.assertEqual(_xq("the number of creatures that died this turn"), ("cxq", "hist", "a creature dies"))
        self.assertEqual(_xq("the number of cards named ~ in all graveyards"), ("cxq", "cards", "all_gy", None))
        self.assertEqual(_xq("half your life total, rounded up"), ("cxq", "half", ("life",), True))
        self.assertEqual(_xq("the total power of creatures you control")[:3], ("cxq", "total", "power"))
        self.assertEqual(_xq("the number of attacking creatures")[1], "perms")

    def test_rejects_what_has_no_fixed_referent(self):
        for q in ("the number of creatures blocking it", "the number of cards in their hand",
                  "half your life total",                      # rounding unstated
                  "the number of creatures target player controls", "the difference",
                  "the number of foo bars on the battlefield"):
            self.assertIsNone(_xq(q), q)


class Resolving(Base):
    def gain(self, quantity):
        self.cast(self.spell(f"You gain X life, where X is {quantity}."))
        return self.a.life - 20

    def test_devotion_counts_hybrid_symbols_once(self):
        self.perm(ZOMBIE, self.a)
        self.perm(HYBRID, self.a)
        self.perm(ZOMBIE, self.b)                       # an opponent's permanents don't count
        self.assertEqual(self.gain("your devotion to black"), 3)
        self.assertEqual(self.gain("your devotion to black and green"), 3 + 3)   # {B/G} counts once, plus 3 again

    def test_noun_phrase_count_reads_all_battlefields(self):
        x, y = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.perm(BEAR, self.a)
        self.game.attackers = [x, y]
        self.assertEqual(self.gain("the number of attacking creatures"), 2)

    def test_turn_history(self):
        effects = self.spell("You gain X life, where X is the number of creatures that died this turn.")
        for victim in (self.perm(BEAR, self.a), self.perm(BEAR, self.b)):
            self.game.destroy(victim)
        self.cast(effects)
        self.assertEqual(self.a.life, 22)
        self.game.turn += 1                               # the count is this turn's only
        self.cast(effects)
        self.assertEqual(self.a.life, 22)

    def test_greatest_total_half(self):
        self.perm(RELIC, self.a)
        self.perm(TRINKET, self.a)
        self.perm(BEAR, self.a)
        self.assertEqual(self.gain("the greatest mana value among artifacts you control"), 4)
        self.assertEqual(self.gain("the total power of creatures you control") - 4, 2)
        self.a.life = 21
        self.cast(self.spell("You gain X life, where X is half your life total, rounded up."))
        self.assertEqual(self.a.life, 32)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)

    def test_cards_come_out_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Accumulated Knowledge", "Aspect of Hydra", "Kindle", "Floating-Dream Zubera", "Chain Reaction",
                     "Endless Ranks of the Dead", "Blight-Breath Catoblepas", "Brilliant Spectrum"):
            row = card_coverage(self.db.get(name))
            self.assertEqual(row.status, "full", (name, row.ignored))

    def test_kindle_counts_copies_in_all_graveyards(self):
        kindle = self.db.get("Kindle")
        self.a.graveyard.append(kindle)
        self.b.graveyard.append(kindle)
        target = self.perm(card("Big", "{4}", "Creature — Giant", "", 6, 6), self.b)
        self.cast(kindle, targets=[target])
        self.assertEqual(target.damage, 4)                 # 2 plus two Kindles in graveyards

    def test_converge_counts_colours_spent(self):
        from mtgsim.engine import StackItem
        spectrum = self.db.get("Brilliant Spectrum")
        effects = list(spectrum.spell_effects)
        item = StackItem(self.a, effects, [None] * len(effects), card=spectrum, name=spectrum.name)
        item.mana_colors = {"U", "R", "G"}
        hand = len(self.a.hand)
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertEqual(len(self.a.hand) - hand, 3 - 2)    # draw 3, then discard 2

    def test_aspect_of_hydra_pumps_by_devotion(self):
        bear = self.perm(BEAR, self.a)                     # {1}{G}: devotion 1
        self.perm(HYBRID, self.a)                          # {B/G}: devotion 2
        self.cast(self.db.get("Aspect of Hydra"), targets=[bear])
        self.assertEqual((bear.power, bear.toughness), (4, 4))


if __name__ == "__main__":
    unittest.main()
