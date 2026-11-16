"""#625: "You may cast this card from your graveyard / from exile [by <costs> ...][ if <condition>]"
(mtgsim.cx_altcost zone_alt)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, PLAINS, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
GHOUL = card("Test Ghoul", "{1}{B}", "Creature — Zombie", "You may cast this card from your graveyard.", 2, 2)
CRAWLER = card("Test Crawler", "{B}", "Creature — Zombie Horror",
               "You may cast this card from your graveyard as long as you control a Zombie.", 2, 1)
SYMBIOTE = card("Test Symbiote", "{1}{B}", "Enchantment — Aura",
                "Enchant creature\nEnchanted creature gets +1/+1.\nYou may cast this card from your graveyard by "
                "discarding a card in addition to paying its other costs.")
GUIDANCE = card("Test Guidance", "{W}", "Sorcery",
                "Target creature gets +2/+2 until end of turn.\nYou may cast this card from your graveyard by paying "
                "{2}{W} rather than paying its mana cost.")
LEGION = card("Test Legion", "{1}{B}", "Sorcery",
              "Create a 1/1 black Rat creature token.\nYou may cast this card from your graveyard.")
SCOURGE = card("Test Scourge", "{1}{B}", "Creature — Spirit", "You may cast this card from exile.", 2, 2)
BRUTE = card("Test Brute", "{2}{B}", "Creature — Demon",
             "Sarcophagus — You may cast this card from your graveyard by exiling another creature card from your "
             "graveyard in addition to paying its other costs.", 4, 3)


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (GHOUL, CRAWLER, SYMBIOTE, GUIDANCE, LEGION, SCOURGE, BRUTE):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(GHOUL.advanced_rules["zone_alt"], ((("gy",), "", (), True),))
        self.assertEqual(SCOURGE.advanced_rules["zone_alt"][0][0], ("ex",))
        zones, code, parts, own = SYMBIOTE.advanced_rules["zone_alt"][0]
        self.assertEqual((parts, own), ((("discard", 1, {}),), True))
        alt = next(a for a in GUIDANCE.alt_costs if a.kind.startswith("zone_alt_"))
        self.assertEqual((alt.cost, GUIDANCE.advanced_rules["zone_alt"][0][3]), ({"generic": 2, "W": 1}, False))
        self.assertTrue(CRAWLER.advanced_rules["zone_alt"][0][1])

    def test_refusals(self):
        for text in ("You may cast this card from your graveyard using its blitz ability.",
                     "You may cast this card from your graveyard if a creature not named ~ died this turn.",
                     "You may cast this card from your graveyard. If you do, it enters with a finality counter on it.",
                     "You may cast ~ from your graveyard if you pay {1} more to cast it for each other creature card "
                     "in your graveyard.",
                     "You may cast this card from your graveyard by paying {2} in addition to paying its other costs.",
                     "You may cast this card from your graveyard, but not from anywhere else."):
            c = card("Test Refused", "{1}{B}", "Creature — Zombie", text, 2, 2)
            self.assertTrue(c.unsupported, text)
            self.assertFalse(c.advanced_rules.get("zone_alt"), text)


class Engine(Base):
    def options(self, name):
        return [c for c in self.game.spell_options(self.a) if c.name.startswith(name) and "_alt_" in c.name]

    def lands(self, land, n):
        self.a.battlefield += [Permanent(land, self.a) for _ in range(n)]

    def test_creature_from_graveyard_pays_its_mana_cost(self):
        self.a.graveyard = [GHOUL]
        self.assertEqual(len(self.options("Test Ghoul")), 1)
        self.assertFalse(self.game.cast(self.a, self.options("Test Ghoul")[0]))     # no mana
        self.lands(SWAMP, 2)
        self.assertTrue(self.game.cast(self.a, self.options("Test Ghoul")[0]))
        self.assertEqual([x.card.name for x in self.a.creatures], ["Test Ghoul"])
        self.assertEqual(self.a.graveyard, [])
        self.assertTrue(all(x.tapped for x in self.a.battlefield if x.card.is_land))

    def test_not_from_hand_or_exile(self):
        self.a.hand = [GHOUL]
        self.assertFalse(self.options("Test Ghoul"))
        self.a.hand, self.a.exile = [], [GHOUL]
        self.assertFalse(self.options("Test Ghoul"))

    def test_condition(self):
        self.a.graveyard = [CRAWLER]
        self.lands(SWAMP, 1)
        self.assertFalse(self.options("Test Crawler"))
        self.perm(GHOUL, self.a)                                       # a Zombie
        self.assertEqual(len(self.options("Test Crawler")), 1)

    def test_additional_discard(self):
        self.a.graveyard = [SYMBIOTE]
        self.perm(BEAR, self.a)
        self.lands(SWAMP, 2)
        self.assertFalse(self.options("Test Symbiote"))                 # nothing to discard
        self.a.hand = [ISLAND]
        option = self.options("Test Symbiote")[0]
        self.assertTrue(self.game.cast(self.a, option))
        self.assertEqual(self.a.hand, [])
        self.assertIn("Island", [c.name for c in self.a.graveyard])
        self.assertNotIn("Test Symbiote", [c.name for c in self.a.graveyard])

    def test_alternative_mana_cost(self):
        self.a.graveyard = [GUIDANCE]
        self.perm(BEAR, self.a)
        self.lands(PLAINS, 1)
        self.assertFalse(self.game.cast(self.a, self.options("Test Guidance")[0]))   # {W} isn't enough
        self.lands(PLAINS, 2)
        self.assertTrue(self.game.cast(self.a, self.options("Test Guidance")[0]))
        self.assertTrue(all(x.tapped for x in self.a.battlefield if x.card.is_land))

    def test_sorcery_returns_to_the_graveyard(self):
        self.a.graveyard = [LEGION]
        self.lands(SWAMP, 4)
        self.assertTrue(self.game.cast(self.a, self.options("Test Legion")[0]))
        self.assertEqual([c.name for c in self.a.graveyard], ["Test Legion"])        # not exiled: again later
        self.assertEqual(len(self.options("Test Legion")), 1)
        self.assertTrue(self.game.cast(self.a, self.options("Test Legion")[0]))
        self.assertEqual(len(self.a.creatures), 2)

    def test_from_exile_only(self):
        self.a.exile = [SCOURGE]
        self.lands(SWAMP, 2)
        self.assertTrue(self.game.cast(self.a, self.options("Test Scourge")[0]))
        self.assertEqual([x.card.name for x in self.a.creatures], ["Test Scourge"])
        self.a.graveyard = [SCOURGE]
        self.assertFalse(self.options("Test Scourge"))

    def test_exile_another_card_never_itself(self):
        self.a.graveyard = [BRUTE]
        self.lands(SWAMP, 3)
        self.assertFalse(self.options("Test Brute"))                    # only itself in the graveyard
        self.a.graveyard.append(BEAR)
        self.assertTrue(self.game.cast(self.a, self.options("Test Brute")[0]))
        self.assertEqual([c.name for c in self.a.exile], ["Grizzly Bears"])
        self.assertEqual([x.card.name for x in self.a.creatures], ["Test Brute"])


class HeuristicUse(Base):
    def test_ai_recasts_a_creature_from_its_graveyard(self):
        self.a.graveyard = [GHOUL]
        self.a.hand = []
        self.a.battlefield = [Permanent(SWAMP, self.a) for _ in range(2)]
        self.a.ai.main_phase(self.game, self.a)
        self.assertEqual([x.card.name for x in self.a.creatures], ["Test Ghoul"])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Their Number Is Legion", "Marang River Prowler", "Gravecrawler", "Oathsworn Vampire",
                     "Alien Symbiosis", "Demonic Embrace", "Helbrute", "Rona, Sheoldred's Faithful",
                     "Wickerfolk Indomitable", "Raffine's Guidance", "Squee, Dubious Monarch", "Scourge of Nel Toth",
                     "Squee, the Immortal", "Eternal Scourge", "Khan, Vengeful Heart", "Misthollow Griffin"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()
