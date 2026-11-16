"""#628: "They / Those creatures / Untap them / ... on each of those creatures" after a group effect act on the
same permanents (mtgsim.cx_group_refs)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Ardbert, Warrior of Darkness", "Domri, City Smasher", "Elspeth, Storm Slayer", "Felidar Retreat",
        "Flying Crane Technique", "Gideon, Martial Paragon", "Great Oak Guardian", "Join Shields",
        "Now for Wrath, Now for Ruin!", "Song of Freyalise", "Spider-Man, Miles Morales", "Thundermaw Hellkite",
        "The General", "Virtue of Loyalty // Ardenvale Fealty", "Suicidal Charge",
        "Monstrosity of the Lake", "Lulu, Loyal Hollyphant")


def kinds(c):
    return [e.kind for e in c.spell_effects]


class Parse(unittest.TestCase):
    def test_counters_then_they(self):
        c = card("Test Rally", "{W}", "Sorcery", "Put a +1/+1 counter on each legendary creature you control. "
                                                 "They gain vigilance until end of turn.")
        self.assertEqual(c.unsupported, [])
        group = c.spell_effects[1]
        self.assertEqual(group.kind, "permanent_group")
        self.assertEqual(group.data["selector"], {"controller": "mine", "types_all": ["creature"],
                                                  "traits": ["legendary"]})
        self.assertEqual([(e.kind, e.data["keyword"]) for e in group.data["effects"]], [("grant", "vigilance")])

    def test_untap_them_joins_a_target_player_group(self):
        c = card("Test Oak", "{G}", "Instant", "Creatures target player controls get +2/+2 until end of turn. "
                                               "Untap them.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(kinds(c), ["cx_group"])
        self.assertEqual([e.kind for e in c.spell_effects[0].data["effects"]], ["pump", "untap_prev"])

    def test_then_inside_one_sentence(self):
        c = card("Test Freeze", "{U}", "Sorcery", "Tap all creatures your opponents control, then put a stun counter "
                                                  "on each of those creatures.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual([e.kind for e in c.spell_effects[0].data["effects"]], ["tap", "stun"])

    def test_refusals(self):
        for text in (
            # the group left the battlefield: "they" are cards elsewhere
            "Return all creature cards from your graveyard to the battlefield. They gain haste until end of turn.",
            "Destroy all creatures you control. They can't block this turn.",
            # no group before it
            "Target creature gets +1/+1 until end of turn. Those creatures gain flying until end of turn.",
            # a rider about something else than each of them
            "Untap all creatures you control. They gain flying until end of turn unless their controller pays {1}.",
            "Untap all creatures you control. They deal damage equal to their power to target creature.",
            # "each of them" names what an unread sentence in between chose, not the group (Suppression Ray)
            "Tap all creatures target player controls. You may pay any amount of {E}. If you do, choose up to that "
            "many creatures tapped this way. Put a stun counter on each of them.",
        ):
            c = card("Test Odd", "{W}", "Sorcery", text)
            self.assertTrue(c.unsupported, text)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def creature(self, owner, p, t, text="", name="Bear"):
        x = self.g.enter_battlefield(owner, card(name, "{1}", "Creature — Bear", text, p, t))
        x.sick = False
        return x

    def resolve(self, c, targets=None):
        self.assertEqual(c.unsupported, [], c.name)
        effects = list(c.spell_effects)
        self.g.stack.append(StackItem(self.a, effects, targets or [None] * len(effects), card=c, name=c.name))
        self.g.resolve_top()

    def test_untap_all_then_they_gain(self):
        c = card("Test Crane", "{R}{W}", "Instant", "Untap all creatures you control. They gain flying and double "
                                                    "strike until end of turn.")
        x, y = self.creature(self.a, 2, 2), self.creature(self.b, 3, 3)
        x.tapped = y.tapped = True
        self.resolve(c)
        self.assertFalse(x.tapped)
        self.assertTrue(x.has("flying") and x.has("double strike"))
        self.assertTrue(y.tapped)
        self.assertFalse(y.has("flying"))

    def test_damage_then_tap_those_creatures(self):
        c = card("Test Hellkite", "{R}", "Sorcery", "Test Hellkite deals 1 damage to each creature with flying your "
                                                    "opponents control. Tap those creatures.")
        bird = self.creature(self.b, 2, 2, "Flying")
        bear = self.creature(self.b, 2, 2)
        mine = self.creature(self.a, 2, 2, "Flying")
        self.resolve(c)
        self.assertEqual((bird.damage, bird.tapped), (1, True))
        self.assertEqual((bear.damage, bear.tapped), (0, False))
        self.assertEqual((mine.damage, mine.tapped), (0, False))

    def test_counters_on_tapped_then_untap_them(self):
        c = card("Test Lulu", "{W}", "Sorcery", "Put a +1/+1 counter on each tapped creature you control, then untap "
                                                "them.")
        x, y = self.creature(self.a, 2, 2), self.creature(self.a, 2, 2)
        x.tapped = True
        self.resolve(c)
        self.assertEqual((x.p1, x.tapped), (1, False))
        self.assertEqual((y.p1, y.tapped), (0, False))

    def test_debuff_then_attack_if_able(self):
        c = card("Test Charge", "{B}", "Instant", "Creatures your opponents control get -1/-1 until end of turn. "
                                                  "Those creatures attack this turn if able.")
        y, mine = self.creature(self.b, 3, 3), self.creature(self.a, 3, 3)
        self.resolve(c)
        self.assertEqual(y.power, 2)
        self.assertIn("must_attack_now", y.temp_kw)
        self.assertNotIn("must_attack_now", mine.temp_kw)

    def test_target_player_group_untaps_and_ai_picks_own_side(self):
        c = card("Test Oak", "{G}", "Instant", "Creatures target player controls get +2/+2 until end of turn. "
                                               "Untap them.")
        x = self.creature(self.a, 2, 2)
        x.tapped = True
        self.creature(self.b, 2, 2).tapped = True
        targets = self.g.auto_targets(self.a, list(c.spell_effects), None)
        self.assertIs(targets[0], self.a)
        self.resolve(c, targets)
        self.assertEqual((x.power, x.tapped), (4, False))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in FULL:
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_thundermaw_etb(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        bird = g.enter_battlefield(b, card("Bird", "{1}", "Creature — Bird", "Flying", 1, 2))
        g.enter_battlefield(a, self.db.get("Thundermaw Hellkite"))
        g.settle()
        self.assertEqual((bird.damage, bird.tapped), (1, True))

    def test_gideon_plus_two(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        x = g.enter_battlefield(a, card("Bear", "{1}", "Creature — Bear", "", 2, 2))
        x.tapped = True
        gideon = g.enter_battlefield(a, self.db.get("Gideon, Martial Paragon"))
        self.assertTrue(g.activate_loyalty(a, gideon, 0))
        g.settle()
        self.assertEqual((x.power, x.tapped), (3, False))


if __name__ == "__main__":
    unittest.main()
