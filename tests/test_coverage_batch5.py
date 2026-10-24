"""Coverage batch: effects on every player, tap-and-freeze, party, per-count pumps and counters, optional removal
aimed at an opponent, random discard, poison, subtype team pumps and subtype targets."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, card

EXECUTIONER = card("Test Executioner", "{2}{B}", "Creature — Human", "When ~ enters, each player sacrifices a creature.", 2, 1)
RESPITE = card("Test Respite", "{G}", "Instant", "Target player shuffles their graveyard into their library.")
FROST = card("Test Frost", "{2}{U}", "Instant", "Tap up to two target creatures. Those creatures don't untap during their "
             "controller's next untap step.")
SLEEP = card("Test Sleep", "{2}{U}{U}", "Sorcery", "Tap all creatures target player controls. Those creatures don't untap "
             "during that player's next untap step.")
ALLIANCE = card("Test Alliance", "{4}{B}", "Instant", "This spell costs {1} less to cast for each creature in your party.\n"
                "Destroy target creature.")
CLERIC = card("Test Cleric", "{W}", "Creature — Human Cleric", "", 1, 1)
ROGUE_WIZ = card("Test Rogue Wizard", "{U}", "Creature — Human Rogue Wizard", "", 1, 1)
SCOUT = card("Test Scout", "{G}", "Instant", "If you have a full party, draw a card.")
CHANGELING = card("Test Shapeshifter", "{1}", "Creature — Shapeshifter", "Changeling", 1, 1)
LANCE = card("Test Lance", "{2}", "Artifact — Equipment", "Equipped creature gets +1/+1 for each artifact you control.\n"
             "Equip {1}", )
MIGHT = card("Test Might", "{G}", "Instant", "Target creature gets +1/+1 until end of turn for each Forest you control.")
TROLL = card("Test Troll", "{3}{G}", "Creature — Troll", "~ enters with a +1/+1 counter on it for each creature card in "
             "your graveyard.", 0, 0)
HERDER = card("Test Herder", "{2}{G}", "Creature — Elf", "~ enters with a +1/+1 counter on it for each Elf you control.", 1, 1)
SAGE = card("Test Sage", "{1}{G}", "Creature — Human", "When ~ enters, you may destroy target artifact or enchantment.", 2, 1)
TROPHY = card("Test Trophy", "{1}", "Artifact", "")
SPECTER = card("Test Specter", "{1}{B}{B}", "Creature — Specter", "Flying\nWhenever ~ deals damage to an opponent, that "
               "player discards a card at random.", 2, 2)
MOSQUITO = card("Test Mosquito", "{1}{B}", "Creature — Insect", "Whenever ~ attacks and isn't blocked, defending player "
                "gets a poison counter.", 0, 1)
UNWIND = card("Test Unwind", "{2}{U}", "Instant", "Untap up to three lands.")
SKEINS = card("Test Skeins", "{1}{U}", "Instant", "Each player draws two cards.")
NAME = card("Test Name", "{1}{W}", "Instant", "Zombies you control get +2/+1 until end of turn.")
ZOMBIE = card("Test Zombie", "{B}", "Creature — Zombie", "", 2, 2)
GRAVEYARD = card("Test Graveyard", "", "Land", "{T}: Regenerate target Elephant.")
ELEPHANT = card("Test Elephant", "{G}", "Creature — Elephant", "", 2, 2)
SKYFISHER = card("Test Skyfisher", "{1}{W}", "Creature — Kor Bird", "Flying\nWhen ~ enters, return a permanent you control "
                 "to its owner's hand.", 2, 3)
PEPPER = card("Test Pepper", "{B}", "Instant", "Target creature gets -1/-1 until end of turn. If you control a Faerie, draw "
              "a card.")
FAERIE = card("Test Faerie", "{1}{U}", "Creature — Faerie", "Flying", 1, 1)
ASSAULT = card("Test Assault", "{R}{G}", "Sorcery", "~ deals damage to target creature equal to the number of lands you "
               "control.")
BERSERKER = card("Test Berserker", "{G}", "Creature — Elf Berserker", "Whenever ~ becomes blocked, it gets +1/+1 until end "
                 "of turn for each creature blocking it.", 1, 1)
ORCS = card("Test Orcs", "{2}{R}", "Creature — Orc", "~ can't block creatures with power 2 or greater.", 3, 2)
MINOTAUR = card("Test Minotaur", "{2}{R}", "Creature — Minotaur", "You may exert ~ as it attacks. When you do, it gets "
                "+1/+1 and gains menace until end of turn.", 3, 3)
ALL = (MINOTAUR, ASSAULT, BERSERKER, ORCS, EXECUTIONER, RESPITE, FROST, SLEEP, ALLIANCE, SCOUT, LANCE, MIGHT, TROLL, HERDER, SAGE, SPECTER, MOSQUITO, UNWIND,
       SKEINS, NAME, GRAVEYARD, SKYFISHER, PEPPER)


class CoverageBatch5(unittest.TestCase):
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

    def test_templates(self):
        for c in ALL:
            self.assertEqual(c.unsupported, [], c.name)

    def test_each_player_sacrifices(self):
        self.put(self.a, BEAR)
        self.put(self.b, BEAR)
        self.put(self.a, EXECUTIONER)
        self.assertEqual(len(self.b.creatures), 0)
        self.assertEqual(len(self.a.creatures), 1)

    def test_graveyard_shuffle_and_each_draw(self):
        self.a.graveyard[:] = [BEAR] * 3
        self.game.resolve(self.a, RESPITE.spell_effects[0], self.a)
        self.assertEqual((len(self.a.graveyard), len(self.a.library)), (0, 23))
        self.game.resolve(self.a, SKEINS.spell_effects[0], None)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (2, 2))

    def test_frozen_taps(self):
        bears = [self.put(self.b, BEAR) for _ in range(3)]
        for e in SLEEP.spell_effects:
            self.game.resolve(self.a, e, self.b)
        self.assertTrue(all(x.tapped and x.skip_untap for x in bears))
        other = self.put(self.b, BEAR)
        self.game.resolve(self.a, FROST.spell_effects[0], other)
        self.game.resolve(self.a, FROST.spell_effects[1], None)
        self.assertEqual(other.skip_untap, 1)

    def test_party(self):
        from mtgsim.discounts import party_size
        self.put(self.a, CLERIC)
        self.put(self.a, ROGUE_WIZ)
        self.assertEqual(party_size(self.a), 2)            # one creature fills one slot
        self.put(self.a, ROGUE_WIZ)
        self.assertEqual(party_size(self.a), 3)
        self.assertEqual(self.game.cost_of(self.a, ALLIANCE)["generic"], 1)
        self.assertFalse(self.game.check_cond(self.a, SCOUT.spell_effects[0], None, None))
        self.put(self.a, CHANGELING)
        self.assertEqual(party_size(self.a), 4)
        self.assertTrue(self.game.check_cond(self.a, SCOUT.spell_effects[0], None, None))

    def test_per_count_pumps_and_counters(self):
        bear = self.put(self.a, BEAR)
        lance = self.put(self.a, LANCE)
        lance.attached_to = bear
        self.put(self.a, TROPHY)
        self.assertEqual(bear.power, 4)                    # two artifacts
        self.put(self.a, FOREST, 3)
        self.game.resolve(self.a, MIGHT.spell_effects[0], bear)
        self.assertEqual(bear.toughness, 7)
        self.a.graveyard[:] = [BEAR, BEAR, ISLAND]
        self.assertEqual(self.put(self.a, TROLL).p1, 2)
        self.put(self.a, card("Test Elf", "{G}", "Creature — Elf", "", 1, 1), 2)
        self.assertEqual(self.put(self.a, HERDER).p1, 2)

    def test_optional_removal_only_at_a_foe(self):
        mine = self.put(self.a, TROPHY)
        self.put(self.a, SAGE)
        self.assertIn(mine, self.a.battlefield)
        theirs = self.put(self.b, TROPHY)
        self.put(self.a, SAGE)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_random_discard_poison_untap(self):
        self.b.hand[:] = [BEAR, ISLAND]
        trig = SPECTER.triggers[0]
        self.game.resolve(self.a, trig.effects[0], self.b)
        self.assertEqual(len(self.b.hand), 1)
        self.game.resolve(self.a, MOSQUITO.triggers[0].effects[0], self.b)
        self.assertEqual(self.b.counters["poison"], 1)
        lands = [self.put(self.a, ISLAND) for _ in range(4)]
        for x in lands:
            x.tapped = True
        self.game.resolve(self.a, UNWIND.spell_effects[0], None)
        self.assertEqual(sum(x.tapped for x in lands), 1)

    def test_subtype_pumps_and_targets(self):
        zombie, bear = self.put(self.a, ZOMBIE), self.put(self.a, BEAR)
        self.game.resolve(self.a, NAME.spell_effects[0], None)
        self.assertEqual((zombie.power, bear.power), (4, 2))
        elephant = self.put(self.a, ELEPHANT)
        eff = GRAVEYARD.activated[0].effects[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [elephant])
        self.put(self.a, FAERIE)
        self.assertTrue(self.game.check_cond(self.a, PEPPER.spell_effects[1], None, None))

    def test_return_a_permanent(self):
        land = self.put(self.a, ISLAND)
        land.tapped = True
        self.put(self.a, SKYFISHER)
        self.assertIn(ISLAND, self.a.hand)


    def test_damage_per_land_blockers_and_power_limit(self):
        from mtgsim.engine.state import can_block
        self.put(self.a, ISLAND, 3)
        ogre = self.put(self.b, card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3))
        self.game.resolve(self.a, ASSAULT.spell_effects[0], ogre)
        self.assertNotIn(ogre, self.b.battlefield)
        berserker = self.put(self.a, BERSERKER)
        self.game.blocks = {berserker: [self.put(self.b, BEAR), self.put(self.b, BEAR)]}
        from mtgsim.engine.state import StackItem
        item = StackItem(self.a, [], [], source=berserker)
        self.game.resolve(self.a, BERSERKER.triggers[0].effects[0], berserker, item=item)
        self.assertEqual(berserker.power, 3)
        orcs = self.put(self.b, ORCS)
        self.assertFalse(can_block(orcs, self.put(self.a, BEAR)))
        self.assertTrue(can_block(orcs, self.put(self.a, card("Test Elf", "{G}", "Creature — Elf", "", 1, 1))))


    def test_exert(self):
        trig = MINOTAUR.triggers[0]
        self.assertEqual(trig.event, "attacks")
        self.assertIn("exert: always exerted when it attacks", MINOTAUR.approximations)
        from mtgsim.engine.state import StackItem
        minotaur = self.put(self.a, MINOTAUR)
        item = StackItem(self.a, [], [], source=minotaur)
        prev = None
        for e in trig.effects:
            prev = self.game.resolve(self.a, e, minotaur, item=item, prev=prev) or prev
        self.assertEqual((minotaur.skip_untap, minotaur.power), (1, 4))
        self.assertTrue(minotaur.has("menace"))


if __name__ == "__main__":
    unittest.main()
