"""#407 slice 2: token replacements. "Twice that many" for anyone (Primal Vigor) and "those tokens plus an
additional X token" adders, once per creation event, before doublers (the affected player's best order)."""
import unittest

from mtgsim.cards import Effect
from mtgsim.cards.tokens import make_token
from mtgsim.cx_replace_amounts import parse_token_line
from tests.test_cx_grammar import Base, DB_FILE


class Parsing(unittest.TestCase):
    def test_lines(self):
        self.assertEqual(parse_token_line("If one or more tokens would be created, twice that many of those tokens "
                                          "are created instead."), ("double_all", None))
        kind, (what, eff) = parse_token_line(
            "If one or more artifact tokens would be created under your control, those tokens plus an additional 1/1 "
            "colorless Thopter artifact creature token with flying are created instead.")
        self.assertEqual((kind, what, eff.data["name"], eff.data["artifact"]), ("adder", "artifact", "Thopter", True))
        kind, (what, eff) = parse_token_line("If you would create one or more Treasure tokens, instead create those "
                                             "tokens plus an additional Treasure token.")
        self.assertEqual((what, eff.data["kind"]), ("treasure", "treasure"))

    def test_refusals(self):
        for line in ("If one or more tokens would be created under your control, those tokens plus two Food tokens "
                     "are created instead.",                                       # more than one extra
                     "If an opponent would create one or more tokens, they create half that many of each of those "
                     "kinds of tokens instead, rounded down.",
                     "If one or more creature tokens would be created under your control, that many 4/4 white Angel "
                     "creature tokens with flying and vigilance are created instead."):   # a different token
            self.assertIsNone(parse_token_line(line), line)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Engine(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.a.battlefield.clear()
        self.b.battlefield.clear()

    def put(self, name, who=None):
        c = self.db.get(name)
        self.assertEqual(c.unsupported, [], name)
        return self.perm(c, who or self.a)

    def tokens(self, who, kind=None):
        return [x for x in who.battlefield if x.card.is_token and (kind is None or kind in x.card.name or
                                                                 (x.card.token_kind or "") == kind)]

    def create(self, who, n=1, **data):
        self.game.create_token(who, Effect("token", n, data=data))

    def test_xorn_adds_one_treasure_per_event(self):
        self.put("Xorn")
        self.create(self.a, 2, kind="treasure")
        self.assertEqual(len(self.tokens(self.a, "treasure")), 3)
        self.create(self.a, 1, kind="food")                    # not a Treasure
        self.assertEqual(len(self.tokens(self.a, "treasure")), 3)

    def test_add_then_double(self):
        self.put("Xorn")
        self.put("Parallel Lives")
        self.create(self.a, 1, kind="treasure")
        self.assertEqual(len(self.tokens(self.a, "treasure")), 4)          # (1 + 1) * 2

    def test_lone_token_outside_a_batch(self):
        self.put("Peregrin Took")
        self.game.enter_battlefield(self.a, make_token("Hero", 1, 1))
        self.assertEqual([x.card.token_kind for x in self.tokens(self.a)].count("food"), 1)
        self.assertEqual(len(self.tokens(self.a)), 2)

    def test_creature_and_artifact_filters(self):
        self.put("Queen Allenal of Ruadach")
        self.create(self.a, 1, kind="treasure")                 # not a creature token
        self.assertEqual(len(self.tokens(self.a)), 1)
        self.create(self.a, 2, name="Elf", power=1, toughness=1)
        self.assertEqual(len([x for x in self.tokens(self.a) if x.is_creature]), 3)
        self.b.battlefield.clear()
        self.put("Stridehangar Automaton", self.b)
        self.create(self.b, 1, kind="clue")
        self.assertEqual(sorted(x.card.name.split()[0] for x in self.tokens(self.b)), ["Clue", "Thopter"])

    def test_only_its_controllers_tokens(self):
        self.put("Xorn", self.b)
        self.create(self.a, 1, kind="treasure")
        self.assertEqual((len(self.tokens(self.a)), len(self.tokens(self.b))), (1, 0))

    def test_primal_vigor_doubles_everyones_tokens(self):
        self.put("Primal Vigor", self.b)
        self.create(self.a, 1, kind="food")
        self.create(self.b, 2, kind="food")
        self.assertEqual((len(self.tokens(self.a)), len(self.tokens(self.b))), (2, 4))

    def test_lost_abilities_stop_the_adder(self):
        xorn = self.put("Xorn")
        xorn.silenced_by = self.perm(make_token("Silencer", 1, 1), self.b)
        self.create(self.a, 1, kind="treasure")
        self.assertEqual(len(self.tokens(self.a, "treasure")), 1)


if __name__ == "__main__":
    unittest.main()
