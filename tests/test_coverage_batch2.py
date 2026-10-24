"""Coverage batches 2-3: spell taxes, Legates, Powerstones, "can't attack alone", team pumps, two-keyword tricks,
Aura and attachment bonuses, life equal to life lost, adapt, "destroy all Forests", color cast triggers,
Keyrunes, sacrifice-instead casts and "assign its combat damage as though it weren't blocked"."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

THORN = card("Test Thorn", "{2}", "Artifact", "Noncreature spells cost {1} more to cast.")
LEGATE = card("Test Legate", "{2}{R}", "Creature — Hound", "If an opponent controls a Plains and you control a Mountain, "
              "you may cast ~ without paying its mana cost.", 1, 1)
PLAINS = card("Plains", "", "Basic Land — Plains", "({T}: Add {W}.)")
LONER = card("Test Loner", "{1}", "Creature — Jackal", "~ can't attack alone.", 2, 2)
HOLD = card("Test Hold", "{W}", "Instant", "Blocking creatures get +7/+7 until end of turn.")
STRIKE = card("Test Strike", "{R}", "Instant", "Target creature gets +1/+0 and gains first strike and haste until end of turn.")
ARTISAN = card("Test Artisan", "{2}{W}", "Creature — Human", "~ gets +2/+2 for each Aura attached to it.", 2, 2)
GRIP = card("Test Grip", "{2}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+0 for each Mountain "
            "you control.")
TITHE = card("Test Tithe", "{3}{B}", "Sorcery", "Each opponent loses 3 life. You gain life equal to the life lost this way.")
BIOMANCER = card("Test Biomancer", "{U}", "Creature — Merfolk", "{1}{U}: Adapt 1.", 1, 1)
RAIN = card("Test Rain", "{3}{U}", "Sorcery", "Destroy all Forests.")
FOREST = card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")
SPHERE = card("Test Sphere", "{1}", "Artifact", "Whenever a player casts a red spell, you may gain 1 life.")
KEYRUNE = card("Test Keyrune", "{3}", "Artifact", "{T}: Add {C}.\n{W}{U}: ~ becomes a 2/3 white and blue Bird artifact "
               "creature with flying until end of turn.")
CLAP = card("Test Clap", "{2}{R}", "Instant", "You may sacrifice a Mountain rather than pay ~'s mana cost.\n~ deals 3 damage "
            "to any target.")
THORNY = card("Test Thorny", "{5}{G}{G}", "Creature — Elemental", "You may have ~ assign its combat damage as though it "
              "weren't blocked.", 7, 7)
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
WALL = card("Test Wall", "{2}", "Creature — Wall", "Defender", 0, 12)


class CoverageBatch2(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def options(self, kind):
        return [o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == kind]

    def test_templates(self):
        for c in (THORN, LEGATE, LONER, HOLD, STRIKE, ARTISAN, GRIP, TITHE, BIOMANCER, RAIN, SPHERE, KEYRUNE, CLAP, THORNY):
            self.assertEqual(c.unsupported, [], c.name)

    def test_tax_and_free_cast(self):
        self.put(self.b, THORN)
        self.assertEqual(self.game.cost_of(self.a, SHOCK)["generic"], 1)
        self.assertEqual(self.game.cost_of(self.a, BEAR)["generic"], 1)
        self.a.hand[:] = [LEGATE]
        self.assertEqual(self.options("free_if"), [])
        self.put(self.b, PLAINS)
        self.put(self.a, MOUNTAIN)
        self.assertEqual(len(self.options("free_if")), 1)

    def test_cant_attack_alone(self):
        loner = self.put(self.a, LONER)
        self.a.ai.attack = [loner]
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)
        self.a.ai.attack = [loner, self.put(self.a, BEAR)]
        loner.tapped = False
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 16)

    def test_team_pump_and_two_keywords(self):
        bear = self.put(self.a, BEAR)
        self.put(self.a, MOUNTAIN)
        self.a.hand[:] = [STRIKE]
        self.assertTrue(self.game.cast(self.a, STRIKE, [bear, None, None]))
        self.game.settle()
        self.assertEqual(bear.power, 3)
        self.assertTrue(bear.has("first strike") and bear.has("haste"))
        theirs = self.put(self.b, BEAR)
        self.b.ai.block = {}
        self.game.blocks = {bear: [theirs]}
        for e in HOLD.spell_effects:
            self.game.resolve(self.a, e, None)
        self.assertEqual((theirs.power, bear.power), (9, 3))      # only the blocking creature

    def test_attachment_and_aura_bonuses(self):
        artisan = self.put(self.a, ARTISAN)
        from mtgsim import auras
        auras.attach(self.game, self.put(self.a, GRIP), artisan)
        self.put(self.a, MOUNTAIN)
        self.put(self.a, MOUNTAIN)
        self.assertEqual((artisan.power, artisan.toughness), (2 + 2 + 4, 2 + 2))

    def test_life_lost_adapt_and_rain(self):
        for e in TITHE.spell_effects:
            self.game.resolve(self.a, e, None)
        self.assertEqual((self.a.life, self.b.life), (23, 17))
        bio = self.put(self.a, BIOMANCER)
        for _ in range(4):
            self.put(self.a, ISLAND)
        for _ in range(2):
            self.assertTrue(self.game.activate_ability(self.a, bio, 0))
            self.game.settle()
        self.assertEqual(bio.p1, 1)                             # the second adapt does nothing
        self.put(self.a, FOREST)
        self.put(self.b, FOREST)
        self.game.resolve(self.a, RAIN.spell_effects[0], None)
        self.assertEqual([x for x in self.a.battlefield + self.b.battlefield if x.card.name == "Forest"], [])
        self.assertIn(bio, self.a.battlefield)

    def test_color_cast_trigger_and_keyrune(self):
        self.put(self.a, SPHERE)
        self.put(self.b, MOUNTAIN)
        self.b.hand[:] = [SHOCK]
        self.assertTrue(self.game.cast(self.b, SHOCK, [self.a]))
        self.game.settle()
        self.assertEqual(self.a.life, 19)                       # 2 damage, 1 life back
        rune = self.put(self.a, KEYRUNE)
        self.put(self.a, PLAINS)
        self.put(self.a, ISLAND)
        self.assertTrue(self.game.activate(self.a, rune, "animate"))
        self.assertTrue(rune.is_creature and rune.has("flying"))

    def test_sacrifice_instead_and_assign_unblocked(self):
        mountain = self.put(self.a, MOUNTAIN)
        mountain.tapped = True
        self.a.hand[:] = [CLAP]
        clap = self.options("alt_sac")[0]
        self.assertTrue(self.game.cast(self.a, clap, [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 17)
        self.assertNotIn(mountain, self.a.battlefield)
        thorny, wall = self.put(self.a, THORNY), self.put(self.b, WALL)
        self.a.ai.attack, self.b.ai.block = [thorny], {thorny: [wall]}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 10)                       # can't kill the 0/12 wall: hits the player


if __name__ == "__main__":
    unittest.main()
