import random
import unittest

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player, find_payment

DB = CardDB(offline=True)


def perm(name, owner, sick=False):
    p = Permanent(DB.get(name), owner)
    p.sick = sick
    p.tapped = False
    owner.battlefield.append(p)
    return p


class StackTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.step = "main1"
        for p in (self.a, self.b):
            p.library = [DB.get("Island")] * 20

    def lands(self, p, name, n):
        return [perm(name, p) for _ in range(n)]

    def test_counterspell_on_opponents_turn(self):
        self.lands(self.a, "Forest", 6)
        self.lands(self.b, "Island", 2)
        self.b.hand = [DB.get("Counterspell")]
        dreadmaw = DB.get("Colossal Dreadmaw")
        self.a.hand = [dreadmaw]
        self.assertTrue(self.game.cast(self.a, dreadmaw))
        self.assertEqual(self.a.creatures, [])
        self.assertIn(dreadmaw, self.a.graveyard)
        self.assertIn(DB.get("Counterspell"), self.b.graveyard)
        self.assertEqual(self.game.stack, [])

    def test_counter_war(self):
        self.lands(self.a, "Island", 8)
        self.lands(self.b, "Island", 2)
        self.a.hand = [DB.get("Colossal Dreadmaw"), DB.get("Counterspell")]
        self.lands(self.a, "Forest", 6)
        self.b.hand = [DB.get("Counterspell")]
        self.game.cast(self.a, DB.get("Colossal Dreadmaw"))
        self.assertEqual([c.card.name for c in self.a.creatures], ["Colossal Dreadmaw"])

    def test_cheap_spells_not_countered_and_filters(self):
        self.lands(self.a, "Forest", 2)
        self.lands(self.b, "Island", 2)
        self.b.hand = [DB.get("Negate")]
        self.a.hand = [DB.get("Grizzly Bears")]
        self.game.cast(self.a, DB.get("Grizzly Bears"))
        self.assertEqual(len(self.a.creatures), 1)  # Negate can't hit creatures
        self.assertEqual(self.b.hand, [DB.get("Negate")])

    def test_jwari_tax_paid_when_possible(self):
        self.lands(self.a, "Forest", 7)
        self.lands(self.b, "Island", 2)
        self.b.ai = BaselineAI()  # engine default responses; HeuristicAI won't cast a tax counter they can pay
        self.b.hand = [DB.get("Jwari Disruption")]
        self.a.hand = [DB.get("Colossal Dreadmaw")]
        self.game.cast(self.a, DB.get("Colossal Dreadmaw"))
        self.assertEqual(len(self.a.creatures), 1)
        self.assertTrue(all(l.tapped for l in self.a.battlefield if l.card.is_land))

    def test_uncounterable_and_protection(self):
        self.lands(self.a, "Island", 7)
        self.lands(self.b, "Island", 2)
        self.b.hand = [DB.get("Counterspell")]
        self.a.hand = [DB.get("Sphinx of the Final Word")]
        self.game.cast(self.a, DB.get("Sphinx of the Final Word"))
        self.assertEqual(len(self.a.creatures), 1)
        self.assertFalse(self.game.can_cast_now(self.b, DB.get("Counterspell")))

    def test_prowess_trigger(self):
        swift = perm("Monastery Swiftspear", self.a)
        self.lands(self.a, "Mountain", 1)
        self.a.hand = [DB.get("Shock")]
        self.game.cast(self.a, DB.get("Shock"), [self.b])
        self.assertEqual((swift.power, swift.toughness), (2, 3))
        self.assertEqual(self.b.life, 18)

    def test_massacre_wurm(self):
        self.lands(self.a, "Swamp", 6)
        perm("Llanowar Elves", self.b)
        perm("Grizzly Bears", self.b)
        perm("Colossal Dreadmaw", self.b)
        self.a.hand = [DB.get("Massacre Wurm")]
        self.game.cast(self.a, DB.get("Massacre Wurm"))
        self.assertEqual([c.card.name for c in self.b.creatures], ["Colossal Dreadmaw"])
        self.assertEqual(self.b.life, 16)

    def test_removal_on_attacker_and_end_step(self):
        self.game.active_idx = 0
        bears = perm("Grizzly Bears", self.a)
        self.lands(self.b, "Swamp", 4)
        self.b.ai = BaselineAI()  # engine default responses (cheapest removal on the attacker)
        self.b.hand = [DB.get("Murder"), DB.get("Infernal Grasp")]
        self.a.ai.choose_attackers = lambda g, me, opp: [bears]
        self.game.combat(self.a, self.b)
        self.assertNotIn(bears, self.a.battlefield)
        self.assertEqual(self.b.life, 18)  # Infernal Grasp: you lose 2 life

    def test_ward_counters_unless_paid(self):
        terror = perm("Tolarian Terror", self.b)
        self.lands(self.a, "Swamp", 3)
        self.a.hand = [DB.get("Murder")]
        self.game.cast(self.a, DB.get("Murder"), [terror])
        self.assertIn(terror, self.b.battlefield)  # no mana left for ward {2}
        self.lands(self.a, "Swamp", 5)
        self.a.hand = [DB.get("Murder")]
        self.game.cast(self.a, DB.get("Murder"), [terror])
        self.assertNotIn(terror, self.b.battlefield)

    def test_hexproof_target_fizzles(self):
        sphinx = perm("Sphinx of the Final Word", self.b)
        self.assertFalse(self.game.targetable(sphinx, self.a))
        self.lands(self.a, "Swamp", 3)
        self.a.hand = [DB.get("Murder")]
        self.game.cast(self.a, DB.get("Murder"), [sphinx])
        self.assertIn(sphinx, self.b.battlefield)

    def test_wrath_and_debuff(self):
        perm("Grizzly Bears", self.a)
        perm("Colossal Dreadmaw", self.b)
        self.lands(self.a, "Swamp", 6)
        self.a.hand = [DB.get("Blood on the Snow")]
        self.game.cast(self.a, DB.get("Blood on the Snow"))
        self.assertEqual(self.a.creatures + self.b.creatures, [])

    def test_dig_and_scry(self):
        self.lands(self.a, "Island", 4)
        self.a.library = [DB.get("Island")] * 10 + [DB.get("Murder")] * 3
        self.a.hand = [DB.get("Memory Deluge")]
        self.game.cast(self.a, DB.get("Memory Deluge"))
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(len(self.a.library), 11)

    def test_cost_reduction_sol_ring_and_tapped_lands(self):
        terror = DB.get("Tolarian Terror")
        self.a.graveyard = [DB.get("Opt")] * 3
        self.assertEqual(self.game.cost_of(self.a, terror)["generic"], 3)
        ring = perm("Sol Ring", self.a)
        island = perm("Island", self.a)
        pay = find_payment([ring, island], {"generic": 1, "U": 1, "B": 0})
        self.assertEqual(set(pay), {ring, island})
        self.assertEqual(find_payment([ring], {"generic": 2}), [ring])
        perm("Swamp", self.a)
        self.a.hand = [DB.get("Shipwreck Marsh")]
        self.game.play_land(self.a, DB.get("Shipwreck Marsh"))
        self.assertFalse(self.a.battlefield[-1].tapped)  # two other lands in play

    def test_triggered_etb_and_combat_damage_draw(self):
        iym = perm("Iymrith, Desert Doom", self.a)
        self.game.combat_damage(self.a, self.b, [iym], {}, lambda c: True)
        self.assertEqual(self.b.life, 15)
        self.assertEqual(len(self.a.hand), 3)  # draw 1, then up to three

    def test_deck_with_instants_finishes(self):
        names = ["Counterspell"] * 8 + ["Murder"] * 8 + ["Serra Angel"] * 8 + ["Island"] * 12 + ["Swamp"] * 12
        deck = [DB.get(n) for n in names] + [DB.get("Plains")] * 12
        aggro = [DB.get("Mountain")] * 24 + [DB.get("Monastery Swiftspear")] * 18 + [DB.get("Lightning Bolt")] * 18
        for seed in range(5):
            Game(Player("x", deck, HeuristicAI()), Player("y", aggro, HeuristicAI()),
                 random.Random(seed)).play()


if __name__ == "__main__":
    unittest.main()
