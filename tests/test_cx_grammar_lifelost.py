"""#337: "loses life equal to the life they lost this turn" and the other life-lost-this-turn quantities."""
import unittest

from mtgsim.cards import parse as P
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import ISLAND, card


class Parsing(unittest.TestCase):
    def test_subject_relative(self):
        for s in ("Each opponent loses life equal to the life that player lost this turn.",
                  "Each opponent loses life equal to the life they lost this turn.",
                  "Target opponent loses life equal to the amount of life they lost this turn."):
            effs = parse_sentence(s)
            self.assertEqual((effs[0].data["xq"], effs[0].data["xq_rel"]), (("cxq", "life_lost"), True), s)

    def test_caster(self):
        effs, bad = P._parse_effects("You gain life equal to the life you've lost this turn.")
        self.assertEqual((bad, effs[0].kind, effs[0].data["xq"]), ([], "gain_life", ("cxq", "life_lost")))
        effs, bad = P._parse_effects("You gain life equal to the total life lost by all players this turn.")
        self.assertEqual((bad, effs[0].data["xq"]), ([], ("cxq", "life_lost_all")))

    def test_refusals(self):
        for s in ("Each player loses life equal to the life you lost this turn.",      # mixes you and the subject
                  "You lose life equal to the life they lost this turn.",              # "they" has no subject here
                  "Each opponent loses life equal to the life that player gained this turn."):
            self.assertIsNone(parse_sentence(s), s)


class Behaviour(Base):
    def resolve(self, text, target=None):
        c = self.spell(text)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [target] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_each_opponent_loses_their_own_loss_again(self):
        self.game.deal_damage(self.b, 3, self.a)
        self.a.life -= 5                    # the caster's own loss doesn't count for the opponent
        self.resolve("Each opponent loses life equal to the life that player lost this turn.")
        self.assertEqual((self.a.life, self.b.life), (15, 14))

    def test_snapshot_and_gains_do_not_reduce_it(self):
        self.b.life -= 4
        self.b.life += 4                    # life lost this turn stays 4 after gaining it back
        self.resolve("Target opponent loses life equal to the amount of life they lost this turn.", self.b)
        self.assertEqual(self.b.life, 16)

    def test_zero_and_new_turn(self):
        self.resolve("Each opponent loses life equal to the life they lost this turn.")
        self.assertEqual(self.b.life, 20)
        self.b.life -= 2
        for pl in self.game.players:      # what the next turn's start does (engine/turns.take_turn)
            pl.life_lost_amount = 0
        self.resolve("Each opponent loses life equal to the life they lost this turn.")
        self.assertEqual(self.b.life, 18)

    def test_caster_gains_their_own_loss(self):
        self.a.life -= 6
        self.b.life -= 2
        self.resolve("You gain life equal to the life you've lost this turn.")
        self.assertEqual(self.a.life, 20)
        self.resolve("You gain life equal to the total life lost by all players this turn.")
        self.assertEqual(self.a.life, 28)


class DefaultAI(Base):
    def test_aims_at_the_opponent_who_lost_life(self):
        spell = card("Test Spell", "{U}", "Sorcery",
                     "Target player loses life equal to the amount of life they lost this turn.")
        self.assertEqual(spell.unsupported, [])
        self.perm(ISLAND, self.a)
        self.a.life -= 1
        self.b.life -= 4
        self.a.hand = [spell]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual((self.a.life, self.b.life), (19, 12))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Archfiend of Despair", "Astarion, the Decadent", "Children of Korlis", "Tainted Sigil",
                     "Warlock Class", "Wound Reflection"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)


if __name__ == "__main__":
    unittest.main()
