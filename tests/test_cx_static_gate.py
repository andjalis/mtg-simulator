"""cx_static_gate: grammar statics behind a condition ("as long as C", "during your turn") or scaled by a quantity
("for each Q", "where X is Q"), #398 / #401, plus the static defender permission (#400)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
HUMAN = card("Test Human", "{1}{W}", "Creature — Human Soldier", "", 2, 2)
WALL = card("Test Wall", "{1}{U}", "Creature — Wall", "Defender", 0, 4)


def gated(text, types="Creature — Beast", power=2, toughness=2):
    c = card("Test Card", "{2}", types, text, power if "Creature" in types else None,
             toughness if "Creature" in types else None)
    return c


class Parsing(unittest.TestCase):
    def full(self, text, types="Creature — Beast"):
        c = gated(text, types)
        self.assertEqual(c.unsupported, [], text)
        return c.advanced_rules.get("gated", ())

    def ignored(self, text, types="Creature — Beast"):
        from mtgsim.cx_static_gate import parse_line

        class St:
            type_line, extra = types, {"aura": "creature"} if "Aura" in types else {}
        self.assertFalse(parse_line(text, St()), text)

    def test_reads_gates_and_scales(self):
        rows = self.full("As long as ~ is monstrous, it can attack as though it didn't have defender.")
        self.assertEqual([(r[1], r[3]) for r in rows], [("self", ("kw", ("attacks_despite_defender",)))])
        rows = self.full("As long as equipped creature is a Human, it gets an additional +1/+1.", "Artifact — Equipment")
        self.assertEqual([(r[1], r[3][:3]) for r in rows], [("host", ("pt", 1, 1))])
        rows = self.full("During your turn, creatures you control have double strike.", "Enchantment")
        self.assertEqual(rows[0][1], "group")
        rows = self.full("~ gets +1/+1 for each creature your opponents control.")
        self.assertEqual(rows[0][0], "")
        self.assertIsNotNone(rows[0][3][3])
        rows = self.full("Enchant creature\nEnchanted creature gets -X/-0, where X is the number of cards in your "
                         "graveyard.", "Enchantment — Aura")
        self.assertEqual(rows[0][3][1:3], (-1, 0))
        self.full("As long as you control a Gate, ~ can attack as though it didn't have defender.")
        self.full("As long as you control exactly one creature, that creature gets +2/+0 and has lifelink.",
                  "Enchantment")

    def test_refuses_what_it_cannot_read(self):
        for text, types in (
                ("As long as you're eating, ~ has flying.", "Creature — Beast"),                    # unknown condition
                ('As long as ~ is monstrous, it has "{T}: Draw a card."', "Creature — Beast"),       # quoted (#338)
                ("During your turn, creatures you control with power 2 or less get +1/+1.", "Enchantment"),
                ("~ gets +1/+1 for each creature with power 4 or greater.", "Creature — Beast"),    # quantity reads P/T
                ("Equipped creature gets +X/+1, where X is the number of artifacts you control.",  # only part scales
                 "Artifact — Equipment"),
                ("Equipped creature gets +X/+X, where X is its mana value.", "Artifact — Equipment"),  # "its"
                ("~ gets +1/+1 for each land you control and each land card in your graveyard.",    # misread Q
                 "Creature — Avatar"),
                ("~ gets +1/+1 for each artifact token you control.", "Creature — Golem"),         # tokens only
                ("Legendary creatures you control get +X/+X, where X is the number of legendary creatures you control.",
                 "Enchantment"),                                                    # "legendary": fits counts none
                ("~ has flying as long as you control a creature with flying.", "Creature — Beast"),   # kw on kw
                ("As long as ~ is monstrous, it has flying until end of turn.", "Creature — Beast"),
                ("Equipped creature gets +1/+1 as long as it's a Human.", "Enchantment — Aura"),    # not an Equipment
        ):
            self.ignored(text, types)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.my_turn = True
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x


class Playing(Base):
    def test_self_keyword_follows_its_condition(self):
        crab = self.perm(gated("As long as ~ is monstrous, it has hexproof."), self.a)
        self.assertFalse(crab.has("hexproof"))
        crab.monstrous = True
        self.assertTrue(crab.has("hexproof"))

    def test_host_bonus_checks_the_host(self):
        fork = self.perm(gated("As long as equipped creature is a Human, it gets +1/+1 and has first strike.",
                               "Artifact — Equipment"), self.a)
        bear, human = self.perm(BEAR, self.a), self.perm(HUMAN, self.a)
        fork.attached_to = bear
        bear.equipment.append(fork)
        self.assertEqual((bear.power, bear.toughness, bear.has("first strike")), (2, 2, False))
        bear.equipment.remove(fork)
        fork.attached_to = human
        human.equipment.append(fork)
        self.assertEqual((human.power, human.toughness, human.has("first strike")), (3, 3, True))

    def test_group_grant_only_during_your_turn(self):
        self.perm(gated("During your turn, creatures you control have double strike.", "Enchantment"), self.a)
        bear, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.assertTrue(bear.has("double strike"))
        self.assertFalse(theirs.has("double strike"))
        self.a.my_turn, self.b.my_turn, self.game.active_idx = False, True, 1
        self.assertFalse(bear.has("double strike"))

    def test_gated_rule_reaches_static_rules(self):
        self.perm(gated("As long as you control a Gate, creatures you control can't be blocked by Walls.",
                        "Enchantment"), self.a)
        bear, wall = self.perm(BEAR, self.a), self.perm(WALL, self.b)
        from mtgsim.cx_grammar_evasion import block_forbidden
        self.assertFalse(block_forbidden(wall, bear))
        self.perm(card("Test Gate", "", "Land — Gate", ""), self.a)
        self.assertTrue(block_forbidden(wall, bear))

    def test_defender_permission(self):
        wall = self.perm(card("Gate Wall", "{1}", "Creature — Wall",
                              "Defender\nAs long as you control a Gate, ~ can attack as though it didn't have defender.",
                              2, 2), self.a)
        wall.sick = False
        self.assertFalse(wall.can_attack())
        self.perm(card("Test Gate", "", "Land — Gate", ""), self.a)
        self.assertTrue(wall.can_attack())

    def test_exactly_one_creature(self):
        self.perm(gated("As long as you control exactly one creature, that creature gets +2/+0 and has lifelink.",
                        "Enchantment"), self.a)
        bear = self.perm(BEAR, self.a)
        self.assertEqual((bear.power, bear.has("lifelink")), (4, True))
        self.perm(HUMAN, self.a)
        self.assertEqual((bear.power, bear.has("lifelink")), (2, False))

    def test_scaled_self_counts_others(self):
        mob = self.perm(card("Mob", "{1}{G}", "Creature — Squirrel",
                             "~ gets +1/+1 for each other Squirrel on the battlefield.", 1, 1), self.a)
        self.assertEqual(mob.power, 1)
        self.perm(card("Sq", "{G}", "Creature — Squirrel", "", 1, 1), self.b)
        self.perm(card("Sq", "{G}", "Creature — Squirrel", "", 1, 1), self.a)
        self.assertEqual((mob.power, mob.toughness), (3, 3))

    def test_scaled_host_by_counters_on_source_and_hostile_aura(self):
        saw = self.perm(gated("Equipped creature gets +X/+0, where X is the number of rev counters on ~.",
                              "Artifact — Equipment"), self.a)
        bear = self.perm(BEAR, self.a)
        saw.attached_to = bear
        bear.equipment.append(saw)
        saw.counters["rev"] = 3
        self.assertEqual((bear.power, bear.toughness), (5, 2))
        curse = gated("Enchant creature\nEnchanted creature gets -X/-0, where X is the number of cards in your "
                      "graveyard.", "Enchantment — Aura")
        self.assertTrue(curse.aura_hostile)
        theirs = self.perm(BEAR, self.b)
        from mtgsim.auras import choose_host
        self.assertIs(choose_host(self.game, self.a, curse), theirs)
        aura = self.perm(curse, self.a)
        aura.aura_host = theirs
        theirs.auras.append(aura)
        self.a.graveyard = [ISLAND, ISLAND]
        self.assertEqual(theirs.power, 0)

    def test_other_means_the_recipient_or_the_source(self):
        self.perm(gated("Each Skeleton you control gets +X/+0, where X is the number of other Skeletons you control.",
                        "Enchantment"), self.a)
        skel = card("Skel", "{B}", "Creature — Skeleton", "", 1, 1)
        one, two = self.perm(skel, self.a), self.perm(skel, self.a)
        self.assertEqual((one.power, two.power), (2, 2))          # each counts the other one, not itself
        mask = self.perm(gated("Enchant creature\nEnchanted creature gets +2/+2 for each other enchantment on the "
                               "battlefield.", "Enchantment — Aura"), self.a)
        bear = self.perm(BEAR, self.a)
        mask.aura_host = bear
        bear.auras.append(mask)
        self.assertEqual(bear.power, 4)                           # the Skeleton enchantment, not the Mask itself
        self.assertFalse(card("Lord", "{3}", "Creature — Elf", "Other creatures you control get +1/+1 for each other "
                              "creature you control.", 2, 2).advanced_rules.get("gated"))   # either could be meant

    def test_life_total_scale(self):
        shadow = self.perm(card("Shade", "{B}", "Creature — Avatar", "~ gets -X/-X, where X is your life total.",
                                13, 13), self.a)
        self.a.life = 10
        self.assertEqual((shadow.power, shadow.toughness), (3, 3))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB(offline=True)
        for name in ("Champion's Helm", "Skittering Crustacean", "Detective of the Month", "Steel of the Godhead",
                     "Mechan Shieldmate", "Deadly Wanderings", "Sharpened Pitchfork", "Goblin Caves",
                     "Scourge of Geier Reach", "Squirrel Mob", "Chainsaw", "Death's Shadow", "Quag Sickness",
                     "Essence Channeler", "Tendershoot Dryad"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()


GOYF = card("Test Goyf", "{1}{G}", "Creature — Lhurgoyf",
            "~'s power is equal to the number of card types among cards in all graveyards and its toughness is equal "
            "to that number plus 1.", 0, 0)


class CharacteristicDefining(Base):
    def test_parses(self):
        self.assertEqual(GOYF.unsupported, [])
        kavu = card("Kavu", "{2}{R}{G}", "Creature — Kavu",
                    "~'s power is equal to the number of red creatures on the battlefield.\n"
                    "~'s toughness is equal to the number of green creatures on the battlefield.", 0, 0)
        self.assertEqual(kavu.unsupported, [])
        self.assertTrue(all(kavu.advanced_rules["cda"]))
        for text in ("~'s power and toughness are each equal to the total power of creatures you control.",
                     "~'s power and toughness are each equal to the number of cards in the chosen zone."):
            self.assertTrue(card("X", "{2}", "Creature — Beast", text, 0, 0).unsupported, text)

    def test_base_follows_the_count_and_set_base_wins(self):
        goyf = self.perm(GOYF, self.a)
        self.assertEqual((goyf.power, goyf.toughness), (0, 1))
        self.b.graveyard = [ISLAND, BEAR]
        self.assertEqual((goyf.power, goyf.toughness), (2, 3))
        goyf.pump_p = 1
        self.assertEqual(goyf.power, 3)                       # modifiers apply on top of the defined base
        from mtgsim import continuous
        continuous.add(self.game, goyf, "set_base", power=1, toughness=1)
        self.assertEqual((goyf.power, goyf.toughness), (2, 1))  # a later set-base effect overrides (layer 7b)

    def test_scaled_twice_plus(self):
        elder = self.perm(card("Elder", "{3}", "Creature — Beast",
                               "~'s power and toughness are each equal to 1 plus twice the number of age counters on it.",
                               0, 0), self.a)
        elder.counters["age"] = 2
        self.assertEqual((elder.power, elder.toughness), (5, 5))

    def test_ai_casts_it(self):
        self.b.graveyard = [ISLAND, BEAR]
        self.a.battlefield += [Permanent(card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)"), self.a)
                               for _ in range(2)]
        self.a.hand = [GOYF]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(GOYF, self.a.hand)
        while self.game.stack:
            self.game.resolve_top()
        self.assertEqual([x.power for x in self.a.battlefield if x.card.name == "Test Goyf"], [2])


MOUNTAIN = card("Mountain", "", "Basic Land — Mountain", "({T}: Add {R}.)")


class MoreConditions(Base):
    def test_graveyard_static(self):
        anger = card("Anger", "{3}{R}", "Creature — Incarnation",
                     "Haste\nAs long as this card is in your graveyard and you control a Mountain, "
                     "creatures you control have haste.", 2, 2)
        self.assertEqual(anger.unsupported, [])
        bear, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.a.graveyard = [anger]
        self.assertFalse(bear.has("haste"))
        self.perm(MOUNTAIN, self.a)
        self.assertTrue(bear.has("haste"))
        self.assertFalse(theirs.has("haste"))
        self.a.graveyard = []
        on_field = self.perm(anger, self.a)            # on the battlefield the line does nothing (only its own haste)
        self.assertFalse(bear.has("haste"))
        self.assertTrue(on_field.has("haste"))

    def test_either_subtype_and_host_controller(self):
        warg = self.perm(card("Warg", "{2}{B}", "Creature — Wolf",
                              "As long as you control a Goblin or Orc, ~ gets +1/+0.", 2, 2), self.a)
        self.assertEqual(warg.power, 2)
        self.perm(card("Orc", "{B}", "Creature — Orc", "", 1, 1), self.a)
        self.assertEqual(warg.power, 3)
        destiny = card("Destiny", "{1}{W}", "Enchantment — Aura",
                       "Enchant creature\nEnchanted creature has shroud as long as its controller controls another "
                       "creature.")
        self.assertEqual(destiny.unsupported, [])
        bear = self.perm(BEAR, self.b)
        aura = self.perm(destiny, self.a)
        aura.aura_host = bear
        bear.auras.append(aura)
        self.assertFalse(bear.has("shroud"))
        self.perm(BEAR, self.b)
        self.assertTrue(bear.has("shroud"))

    def test_any_counter_and_enchanted_or_equipped(self):
        wall = self.perm(card("Wall", "{1}{B}", "Creature — Wall",
                              "Defender\nAs long as ~ has a counter on it, it can attack as though it didn't have "
                              "defender.", 3, 3), self.a)
        wall.sick = False
        self.assertFalse(wall.can_attack())
        wall.counters["-1/-1"] = 1
        self.assertTrue(wall.can_attack())
