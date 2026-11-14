"""#337: "~ deals damage to <players> equal to <a count of their own things>" (Acidic Soil, Karma, Typhoon)."""
import unittest

from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Permanent, StackItem

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
WHITE = card("Test Knight", "{W}", "Creature — Human", "", 1, 1)
FLIER = card("Test Bird", "{U}", "Creature — Bird", "Flying", 1, 1)


def each(s):
    effs = parse_sentence(s)
    return None if not effs else [(i.kind, e.data.get("who"), i.data.get("xq_each"))
                                  for e in effs for i in e.data.get("effects", ())]


class Parsing(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(each("~ deals damage to each player equal to the number of lands they control."),
                         [("cx_damage", "each", ("count", "land"))])
        self.assertEqual(each("~ deals damage to that player equal to the number of Swamps they control."),
                         [("cx_damage", "that_player", ("count", "Swamp"))])
        self.assertEqual(each("~ deals damage to each opponent equal to the number of cards in that player's hand."),
                         [("cx_damage", "opponents", ("hand",))])
        self.assertEqual(each("It deals damage to defending player equal to the number of artifacts they control."),
                         [("cx_damage", "defending", ("count", "artifact"))])
        got = each("~ deals damage to each player equal to twice the number of creatures that player controls with "
                   "flying.")
        self.assertEqual(got[0][2][:2], ("cxq", "twice"))

    def test_refusals(self):
        for s in ("~ deals damage to target player equal to the number of artifacts they control.",   # targeted
                  "~ deals damage to each player equal to the number of lands you control.",          # the caster's
                  "~ deals damage to that player equal to the number of snow lands they control.",    # #428
                  "~ deals damage to each player equal to the number of spells they've cast this turn.",
                  "~ deals damage to each creature equal to the number of lands they control."):
            self.assertIsNone(parse_sentence(s), s)


class Behaviour(Base):
    def resolve(self, text, targets=None, source=None):
        c = self.spell(text, "Sorcery")
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), targets or [None] * len(c.spell_effects),
                                         card=c, name=c.name, source=source))
        self.game.resolve_top()

    def test_each_player_their_own_count(self):
        for _ in range(2):
            self.perm(ISLAND, self.a)
        for _ in range(5):
            self.perm(ISLAND, self.b)
        self.resolve("~ deals damage to each player equal to the number of lands they control.")
        self.assertEqual((self.a.life, self.b.life), (18, 15))

    def test_nonbasic_lands_each_player_their_own(self):     # read through the perms quantity, not copies.fits (#428)
        nonbasic = card("Test Nonbasic", types="Land", text="({T}: Add {C}.)")
        self.perm(nonbasic, self.a)
        for _ in range(3):
            self.perm(nonbasic, self.b)
        for _ in range(4):
            self.perm(ISLAND, self.b)
        self.resolve("~ deals damage to each player equal to twice the number of nonbasic lands that player controls.")
        self.assertEqual((self.a.life, self.b.life), (18, 14))

    def test_zero(self):
        self.resolve("~ deals damage to each opponent equal to the number of cards in that player's hand.")
        self.assertEqual(self.b.life, 20)

    def test_that_player_in_a_spell_is_the_chosen_player(self):
        self.b.hand = [WHITE, WHITE, BEAR]
        c = self.spell("Target player reveals their hand. ~ deals damage to that player equal to the number of white "
                       "cards in their hand.", "Sorcery")
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [self.b] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life), (20, 18))

    def test_twice_flying(self):
        for _ in range(2):
            self.perm(FLIER, self.b)
        self.perm(BEAR, self.b)
        self.resolve("~ deals damage to each player equal to twice the number of creatures that player controls with "
                     "flying.")
        self.assertEqual((self.a.life, self.b.life), (20, 16))

    def test_upkeep_trigger_hits_the_player_whose_upkeep_it_is(self):
        karma = self.perm(card("Test Karma", "{2}{W}{W}", "Enchantment",
                               "At the beginning of each player's upkeep, Test Karma deals damage to that player equal "
                               "to the number of Swamps they control."), self.a)
        self.assertEqual(karma.card.unsupported, [])
        for _ in range(3):
            self.perm(SWAMP, self.b)
        self.perm(SWAMP, self.a)
        self.game.fire(self.b, "upkeep")
        self.game.flush_triggers()
        while self.game.stack:
            self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life), (20, 17))


class DefaultAI(Base):
    def test_casts_it_when_the_opponent_has_more(self):
        spell = card("Test Spell", "{G}", "Sorcery",
                     "~ deals damage to each opponent equal to the number of Islands that player controls.")
        self.assertEqual(spell.unsupported, [])
        self.perm(card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)"), self.a)
        for _ in range(4):
            self.perm(ISLAND, self.b)
        self.a.hand = [spell]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual(self.b.life, 16)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Acidic Soil", "Ancient Runes", "Generous Plunderer", "Inquisition", "Karma", "Roiling Terrain",
                     "Stormbreath Dragon", "Sword of War and Peace", "Treacherous Terrain", "Typhoon", "Wing Storm"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)

    def test_sword_of_war_and_peace(self):
        from mtgsim.carddb import CardDB
        sword = CardDB(offline=True).get("Sword of War and Peace")
        bear = self.perm(BEAR, self.a)
        equip = Permanent(sword, self.a)
        self.a.battlefield.append(equip)
        equip.attached_to = bear
        bear.equipment.append(equip)
        self.a.hand, self.b.hand = [BEAR] * 2, [BEAR] * 3
        trig = sword.host_triggers[0]
        self.game.queue_trigger(self.a, trig.effects, equip, sword.name, context=self.b)
        self.game.flush_triggers()
        while self.game.stack:
            self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life), (22, 17))


if __name__ == "__main__":
    unittest.main()
