"""#646 slice 5: Morph with a non-mana cost (CR 702.37, mtgsim.morph_costs)."""
import unittest

from mtgsim.cards import CardDef
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

RIPPER = card("Test Ripper", "{B}", "Creature — Human Assassin",
              "Deathtouch\nMorph—Reveal a black card in your hand.\n"
              "When this creature is turned face up, target player loses 2 life.", 1, 1)
CUTTHROAT = card("Test Cutthroat", "{4}{B}{B}", "Creature — Zombie", "Fear\nMorph—Pay 5 life.", 4, 4)
RAPTOR = card("Test Raptor", "{3}{B}{B}", "Creature — Zombie Dinosaur Beast", "Morph—Discard a Zombie card.", 4, 4)
VOLCANIST = card("Test Volcanist", "{3}{R}", "Creature — Goblin Shaman", "Morph—Sacrifice two Mountains.", 3, 1)
SHADE = card("Test Shade", "{B}", "Creature — Zombie", "", 1, 1)
DARK = card("Test Dark Ritual", "{B}", "Instant", "Add {B}{B}{B}.")


class Parsing(unittest.TestCase):
    def test_positives(self):
        for c, spec in ((RIPPER, {"reveal": "B"}), (CUTTHROAT, {"life": 5}), (RAPTOR, {"discard": "Zombie"}),
                        (VOLCANIST, {"sacrifice": ("Mountain", 2)})):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertEqual(c.advanced_rules["morph_cost"], spec)
            self.assertEqual([a.kind for a in c.alt_costs], ["morph"])

    def test_refusals(self):
        for text in ("Morph—Reveal a colorless card in your hand.", "Morph—Discard two cards.",
                     "Morph—Discard a Blorb card.", "Morph—Sacrifice a creature.", "Morph—Pay {E}{E}.",
                     "Morph—Return a Bird you control to its owner's hand."):
            c = card("X", "{3}", "Creature — Bird", text, 2, 2)
            self.assertTrue(c.unsupported, text)
            self.assertNotIn("morph_cost", c.advanced_rules, text)


class Engine(Base):
    def face_down(self, c):
        """A morph card cast face down (CR 702.37c): a 2/2 with no name, text or types beyond creature."""
        perm = self.perm(CardDef(name="Face-down creature", mana_cost={"generic": 0}, cmc=0,
                                 types=frozenset({"Creature"}), power=2, toughness=2), self.a)
        perm.hidden = c
        return perm

    def test_can_be_cast_face_down_for_three(self):
        """CR 702.37c: cast face down for {3}, whatever the morph cost is (offered when the full cost can't be paid)."""
        self.a.battlefield = [Permanent(ISLAND, self.a) for _ in range(3)]
        morph = [o for o in self.game._hand_options(self.a, CUTTHROAT) if o is not CUTTHROAT]
        self.assertEqual(len(morph), 1)
        self.assertEqual(self.game.cost_of(self.a, morph[0]).get("generic"), 3)

    def test_reveal_turns_it_up_and_fires_its_trigger(self):
        """CR 702.37e: pay the morph cost (reveal a black card) to turn it face up; "when turned face up" fires."""
        perm = self.face_down(RIPPER)
        self.a.hand = [SHADE]
        self.game.turn_face_up(self.a)
        self.game.settle()
        self.assertIs(perm.card, RIPPER)
        self.assertEqual(self.a.hand, [SHADE])                 # revealed, not spent
        self.assertEqual(self.b.life, 18)

    def test_reveal_needs_a_card_of_that_color(self):
        perm = self.face_down(RIPPER)
        self.a.hand = [BEAR]
        self.game.turn_face_up(self.a)
        self.assertIsNotNone(perm.hidden)

    def test_pay_life(self):
        perm = self.face_down(CUTTHROAT)
        self.game.turn_face_up(self.a)
        self.assertIs(perm.card, CUTTHROAT)
        self.assertEqual(self.a.life, 15)

    def test_discard_a_zombie_card(self):
        perm = self.face_down(RAPTOR)
        self.a.hand = [BEAR, DARK]
        self.game.turn_face_up(self.a)
        self.assertIsNotNone(perm.hidden)                      # no Zombie card in hand
        self.a.hand = [BEAR, SHADE]
        self.game.turn_face_up(self.a)
        self.assertIs(perm.card, RAPTOR)
        self.assertEqual(self.a.hand, [BEAR])
        self.assertIn(SHADE, self.a.graveyard)

    def test_sacrifice_two_mountains(self):
        perm = self.face_down(VOLCANIST)
        self.a.battlefield += [Permanent(MOUNTAIN, self.a) for _ in range(6)]
        self.game.turn_face_up(self.a)
        self.assertIs(perm.card, VOLCANIST)
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 4)


class HeuristicUse(Base):
    def test_ai_keeps_life_and_lands_when_short(self):
        face = CardDef(name="Face-down creature", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Creature"}),
                       power=2, toughness=2)
        cut = Permanent(face, self.a)
        cut.hidden = CUTTHROAT
        vol = Permanent(face, self.a)
        vol.hidden = VOLCANIST
        self.a.battlefield = [cut, vol] + [Permanent(MOUNTAIN, self.a) for _ in range(5)]
        self.a.life = 12
        self.game.turn_face_up(self.a)
        self.assertIsNotNone(cut.hidden)                       # 12 - 5 would leave 7
        self.assertIsNotNone(vol.hidden)                       # 5 lands - 2 would leave 3
        self.a.life = 20
        self.game.turn_face_up(self.a)
        self.assertIsNone(cut.hidden)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Dragon's Eye Savants", "Gathan Raiders", "Horde Ambusher", "Putrid Raptor", "Ruthless Ripper",
                     "Skirk Volcanist", "Temur Charger", "Watcher of the Roost", "Zombie Cutthroat"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()
