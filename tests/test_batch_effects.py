"""Metalcraft and other conditional P/T, "when you control no Islands", Aura activated abilities, mass destruction
of a card type, artifact-or-land removal, "that player discards", ingest, devour, extort, life gates, "blocks a
creature with flying", entwine, disturb and untapping everything."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, PLAINS, SWAMP, card

WARDEN = card("Test Warden", "{3}{W}", "Creature — Elephant Soldier",
              "Metalcraft — ~ gets +2/+2 as long as you control three or more artifacts.", 3, 3)
TRINKET = card("Test Trinket", "{1}", "Artifact", "")
SHARK = card("Test Shark", "{5}{U}", "Creature — Shark", "When you control no Islands, sacrifice ~.", 5, 5)
FIREBREATH = card("Test Firebreathing", "{1}{R}", "Enchantment — Aura",
                  "Enchant creature\n{R}: Enchanted creature gets +1/+0 until end of turn.")
SCORN = card("Test Scorn", "{3}{W}", "Instant", "Destroy all enchantments.")
ICEFALL = card("Test Icefall", "{3}{R}{R}", "Sorcery", "Destroy target artifact or land.")
RACKETEER = card("Test Racketeer", "{2}{B}", "Creature — Human Rogue",
                 "Whenever ~ deals combat damage to a player, that player discards a card.", 2, 2)
INTRUDER = card("Test Intruder", "{2}{C}", "Creature — Eldrazi Drone", "Flying\nIngest", 1, 2)
FIEND = card("Test Fiend", "{4}{B}", "Creature — Elemental", "Devour 2", 1, 1)
GHAST = card("Test Ghast", "{3}{B}", "Creature — Spirit", "Extort", 2, 2)
SAVRA = card("Test Savra", "{2}{B}{G}", "Legendary Creature — Elf Shaman",
             "Whenever you sacrifice a black creature, you may pay 2 life. If you do, each other player sacrifices a "
             "creature.", 2, 2)
SPIDER = card("Test Spider", "{1}{G}", "Creature — Spider",
              "Reach\nWhenever ~ blocks a creature with flying, ~ gets +0/+2 until end of turn.", 2, 3)
BIRD = card("Test Bird", "{2}{U}", "Creature — Bird", "Flying", 2, 2)
KHA = card("Test Kha", "{1}{W}", "Instant", "Choose one —\n• Creatures you control get +1/+1 until end of turn.\n"
                                            "• Untap all creatures you control.\nEntwine {1}{W}")
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")


class BatchEffects(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = attackers
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def option(self, p, kind):
        return next((o for o in self.game.spell_options(p) if self.game._origin(o)[1] == kind), None)

    def test_templates(self):
        for c in (WARDEN, SHARK, FIREBREATH, SCORN, ICEFALL, RACKETEER, INTRUDER, FIEND, GHAST, SAVRA, SPIDER, KHA):
            self.assertEqual(c.unsupported, [], c.name)

    def test_metalcraft(self):
        warden = self.put(self.a, WARDEN)
        self.put(self.a, TRINKET, 2)
        self.assertEqual(warden.power, 3)
        self.put(self.a, TRINKET)
        self.assertEqual(warden.power, 5)

    def test_sacrificed_without_islands(self):
        island = self.put(self.a, ISLAND)
        shark = self.put(self.a, SHARK)
        self.assertIn(shark, self.a.battlefield)
        self.game.leave_battlefield(island, "hand")
        self.game.state_based_actions()
        self.assertNotIn(shark, self.a.battlefield)

    def test_aura_ability_pumps_its_host(self):
        bear = self.put(self.a, BEAR)
        self.put(self.a, MOUNTAIN, 3)
        self.game._aura_host = bear
        aura = self.put(self.a, FIREBREATH)
        self.assertIs(aura.aura_host, bear)
        self.assertTrue(self.game.activate_ability(self.a, aura, 0))
        self.game.settle()
        self.assertEqual(bear.power, 3)

    def test_mass_enchantment_and_artifact_or_land_removal(self):
        self.put(self.b, FIREBREATH)
        self.put(self.a, PLAINS, 4)
        self.a.hand.append(SCORN)
        self.assertTrue(self.game.cast(self.a, SCORN))
        self.game.settle()
        self.assertFalse(any("Enchantment" in x.card.types for x in self.b.battlefield))
        land = self.put(self.b, FOREST)
        self.assertIn(land, self.game.legal_targets(self.a, ICEFALL.spell_effects[0]))

    def test_that_player_discards_and_ingest(self):
        racketeer, intruder = self.put(self.a, RACKETEER), self.put(self.a, INTRUDER)
        self.b.hand.append(BEAR)
        top = self.b.library[-1]
        self.fight([racketeer, intruder])
        self.assertEqual(self.b.hand, [])
        self.assertIn(top, self.b.exile)

    def test_devour_eats_tokens(self):
        from mtgsim.cards import make_token
        for _ in range(2):
            self.game.enter_battlefield(self.a, make_token("Saproling", 1, 1))
        bear = self.put(self.a, BEAR)
        fiend = self.put(self.a, FIEND)
        self.assertEqual(fiend.p1, 4)
        self.assertIn(bear, self.a.battlefield)

    def test_extort(self):
        self.put(self.a, GHAST)
        self.put(self.a, SWAMP, 2)
        self.put(self.a, MOUNTAIN)
        self.a.hand.append(SHOCK)
        self.assertTrue(self.game.cast(self.a, SHOCK, [self.b]))
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (21, 17))

    def test_life_gate(self):
        self.put(self.a, SAVRA)
        victim = self.put(self.b, BEAR)
        black = self.put(self.a, card("Test Thrull", "{B}", "Creature — Thrull", "", 1, 1))
        self.game.sacrifice(black)
        self.game.settle()
        self.assertEqual(self.a.life, 18)
        self.assertNotIn(victim, self.b.battlefield)

    def test_blocks_a_flyer(self):
        bird = self.put(self.a, BIRD)
        spider = self.put(self.b, SPIDER)
        self.fight([bird], {bird: [spider]})
        self.assertEqual(spider.toughness, 5)
        bear = self.put(self.a, BEAR)
        spider2 = self.put(self.b, SPIDER)
        self.fight([bear], {bear: [spider2]})
        self.assertEqual(spider2.toughness, 3)

    def test_entwine_chooses_both(self):
        bear = self.put(self.a, BEAR)
        bear.tapped = True
        self.put(self.a, PLAINS, 4)
        self.a.hand.append(KHA)
        entwined = self.option(self.a, "entwine")
        self.assertEqual(entwined.mana_cost, {"generic": 2, "W": 2})
        self.assertTrue(self.game.cast(self.a, entwined))
        self.game.settle()
        self.assertFalse(bear.tapped)
        self.assertEqual(bear.power, 3)


    def test_disturb_casts_the_back_face_from_the_graveyard(self):
        from mtgsim.carddb import ALL_CARDS, CardDB
        if not ALL_CARDS.exists():
            self.skipTest("card database not built")
        veteran = CardDB().get("Lunarch Veteran")
        self.a.graveyard.append(veteran)
        self.put(self.a, PLAINS, 2)
        option = self.option(self.a, "disturb")
        self.assertIsNotNone(option)
        self.assertTrue(self.game.cast(self.a, option))
        self.game.settle()
        phantom = next(x for x in self.a.battlefield if x.card.name == "Luminous Phantom")
        self.assertTrue(phantom.has("flying"))
        self.game.destroy(phantom)
        self.assertIn(veteran, self.a.exile)


if __name__ == "__main__":
    unittest.main()
