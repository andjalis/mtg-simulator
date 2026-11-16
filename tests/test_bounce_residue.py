"""#638 bounce residue: "<player> returns a <permanent> they control to its owner's hand" for any grammar player
subject, and "return this card to its owner's hand" after the source left the battlefield."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)


def db():
    from mtgsim.carddb import CardDB
    return CardDB()


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10


class Parse(unittest.TestCase):
    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards_full(self):
        cards = db()
        for name in ("Blizzard Specter", "Blood Clock", "Mana Breach", "Sunken Hope", "Angelic Destiny", "Whelming Wave",
                     "Slinn Voda, the Rising Deep", "Cyclone Summoner",
                     "Nurgle's Rot", "Weatherseed Totem", "Endless Evil", "Ringskipper"):
            with self.subTest(name=name):
                c = cards.get(name)
                self.assertEqual((c.unsupported, c.approximations), ([], []))

    def test_refusals(self):
        for s in ("That player returns a creature you control to its owner's hand.",     # whose?
                  "That player returns a Foo they control to its owner's hand.",
                  "Return that card to its owner's hand.",                              # referent varies
                  "That player returns a creature they control to its owner's hand until end of turn."):
            with self.subTest(s=s):
                self.assertTrue(_parse_effects(s)[1], s)


class PlayerReturns(Base):
    def test_target_opponent_returns_their_cheapest(self):
        spell = card("Test Recall", "{1}{U}", "Sorcery", "Target opponent returns a creature they control to its "
                     "owner's hand.")
        self.assertEqual(spell.unsupported, [])
        bear, ogre = self.game.enter_battlefield(self.b, BEAR), self.game.enter_battlefield(self.b, OGRE)
        mine = self.game.enter_battlefield(self.a, BEAR)
        effs = list(spell.spell_effects)
        self.game.stack.append(StackItem(self.a, effs, [self.b], card=spell, name=spell.name))
        self.game.resolve_top()
        self.assertEqual(len(self.b.hand), 1)
        self.assertEqual(sum(x in self.b.battlefield for x in (bear, ogre)), 1)
        self.assertIn(mine, self.a.battlefield)

    def test_ai_aims_it_at_the_opponent(self):
        from mtgsim.engine.policy import default_choose_target
        spell = card("Test Recall", "{1}{U}", "Sorcery", "Target opponent returns a creature they control to its "
                     "owner's hand.")
        self.game.enter_battlefield(self.b, OGRE)
        self.game.enter_battlefield(self.a, BEAR)
        self.assertIs(default_choose_target(self.game, self.a, spell.spell_effects[0]), self.b)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_mana_breach_returns_a_land_of_the_caster(self):
        breach = db().get("Mana Breach")
        src = self.game.enter_battlefield(self.a, breach)
        land = self.game.enter_battlefield(self.b, FOREST)
        trig = breach.triggers[0]
        self.game.stack.append(StackItem(self.a, list(trig.effects), [None] * len(trig.effects), source=src,
                                         name="Mana Breach", context=self.b))
        self.game.resolve_top()
        self.assertNotIn(land, self.b.battlefield)
        self.assertEqual(len(self.b.hand), 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class ThisCard(Base):
    def test_angelic_destiny_comes_back_when_the_creature_dies(self):
        destiny = db().get("Angelic Destiny")
        bear = self.game.enter_battlefield(self.a, BEAR)
        aura = self.game.enter_battlefield(self.a, destiny)
        aura.aura_host = bear
        bear.auras.append(aura)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Angelic Destiny"])
        self.assertNotIn("Angelic Destiny", [c.name for c in self.a.graveyard])

    def test_weatherseed_totem_only_when_it_was_a_creature(self):
        totem = self.game.enter_battlefield(self.a, db().get("Weatherseed Totem"))
        self.game.destroy(totem)
        self.game.settle()
        self.assertEqual(self.a.hand, [])
        self.assertIn("Weatherseed Totem", [c.name for c in self.a.graveyard])


if __name__ == "__main__":
    unittest.main()


class WithAuras(Base):
    def aura(self, owner, colors="{W}", name="Test Aura"):
        c = card(name, colors, "Enchantment — Aura", "Enchant creature")
        return self.game.enter_battlefield(owner, c)

    def attach(self, aura, host):
        aura.aura_host = host
        host.auras.append(aura)

    def test_hubris_returns_the_creature_and_every_aura(self):
        spell = card("Test Hubris", "{1}{U}", "Instant", "Return target creature and all Auras attached to it to "
                     "their owners' hands.")
        self.assertEqual(spell.unsupported, [])
        bear = self.game.enter_battlefield(self.b, BEAR)
        mine, theirs = self.aura(self.a), self.aura(self.b, "{B}")
        self.attach(mine, bear)
        self.attach(theirs, bear)
        self.game.stack.append(StackItem(self.a, list(spell.spell_effects), [bear], card=spell, name=spell.name))
        self.game.resolve_top()
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 2))       # each Aura to its owner's hand
        self.assertEqual([c.name for c in self.a.graveyard + self.b.graveyard], ["Test Hubris"])

    def test_word_of_undoing_only_white_auras_you_own(self):
        spell = card("Test Undoing", "{U}", "Instant", "Return target creature and all white Auras you own attached "
                     "to it to their owners' hands.")
        bear = self.game.enter_battlefield(self.b, BEAR)
        white_mine, black_mine, white_theirs = self.aura(self.a), self.aura(self.a, "{B}"), self.aura(self.b)
        for a in (white_mine, black_mine, white_theirs):
            self.attach(a, bear)
        self.game.stack.append(StackItem(self.a, list(spell.spell_effects), [bear], card=spell, name=spell.name))
        self.game.resolve_top()
        self.assertEqual(len(self.a.hand), 1)                                # only the white Aura you own
        self.assertEqual(sorted(c.name for c in self.b.hand), ["Grizzly Bears"])
        self.assertEqual(sorted(c.name for c in self.a.graveyard), ["Test Aura", "Test Undoing"])  # black one
        self.assertEqual(len(self.b.graveyard), 1)                           # their white one


class AllExcept(Base):
    def cast(self, text):
        c = card("Test Wave", "{2}{U}{U}", "Sorcery", text)
        self.assertEqual(c.unsupported, [], text)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_whelming_wave_spares_the_sea_monsters(self):
        kraken = self.game.enter_battlefield(self.b, card("Test Kraken", "{5}{U}", "Creature — Kraken", "", 6, 6))
        octopus = self.game.enter_battlefield(self.a, card("Test Octopus", "{U}", "Creature — Octopus", "", 1, 1))
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.cast("Return all creatures to their owners' hands except for Krakens, Leviathans, Octopuses, and "
                  "Serpents.")
        self.assertIn(kraken, self.b.battlefield)
        self.assertIn(octopus, self.a.battlefield)
        self.assertNotIn(bear, self.b.battlefield)

    def test_except_giants_wizards_and_lands(self):
        giant = self.game.enter_battlefield(self.a, card("Test Giant", "{4}", "Creature — Giant", "", 4, 4))
        land = self.game.enter_battlefield(self.b, FOREST)
        rock = self.game.enter_battlefield(self.b, card("Test Rock", "{2}", "Artifact", ""))
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.cast("Return all permanents to their owners' hands except for Giants, Wizards, and lands.")
        self.assertIn(giant, self.a.battlefield)
        self.assertIn(land, self.b.battlefield)
        self.assertNotIn(rock, self.b.battlefield)
        self.assertNotIn(bear, self.b.battlefield)

    def test_unknown_exception_stays_ignored(self):
        self.assertTrue(_parse_effects("Return all creatures to their owners' hands except for Foos.")[1])
