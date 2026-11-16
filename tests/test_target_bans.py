"""#643 slice 1: "can't be the target of ..." on ~, hosts and groups (mtgsim.target_bans, Game.targetable)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, SHOCK, card

SHANNA = card("Test Shanna", "{G}{W}", "Legendary Creature — Human", "~ can't be the target of abilities your "
              "opponents control.", 2, 2)
PALADIN = card("Test Paladin", "{1}{W}{W}", "Creature — Human Knight", "First strike, lifelink\n~ can't be the target "
               "of black or red spells your opponents control.", 2, 2)
REVENGE = card("Test Revenge", "{5}{G}{G}", "Creature — Elemental", "Haste\n~ can't be the target of nongreen "
               "spells or abilities from nongreen sources.", 8, 5)
TETSUO = card("Test Tetsuo", "{U}{B}{R}", "Legendary Creature — Human", "~ can't be the target of Aura spells.", 1, 3)
PLAX = card("Test Plax", "{2}{G/U}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't be the target "
            "of spells or abilities your opponents control.")
CENTAUR = card("Test Centaur", "{2}{G}", "Creature — Centaur", "Creatures you control can't be the targets of blue "
               "spells or abilities from blue sources.", 3, 3)
WARD = card("Test Artifact Ward", "{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't be the "
            "target of abilities from artifact sources.")
DOOM = card("Test Doom Blade", "{1}{B}", "Instant", "Destroy target creature.")
GIANT_GROWTH = card("Test Growth", "{G}", "Instant", "Target creature gets +3/+3 until end of turn.")
UNSUMMON = card("Test Unsummon", "{U}", "Instant", "Return target creature to its owner's hand.")
PACIFISM = card("Test Pacifism", "{1}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack.")
PINGER = card("Test Pinger", "{2}{R}", "Creature — Human Wizard", "{T}: ~ deals 1 damage to any target.", 1, 1)
ROD = card("Test Rod", "{3}", "Artifact", "{T}: ~ deals 1 damage to any target.")


class Parsing(unittest.TestCase):
    def test_positives(self):
        self.assertEqual(SHANNA.advanced_rules["target_ban"], ({"kind": "ability", "opp": True},))
        self.assertEqual(PALADIN.advanced_rules["target_ban"],
                         ({"kind": "spell", "opp": True, "aura": False, "colors": ("B", "R")},))
        self.assertEqual(REVENGE.advanced_rules["target_ban"],
                         ({"kind": "spell", "opp": False, "aura": False, "non": "G"},
                          {"kind": "ability", "opp": False, "non": "G"}))
        self.assertTrue(TETSUO.advanced_rules["target_ban"][0]["aura"])
        self.assertEqual(len(PLAX.advanced_rules["target_ban_host"]), 2)
        (spec, found), = CENTAUR.advanced_rules["target_ban_group"]
        self.assertEqual(spec.get("controller"), "mine")
        for c in (SHANNA, PALADIN, REVENGE, TETSUO, PLAX, CENTAUR, WARD):
            self.assertEqual(c.unsupported, [], c.name)

    def test_refusals(self):
        for text in ("~ can't be the target of spells unless it attacked or blocked this turn.",
                     "~ can't be the target of spells that can target only Walls.",
                     "Cards in graveyards can't be the targets of spells or abilities.",
                     "This turn, creatures can't be the targets of spells.",
                     "~ can't be the target of purple spells.",
                     "~ can't be the target of spells or abilities your opponents control this turn."):
            c = card("X", "{1}", "Creature — Wall", text, 1, 1)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def spell(self, c, by):
        return StackItem(by, list(c.spell_effects), [None], card=c, name=c.name)

    def test_abilities_your_opponents_control(self):
        """Shanna: the opponent's abilities can't target her; their spells can, and so can her controller's abilities."""
        shanna = self.perm(SHANNA, self.a)
        theirs, mine = self.perm(PINGER, self.b), self.perm(PINGER, self.a)
        self.assertFalse(self.game.targetable(shanna, self.b, theirs))
        self.assertTrue(self.game.targetable(shanna, self.b, self.spell(SHOCK, self.b)))
        self.assertTrue(self.game.targetable(shanna, self.a, mine))

    def test_colored_spells_your_opponents_control(self):
        paladin = self.perm(PALADIN, self.a)
        self.assertFalse(self.game.targetable(paladin, self.b, self.spell(SHOCK, self.b)))      # red
        self.assertFalse(self.game.targetable(paladin, self.b, self.spell(DOOM, self.b)))       # black
        self.assertTrue(self.game.targetable(paladin, self.b, self.spell(UNSUMMON, self.b)))    # blue
        self.assertTrue(self.game.targetable(paladin, self.a, self.spell(DOOM, self.a)))        # its controller's

    def test_nongreen_for_everyone(self):
        """No "your opponents control": the controller's own nongreen spells can't target it either."""
        rev = self.perm(REVENGE, self.a)
        self.assertTrue(self.game.targetable(rev, self.b, self.spell(GIANT_GROWTH, self.b)))
        self.assertFalse(self.game.targetable(rev, self.a, self.spell(SHOCK, self.a)))
        self.assertFalse(self.game.targetable(rev, self.b, self.perm(ROD, self.b)))             # colourless source
        self.assertFalse(self.game.targetable(rev, self.b, self.perm(PINGER, self.b)))          # red source

    def test_aura_spells(self):
        tetsuo = self.perm(TETSUO, self.a)
        self.assertFalse(self.game.targetable(tetsuo, self.b, self.spell(PACIFISM, self.b)))
        self.assertTrue(self.game.targetable(tetsuo, self.b, self.spell(SHOCK, self.b)))

    def test_host_and_group(self):
        bear = self.perm(BEAR, self.a)
        plax = self.perm(PLAX, self.a)
        plax.attached_to = bear
        if plax not in bear.auras:
            bear.auras.append(plax)
        self.assertFalse(self.game.targetable(bear, self.b, self.spell(SHOCK, self.b)))
        self.assertTrue(self.game.targetable(bear, self.a, self.spell(GIANT_GROWTH, self.a)))
        other = self.perm(BEAR, self.a)
        self.assertTrue(self.game.targetable(other, self.b, self.spell(UNSUMMON, self.b)))
        self.perm(CENTAUR, self.a)
        self.assertFalse(self.game.targetable(other, self.b, self.spell(UNSUMMON, self.b)))
        self.assertTrue(self.game.targetable(other, self.b, self.spell(SHOCK, self.b)))
        theirs = self.perm(BEAR, self.b)
        self.assertTrue(self.game.targetable(theirs, self.a, self.spell(UNSUMMON, self.a)))     # only "you control"

    def test_ban_ends_when_the_source_leaves(self):
        other = self.perm(BEAR, self.a)
        centaur = self.perm(CENTAUR, self.a)
        self.assertFalse(self.game.targetable(other, self.b, self.spell(UNSUMMON, self.b)))
        self.game.leave_battlefield(centaur, "graveyard")
        self.assertTrue(self.game.targetable(other, self.b, self.spell(UNSUMMON, self.b)))


class HeuristicUse(Base):
    def test_ai_aims_around_the_ban(self):
        """HeuristicAI picks a legal target: the Paladin is out of reach of its Shock, the Bear isn't."""
        self.perm(PALADIN, self.a)
        bear = self.perm(BEAR, self.a)
        eff = SHOCK.spell_effects[0]
        with self.game.targeting(SHOCK):
            self.assertIs(self.b.ai.choose_target(self.game, self.b, eff, SHOCK), bear)

    def test_ai_still_pumps_its_own_banned_creature(self):
        """Its controller's own spells can still target it where the wording says "your opponents control"."""
        bear = self.perm(BEAR, self.a)
        plax = self.perm(PLAX, self.a)
        plax.attached_to = bear
        if plax not in bear.auras:
            bear.auras.append(plax)
        eff = GIANT_GROWTH.spell_effects[0]
        with self.game.targeting(GIANT_GROWTH):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, eff, GIANT_GROWTH), bear)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Shanna, Sisay's Legacy", "Shielding Plax", "Species 8472", "Artifact Ward", "Bartel Runeaxe",
                     "Tetsuo Umezawa", "Karplusan Strider", "Fiendslayer Paladin", "Gaea's Revenge",
                     "Mercenary Informer", "Rebel Informer", "Suq'Ata Firewalker", "Spellbane Centaur",
                     "Thrun, Breaker of Silence", "Dense Foliage"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))
        for name in ("Lurker", "Ground Seal", "Wall of Shadows", "Anti-Magic Aura"):
            self.assertEqual(card_coverage(db.get(name)).status, "partial", name)


if __name__ == "__main__":
    unittest.main()
