"""Vertical mechanics batch 4: For Mirrodin!, becomes prepared, and the predecessor
residuals that fit the dice / pay-repeat machinery — Arcane Endeavor's free cast,
Mr. House's Treasure rider and one-die ability, and Primal Adversary's land animation.
"""
import dataclasses
import random
import unittest

from mtgsim import dungeon_mechanics
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, PLAINS, card

BARDICHE = card("Mirran Bardiche", "{2}{W}", "Artifact — Equipment",
                "For Mirrodin!\nEquipped creature gets +2/+1 and has vigilance.\nEquip {3}{W}")
SKYCOACH = card("Skycoach Waypoint", "", "Land",
                "{T}: Add {C}.\n{3}, {T}: Target creature becomes prepared.")
HEXHAVEN = card("Hexhaven Dueling Arena", "", "Land",
                "{T}: Add {C}.\n{2}, {T}: Target creature that attacked this turn becomes "
                "prepared. Activate only as a sorcery.\n{4}, {T}: Target creature becomes prepared.")
BIBLIPLEX = card("Biblioplex Tomekeeper", "{2}{W}", "Creature — Human Cleric",
                 "When this creature enters, choose up to one —\n• Target creature becomes "
                 "prepared.\n• Target creature becomes unprepared.", 2, 2)
ARCANE = card("Arcane Endeavor", "{X}{U}{R}", "Sorcery",
              "Roll two d8 and choose one result. Draw cards equal to that result. Then you "
              "may cast an instant or sorcery spell with mana value less than or equal to the "
              "other result from your hand without paying its mana cost.")
MR_HOUSE = card("Mr. House, President and CEO", "{3}{B}{R}", "Legendary Creature — Human",
                "Whenever you roll a 4 or higher, create a 3/3 colorless Robot artifact "
                "creature token. If you rolled 6 or higher, instead create that token and a "
                "Treasure token.\n{4}, {T}: Roll a six-sided die plus an additional six-sided "
                "die for each mana from Treasures spent to activate this ability.", 3, 4)
PRIMAL = card("Primal Adversary", "{1}{G}", "Creature — Wolf",
              "Trample\nWhen this creature enters, you may pay {1}{G} any number of times. "
              "When you pay this cost one or more times, put that many +1/+1 counters on "
              "this creature, then up to that many target lands you control become 3/3 Wolf "
              "creatures with haste that are still lands.", 2, 2)
FOREST = card("Test Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")
RENDEZVOUS = card("Secret Rendezvous", "{1}{W}", "Instant", "You draw a card.")
PREPARED_DUDE = dataclasses.replace(BEAR, name="Prepared Dude", back=RENDEZVOUS)
BOLT = card("Test Bolt", "{2}{R}", "Instant", "Test Bolt deals 3 damage to any target.")
ANALYST = card("Paranormal Analyst", "{1}{U}", "Creature — Human Detective",
               "Whenever you manifest dread, put a card you put into your graveyard this "
               "way into your hand.", 2, 2)
PIPES = card("They Came from the Pipes", "{2}{U}", "Sorcery", "Manifest dread twice.")
STAY_HIDDEN = card("Stay Hidden, Stay Silent", "{2}{U}", "Enchantment — Aura", "Enchant creature\n"
                   "When this Aura enters, tap enchanted creature.\nEnchanted creature doesn't "
                   "untap during its controller's untap step.\n{4}{U}{U}: Shuffle enchanted "
                   "creature into its owner's library, then manifest dread. Activate only as a "
                   "sorcery.")


def _kinds(effects):
    return [e.kind for e in effects]


class ParseBatch4(unittest.TestCase):
    def test_for_mirrodin_trigger_and_clean_parse(self):
        self.assertEqual(BARDICHE.unsupported, [])
        self.assertEqual([(t.event, _kinds(t.effects)) for t in BARDICHE.triggers],
                         [("etb", ["for_mirrodin"])])
        self.assertEqual(BARDICHE.equip_cost, {"generic": 3, "W": 1})

    def test_prepare_wordings(self):
        self.assertEqual(SKYCOACH.unsupported, [])
        self.assertEqual(HEXHAVEN.unsupported, [])        # the attacked-this-turn restriction sub
        for ability in SKYCOACH.activated + HEXHAVEN.activated:
            if ability.text.startswith("{3}") or ability.text.startswith("{4}"):
                self.assertEqual(_kinds(ability.effects), ["prepare"])
        effs, bad = _parse_effects("Target creature becomes prepared.")
        self.assertFalse(bad)
        self.assertEqual((effs[0].kind, effs[0].data["prepared"]), ("prepare", True))
        effs, bad = _parse_effects("Target creature becomes unprepared.")
        self.assertEqual((effs[0].kind, effs[0].data["prepared"]), ("prepare", False))

    def test_biblioplex_modes(self):
        self.assertEqual(BIBLIPLEX.unsupported, [])
        etb = [t for t in BIBLIPLEX.triggers if t.event == "etb"]
        self.assertEqual(len(etb), 1)
        self.assertEqual(len(etb[0].modes), 2)
        self.assertEqual([m[0].kind for m in etb[0].modes], ["prepare", "prepare"])
        self.assertEqual([m[0].data["prepared"] for m in etb[0].modes], [True, False])

    def test_prepare_all_wording(self):
        effs, bad = _parse_effects("Each creature you control becomes prepared.")
        self.assertFalse(bad)
        self.assertEqual(effs[0].kind, "prepare_all")

    def test_manifest_dread_listener_parse(self):
        self.assertEqual(ANALYST.unsupported, [])
        self.assertEqual([(t.event, _kinds(t.effects)) for t in ANALYST.triggers],
                         [("manifest_dread", ["manifest_recover"])])
        self.assertEqual(STAY_HIDDEN.unsupported, [])
        shuffle = [a for a in STAY_HIDDEN.activated if "Shuffle" in a.text]
        self.assertEqual(len(shuffle), 1)
        self.assertEqual(_kinds(shuffle[0].effects), ["shuffle_enchanted", "manifest_dread"])

    def test_arcane_endeavor_free_cast_parse(self):
        self.assertEqual(ARCANE.unsupported, [])
        self.assertEqual(_kinds(ARCANE.spell_effects), ["die_roll", "die_amount", "die_free_cast"])
        self.assertEqual((ARCANE.spell_effects[0].data["sides"],
                          ARCANE.spell_effects[0].data["count"]), (8, 2))
        self.assertEqual(ARCANE.spell_effects[2].data["agg"], "other")

    def test_mr_house_parse(self):
        self.assertEqual(MR_HOUSE.unsupported, [])
        events = [t.event for t in MR_HOUSE.triggers]
        self.assertEqual(events, ["you_roll>=4"])
        robot, check = MR_HOUSE.triggers[0].effects
        self.assertEqual((robot.kind, robot.data["power"]), ("token", 3))
        self.assertEqual(check.kind, "die_check")
        self.assertEqual((check.data["lo"], check.data["hi"]), (6, 99))
        self.assertEqual((check.data["then"][0].kind, check.data["then"][0].data.get("kind")),
                         ("token", "treasure"))
        roll = [a for a in MR_HOUSE.activated if "Roll" in a.text]
        self.assertEqual(len(roll), 1)                       # the Treasure-scaled rider sub'd away
        self.assertEqual(_kinds(roll[0].effects), ["die_roll"])
        self.assertEqual(roll[0].effects[0].data["sides"], 6)

    def test_primal_adversary_parse(self):
        self.assertEqual(PRIMAL.unsupported, [])
        etb = [t for t in PRIMAL.triggers if t.event == "etb"]
        self.assertEqual(len(etb), 1)
        self.assertEqual(_kinds(etb[0].effects), ["pay_repeat", "pay_repeat_lands"])
        self.assertEqual(etb[0].effects[1].data["power"], 3)


class EngineBatch4(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def faces(self, *values, who=None):
        who = who or self.a
        self.g.__dict__.setdefault("_die_faces", {})[who] = list(values)
        self.g.__dict__.setdefault("_die_rolls", {})[who] = sum(values)

    def apply(self, text, targets=()):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets)
        prev = None
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item, prev=prev)
            prev = target
        self.g.settle()
        return item

    # --- For Mirrodin! ---------------------------------------------------------
    def test_for_mirrodin_creates_and_attaches_rebel(self):
        axe = self.g.enter_battlefield(self.a, BARDICHE)
        self.g.settle()
        rebels = [x for x in self.a.battlefield if x.card.name == "Rebel token"]
        self.assertEqual(len(rebels), 1)
        rebel = rebels[0]
        self.assertIs(axe.attached_to, rebel)
        self.assertEqual((rebel.power, rebel.toughness), (4, 3))   # 2/2 Rebel, +2/+1 equip bonus
        self.assertTrue(rebel.has("vigilance"))

    def test_for_mirrodin_equip_moves_later(self):
        axe = self.g.enter_battlefield(self.a, BARDICHE)
        self.g.settle()
        for _ in range(4):
            self.g.enter_battlefield(self.a, PLAINS)     # Equip {3}{W}
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.g.settle()
        self.assertTrue(self.g.equip(self.a, axe, bear))
        self.assertIs(axe.attached_to, bear)

    # --- becomes prepared ------------------------------------------------------
    def test_prepare_and_unprepare_flag(self):
        dude = self.g.enter_battlefield(self.a, PREPARED_DUDE)
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.g.settle()
        self.assertFalse(dude.prepared)
        self.apply("Target creature becomes prepared.", [dude])
        self.assertTrue(dude.prepared)
        self.apply("Target creature becomes prepared.", [bear])
        self.assertFalse(bear.prepared)          # no prepare spell: stays unprepared
        self.apply("Target creature becomes unprepared.", [dude])
        self.assertFalse(dude.prepared)

    def test_prepare_all(self):
        dude = self.g.enter_battlefield(self.a, PREPARED_DUDE)
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.g.settle()
        self.apply("Each creature you control becomes prepared.")
        self.assertTrue(dude.prepared)
        self.assertFalse(bear.prepared)

    # --- dice residuals --------------------------------------------------------
    def test_arcane_endeavor_free_cast(self):
        self.a.hand = [BOLT, RENDEZVOUS]
        self.faces(7, 2)                                # chosen 7, other 2: budget 2
        self.apply("You may cast an instant or sorcery spell with mana value less than or "
                   "equal to the other result from your hand without paying its mana cost.")
        self.assertNotIn(RENDEZVOUS, self.a.hand)       # cmc 2: cast for free
        self.assertIn(BOLT, self.a.hand)                # cmc 3: over the budget

    def test_arcane_endeavor_nothing_affordable(self):
        self.a.hand = [BOLT]
        self.faces(7, 1)                                # budget 1: nothing affordable
        self.apply("You may cast an instant or sorcery spell with mana value less than or "
                   "equal to the other result from your hand without paying its mana cost.")
        self.assertIn(BOLT, self.a.hand)

    def test_mr_house_rolls(self):
        house = self.g.enter_battlefield(self.a, MR_HOUSE)
        self.g.settle()
        self.apply("Roll a six-sided die.")
        robots = [x for x in self.a.battlefield if x.card.name == "Robot token"]
        treasures = [x for x in self.a.battlefield if x.card.token_kind == "treasure"]
        total = dungeon_mechanics._last_die(self.g, self.a)
        if total >= 6:
            self.assertEqual(len(robots), 1)
            self.assertEqual(len(treasures), 1)
        elif total >= 4:
            self.assertEqual(len(robots), 1)
            self.assertEqual(len(treasures), 0)
        self.assertIsNotNone(house)

    def test_mr_house_high_roll_pinned(self):
        self.g.enter_battlefield(self.a, MR_HOUSE)
        self.g.settle()
        for perm in list(self.a.battlefield):
            if perm.card.name != "Mr. House, President and CEO":
                self.g.leave_battlefield(perm, "hand")
        self.faces(6)                                   # one face: a 6
        self.g.fire(self.a, "you_roll>=4")
        self.g.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.name == "Robot token"]), 1)
        self.assertEqual(len([x for x in self.a.battlefield if x.card.token_kind == "treasure"]), 1)

    def test_mr_house_low_roll_pinned(self):
        self.g.enter_battlefield(self.a, MR_HOUSE)
        self.g.settle()
        for perm in list(self.a.battlefield):
            if perm.card.name != "Mr. House, President and CEO":
                self.g.leave_battlefield(perm, "hand")
        self.faces(4)
        self.g.fire(self.a, "you_roll>=4")
        self.g.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.name == "Robot token"]), 1)
        self.assertEqual(len([x for x in self.a.battlefield if x.card.token_kind == "treasure"]), 0)

    # --- Primal Adversary ------------------------------------------------------
    def test_primal_adversary_animation(self):
        for _ in range(6):
            self.g.enter_battlefield(self.a, FOREST)
        primal = self.g.enter_battlefield(self.a, PRIMAL)
        self.g.settle()
        wolves = [x for x in self.a.battlefield
                  if x.card.is_land and "Creature" in x.card.types]
        self.assertEqual(len(wolves), 3)                 # {1}{G} twice per payment, thrice here
        for wolf in wolves:
            self.assertTrue(wolf.is_creature)
            self.assertEqual((wolf.power, wolf.toughness), (3, 3))
            self.assertIn("Wolf", wolf.card.subtypes)
            self.assertTrue(wolf.has("haste"))
        self.assertEqual(primal.counters.get("+1/+1", 0), 3)
        self.assertEqual(primal.power, 5)                # 2/2 with three +1/+1 counters

    # --- manifest dread residuals ----------------------------------------------
    def test_paranormal_analyst_recovers_milled_card(self):
        self.g.enter_battlefield(self.a, ANALYST)
        fresh = [card("Doomed Bear", "{1}{G}", "Creature — Bear", "", 2, 2),
                 card("Doomed Bolt", "{1}{R}", "Instant", "Doomed Bolt deals 3 damage to any target.")]
        self.a.library = [card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")
                          for _ in range(20)] + fresh    # top of the library: the fresh cards
        self.apply("Manifest dread twice.")
        self.assertEqual(len(self.a.graveyard), 0)        # both milled cards were recovered
        self.assertEqual(len([c for c in fresh if c in self.a.hand]), 1)   # the Bear manifested,
        faces = [x for x in self.a.battlefield if x.card.name == "Face-down creature"]
        self.assertEqual(len(faces), 2)                  # the Bolt came back instead

    def test_stay_hidden_shuffles_host_then_dreads(self):
        aura = self.g.enter_battlefield(self.a, STAY_HIDDEN)
        bear = self.g.enter_battlefield(self.b, BEAR)     # opponent's host: shuffled away
        aura.aura_host = bear
        self.g.settle()
        effs, bad = _parse_effects("Shuffle enchanted creature into its owner's library, "
                                   "then manifest dread.")
        self.assertFalse(bad)
        item = StackItem(self.a, list(effs), [], source=aura)
        for eff in effs:
            self.g.resolve(self.a, eff, None, item)
        self.g.settle()
        self.assertNotIn(bear, self.b.battlefield)        # the host is gone from play
        self.assertIn(bear.front, self.b.library)         # it sits in its owner's library
        faces = [x for x in self.a.battlefield if x.card.name == "Manifest"]
        self.assertEqual(len(faces), 1)                   # the dread manifested the top card


if __name__ == "__main__":
    unittest.main()
