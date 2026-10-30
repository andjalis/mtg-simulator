"""smol-chonk-3 batch 4: flying damage and the Kumano exile-damaged wordings.

- "deals N (or X) damage to each creature with flying and each player" (Hurricane, Squallmonger):
  the each-creature damage carries filter="flying" (engine honors it since 9596aac) plus the
  damage_each_player companion; driven end to end off the parsed Hurricane spell.
- "If a creature dealt damage by [this creature / enchanted creature] this turn would die, exile
  it instead" (Kumano, Master Yamabushi, Frostwielder, Kumano's Blessing) parses to
  extra["exile_damaged"], the same flag the engine's damage kind reads.
"""
import random
import unittest

from mtgsim.engine import Game, Player, Permanent
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, MOUNTAIN, card

BIRD = card("Test Bird", "{1}{U}", "Creature — Bird", "Flying", 1, 1)
HURRICANE = card("Hurricane", "{X}{G}", "Sorcery",
                 "Hurricane deals X damage to each creature with flying and each player.")
SQUALLMONGER = card("Squallmonger", "{2}{G}", "Creature — Human",
                    "{2}: Squallmonger deals 1 damage to each creature with flying and each player. "
                    "Any player may activate this ability.", 2, 3)
WARMONGER = card("Warmonger", "{2}{R}", "Creature — Human",
                 "{2}: Warmonger deals 1 damage to each creature without flying and each player. "
                 "Any player may activate this ability.", 2, 3)
KUMANO = card("Kumano, Master Yamabushi", "{3}{R}{R}", "Legendary Creature — Human Shaman",
              "{1}{R}: Kumano deals 1 damage to any target.\nIf a creature dealt damage by Kumano "
              "this turn would die, exile it instead.", 4, 4)
FROSTWIELDER = card("Frostwielder", "{3}{R}", "Creature — Human Shaman",
                    "If a creature dealt damage by this creature this turn would die, exile it "
                    "instead.\n{T}: This creature deals 1 damage to any target.", 1, 3)
BLESSING = card("Kumano's Blessing", "{1}{R}", "Enchantment — Aura",
                "Enchant creature\nEnchanted creature gets +1/+1.\nIf a creature dealt damage by "
                "enchanted creature this turn would die, exile it instead.")


class FlyingDamageParse(unittest.TestCase):
    def test_hurricane_spell_effects(self):
        self.assertEqual(HURRICANE.unsupported, [])
        damage, players = HURRICANE.spell_effects
        self.assertEqual((damage.kind, damage.amount, damage.target, damage.filter, damage.data["x"]),
                         ("damage", 0, "each_creature", "flying", True))
        self.assertEqual((players.kind, players.amount, players.data["x"]),
                         ("damage_each_player", 0, True))

    def test_squallmonger_and_warmonger_abilities(self):
        for cdef, flt in ((SQUALLMONGER, "flying"), (WARMONGER, "nonflying")):
            self.assertEqual(cdef.unsupported, [], cdef.name)
            damage, players = cdef.activated[0].effects
            self.assertEqual((damage.kind, damage.amount, damage.target, damage.filter),
                             ("damage", 1, "each_creature", flt), cdef.name)
            self.assertEqual((players.kind, players.amount), ("damage_each_player", 1), cdef.name)

    def test_hurricane_hits_only_fliers_end_to_end(self):
        a, b = Player("a", [BEAR] * 20, Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 2, "main1", 0
        for _ in range(6):
            land = Permanent(MOUNTAIN, a)
            land.sick = False
            a.battlefield.append(land)
        forest = Permanent(FOREST, a)                       # the {G}: X then takes the rest
        forest.sick = False
        a.battlefield.append(forest)
        a.hand = [HURRICANE]
        bird = Permanent(BIRD, b)
        bird.sick = False
        b.battlefield.append(bird)
        bear = Permanent(BEAR, b)
        bear.sick = False
        b.battlefield.append(bear)
        life_a, life_b = a.life, b.life
        self.assertTrue(game.cast(a, HURRICANE))
        game.settle()
        self.assertEqual(bird.damage, 6)                    # X ends up as the remaining mana
        self.assertEqual(bear.damage, 0)                    # no flying: Hurricane misses it
        self.assertEqual((a.life, b.life), (life_a - 6, life_b - 6))


class ExileDamagedWordings(unittest.TestCase):
    def test_flags(self):
        for cdef in (KUMANO, FROSTWIELDER, BLESSING):
            self.assertEqual(cdef.unsupported, [], cdef.name)
            self.assertTrue(cdef.exile_damaged, cdef.name)

    def test_damage_by_kumano_exiles_instead_of_dying(self):
        a, b = Player("a", [BEAR] * 20, Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 2, "main1", 0
        for _ in range(2):
            land = Permanent(MOUNTAIN, a)
            land.sick = False
            a.battlefield.append(land)
        kumano = Permanent(KUMANO, a)
        kumano.sick = False
        a.battlefield.append(kumano)
        bear = Permanent(BEAR, b)                            # a 2/2: 1 damage is not lethal ...
        bear.sick = False
        b.battlefield.append(bear)
        frail = Permanent(BIRD, b)                            # ... but a 1/1 dies to it
        frail.sick = False
        b.battlefield.append(frail)
        self.assertTrue(game.can_activate(a, kumano, 0))
        self.assertTrue(game.activate(a, kumano, "ability:0", target=[frail]))
        game.settle()
        self.assertNotIn(frail, b.battlefield)               # lethal damage: exiled instead of dying
        self.assertNotIn(frail, b.graveyard)
        self.assertTrue(any(c.name == frail.card.name for c in b.exile))
        self.assertIn(bear, b.battlefield)
        self.assertEqual(bear.damage, 0)                     # only the chosen target was hit


if __name__ == "__main__":
    unittest.main()
