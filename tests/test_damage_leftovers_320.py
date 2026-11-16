"""#320 / #319 leftovers: "he/she deals ... and ..." in a self trigger, ability / flavor words with punctuation before
a trigger ("Vibro-Shock Gauntlets —", "Bring it Down! —"; CR 207.2c), "that much damage to target creature an opponent
controls" (Mordant Dragon), "damage equal to <Q> to <recipient>" word order (Goblin Razerunners) and a third recipient
("1 damage to you and each creature you control", Hail Storm)."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, GOBLIN, Base, card


class Parsing(unittest.TestCase):
    def test_hail_storm_shape(self):
        effs = parse_sentence("~ deals 2 damage to each attacking creature and 1 damage to you and each creature you "
                              "control.")
        self.assertEqual([e.kind for e in effs], ["cx_group", "cx_damage", "cx_group"])
        self.assertIsNone(parse_sentence("~ deals 2 damage to each attacking creature and 1 damage to you and target "
                                         "creature."))

    def test_reordered_amount(self):
        effs, bad = _parse_effects("~ deals damage equal to the number of Goblins you control to target player or "
                                   "planeswalker.")
        self.assertFalse(bad)
        self.assertEqual((effs[0].target, effs[0].data.get("or_pw"), effs[0].data["xq"]), ("player", True,
                                                                                         ("count", "Goblin")))

    def test_ability_words(self):
        for text in ("Vibro-Shock Gauntlets — When ~ enters, ~ deals 2 damage to any target.",
                     "Bring it Down! — Whenever ~ attacks, creatures you control gain deathtouch until end of turn."):
            self.assertEqual(card("Test Thing", "{2}", "Creature — Human", text, 2, 2).unsupported, [], text)

    def test_saga_chapters_keep_their_marker(self):
        c = card("Test Saga", "{2}", "Enchantment — Saga", "(As this Saga enters and after your draw step, add a lore "
                 "counter.)\nI — You gain 1 life.\nII, III — Whenever you cast a spell this turn, put a +1/+1 counter "
                 "on target creature you control.")
        self.assertIn("II, III — Whenever you cast a spell this turn, put a +1/+1 counter on target creature you "
                      "control.", c.unsupported)     # not stripped into a plain, permanent trigger

    def test_he_deals_in_a_self_trigger(self):
        c = card("Test Shocker", "{2}{R}", "Creature — Human", "When ~ enters, he deals 2 damage to target creature and "
                 "2 damage to that creature's controller.", 2, 2)
        self.assertEqual(c.unsupported, [])
        self.assertEqual([e.kind for e in c.triggers[0].effects], ["damage", "cx_damage"])


class Resolving(Base):
    def test_hail_storm(self):
        attacker, mine = self.perm(GOBLIN, self.b), self.perm(GOBLIN, self.a)
        bear = self.perm(BEAR, self.a)
        self.game.attackers = [attacker]
        attacker.attacking = True
        self.cast(self.spell("~ deals 2 damage to each attacking creature and 1 damage to you and each creature you "
                             "control."))
        self.assertNotIn(attacker, self.b.battlefield)
        self.assertNotIn(mine, self.a.battlefield)
        self.assertEqual((bear.damage, self.a.life, self.b.life), (1, 19, 20))

    def test_counter_count_damage(self):
        c = card("Test Razerunner", "{2}{R}", "Creature — Goblin", "At the beginning of your end step, you may have ~ "
                 "deal damage equal to the number of +1/+1 counters on it to target player or planeswalker.", 1, 1)
        self.assertEqual(c.unsupported, [])
        src = self.perm(c, self.a)
        src.counters["+1/+1"] = 3
        effs = c.triggers[0].effects
        self.game.stack.append(StackItem(self.a, list(effs), [self.b], source=src, kind="trigger", name=c.name))
        self.game.resolve_top()
        self.assertEqual(self.b.life, 17)

    def test_that_much_to_their_creature(self):
        c = card("Test Dragon", "{5}{R}", "Creature — Dragon", "Flying\nWhenever ~ deals combat damage to a player, you "
                 "may have it deal that much damage to target creature that player controls.", 4, 4)
        self.assertEqual(c.unsupported, [])
        eff = next(t for t in c.triggers if t.event == "combat_damage_player").effects[0]
        self.assertEqual((eff.target, eff.filter), ("creature", "opp"))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Shocker, Unshakable", "Mordant Dragon", "Goblin Razerunners", "Hail Storm", "Company Commander",
                     "Dalek Drone", "Knight Paladin", "Space Marine Devastator"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()
