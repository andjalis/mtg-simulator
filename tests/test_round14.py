"""Round 14: "if <condition>, <effect>" sentences, tapped tokens, token anthems, outlaw cast triggers."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card

MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
RICH = card("Test Envy", "{1}", "Sorcery", "If an opponent controls more lands than you, create a Treasure token.")
RAID = card("Test Raid", "{1}{R}", "Sorcery", "If you attacked this turn, create a 1/1 red Goblin creature token.")
DUO = card("Test Duo", "{1}{R}", "Sorcery", "If you control another Elf, create a 2/2 green Elf Warrior creature token.")
TAPPED = card("Test Hoard", "{2}", "Sorcery", "Create two tapped Treasure tokens.")
TAPPED_BODY = card("Test Zombies", "{2}{R}", "Sorcery", "Create two tapped 2/2 black Zombie creature tokens.")
ANTHEM = card("Test Banner", "{2}", "Enchantment", "Creature tokens you control get +1/+1.")
ELF = card("Test Elf", "{1}", "Creature — Elf", "", 1, 1)
OUT = card("Test Outlaw Fan", "{2}", "Enchantment", "Whenever you cast an outlaw spell, you gain 2 life.")
PIRATE = card("Test Pirate", "{1}", "Creature — Pirate", "", 1, 1)


class Round14(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def cast(self, spell, lands):
        for l in lands:
            self.perm(l)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()

    def tokens(self, name=None):
        return [x for x in self.a.battlefield if x.card.is_token and (name is None or name in x.card.name)]

    def test_templates(self):
        for c in (RICH, RAID, DUO, TAPPED, TAPPED_BODY, ANTHEM, OUT):
            self.assertEqual(c.unsupported, [], c.name)

    def test_condition_false_and_true(self):
        self.cast(RAID, [MOUNTAIN, MOUNTAIN])
        self.assertEqual(self.tokens("Goblin"), [])
        self.a.attacked_with = 1
        self.cast(RAID, [MOUNTAIN, MOUNTAIN])
        self.assertEqual(len(self.tokens("Goblin")), 1)

    def test_more_lands(self):
        self.perm(ISLAND, self.b)
        self.cast(RICH, [MOUNTAIN])
        self.assertEqual([x for x in self.tokens() if x.card.token_kind == "treasure"], [])
        self.perm(ISLAND, self.b)
        self.perm(ISLAND, self.b)
        self.cast(RICH, [MOUNTAIN])
        self.assertEqual(len([x for x in self.tokens() if x.card.token_kind == "treasure"]), 1)

    def test_other_elf(self):
        self.cast(DUO, [MOUNTAIN, MOUNTAIN])
        self.assertEqual(self.tokens("Elf"), [])
        self.perm(ELF)
        self.cast(DUO, [MOUNTAIN, MOUNTAIN])
        self.assertEqual(len(self.tokens("Elf")), 1)

    def test_tapped_tokens(self):
        self.cast(TAPPED, [MOUNTAIN, MOUNTAIN])
        ts = [x for x in self.tokens() if x.card.token_kind == "treasure"]
        self.assertEqual((len(ts), all(x.tapped for x in ts)), (2, True))
        self.cast(TAPPED_BODY, [MOUNTAIN] * 3)
        zs = self.tokens("Zombie")
        self.assertEqual((len(zs), all(x.tapped for x in zs)), (2, True))

    def test_token_anthem(self):
        self.cast(TAPPED_BODY, [MOUNTAIN] * 3)
        z = self.tokens("Zombie")[0]
        before = z.power
        self.perm(ANTHEM)
        self.assertEqual(z.power, before + 1)
        self.assertEqual(self.perm(BEAR).power, BEAR.power)

    def test_outlaw_trigger(self):
        self.perm(OUT)
        life = self.a.life
        self.cast(PIRATE, [MOUNTAIN])
        self.assertEqual(self.a.life, life + 2)
        life = self.a.life
        self.cast(card("Plain Bear", "{2}", "Creature — Bear", "", 2, 2), [MOUNTAIN] * 2)
        self.assertEqual(self.a.life, life)


if __name__ == "__main__":
    unittest.main()
