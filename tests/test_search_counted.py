"""Counted library searches with a player scope and a destination plan (mtgsim.search_counted, #339)."""
import random
import unittest
from collections import Counter
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.search_counted import parse

from tests.test_templates import BEAR, ISLAND, PLAINS, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
OGRE = card("Big Ogre", "{4}{R}", "Creature — Ogre", "", 5, 5)
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
NAMED = card("Clan Elf", "{G}", "Creature — Elf", "", 1, 1)


def spell(name, cost, text, types="Sorcery"):
    c = card(name, cost, types, text)
    assert c.unsupported == [], (text, c.unsupported)
    return c


class Parsing(unittest.TestCase):
    def data(self, text):
        e = parse(text)
        self.assertIsNotNone(e, text)
        return e

    def test_shapes(self):
        e = self.data("Search your library for three cards, put them into your hand, then shuffle.")
        self.assertEqual((e.kind, e.amount, e.target), ("search_plan", 3, "none"))
        self.assertEqual(e.data["plan"], [["hand", None, False]])
        self.assertEqual((e.data["what"], e.data["upto"], e.data["shuffle"]), ("a card", False, "after"))
        e = self.data("Search your library for up to three creature cards, put them into your graveyard, then shuffle.")
        self.assertEqual((e.amount, e.data["upto"], e.data["plan"][0][0]), (3, True, "graveyard"))
        e = self.data("Search your library for up to two basic land cards, reveal those cards, put one onto the "
                      "battlefield tapped and the other into your hand, then shuffle.")
        self.assertEqual(e.data["plan"], [["battlefield", 1, True], ["hand", None, False]])
        e = self.data("Search your library for a card, then shuffle and put that card on top.")
        self.assertEqual((e.data["plan"][0][0], e.data["shuffle"]), ("top", "before"))
        e = self.data("Search your library for up to X cards, put those cards into your hand, then shuffle.")
        self.assertTrue(e.data["x_count"])
        e = self.data("Search your library for a green creature card with mana value X or less, put it onto the "
                      "battlefield, then shuffle.")
        self.assertEqual((e.data["what"], e.data["mv_x"]), ("a green creature card", "less"))
        e = self.data("Search your library for an instant or sorcery card with mana value 3 or less, reveal it, "
                      "put it into your hand, then shuffle.")
        self.assertEqual(e.data["what"], "an instant card with mana value 3 or less or "
                                         "a sorcery card with mana value 3 or less")
        e = self.data("Search your library for a Plains, Island, Swamp, Mountain, or Forest card and put that card "
                      "onto the battlefield.")
        self.assertEqual(e.data["what"].count(" or a "), 4)
        e = self.data("Search your library for up to two basic land cards and/or Gate cards, reveal those cards, "
                      "put one onto the battlefield tapped and the other into your hand, then shuffle.")
        self.assertEqual(e.data["what"], "a basic land card or a Gate card")

    def test_player_scope(self):
        e = self.data("Each player searches their library for up to two basic land cards, puts them onto the "
                      "battlefield, then shuffles.")
        self.assertEqual((e.data["searcher"], e.amount), ("each", 2))
        e = self.data("Each opponent may search their library for a basic land card, put it onto the battlefield "
                      "tapped, then shuffle.")
        self.assertEqual(e.data["searcher"], "each_opp")
        e = self.data("Target player searches their library for a basic land card, puts it onto the battlefield "
                      "tapped, then shuffles.")
        self.assertEqual((e.target, e.data["searcher"], e.data["side"]), ("player", "target", "mine"))
        e = self.data("That creature's controller may search their library for a creature card, put that card "
                      "onto the battlefield, then shuffle.")
        self.assertEqual((e.target, e.data["searcher"]), ("that_controller", "that"))

    def test_refusals(self):
        for text in (
                "Search your library for a nonlegendary card, put that card into your graveyard, then shuffle.",
                "Search your library for up to two creature cards with different names, reveal them, put them "
                "into your hand, then shuffle.",
                "Search your library for a creature card, reveal it, put it into your hand or graveyard, then shuffle.",
                "Search your library for any number of land cards, exile them, then shuffle.",
                "Search your library for a basic land card that doesn't share a land type with a land you control, "
                "put that card onto the battlefield, then shuffle.",
                "Search your library for an artifact creature card, put it onto the battlefield, then shuffle.",
                "Target player searches your library for a card, puts it into their hand, then shuffles.",
                "Search their library for a card, put it into their hand, then shuffle.",
                "Search your library for a card, then shuffle and put that card third from the top.",
                "Search your library for a card, put that card into your hand, discard a card at random, then shuffle.",
                "Search your library for a land card with a basic land type, put it onto the battlefield tapped, "
                "then shuffle.",
                "Search your library for up to X basic land cards with mana value X or less, put them onto the "
                "battlefield, then shuffle."):
            self.assertIsNone(parse(text), text)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def cast(self, c, by=None, targets=None, x=0):
        effects = list(c.spell_effects)
        item = StackItem(by or self.a, effects, targets or [None] * len(effects), card=c, name=c.name)
        item.x = x
        self.game.stack.append(item)
        self.game.resolve_top()

    def zones(self, p):
        return Counter(c.name for c in p.library + p.hand + p.graveyard + p.exile) + \
            Counter(x.card.name for x in p.battlefield)


class Resolution(Base):
    def test_exact_count_to_hand_conserves_cards(self):
        self.a.library = [ISLAND] * 3 + [BEAR] * 4
        before = self.zones(self.a)
        self.cast(spell("Test Beyond", "{5}{B}{B}",
                        "Search your library for three cards, put them into your hand, then shuffle."))
        self.assertEqual(len(self.a.hand), 3)
        self.assertEqual(len(self.a.library), 4)
        self.assertEqual(self.zones(self.a) - Counter({"Test Beyond": 1}), before)

    def test_short_and_empty_library(self):
        beyond = spell("Test Beyond", "{5}{B}{B}",
                       "Search your library for three cards, put them into your hand, then shuffle.")
        self.a.library = [ISLAND, BEAR]
        self.cast(beyond)
        self.assertEqual((len(self.a.hand), self.a.library), (2, []))
        self.cast(beyond)               # nothing left: a legal no-op
        self.assertEqual(len(self.a.hand), 2)

    def test_filter_and_fail_to_find(self):
        buried = spell("Test Buried", "{2}{B}", "Search your library for up to three creature cards, put them into "
                                               "your graveyard, then shuffle.")
        self.a.library = [ISLAND] * 5 + [BEAR, OGRE]
        self.cast(buried)
        self.assertEqual(sorted(c.name for c in self.a.graveyard), ["Big Ogre", "Grizzly Bears", "Test Buried"])
        self.assertEqual([c.name for c in self.a.library], ["Island"] * 5)
        self.cast(buried)               # no creature left: finds nothing
        self.assertEqual(len(self.a.library), 5)

    def test_split_plan_tapped_land_and_hand(self):
        self.a.library = [BEAR] * 5 + [FOREST, PLAINS, ISLAND]
        self.a.hand = [card("Green Thing", "{G}{G}{G}", "Creature — Elf", "", 3, 3)]
        self.cast(spell("Test Cultivate", "{2}{G}",
                        "Search your library for up to two basic land cards, reveal those cards, put one onto the "
                        "battlefield tapped and the other into your hand, then shuffle."))
        lands = [x for x in self.a.battlefield if x.card.is_land]
        self.assertEqual(len(lands), 1)
        self.assertTrue(lands[0].tapped)
        self.assertEqual(lands[0].card.name, "Forest")       # the colour the hand needs
        self.assertEqual(sum(c.is_land for c in self.a.hand), 1)
        self.assertEqual(len(self.a.library), 6)

    def test_top_of_library_after_shuffle(self):
        self.a.library = [ISLAND] * 6 + [OGRE]
        self.a.battlefield = [Permanent(ISLAND, self.a) for _ in range(6)]
        self.cast(spell("Test Tutor", "{B}", "Search your library for a card, then shuffle and put that card on top."))
        self.assertEqual(self.a.library[-1].name, "Big Ogre")
        self.assertEqual(len(self.a.library), 7)

    def test_x_count_and_x_mana_value(self):
        self.a.library = [BEAR] * 5
        self.cast(spell("Test Revelation", "{X}{3}{B}{B}",
                        "Search your library for up to X cards, put those cards into your hand, then shuffle."), x=2)
        self.assertEqual(len(self.a.hand), 2)
        self.a.library = [OGRE, BEAR, GOBLIN]
        self.a.battlefield = [Permanent(ISLAND, self.a) for _ in range(6)]
        zenith = spell("Test Zenith", "{X}{G}", "Search your library for a creature card with mana value X or less, "
                                               "put it onto the battlefield, then shuffle.")
        self.cast(zenith, x=2)
        self.assertEqual([x.card.name for x in self.a.creatures], ["Grizzly Bears"])
        self.cast(zenith, x=0)          # nothing with mana value 0
        self.assertEqual(len(self.a.creatures), 1)

    def test_mid_sentence_where_x(self):
        realms = spell("Test Realms", "{6}{G}", "Search your library for up to X basic land cards, where X is the "
                                               "number of lands you control, put them onto the battlefield tapped, "
                                               "then shuffle.")
        self.assertEqual(realms.spell_effects[0].data["xq"], ("count", "land"))
        self.a.battlefield = [Permanent(ISLAND, self.a) for _ in range(3)]
        self.a.library = [FOREST] * 5 + [BEAR]
        self.cast(realms)
        self.assertEqual(sum(x.tapped for x in self.a.battlefield), 3)
        self.assertEqual(len(self.a.battlefield), 6)
        self.assertIsNone(parse("Search your library for up to X basic land cards, where X is the number of "
                                "creatures attacking you, put them onto the battlefield tapped, then shuffle."))

    def test_each_player_searches_their_own_library(self):
        self.a.library = [FOREST] * 3 + [BEAR]
        self.b.library = [PLAINS] * 1 + [BEAR] * 3
        self.cast(spell("Test Growth", "{4}{G}", "Each player searches their library for up to two basic land cards, "
                                                "puts them onto the battlefield, then shuffles."))
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Forest", "Forest"])
        self.assertEqual([x.card.name for x in self.b.battlefield], ["Plains"])
        self.assertFalse(any(x.tapped for x in self.a.battlefield + self.b.battlefield))
        self.assertEqual((len(self.a.library), len(self.b.library)), (2, 3))

    def test_each_opponent(self):
        self.a.library = [FOREST] * 3
        self.b.library = [PLAINS] * 3
        self.cast(spell("Test Dryads", "{G}", "Each opponent may search their library for a basic land card, put it "
                                             "onto the battlefield tapped, then shuffle."))
        self.assertEqual(self.a.battlefield, [])
        self.assertEqual([(x.card.name, x.tapped) for x in self.b.battlefield], [("Plains", True)])

    def test_target_player(self):
        favor = spell("Test Favor", "{G}", "Target player searches their library for a basic land card, puts it onto "
                                          "the battlefield tapped, then shuffles.")
        self.a.library, self.b.library = [FOREST] * 3, [PLAINS] * 3
        self.cast(favor, targets=[self.b])
        self.assertEqual([x.card.name for x in self.b.battlefield], ["Plains"])
        self.assertEqual(self.a.battlefield, [])

    def test_named_self(self):
        clan = card("Clan Elf", "{G}", "Creature — Elf",
                    "{1}{G}, {T}: Search your library for a card named Clan Elf, put it onto the battlefield, then "
                    "shuffle.", 1, 1)
        self.assertEqual(clan.unsupported, [])
        self.a.library = [BEAR, clan, ISLAND]
        perm = Permanent(clan, self.a)
        self.a.battlefield.append(perm)
        eff = clan.activated[0].effects[0]
        self.game.stack.append(StackItem(self.a, [eff], [None], source=perm, name="Clan Elf ability", kind="ability"))
        self.game.resolve_top()
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Clan Elf", "Clan Elf"])

    def test_dead_creatures_controller_searches(self):
        from mtgsim import auras
        pattern = card("Test Pattern", "{3}{G}", "Enchantment — Aura",
                       "Enchant creature\nWhen enchanted creature dies, that creature's controller may search their "
                       "library for a creature card, put that card onto the battlefield, then shuffle.")
        self.assertEqual(pattern.unsupported, [])
        self.a.library, self.b.library = [FOREST] * 3 + [OGRE], [OGRE, ISLAND]
        bear = Permanent(BEAR, self.b)
        self.b.battlefield.append(bear)
        aura = Permanent(pattern, self.a)
        self.a.battlefield.append(aura)
        auras.attach(self.game, aura, bear)
        self.game.destroy(bear)
        while self.game.stack or self.game.pending:
            self.game.flush_triggers()
            if self.game.stack:
                self.game.resolve_top()
        self.assertEqual([x.card.name for x in self.b.battlefield], ["Big Ogre"])
        self.assertEqual(len(self.a.library), 4)        # the aura's controller didn't search

    def test_enters_x_counts(self):
        spore = card("Test Spore", "{X}{G}", "Creature — Fungus",
                     "When this creature enters, search your library for up to X basic land cards, put them onto the "
                     "battlefield tapped, then shuffle.", 0, 1)
        self.assertEqual(spore.unsupported, [])
        self.a.library = [FOREST] * 4
        perm = Permanent(spore, self.a)
        perm.entered_x = 3
        self.a.battlefield.append(perm)
        self.game.stack.append(StackItem(self.a, list(spore.triggers[0].effects), [None], source=perm,
                                         name="Test Spore trigger", kind="trigger"))
        self.game.resolve_top()
        self.assertEqual(sum(x.card.is_land and x.tapped for x in self.a.battlefield), 3)


class AIChoice(Base):
    def test_ai_casts_and_aims_at_itself(self):
        favor = spell("Test Favor", "{G}", "Target player searches their library for a basic land card, puts it onto "
                                          "the battlefield tapped, then shuffles.")
        self.a.library = [FOREST] * 5
        plan = self.a.ai.plan_spell(self.game, self.a, favor)
        self.assertIsNotNone(plan)
        self.assertIs(plan[1][0], self.a)

    def test_ai_values_tutor_but_not_gifts_to_opponents(self):
        tutor = spell("Test Tutor", "{B}", "Search your library for a card, then shuffle and put that card on top.")
        self.a.library = [BEAR] * 5
        self.assertIsNotNone(self.a.ai.plan_spell(self.game, self.a, tutor))
        gift = spell("Test Gift", "{G}", "Each opponent may search their library for a basic land card, put it onto "
                                        "the battlefield tapped, then shuffle.")
        self.assertIsNone(self.a.ai.plan_spell(self.game, self.a, gift))

    def test_ai_weighs_symmetric_searches(self):
        growth = spell("Test Growth", "{4}{G}", "Each player searches their library for up to two basic land cards, "
                                               "puts them onto the battlefield, then shuffles.")
        self.a.library, self.b.library = [FOREST] * 5, [BEAR] * 5
        self.assertIsNotNone(self.a.ai.plan_spell(self.game, self.a, growth))
        self.b.library = [PLAINS] * 5
        self.assertIsNone(self.a.ai.plan_spell(self.game, self.a, growth))      # they would ramp as much
        buried = spell("Test Buried", "{2}{B}", "Search your library for up to three creature cards, put them into "
                                               "your graveyard, then shuffle.")
        self.a.library = [ISLAND] * 5
        self.assertIsNone(self.a.ai.plan_spell(self.game, self.a, buried))      # nothing to find

    def test_ai_plays_cultivate_in_a_game(self):
        cult = spell("Test Cultivate", "{2}{G}",
                     "Search your library for up to two basic land cards, reveal those cards, put one onto the "
                     "battlefield tapped and the other into your hand, then shuffle.")
        self.a.library = [FOREST] * 10
        self.a.hand = [cult]
        self.a.battlefield = [Permanent(FOREST, self.a) for _ in range(3)]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(cult, self.a.graveyard)
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 4)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Behold the Beyond", "Buried Alive", "Cultivate", "Kodama's Reach", "Vampiric Tutor",
                     "Avatar of Growth", "Field of Ruin", "Fertilid", "Green Sun's Zenith", "Diabolic Revelation",
                     "Entomb", "Worldly Tutor", "Spoils of Victory", "Increasing Ambition", "Old-Growth Dryads",
                     "Pattern of Rebirth"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
