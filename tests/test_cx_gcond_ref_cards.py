"""Referent-bound conditions (#405) on real cards from the database, resolved in games: who "it" / "that
creature" / "that land" is decides whether the effect fires."""
import os
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, SWAMP, PLAINS, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
if HAVE_DB:
    from mtgsim.carddb import CardDB
    DB = CardDB()

HERO = card("Test Hero", "{1}", "Creature — Human Hero", "", 1, 1)
OGRE = card("Test Ogre", "{4}", "Creature — Ogre", "", 5, 5)
DESERT = card("Test Desert", types="Land — Desert", text="({T}: Add {C}.)")


@unittest.skipUnless(HAVE_DB, "card database not built")
class RealCardGames(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def lands(self, land, n, p=None):
        for _ in range(n):
            self.game.enter_battlefield(p or self.a, land).sick = False

    def aim(self, p, target):
        """Every target p's AI picks from here on is ``target``."""
        p.ai.choose_target = lambda game, me, eff, card=None: target

    def get(self, name):
        c = DB.get(name)
        self.assertEqual(c.unsupported, [], name)
        return c

    def test_brackish_blunder_it_was_tapped(self):
        blunder = self.get("Brackish Blunder")
        for tapped, maps in ((True, 1), (False, 0)):
            self.setUp()
            bear = self.game.enter_battlefield(self.b, BEAR)
            bear.tapped = tapped
            self.lands(ISLAND, 2)
            self.a.hand = [blunder]
            self.assertTrue(self.game.cast(self.a, blunder, [bear]))
            self.game.settle()
            self.assertIn(BEAR, self.b.hand)
            self.assertEqual(sum(x.card.name == "Map" for x in self.a.battlefield), maps, f"tapped={tapped}")

    def test_wakandan_royal_guard_another_hero(self):
        guard = self.get("Wakandan Royal Guard")
        hero = self.game.enter_battlefield(self.a, HERO)
        self.aim(self.a, hero)
        self.game.enter_battlefield(self.a, guard)
        self.game.settle()
        self.assertEqual(hero.counters.get("+1/+1", 0), 2, "another Hero: two counters")
        self.setUp()
        holder = {}
        self.a.ai.choose_target = lambda game, me, eff, card=None: holder["perm"]
        holder["perm"] = perm = self.game.enter_battlefield(self.a, guard)
        self.game.settle()
        self.assertEqual(perm.counters.get("+1/+1", 0), 1, "a Hero, but not another one: one counter")

    def test_sphinx_dies_if_it_isnt_a_token(self):
        sphinx = self.get("Sphinx of False Conclusions")
        perm = self.game.enter_battlefield(self.a, sphinx)
        self.game.settle()
        self.game.destroy(perm)
        self.game.settle()
        copies = [x for x in self.a.battlefield if x.card.name == sphinx.name]
        self.assertEqual(len(copies), 1, "the card died: a token copy")
        self.assertTrue(copies[0].card.is_token)
        self.game.destroy(copies[0])
        self.game.settle()
        self.assertEqual([x for x in self.a.battlefield if x.card.name == sphinx.name], [],
                         "the token died: no new copy")

    def test_shelinda_power_vs_source(self):
        shelinda = self.get("Shelinda, Yevon Acolyte")      # 2/2
        src = self.game.enter_battlefield(self.a, shelinda)
        self.game.settle()
        hero = self.game.enter_battlefield(self.a, HERO)     # 1 < 2: counter on it
        self.game.settle()
        self.assertEqual(hero.counters.get("+1/+1", 0), 1)
        self.assertEqual(src.counters.get("+1/+1", 0), 0)
        self.game.enter_battlefield(self.a, OGRE)            # 5 >= 2: otherwise, counter on Shelinda
        self.game.settle()
        self.assertEqual(src.counters.get("+1/+1", 0), 1)

    def test_hulkling_greater_power_or_toughness(self):
        hulk = self.get("Hulkling, Burgeoning Bruiser")
        src = self.game.enter_battlefield(self.a, hulk)
        self.game.settle()
        self.game.enter_battlefield(self.a, HERO)
        self.game.settle()
        self.assertEqual(src.counters.get("+1/+1", 0), 0, "a smaller creature")
        self.game.enter_battlefield(self.a, OGRE)
        self.game.settle()
        self.assertEqual(src.counters.get("+1/+1", 0), 1, "a bigger creature")
        self.game.enter_battlefield(self.b, OGRE)
        self.game.settle()
        self.assertEqual(src.counters.get("+1/+1", 0), 1, "an opponent's creature doesn't trigger it")

    def test_helldozer_that_land_was_nonbasic(self):
        dozer = self.get("Helldozer")
        for land, untapped in ((FOREST, False), (DESERT, True)):
            self.setUp()
            src = self.game.enter_battlefield(self.a, dozer)
            src.sick = False
            self.lands(SWAMP, 3)
            target = self.game.enter_battlefield(self.b, land)
            self.aim(self.a, target)
            self.assertTrue(self.game.activate_ability(self.a, src, 0))
            self.game.settle()
            self.assertNotIn(target, self.b.battlefield)
            self.assertEqual(not src.tapped, untapped, land.name)

    def test_gloomlance_that_creature_was_green(self):
        lance = self.get("Gloomlance")
        for victim, discards in ((BEAR, 1), (HERO, 0)):      # Grizzly Bears is green, the Hero colourless
            self.setUp()
            perm = self.game.enter_battlefield(self.b, victim)
            self.b.hand = [ISLAND, ISLAND]
            self.lands(SWAMP, 5)
            self.a.hand = [lance]
            self.assertTrue(self.game.cast(self.a, lance, [perm]))
            self.game.settle()
            self.assertEqual(len(self.b.hand), 2 - discards, victim.name)

    def test_leaders_talent_line_had_a_counter(self):
        talent = card("Test Talent", "{1}{W}", "Enchantment",
                      "Whenever a creature you control leaves the battlefield, if it had a counter on it, "
                      "you gain 2 life.")
        self.assertEqual(talent.unsupported, [])
        self.game.enter_battlefield(self.a, talent)
        plain = self.game.enter_battlefield(self.a, BEAR)
        self.game.destroy(plain)
        self.game.settle()
        self.assertEqual(self.a.life, 20, "no counter: no life")
        marked = self.game.enter_battlefield(self.a, BEAR)
        marked.counters["+1/+1"] = 1
        self.game.destroy(marked)
        self.game.settle()
        self.assertEqual(self.a.life, 22, "it had a counter as it left: +2 life")

    def test_tawnos_tinkering_if_it_isnt_a_creature(self):
        tinkering = self.get("Tawnos's Tinkering")
        for target_card, creature_before in ((PLAINS, False), (BEAR, True)):
            self.setUp()
            target = self.game.enter_battlefield(self.a, target_card)
            self.lands(FOREST, 4)
            self.a.hand = [tinkering]
            self.assertTrue(self.game.cast(self.a, tinkering, [target]))
            self.game.settle()
            self.assertTrue(target.is_creature, target_card.name)
            self.assertEqual((target.power, target.toughness), (2, 2) if not creature_before else (4, 4))

    def test_consuls_lieutenant_if_its_renowned(self):
        lt = self.get("Consul's Lieutenant")
        src = self.game.enter_battlefield(self.a, lt)
        bear = self.game.enter_battlefield(self.a, BEAR)
        for perm in (src, bear):
            perm.sick = False
        self.a.ai.attack = (src, bear)
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 20 - 2 - 2, "not renowned yet: no pump")
        self.game.turn += 1
        self.assertTrue(src.renowned)                      # renown 1 on combat damage
        bear.tapped = src.tapped = False
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 16 - 3 - 3, "renowned: the other attacker gets +1/+1")

    def test_goblin_savant_that_card_is_a_goblin(self):
        savant = self.get("Goblin Savant")
        goblin = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
        for top, playable in ((goblin, True), (ISLAND, False)):
            self.setUp()
            src = self.game.enter_battlefield(self.a, savant)
            src.sick = False
            self.a.library = [ISLAND] * 5 + [top]           # the end of the list is the top
            self.assertTrue(self.game.activate_ability(self.a, src, 0))
            self.game.settle()
            self.assertIn(top, self.a.exile)
            self.assertEqual(any(c.name == top.name for c, _ in self.a.impulse), playable, top.name)

    def test_instrument_of_the_bards_that_card_is_legendary(self):
        instrument = self.get("Instrument of the Bards")
        legend = card("Test Legend", "{2}", "Legendary Creature — Human", "", 2, 2)
        for found, treasures in ((legend, 1), (BEAR, 0)):
            self.setUp()
            src = self.game.enter_battlefield(self.a, instrument)
            src.counters["harmony"] = 2
            self.lands(FOREST, 4)
            self.a.library = [found] + [ISLAND] * 5
            self.assertTrue(self.game.activate_ability(self.a, src, 0))
            self.game.settle()
            self.assertIn(found, self.a.hand)
            self.assertEqual(sum(x.card.name == "Treasure" for x in self.a.battlefield), treasures, found.name)


if __name__ == "__main__":
    unittest.main()
