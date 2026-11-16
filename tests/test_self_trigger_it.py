""""It" in the permanent's own trigger and "you may have it deal / fight" (#319, mtgsim/self_trigger_it.py), the
lone-fight fighter (removal.resolve) and "the number of ... you control" amounts under "you may have"."""
import unittest

from mtgsim.engine import StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, FLIER, GOBLIN, Base, card

ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)


class Parsing(unittest.TestCase):
    def full(self, text, pt=(2, 2)):
        return card("Test Thing", "{2}", "Creature — Thing", text, *pt)

    def test_shapes(self):
        for text in ("Whenever this creature attacks, you may have it deal 1 damage to each creature without flying "
                     "defending player controls.",
                     "Whenever this creature deals combat damage to a player, you may have it deal 2 damage to target "
                     "creature that player controls.",
                     "When this creature enters, you may have it fight another target creature.",
                     "When this creature enters, you may have it deal damage to target creature equal to the number "
                     "of artifacts you control.",
                     "When this creature dies, you may have it deal damage to any target equal to the number of land "
                     "cards in your graveyard."):
            self.assertEqual(self.full(text).unsupported, [], text)

    def test_other_its_stay_unsupported(self):
        for text in ("Whenever another creature enters, you may have it fight another target creature.",
                     "Whenever another creature enters, you may have it deal damage to target creature equal to the "
                     "number of artifacts you control.",
                     "Whenever this creature attacks, you may have it deal 1 damage to target creature defending "
                     "player controls and 1 damage to you."):
            self.assertNotEqual(self.full(text).unsupported, [], text)

    def test_plain_may_damage_stays_optional(self):
        """"you may have it deal 2 damage to target creature" keeps its optional, hostile-only reading."""
        c = self.full("When this creature enters, you may have it deal 2 damage to target creature.")
        self.assertEqual(c.unsupported, [])
        self.assertTrue(c.triggers[0].effects[0].data.get("may_hostile"))

    def test_your_count_is_not_a_your_target(self):
        """"... equal to the number of artifacts you control" doesn't make the target "yours": still hostile-only."""
        c = self.full("When this creature enters, you may have it deal damage to target creature equal to the number "
                      "of artifacts you control.")
        eff = c.triggers[0].effects[0]
        self.assertEqual((eff.kind, eff.target), ("damage", "creature"))
        self.assertTrue(eff.data.get("may_hostile"))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Atzocan Archer", "Brash Taunter", "Munitions Expert", "Murasa Pyromancer", "Reclusive Artificer",
                     "Ronin Cliffrider", "Ruination Rioter", "Scalding Salamander", "Skirk Commando", "Snapping Thragg",
                     "Spark Mage", "Swathcutter Giant", "Tajuru Archer", "Thorn Mammoth", "Somberwald Stag",
                     "Igneous Elemental", "Geistcatcher's Rig", "Goblin Arsonist"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


class Resolving(Base):
    def trigger(self, c, src, targets, effects=None):
        effs = list(effects if effects is not None else c.triggers[0].effects)
        self.game.stack.append(StackItem(self.a, effs, targets + [None] * (len(effs) - len(targets)), source=src,
                                         kind="trigger", name=c.name))
        self.game.resolve_top()

    def test_lone_fight_is_fought_by_the_source(self):
        """"{T}: ~ fights another target creature": the source fights (it used to make the target fight itself)."""
        c = card("Test Taunter", "{R}", "Creature — Goblin", "{T}: ~ fights another target creature.", 4, 4)
        self.assertEqual(c.unsupported, [])
        src, bear = self.perm(c, self.a), self.perm(BEAR, self.b)
        eff = c.activated[0].effects[0]
        with self.game.targeting(src):
            self.assertNotIn(src, self.game.legal_targets(self.a, eff))
        self.game.stack.append(StackItem(self.a, [eff], [bear], source=src, kind="ability", name=c.name))
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(src.damage, 2)

    def test_attack_trigger_hits_only_their_ground_creatures(self):
        c = card("Test Salamander", "{R}", "Creature — Salamander", "Whenever this creature attacks, you may have it "
                 "deal 1 damage to each creature without flying defending player controls.", 1, 1)
        src, elf, flier, mine = self.perm(c, self.a), self.perm(ELF, self.b), self.perm(FLIER, self.b), \
            self.perm(GOBLIN, self.a)
        self.trigger(c, src, [])
        self.assertNotIn(elf, self.b.battlefield)
        self.assertIn(flier, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)

    def test_count_of_your_artifacts(self):
        c = card("Test Artificer", "{R}", "Creature — Human", "When this creature enters, you may have it deal damage "
                 "to target creature equal to the number of artifacts you control.", 2, 2)
        trinket = card("Test Trinket", "{1}", "Artifact", "")
        src, bear = self.perm(c, self.a), self.perm(BEAR, self.b)
        self.perm(trinket, self.a)
        self.perm(trinket, self.b)          # the opponent's artifact doesn't count
        self.trigger(c, src, [bear])
        self.assertEqual(bear.damage, 1)
        self.perm(trinket, self.a)
        self.trigger(c, src, [bear])
        self.assertNotIn(bear, self.b.battlefield)

    def test_combat_damage_trigger_targets_their_creature(self):
        c = card("Test Commando", "{R}", "Creature — Goblin", "Whenever this creature deals combat damage to a player, "
                 "you may have it deal 2 damage to target creature that player controls.", 1, 1)
        eff = c.triggers[0].effects[0]
        self.assertEqual((eff.kind, eff.target, eff.filter), ("damage", "creature", "opp"))
        src, bear = self.perm(c, self.a), self.perm(BEAR, self.b)
        self.trigger(c, src, [bear])
        self.assertNotIn(bear, self.b.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCardResolving(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB()

    def test_voracious_hydra_fight_mode(self):
        c = self.db.get("Voracious Hydra")
        src, bear = self.perm(c, self.a), self.perm(BEAR, self.b)
        src.counters["+1/+1"] = 3
        mode = next(t for t in c.triggers if t.modes).modes[1]
        self.game.stack.append(StackItem(self.a, list(mode), [bear], source=src, kind="trigger", name=c.name))
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(src.damage, 2)

    def test_ai_aims_atzocan_archer_at_their_creature(self):
        archer = self.db.get("Atzocan Archer")
        mine, theirs = self.perm(ELF, self.a), self.perm(ELF, self.b)
        for _ in range(3):
            self.perm(self.db.get("Forest"), self.a)
        self.a.hand = [archer]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(archer, self.a.hand, "the AI didn't cast it")
        while self.game.stack:
            self.game.resolve_top()
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()
