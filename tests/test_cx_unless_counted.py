"""#330: more counted "unless" costs. Return N permanents you control to hand, tap N untapped permanents, remove
counters from it, exile a card from your graveyard, and "has ~ deal N damage to them" (the payer takes it)."""
import unittest

from mtgsim.cx_grammar_cond import _costs
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
ISLAND = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")


class Parsing(unittest.TestCase):
    def test_costs(self):
        self.assertEqual(_costs("return an untapped Plains you control to its owner's hand"),
                         [{"bounce": {"tapped": False, "sub": ["Plains"]}, "count": 1, "other": False}])
        self.assertEqual(_costs("return two Forests you control to their owner's hand")[0]["count"], 2)
        self.assertTrue(_costs("return another creature you control to its owner's hand")[0]["other"])
        self.assertEqual(_costs("tap an untapped creature you control")[0]["tap"], {"types": ["creature"]})
        self.assertEqual(_costs("remove two oil counters from it"), [{"remove_counter": "oil", "count": 2}])
        self.assertEqual(_costs("exile a card from your graveyard"), [{"exile_gy": {}}])
        self.assertEqual(_costs("has ~ deal 6 damage to them"), [{"damage": 6}])

    def test_refusals(self):
        for text in ("return an enchantment you don't control to its owner's hand",
                     "tap an untapped creature you control not declared as an attacking creature",
                     "remove a counter from a permanent an opponent controls",
                     "exile the top two cards of your graveyard",
                     "has ~ deal damage to them equal to its power"):
            self.assertIsNone(_costs(text), text)


class Resolving(Base):
    def trigger(self, perm, n=0):
        effects = list(perm.card.triggers[n].effects)
        self.game.stack.append(StackItem(perm.controller, effects, [None] * len(effects), source=perm,
                                         name=perm.card.name))
        self.game.resolve_top()

    def test_karoo_returns_an_untapped_plains_or_is_sacrificed(self):
        karoo = card("Test Karoo", "", "Land", "~ enters tapped.\nWhen ~ enters, sacrifice it unless you return an "
                     "untapped Plains you control to its owner's hand.\n{T}: Add {C}{W}.")
        self.assertEqual(karoo.unsupported, [])
        land = self.perm(karoo, self.a)
        tapped = self.perm(PLAINS, self.a)
        tapped.tapped = True                      # not untapped: can't be returned
        self.trigger(land, next(i for i, t in enumerate(karoo.triggers) if t.event == "etb"))
        self.assertNotIn(land, self.a.battlefield)
        self.assertIn(tapped, self.a.battlefield)
        land = self.perm(karoo, self.a)
        plains = self.perm(PLAINS, self.a)
        self.trigger(land, next(i for i, t in enumerate(karoo.triggers) if t.event == "etb"))
        self.assertIn(land, self.a.battlefield)
        self.assertNotIn(plains, self.a.battlefield)
        self.assertIn("Plains", [c.name for c in self.a.hand])

    def test_counted_return_needs_every_object(self):
        elephant = card("Test Elephant", "{G}", "Creature — Elephant", "When ~ enters, sacrifice it unless you return "
                        "two Forests you control to their owner's hand.", 3, 3)
        beast = self.perm(elephant, self.a)
        forest = self.perm(FOREST, self.a)
        self.trigger(beast)
        self.assertNotIn(beast, self.a.battlefield)
        self.assertIn(forest, self.a.battlefield)            # no partial payment
        beast = self.perm(elephant, self.a)
        self.perm(FOREST, self.a)
        self.trigger(beast)
        self.assertIn(beast, self.a.battlefield)
        self.assertEqual(sum(c.name == "Forest" for c in self.a.hand), 2)

    def test_tap_an_untapped_creature(self):
        falls = card("Test Falls", "{2}", "Enchantment", "At the beginning of your upkeep, sacrifice ~ unless you tap "
                     "an untapped creature you control.")
        ench = self.perm(falls, self.a)
        bear = self.perm(BEAR, self.a)
        self.trigger(ench)
        self.assertTrue(bear.tapped)
        self.assertIn(ench, self.a.battlefield)
        self.trigger(ench)                                     # the only creature is tapped now
        self.assertNotIn(ench, self.a.battlefield)

    def test_remove_counters_from_it(self):
        golem = card("Test Golem", "{4}", "Artifact Creature — Golem",
                     "At the beginning of your upkeep, sacrifice ~ unless you remove a +1/+1 counter from it.", 1, 1)
        g = self.perm(golem, self.a)
        g.counters["+1/+1"] = 1
        self.trigger(g)
        self.assertIn(g, self.a.battlefield)
        self.assertEqual(g.counters.get("+1/+1", 0), 0)
        self.trigger(g)                                        # no counter left: unpayable
        self.assertNotIn(g, self.a.battlefield)

    def test_exile_a_card_from_your_graveyard(self):
        ghoul = card("Test Ghoul", "{1}{B}", "Creature — Zombie", "At the beginning of your upkeep, sacrifice ~ "
                     "unless you exile a card from your graveyard.", 2, 2)
        z = self.perm(ghoul, self.a)
        self.a.graveyard = [BEAR]
        self.trigger(z)
        self.assertIn(z, self.a.battlefield)
        self.assertEqual([c.name for c in self.a.exile], [BEAR.name])
        self.trigger(z)
        self.assertNotIn(z, self.a.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Punisher(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)

    def cast(self, c, targets):
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), targets, card=c))
        self.game.resolve_top()

    def test_lava_blister_controller_takes_damage_or_loses_the_land(self):
        c = self.db.get("Lava Blister")
        self.assertEqual(c.unsupported, [])
        land = card("Test Nonbasic", "", "Land", "{T}: Add {C}.")
        for life, kept in ((20, True), (7, False)):
            with self.subTest(life=life):
                self.b.life = life
                target = self.perm(land, self.b)
                targets = [target if e.target in ("land", "permanent", "nonland_perm") or e.kind == "destroy" else None
                           for e in c.spell_effects]
                self.cast(c, targets)
                self.assertEqual(target in self.b.battlefield, kept)
                self.assertEqual(self.b.life, life - 6 if kept else life)
                self.assertEqual(self.a.life, 20)

    def test_skullscorch_payer_is_the_target_player(self):
        c = self.db.get("Skullscorch")
        self.assertEqual(c.unsupported, [])
        self.b.hand = [BEAR, BEAR, BEAR]
        targets = [self.b if e.target == "player" else None for e in c.spell_effects]
        self.cast(c, targets)
        self.assertEqual((self.b.life, len(self.b.hand)), (16, 3))

    def test_real_cards_full(self):
        for name in ("Karoo", "Coral Atoll", "Glint Hawk", "Faerie Impostor", "Living Tsunami", "Bull Elephant",
                     "Ovinomancer", "Command Bridge", "Koskun Falls", "Junk Golem", "Magmatic Sprinter",
                     "Dwarven Driller", "Molten Influence", "Blazing Salvo"):
            with self.subTest(name):
                self.assertEqual(self.db.get(name).unsupported, [])


if __name__ == "__main__":
    unittest.main()
