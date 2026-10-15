"""The coverage report, and cards added to the engine for the tier decks (card text from the card database)."""
import glob
import inspect
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.coverage import FULL, PARTIAL, SIMPLIFIED, UNKNOWN, deck_coverage, format_coverage, summary
from mtgsim.decklist import load_deck
from mtgsim.engine import Game, Permanent, Player

DB = CardDB(offline=True)
ROOT = Path(__file__).resolve().parent.parent


def perm(card, owner, tapped=False):
    p = Permanent(DB.get(card), owner)
    p.sick = False
    p.tapped = tapped
    owner.battlefield.append(p)
    return p


class CoverageReportTests(unittest.TestCase):
    def test_statuses_and_summary(self):
        rows = deck_coverage(DB, {"Lightning Bolt": 4, "Old-Growth Troll": 2, "Graveyard Trespasser": 3,
                                  "Not A Real Card Name": 1})
        status = {r.name: r.status for r in rows}
        self.assertEqual(status, {"Lightning Bolt": FULL, "Old-Growth Troll": PARTIAL,
                                  "Graveyard Trespasser": SIMPLIFIED, "Not A Real Card Name": UNKNOWN})
        self.assertEqual([r.status for r in rows], [UNKNOWN, PARTIAL, SIMPLIFIED, FULL])
        self.assertEqual(summary(rows), {FULL: 4, SIMPLIFIED: 3, PARTIAL: 2, UNKNOWN: 1, "total": 10})
        text = format_coverage("test", rows)
        self.assertIn("test: 70% playable as written", text)
        self.assertIn("Old-Growth Troll [partial]", text)
        self.assertNotIn("Lightning Bolt", text)

    def test_lower_tiers_and_snow_list_fully_supported(self):
        paths = [ROOT / "decks" / "ub_snow_control.txt"]
        for tier in ("1-trash", "2-beginner", "3-advanced"):
            paths += [Path(p) for p in glob.glob(str(ROOT / "decks" / "tiers" / tier / "*.txt"))]
        for path in paths:
            for row in deck_coverage(DB, load_deck(path)[1]):
                if path.stem == "ub_snow_control" and row.name == "Jwari Disruption":
                    continue  # its land back face is never played
                self.assertIn(row.status, (FULL, SIMPLIFIED), f"{path.stem}: {row.name} {row.ignored}")

    def test_every_parsed_effect_is_resolved(self):
        source = inspect.getsource(Game.resolve)
        kinds = set()
        for path in glob.glob(str(ROOT / "decks" / "**" / "*.txt"), recursive=True):
            for name in load_deck(path)[1]:
                card = DB.get(name)
                for face in filter(None, (card, card.back, card.adventure)):
                    effects = face.spell_effects + [e for t in face.triggers for e in t.effects]
                    effects += [e for m in face.modes + face.chapters for e in m]
                    effects += [e for _, es in face.loyalty_abilities for e in es]
                    effects += [e for a in face.alt_costs for e in (a.effects or [])]
                    kinds |= {e.kind for e in effects}
        kinds -= {"revolt"}   # Fatal Push's revolt is a targeting filter, not an effect of its own
        self.assertEqual({k for k in kinds if f'"{k}"' not in source}, set())


class NewCardTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn = 1
        for p in (self.a, self.b):
            p.library = [DB.get("Island")] * 20

    def lands(self, p, name, n):
        return [perm(name, p) for _ in range(n)]

    def cast(self, p, name, targets=None):
        card = DB.get(name)
        p.hand.append(card)
        self.assertTrue(self.game.cast(p, card, targets))
        return card

    def test_planeswalker_loyalty_without_brackets(self):
        emperor = DB.get("The Wandering Emperor")
        self.assertEqual([c for c, _ in emperor.loyalty_abilities], [1, -1, -2])
        self.assertEqual(DB.get("Elspeth Resplendent").loyalty_abilities[2][1][0].amount, 5)

    def test_gray_merchant_drains_devotion(self):
        self.lands(self.a, "Swamp", 5)
        perm("Vampire Nighthawk", self.a)   # {1}{B}{B}
        self.cast(self.a, "Gray Merchant of Asphodel")
        self.assertEqual((self.a.life, self.b.life), (24, 16))

    def test_keldon_raider_rummages(self):
        self.lands(self.a, "Mountain", 4)
        self.lands(self.a, "Forest", 1)
        self.a.hand = [DB.get("Swamp"), DB.get("Swamp")]   # a spare land is discarded
        self.cast(self.a, "Keldon Raider")
        self.assertEqual([c.name for c in self.a.graveyard], ["Swamp"])
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Island", "Swamp"])

    def test_goblin_guide_gives_lands(self):
        guide = perm("Goblin Guide", self.a)
        self.a.ai.choose_attackers = lambda g, me, opp: [guide]
        self.game.combat(self.a, self.b)
        self.assertEqual([c.name for c in self.b.hand], ["Island"])

    def test_burst_lightning_kicker(self):
        self.lands(self.a, "Mountain", 5)
        bolt = DB.get("Burst Lightning")
        self.a.hand = [bolt]
        kicked = next(c for c in self.game.spell_options(self.a) if c.name == "Burst Lightning (kicker)")
        self.assertTrue(self.game.can_cast_now(self.a, kicked))
        self.game.cast(self.a, kicked, [self.b])
        self.assertEqual(self.b.life, 16)
        self.assertEqual(self.a.graveyard, [bolt])

    def test_spell_snare_and_duress(self):
        snare = DB.get("Spell Snare").spell_effects[0]
        self.assertEqual(snare.filter, "cmc:2")
        self.lands(self.a, "Swamp", 1)
        self.b.hand = [DB.get("Colossal Dreadmaw"), DB.get("Murder"), DB.get("Swamp")]
        self.cast(self.a, "Duress", [self.b])
        self.assertEqual([c.name for c in self.b.graveyard], ["Murder"])

    def test_fast_land_and_fetch_land(self):
        self.lands(self.a, "Island", 3)
        canal = DB.get("Spirebluff Canal")
        self.a.hand = [canal]
        self.game.play_land(self.a, canal)
        self.assertTrue(self.a.battlefield[-1].tapped)
        self.a.library = [DB.get("Mountain"), DB.get("Colossal Dreadmaw")]
        self.a.hand = [DB.get("Fabled Passage")]
        self.a.land_played = False
        self.game.play_land(self.a, self.a.hand[0])
        names = [x.card.name for x in self.a.battlefield]
        self.assertNotIn("Fabled Passage", names)
        self.assertEqual(names[-1], "Mountain")
        self.assertFalse(self.a.battlefield[-1].tapped)   # four or more lands: untapped
        self.assertEqual([c.name for c in self.a.graveyard], ["Fabled Passage"])

    def test_stun_counter_keeps_creature_tapped(self):
        bear = perm("Grizzly Bears", self.b)
        self.lands(self.a, "Island", 3)
        self.cast(self.a, "Floodpits Drowner")
        self.assertTrue(bear.tapped)
        self.assertEqual(bear.counters.get("stun"), 1)
        self.game.active_idx = 1
        self.game.take_turn(self.b)
        self.assertTrue(bear.tapped)
        self.assertEqual(bear.counters.get("stun"), 0)

    def test_soul_scar_mage_turns_burn_into_counters(self):
        perm("Soul-Scar Mage", self.a)
        maw = perm("Colossal Dreadmaw", self.b)
        self.lands(self.a, "Mountain", 1)
        self.cast(self.a, "Shock", [maw])
        self.assertEqual((maw.damage, maw.counters.get("-1/-1"), maw.power), (0, 2, 4))

    def test_mossborn_hydra_counters(self):
        self.lands(self.a, "Forest", 3)
        self.cast(self.a, "Mossborn Hydra")
        hydra = self.a.creatures[0]
        self.assertEqual(hydra.p1, 1)
        forest = DB.get("Forest")
        self.a.hand = [forest]
        self.game.play_land(self.a, forest)
        self.assertEqual(hydra.p1, 2)


if __name__ == "__main__":
    unittest.main()
