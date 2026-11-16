"""#626 DMG-EQUAL: damage with an amount equal to a quantity ("deals damage to R equal to Q", "equal to Q to R")."""
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import StackItem
from mtgsim.engine.policy import choose_ability

from tests.test_cx_abil_damage import arena
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import MOUNTAIN, card

BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
GIANT = card("Test Giant", "{3}{R}", "Creature — Giant", "", 4, 4)
FLYER = card("Test Flyer", "{2}", "Creature — Bird", "Flying", 2, 2)
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)

CARDS = ("Fire Dragon", "Spawn of Thraxes", "Omnath, Locus of the Roil", "Foundry Champion", "Volley Veteran",
         "Kessig Malcontents", "Gruesome Scourger", "Thundering Djinn", "Preyseizer Dragon", "Ember-Fist Zubera",
         "Fanatic of Mogis", "Meria's Outrider", "Eivor, Battle-Ready", "Barret Wallace", "Armageddon Clock",
         "Time Bomb", "Thundercloud Shaman", "Skyreaping", "Deathforge Shaman", "Crash Landing",
         "Hallar, the Firefletcher", "Contraption Cannon")


def db():
    from mtgsim.carddb import CardDB
    return CardDB()


def ignored(sentence):
    return _parse_effects(sentence)[1]


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        cards = db()
        for name in CARDS:
            with self.subTest(name=name):
                c = cards.get(name)
                self.assertEqual((c.unsupported, c.approximations), ([], []))

    def test_still_ignored(self):
        """Quantities that name the recipient, an earlier object or a granted ability's holder stay ignored."""
        cards = db()
        for name, line in (("Anathemancer", "nonbasic lands that player controls"),
                           ("Runebound Wolf", "Wolves and Werewolves"),
                           ("Food Fight", "named ~"),
                           ("Weight of Spires", "that creature's controller controls")):
            with self.subTest(name=name):
                self.assertTrue(any(line in u for u in cards.get(name).unsupported), name)


class Refusals(unittest.TestCase):
    def test_near_misses(self):
        for s in ("~ deals damage to target creature equal to the number of cards in that player's hand.",
                  "~ deals damage to target player equal to the number of creatures they control.",
                  "~ deals damage to each opponent equal to the number of Wolves and Werewolves you control.",
                  "~ deals damage to target creature equal to the number of counters on it.",      # whose "it"?
                  # ("... equal to the excess damage dealt this way" is read since #603: the excess of the damage before)
                  "~ deals damage to each opponent equal to the number of Foo Bars you control.",
                  "~ deals damage to each opponent equal to the difference.",
                  "it deals damage to each opponent equal to twice the number of times it was kicked."):
            with self.subTest(s=s):
                self.assertTrue(ignored(s), s)

    def test_shapes(self):
        effs, bad = _parse_effects("~ deals damage to each creature and each player equal to your devotion to red.")
        self.assertEqual(bad, [])
        self.assertEqual([e.data.get("xq") for e in effs], [("devotion", ("R",))] * 2)
        effs, bad = _parse_effects("it deals damage to target player or planeswalker equal to the number of Humans "
                                   "you control.")
        self.assertEqual((bad, effs[0].kind, effs[0].target, effs[0].data["xq"]),
                         ([], "damage", "player", ("count", "Human")))


class Resolve(unittest.TestCase):
    def mountains(self, game, p, n):
        for _ in range(n):
            game.enter_battlefield(p, MOUNTAIN)

    def test_fire_dragon_kills_by_mountain_count(self):
        """HeuristicAI aims the ETB at the opponent's creature the count kills, never its own."""
        game, a, b = arena(HeuristicAI)
        self.mountains(game, a, 3)
        mine = game.enter_battlefield(a, OGRE)
        bear, ogre = game.enter_battlefield(b, BEAR), game.enter_battlefield(b, OGRE)
        game.enter_battlefield(a, db().get("Fire Dragon") if DB_FILE.exists() else card(
            "Test Dragon", "{6}{R}{R}{R}", "Creature — Dragon", "Flying\nWhen ~ enters, it deals damage to target "
            "creature equal to the number of Mountains you control.", 6, 6))
        game.settle()
        self.assertNotIn(ogre, b.battlefield)       # the best creature 3 damage kills
        self.assertIn(bear, b.battlefield)
        self.assertIn(mine, a.battlefield)

    def test_kessig_aims_at_the_opponent(self):
        game, a, b = arena(HeuristicAI)
        humans = card("Test Human", "{W}", "Creature — Human", "", 1, 1)
        for _ in range(2):
            game.enter_battlefield(a, humans)
        malcontents = card("Test Malcontents", "{2}{R}", "Creature — Human Warrior",
                           "When ~ enters, it deals damage to target player or planeswalker equal to the number of "
                           "Humans you control.", 3, 1)
        game.enter_battlefield(a, malcontents)
        game.settle()
        self.assertEqual((a.life, b.life), (20, 17))        # two Humans and itself

    def test_fanatic_devotion_to_each_opponent(self):
        game, a, b = arena(HeuristicAI)
        fanatic = card("Test Fanatic", "{3}{R}", "Creature — Human Shaman",
                       "When ~ enters, it deals damage to each opponent equal to your devotion to red.", 4, 2)
        game.enter_battlefield(a, card("Test Red", "{R}{R}", "Enchantment", ""))
        game.enter_battlefield(a, fanatic)
        game.settle()
        self.assertEqual((a.life, b.life), (20, 17))

    def test_thundercloud_shaman_spares_giants(self):
        game, a, b = arena(HeuristicAI)
        shaman = card("Test Thundercloud", "{3}{R}{R}", "Creature — Giant Shaman",
                      "When ~ enters, it deals damage equal to the number of Giants you control to each non-Giant "
                      "creature.", 4, 4)
        giant = game.enter_battlefield(a, GIANT)
        bear, ogre, goblin = game.enter_battlefield(b, BEAR), game.enter_battlefield(b, OGRE), \
            game.enter_battlefield(a, GOBLIN)
        game.enter_battlefield(a, shaman)
        game.settle()
        self.assertNotIn(bear, b.battlefield)           # 2 Giants: 2 damage
        self.assertNotIn(goblin, a.battlefield)
        self.assertIn(ogre, b.battlefield)
        self.assertEqual(ogre.damage, 2)
        self.assertIn(giant, a.battlefield)
        self.assertEqual(giant.damage, 0)

    def test_time_bomb_counts_its_counters_after_the_sacrifice(self):
        game, a, b = arena(HeuristicAI)
        bomb = game.enter_battlefield(a, card(
            "Test Bomb", "{4}", "Artifact", "{1}, {T}, Sacrifice ~: ~ deals damage equal to the number of time "
            "counters on it to each creature and each player."), counters={"time": 3})
        game.enter_battlefield(a, MOUNTAIN)
        bear, ogre = game.enter_battlefield(b, BEAR), game.enter_battlefield(b, GIANT)
        self.assertTrue(game.activate_ability(a, bomb, 0))
        game.settle()
        self.assertNotIn(bomb, a.battlefield)
        self.assertNotIn(bear, b.battlefield)
        self.assertEqual(ogre.damage, 3)
        self.assertEqual((a.life, b.life), (17, 17))

    def test_skyreaping_hits_only_flyers(self):
        game, a, b = arena(HeuristicAI)
        spell = card("Test Skyreaping", "{1}{G}", "Sorcery",
                     "~ deals damage to each creature with flying equal to your devotion to green.")
        game.enter_battlefield(a, card("Test Green", "{G}{G}", "Enchantment", ""))
        flyer, bear = game.enter_battlefield(b, FLYER), game.enter_battlefield(b, BEAR)
        game.stack.append(StackItem(a, list(spell.spell_effects), [None] * len(spell.spell_effects), card=spell,
                                    name=spell.name))
        game.resolve_top()
        self.assertNotIn(flyer, b.battlefield)
        self.assertEqual(bear.damage, 0)

    def test_crash_landing_damages_that_creature(self):
        game, a, b = arena(HeuristicAI)
        forest = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
        for _ in range(3):
            game.enter_battlefield(a, forest)
        spell = card("Test Crash", "{G}{G}", "Instant", "Target creature with flying loses flying until end of turn. "
                     "~ deals damage to that creature equal to the number of Forests you control.")
        self.assertEqual(spell.unsupported, [])
        big = game.enter_battlefield(b, card("Test Drake", "{3}", "Creature — Drake", "Flying", 3, 3))
        game.stack.append(StackItem(a, list(spell.spell_effects), [big] * len(spell.spell_effects), card=spell,
                                    name=spell.name))
        game.resolve_top()
        self.assertNotIn(big, b.battlefield)

    def test_deathforge_counts_kicks(self):
        game, a, b = arena(HeuristicAI)
        shaman = card("Test Deathforge", "{4}{R}", "Creature — Ogre Shaman",
                      "Multikicker {R}\nWhen ~ enters, it deals damage to target player or planeswalker equal to "
                      "twice the number of times it was kicked.", 4, 3)
        self.assertEqual(shaman.unsupported, [])
        perm = game.enter_battlefield(a, OGRE)
        perm.kicks = 2
        trig = next(t for t in shaman.triggers if t.event == "etb")
        game.stack.append(StackItem(a, list(trig.effects), [b], source=perm, name="etb"))
        game.resolve_top()
        self.assertEqual(b.life, 16)
        perm.kicks = 0
        game.stack.append(StackItem(a, list(trig.effects), [b], source=perm, name="etb"))
        game.resolve_top()
        self.assertEqual(b.life, 16)


class AIActivates(unittest.TestCase):
    def test_counter_ability_aimed_at_their_creature(self):
        """Preyseizer-style "equal to the number of +1/+1 counters on ~" is sized by the AI from the counters now."""
        game, a, b = arena(HeuristicAI)
        pinger = game.enter_battlefield(a, card(
            "Test Counter Pinger", "{2}", "Creature — Goblin", "{T}: ~ deals damage to target creature equal to "
            "the number of +1/+1 counters on ~.", 1, 1), counters={"+1/+1": 3})
        pinger.sick = False
        mine = game.enter_battlefield(a, OGRE)
        theirs = game.enter_battlefield(b, OGRE)
        ability = choose_ability(game, a, instant=False)
        self.assertIsNotNone(ability)
        self.assertTrue(game.do_action(a, ability))
        game.settle()
        self.assertNotIn(theirs, b.battlefield)
        self.assertIn(mine, a.battlefield)


if __name__ == "__main__":
    unittest.main()
