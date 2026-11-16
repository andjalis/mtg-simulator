"""#839 (opus-cast slice): planeswalker "for each" wordings, a planeswalker's own loyalty as a quantity, and
Compleated.
- "For each opponent, <verb> up to one target X that player controls" is "an opponent controls" (two players).
- "For each creature card in your graveyard, put a +1/+1 counter on each creature you control" (Vraska, Regal Gorgon).
- "Until end of turn, creatures you control get +1/+1 for each Forest you control and gain trample" (Nissa, AA).
- "~ deals 2 damage to target tapped creature for each card you've drawn this turn" (Niko Aris).
- "where X is ~'s loyalty" / "the number of loyalty counters on ~" (Nissa, Ascended Animist).
- "Compleated": a no-op while Phyrexian mana is paid with its colour (README)."""
import unittest

from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card, BEAR

OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
FOREST = card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")


def walker(text, loyalty=4, name="Test Walker"):
    return card_from_scryfall({"name": name, "mana_cost": "{3}{G}", "cmc": 4, "type_line": "Legendary Planeswalker — Test",
                               "oracle_text": text, "loyalty": str(loyalty)})


def spell(text):
    return card("Test Spell", "{2}", "Sorcery", text)


class Parse(unittest.TestCase):
    def test_for_each_opponent(self):
        for text, kind in (("For each opponent, return up to one target nonland permanent that player controls to its "
                            "owner's hand.", "bounce"),
                           ("For each other player, exile up to one target creature that player controls.",
                            "exile_permanent")):
            c = spell(text)
            self.assertEqual([e.kind for e in c.spell_effects], [kind], text)
            self.assertEqual(c.unsupported, [])

    def test_counters_for_each_graveyard_card(self):
        c = spell("For each creature card in your graveyard, put a +1/+1 counter on each creature you control.")
        self.assertEqual(c.spell_effects[0].data.get("xq"), ("gy", "creature"))

    def test_loyalty_quantity(self):
        c = walker("+1: Create an X/X green Phyrexian Horror creature token, where X is Test Walker's loyalty.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.loyalty_abilities[0][1][0].data.get("xq"), ("stat", "self", "loyalty"))

    def test_compleated(self):
        self.assertEqual(walker("Compleated\n+1: Draw a card.").unsupported, [])

    def test_refusal(self):
        self.assertTrue(spell("For each opponent, gain control of up to one target creature that player controls until "
                              "your next turn.").unsupported)


class Game(Base):
    def setUp(self):
        super().setUp()
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0

    def resolve(self, c, targets=()):
        item = StackItem(self.a, list(c.spell_effects), list(targets) + [None] * (len(c.spell_effects) - len(targets)),
                         card=c, name=c.name)
        self.game.stack.append(item)
        self.game.resolve_top()
        self.game.settle()

    def test_bounce_their_permanent(self):
        mine, theirs = Permanent(BEAR, self.a), Permanent(OGRE, self.b)
        self.a.battlefield, self.b.battlefield = [mine], [theirs]
        c = spell("For each opponent, return up to one target nonland permanent that player controls to its owner's hand.")
        with self.game.targeting(c):
            self.assertEqual(self.game.legal_targets(self.a, c.spell_effects[0]), [theirs])
        self.resolve(c, [theirs])
        self.assertNotIn(theirs, self.b.battlefield)

    def test_counters_per_creature_card(self):
        bear = Permanent(BEAR, self.a)
        self.a.battlefield, self.a.graveyard = [bear], [OGRE, OGRE, FOREST]
        self.resolve(spell("For each creature card in your graveyard, put a +1/+1 counter on each creature you control."))
        self.assertEqual(bear.counters.get("+1/+1"), 2)

    def test_pump_per_forest_and_trample(self):
        bear = Permanent(BEAR, self.a)
        self.a.battlefield = [bear, Permanent(FOREST, self.a), Permanent(FOREST, self.a)]
        self.resolve(spell("Until end of turn, creatures you control get +1/+1 for each Forest you control and gain "
                           "trample."))
        self.assertEqual((bear.power, bear.toughness, bear.has("trample")), (4, 4, True))

    def test_loyalty_sized_token(self):
        pw = Permanent(walker("+1: Create an X/X green Phyrexian Horror creature token, where X is Test Walker's "
                              "loyalty."), self.a)
        pw.counters["loyalty"] = 4
        self.a.battlefield = [pw]
        self.assertTrue(self.game.activate_loyalty(self.a, pw, 0))
        self.game.settle()
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual([(t.power, t.toughness) for t in tokens], [(5, 5)])     # X is read on resolution: 4 + 1

    def test_ai_uses_the_loyalty_token(self):
        pw = Permanent(walker("+1: Create an X/X green Phyrexian Horror creature token, where X is Test Walker's "
                              "loyalty."), self.a)
        pw.counters["loyalty"] = 4
        self.a.battlefield = [pw]
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertTrue(any(x.card.is_token for x in self.a.battlefield))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Vraska, Regal Gorgon", "Nissa, Ascended Animist"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)
        for name in ("Venser, Visionary Traveler", "Kaya, Spirits' Justice", "Niko Aris", "Ajani, Sleeper Agent"):
            ignored = card_coverage(db.get(name)).ignored
            self.assertFalse(any("For each opponent" in i or "For each other player" in i or "for each card you've drawn"
                                 in i or i == "Compleated" for i in ignored), name)


if __name__ == "__main__":
    unittest.main()
