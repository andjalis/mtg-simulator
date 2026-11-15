""""Prevent the next N damage that would be dealt this turn to any number of targets, divided as you choose" (#333,
mtgsim/divided_prevent.py): the division is chosen as it goes on the stack, against the damage that is coming."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, Base, card

LINE = "Prevent the next 4 damage that would be dealt this turn to any number of targets, divided as you choose."
EMBOLDEN = card("Test Embolden", "{W}", "Instant", LINE)
BOLT = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")
LION = card("Test Lion", "{2}{W}", "Creature — Cat", "", 3, 3)


class Parsing(unittest.TestCase):
    def test_shapes(self):
        effs, bad = _parse_effects(LINE)
        self.assertEqual((bad, effs[0].kind, effs[0].amount), ([], "divided_prevent", 4))
        effs, bad = _parse_effects("Prevent the next X damage that would be dealt this turn to any number of targets, "
                                   "divided as you choose, where X is the number of verse counters on ~.")
        self.assertEqual((bad, effs[0].data["xq"]), ([], ("counters", "verse")))

    def test_refusals(self):
        for text in ("Prevent the next 4 damage that would be dealt this turn to any number of target creatures, "
                     "divided as you choose.",
                     "Prevent the next 4 damage that would be dealt this turn to any number of targets, divided as you "
                     "choose, where X is the number of Foos.",
                     "Prevent the next 4 damage that would be dealt this turn to any number of targets."):
            _, bad = _parse_effects(text)
            self.assertTrue(bad, text)


class Resolving(Base):
    def push(self, c, who):
        self.game.stack.append(StackItem(who, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))

    def test_shield_goes_to_the_threatened_creature(self):
        bear = self.perm(BEAR, self.a)
        self.game.stack.append(StackItem(self.b, list(BOLT.spell_effects), [bear], card=BOLT, name=BOLT.name))
        self.push(EMBOLDEN, self.a)
        self.assertEqual(self.game.stack[-1].divided_prevent, [[[bear, 2], [self.a, 2]]])
        self.game.resolve_top()
        self.assertEqual((bear.prevent_next, self.a.prevent_next), (2, 2))
        self.game.resolve_top()
        self.assertIn(bear, self.a.battlefield)
        self.assertEqual(bear.damage, 1)

    def test_nothing_coming_shields_you(self):
        self.push(EMBOLDEN, self.a)
        self.game.resolve_top()
        self.assertEqual(self.a.prevent_next, 4)
        self.game.deal_damage(self.a, 5, by=self.b, cause="test")
        self.assertEqual(self.a.life, 19)

    def test_unblocked_attackers_and_blocked_creature(self):
        lion, attacker, blocked = self.perm(LION, self.a), self.perm(BEAR, self.b), self.perm(BEAR, self.b)
        self.game.attackers = [attacker, blocked]
        self.game.blocks = {blocked: [lion]}
        self.push(card("Test Remedy", "{1}{W}", "Instant", LINE.replace("4", "5")), self.a)
        plan = self.game.stack[-1].divided_prevent[0]
        self.assertEqual(plan, [[self.a, 5]])      # the 3/3 survives the 2/2 anyway: everything on the face

    def test_a_shield_on_an_illegal_target_is_lost(self):
        bear = self.perm(BEAR, self.a)
        self.game.stack.append(StackItem(self.b, list(BOLT.spell_effects), [bear], card=BOLT, name=BOLT.name))
        self.push(EMBOLDEN, self.a)
        self.a.battlefield.remove(bear)
        self.game.resolve_top()
        self.assertEqual(self.a.prevent_next, 2)


class DefaultAI(Base):
    def test_ai_saves_its_creature_with_embolden(self):
        lion = self.perm(LION, self.a)
        self.perm(card("Test Plains", "", "Land — Plains", "({T}: Add {W}.)"), self.a)
        self.a.hand = [EMBOLDEN]
        bolt = card("Test Big Bolt", "{R}", "Instant", "~ deals 4 damage to any target.")
        self.game.stack.append(StackItem(self.b, list(bolt.spell_effects), [lion], card=bolt, name=bolt.name))
        play = self.a.ai.respond(self.game, self.a)
        self.assertIsNotNone(play)
        self.assertEqual(play[0].name, EMBOLDEN.name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Embolden", "Remedy", "Serra's Hymn"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))

    def test_serras_hymn_counts_its_verses(self):
        from mtgsim.carddb import CardDB
        hymn = self.perm(CardDB().get("Serra's Hymn"), self.a)
        hymn.counters["verse"] = 3
        self.assertTrue(self.game.activate(self.a, hymn, "ability:0"))
        while self.game.stack:
            self.game.resolve_top()
        self.assertNotIn(hymn, self.a.battlefield)
        self.assertEqual(self.a.prevent_next, 3)


if __name__ == "__main__":
    unittest.main()
