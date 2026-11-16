"""#643 slice 5: protection from coloured spells, from non-<type> [creatures], from instant / sorcery spells, and comma
keyword lists with a numbered keyword ("Flying, ..., annihilator 6")."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, StackItem, can_block, protected_from
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, SHOCK, card

EMRAKUL = card("Test Emrakul", "{15}", "Legendary Creature — Eldrazi",
               "Flying, protection from spells that are one or more colors, annihilator 6", 15, 15)
HARBINGER = card("Test Harbinger", "{1}{G}", "Creature — Spirit", "Protection from non-Spirit creatures", 2, 1)
CHATTERFANG = card("Test Chatterfang", "{5}{G}", "Legendary Creature — Eldrazi Squirrel",
                   "Flying, trample, protection from non-Squirrels", 6, 6)
SPIRIT = card("Test Spirit", "{1}{W}", "Creature — Spirit", "", 2, 2)
SQUIRREL = card("Test Squirrel", "{G}", "Creature — Squirrel", "", 1, 1)
ROD = card("Test Rod", "{3}", "Artifact", "{T}: ~ deals 1 damage to any target.")


class Parsing(unittest.TestCase):
    def test_keyword_lists(self):
        self.assertEqual(EMRAKUL.unsupported, [])
        self.assertIn("protection from spells that are one or more colors", EMRAKUL.keywords)
        self.assertIn("flying", EMRAKUL.keywords)
        self.assertTrue(any(t.event == "attacks" for t in EMRAKUL.triggers))     # annihilator 6
        self.assertEqual(HARBINGER.advanced_rules["protection_non"], ("Spirit", True))
        self.assertEqual(CHATTERFANG.advanced_rules["protection_non"], ("Squirrel", False))
        self.assertEqual(CHATTERFANG.unsupported, [])

    def test_instant_and_sorcery_spells(self):
        effects, bad = _parse_effects("Target permanent you control gains protection from instant spells and from "
                                      "sorcery spells until end of turn.")
        self.assertEqual(bad, [])
        self.assertEqual([(e.kind, e.data["keyword"]) for e in effects],
                         [("grant", "protection from instants"), ("grant", "protection from sorceries")])
        self.assertEqual(effects[1].target, "prev")             # the same permanent

    def test_refusals(self):
        for text in ("Flying, annihilator 6, blorbing", "Flying, foozle 3", "Protection from non-Blorbs"):
            c = card("X", "{1}", "Creature — Eldrazi", text, 1, 1)
            self.assertTrue(c.unsupported, text)


class Rules(Base):
    def test_coloured_spells_only(self):
        """Emrakul: coloured spells can't target or damage it; a colourless spell, a red creature's ability or a red
        creature in combat can."""
        emrakul = self.perm(EMRAKUL, self.a)
        self.assertTrue(protected_from(emrakul, StackItem(self.b, list(SHOCK.spell_effects), [emrakul], card=SHOCK)))
        self.assertTrue(protected_from(emrakul, SHOCK))
        pinger = Permanent(card("Test Pinger", "{R}", "Creature — Goblin", "{T}: ~ deals 1 damage to any target.", 1, 1),
                           self.b)
        self.assertFalse(protected_from(emrakul, pinger))
        self.assertFalse(protected_from(emrakul, Permanent(ROD, self.b)))

    def test_non_spirit_creatures(self):
        harb = self.perm(HARBINGER, self.a)
        self.assertFalse(can_block(Permanent(BEAR, self.b), harb))
        self.assertTrue(can_block(Permanent(SPIRIT, self.b), harb))
        self.assertFalse(protected_from(harb, SHOCK))                    # not a creature

    def test_non_squirrels(self):
        chat = self.perm(CHATTERFANG, self.a)
        self.assertTrue(protected_from(chat, SHOCK))                     # anything that isn't a Squirrel
        self.assertFalse(protected_from(chat, Permanent(SQUIRREL, self.b)))


class HeuristicUse(Base):
    def test_ai_does_not_aim_shock_at_emrakul(self):
        self.perm(EMRAKUL, self.a)
        bear = self.perm(BEAR, self.a)
        eff = SHOCK.spell_effects[0]
        with self.game.targeting(SHOCK):
            self.assertIs(self.b.ai.choose_target(self.game, self.b, eff, SHOCK), bear)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Emrakul, the Aeons Torn", "Emrakul and Chatterfang", "Harbinger of Spring", "Devoted Caretaker"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()
