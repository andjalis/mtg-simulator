"""Enters prepared (cast a copy of the creature's spell once) and Convoke. Card text is written out."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card


def two_faced(front, back):
    return card_from_scryfall({"name": f"{front['name']} // {back['name']}", "layout": "prepare", "cmc": front["cmc"],
                               "type_line": f"{front['type_line']} // {back['type_line']}",
                               "card_faces": [front, back]})


WRANGLER = two_faced(
    {"name": "Test Wrangler", "mana_cost": "{4}{R}", "cmc": 5, "type_line": "Creature — Orc",
     "oracle_text": "This creature enters prepared. (While it's prepared, you may cast a copy of its spell.)",
     "power": "4", "toughness": "4"},
    {"name": "Test Spark", "mana_cost": "{R}", "cmc": 1, "type_line": "Sorcery",
     "oracle_text": "Test Spark deals 2 damage to any target."})
SEER = card("Convoke Seer", "{3}{U}", "Instant", "Convoke\nDraw two cards.")


class PreparedAndConvoke(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main2"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c):
        p = Permanent(c, self.a)
        p.sick = False
        self.a.battlefield.append(p)
        return p

    def test_templates(self):
        self.assertTrue(WRANGLER.prepared)
        self.assertEqual(WRANGLER.unsupported, [])
        self.assertTrue(SEER.convoke)
        self.assertEqual(SEER.unsupported, [])

    def test_prepared_copy_is_cast_once(self):
        self.game.enter_battlefield(self.a, WRANGLER)
        wr = self.a.battlefield[0]
        self.assertTrue(wr.prepared)
        self.perm(MOUNTAIN)
        options = [c for c in self.game.spell_options(self.a) if c.name.endswith("(prepared)")]
        self.assertEqual(len(options), 1)
        self.assertTrue(self.game.cast(self.a, options[0], [self.b]))
        self.assertEqual(self.b.life, 18)
        self.assertFalse(wr.prepared)
        self.assertEqual(self.a.graveyard, [])                 # a copy: nothing goes to the graveyard
        self.assertEqual([c for c in self.game.spell_options(self.a) if c.name.endswith("(prepared)")], [])

    def test_convoke_taps_creatures_for_generic(self):
        for _ in range(2):
            self.perm(BEAR)
        self.perm(ISLAND)
        self.perm(ISLAND)
        self.a.hand = [SEER]
        self.assertTrue(self.game.cast(self.a, SEER))
        self.assertTrue(all(c.tapped for c in self.a.creatures))
        self.assertEqual(len(self.a.hand), 2)

    def test_mobilize_creates_tapped_attacking_warriors_that_are_sacrificed(self):
        mob = card("Mob Leader", "{2}{R}", "Creature — Goblin", "Mobilize 2", 2, 2)
        self.assertEqual(mob.unsupported, [])
        m = self.perm(mob)
        self.game.step = "declare_attackers"
        self.game.attackers, self.game.attack_targets = [m], {m: self.b}
        self.game.fire(self.a, "attacks", m)
        self.game.settle()
        warriors = [c for c in self.a.creatures if c.card.is_token]
        self.assertEqual(len(warriors), 2)
        self.assertTrue(all(w.tapped and w in self.game.attackers for w in warriors))
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual([c for c in self.a.creatures if c.card.is_token], [])

    def test_endure_puts_counters_on_the_source(self):
        e = card("Endurer", "{1}{W}", "Creature — Human", "When this creature enters, it endures 2.", 1, 1)
        self.assertEqual(e.unsupported, [])
        self.game.enter_battlefield(self.a, e)
        self.game.settle()
        self.assertEqual(self.a.battlefield[0].power, 3)

    def test_manifest_dread(self):
        d = card("Dread Dweller", "{1}{B}", "Creature — Horror", "When this creature enters, manifest dread.", 1, 1)
        self.assertEqual(d.unsupported, [])
        self.a.library = [BEAR, ISLAND, ISLAND]
        self.game.enter_battlefield(self.a, d)
        self.game.settle()
        manifests = [c for c in self.a.creatures if c.card.name == "Manifest"]
        self.assertEqual(len(manifests), 1)
        self.assertEqual((manifests[0].power, manifests[0].toughness), (2, 2))
        self.assertEqual(len(self.a.graveyard), 1)

    def test_disguise_cast_face_down_and_turned_up(self):
        ph = card("Disguised Phantom", "{3}{W}{W}", "Creature — Spirit", "Flying\nDisguise {1}{W}", 3, 3)
        self.assertEqual(ph.unsupported, [])
        plains = card("Plains", "", "Basic Land — Plains", "{T}: Add {W}.")
        for _ in range(3):
            self.perm(plains)
        self.a.hand = [ph]
        opts = [c for c in self.game.spell_options(self.a) if c.name.endswith("(disguise)")]
        self.assertEqual(len(opts), 1)
        self.assertTrue(self.game.cast(self.a, opts[0]))
        face_down = [x for x in self.a.battlefield if x.hidden is not None][0]
        self.assertEqual((face_down.power, face_down.card.ward), (2, 2))
        for land in self.a.battlefield:
            land.tapped = False
        self.game.turn_face_up(self.a)
        self.assertEqual((face_down.card.name, face_down.power), ("Disguised Phantom", 3))


if __name__ == "__main__":
    unittest.main()
