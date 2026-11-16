"""#316: "You may play / cast that card for as long as it remains exiled" (mtgsim.cx_exile_play)."""
import unittest

from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, card

SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
GIANT = card("Test Giant", "{2}{R}{R}", "Creature — Giant", "", 4, 4)
TOP = "Look at the top card of that player's library, then exile it face down. "


class Parsing(unittest.TestCase):
    def kinds(self, text):
        effects, bad = _parse_effects(text)
        return [e.kind for e in effects], bad

    def test_wordings(self):
        for rider in ("You may play that card for as long as it remains exiled.",
                      "You may cast that card for as long as it remains exiled.",
                      "You may play that card for as long as it remains exiled, and mana of any type can be spent to "
                      "cast that spell.",
                      "For as long as that card remains exiled, you may play it.",
                      "You may look at and play that card for as long as it remains exiled."):
            kinds, bad = self.kinds(TOP + rider)
            self.assertEqual((kinds, bad), (["cx_exile_watch", "cx_exile_top_of", "cx_exile_play"], []), rider)

    def test_flags(self):
        effects, _ = _parse_effects(TOP + "You may cast that card without paying its mana cost for as long as it "
                                    "remains exiled.")
        self.assertEqual(effects[-1].data, {"play": False, "free": True, "owner": False})
        effects, _ = _parse_effects("Exile target nonland permanent. For as long as that card remains exiled, its "
                                    "owner may play it.")
        self.assertTrue(effects[-1].data["owner"])

    def test_refusals(self):
        for text in (
                "Draw a card. You may play that card for as long as it remains exiled.",           # nothing exiled
                TOP + "For as long as that card remains exiled, you may play it if you control a Kavu.",  # a condition
                TOP + "You may play that card for as long as it remains exiled, and you may spend colorless mana as "
                      "though it were mana of any color to cast that spell."):                  # another mana rule
            kinds, bad = self.kinds(text)
            self.assertTrue(bad, text)
            self.assertNotIn("cx_exile_play", kinds, text)


class Engine(Base):
    def trigger(self, text, context=None):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [])
        item = StackItem(self.a, effects, [None] * len(effects), name="test trigger", kind="trigger", context=context)
        self.game.stack.append(item)
        self.game.resolve_top()
        return item

    def names(self, cards):
        return [getattr(c, "name", "") for c in cards]

    def test_cast_an_opponents_card_later_and_only_while_exiled(self):
        self.b.library = [ISLAND] * 3 + [SHOCK]
        self.trigger(TOP + "You may play that card for as long as it remains exiled.", context=self.b)
        self.assertEqual(self.names(self.b.exile), ["Test Shock"])
        self.game.turn += 3                                     # no end turn
        options = [c for c in self.game.spell_options(self.a) if c.name.startswith("Test Shock")]
        self.assertEqual(len(options), 1)
        self.assertNotIn("Test Shock", self.names(self.game.spell_options(self.b)))
        shock = self.b.exile.get(SHOCK)
        self.b.exile.remove(shock)                              # leaves exile: a new object, no permission
        self.b.graveyard.append(shock)
        self.assertFalse([c for c in self.game.spell_options(self.a) if c.name.startswith("Test Shock")])

    def test_play_a_land_from_an_opponents_exile(self):
        self.b.library = [ISLAND]
        self.trigger(TOP + "You may play that card for as long as it remains exiled.", context=self.b)
        lands = [c for c in self.game.impulse_cards(self.a) if c.is_land]
        self.assertEqual(self.names(lands), ["Island"])
        self.game.play_land(self.a, lands[0])
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Island"])
        self.assertEqual(self.b.exile, [])
        self.assertFalse(self.game.impulse_cards(self.a))

    def test_cast_only_skips_lands(self):
        self.b.library = [ISLAND]
        self.trigger(TOP + "You may cast that card for as long as it remains exiled.", context=self.b)
        self.assertFalse(self.game.impulse_cards(self.a))

    def test_mana_of_any_type(self):
        self.b.library = [GIANT]
        self.trigger(TOP + "You may play that card for as long as it remains exiled, and mana of any type can be "
                     "spent to cast that spell.", context=self.b)
        option, = [c for c in self.game.spell_options(self.a) if c.name.startswith("Test Giant")]
        self.assertEqual(option.mana_cost, {"generic": 4})

    def test_free_and_own_exile(self):
        self.a.graveyard = [GIANT]
        effects, bad = _parse_effects("Exile target creature card from your graveyard. You may cast that card "
                                      "without paying its mana cost for as long as it remains exiled.")
        self.assertEqual(bad, [])
        targets = [self.a.graveyard[0] if e.target == "graveyard_card" else None for e in effects]
        self.game.stack.append(StackItem(self.a, effects, targets, name="test", kind="trigger"))
        self.game.resolve_top()
        option, = [c for c in self.game.spell_options(self.a) if c.name.startswith("Test Giant")]
        self.assertEqual(option.mana_cost, {"generic": 0})

    def test_owner_may_play_it(self):
        bear = self.perm(BEAR, self.b)
        effects, bad = _parse_effects("Exile target nonland permanent. For as long as that card remains exiled, its "
                                      "owner may play it.")
        self.assertEqual(bad, [])
        self.game.stack.append(StackItem(self.a, effects, [None, bear, None], name="test", kind="trigger"))
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertTrue([c for c in self.game.spell_options(self.b) if c.name.startswith(BEAR.name)])
        self.assertFalse([c for c in self.game.spell_options(self.a) if c.name.startswith(BEAR.name)])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Edward Kenway", "Blightwing Bandit", "Ramirez DePietro, Pillager", "Savvy Trader", "Spelljack",
                     "Kheru Spellsnatcher"):
            with self.subTest(name):
                self.assertEqual(db.get(name).unsupported, [])

    def test_hostage_taker_casts_the_card_until_it_returns(self):
        from mtgsim.carddb import CardDB
        taker = CardDB(offline=True).get("Hostage Taker")
        self.assertEqual(taker.unsupported, [])
        victim = self.perm(GIANT, self.b)
        trig = next(t for t in taker.triggers if t.event == "etb")
        source = self.perm(taker, self.a)
        self.game.stack.append(StackItem(self.a, list(trig.effects),
                                         [victim if e.target != "none" else None for e in trig.effects],
                                         source=source, name="Hostage Taker", kind="trigger"))
        self.game.resolve_top()
        self.assertNotIn(victim, self.b.battlefield)
        option, = [c for c in self.game.spell_options(self.a) if c.name.startswith("Test Giant")]
        self.assertEqual(option.mana_cost, {"generic": 4})      # mana of any type
        self.game.leave_battlefield(source, "graveyard")          # the creature returns: no permission any more
        self.assertFalse([c for c in self.game.spell_options(self.a) if c.name.startswith("Test Giant")])

    def test_spelljack_casts_the_countered_spell_free(self):
        from mtgsim.carddb import CardDB
        jack = CardDB(offline=True).get("Spelljack")
        theirs = StackItem(self.b, list(GIANT.spell_effects), [], card=GIANT)
        self.game.stack.append(theirs)
        self.game.stack.append(StackItem(self.a, list(jack.spell_effects),
                                         [theirs if e.target == "spell" else None for e in jack.spell_effects],
                                         card=jack))
        self.game.resolve_top()
        self.assertNotIn(theirs, self.game.stack)
        self.assertEqual([c.name for c in self.b.exile], ["Test Giant"])
        option, = [c for c in self.game.spell_options(self.a) if c.name.startswith("Test Giant")]
        self.assertEqual(option.mana_cost, {"generic": 0})

    def test_ai_casts_the_stolen_card(self):
        self.b.library = [BEAR]
        effects, _ = _parse_effects(TOP + "You may play that card for as long as it remains exiled.")
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects), name="t", kind="trigger",
                                         context=self.b))
        self.game.resolve_top()
        self.a.hand = []
        forest = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
        self.perm(forest, self.a)
        self.perm(forest, self.a)
        self.assertIs(self.game.active, self.a)
        self.game.main_phase(self.a)
        self.assertEqual(self.b.exile, [])                     # cast from the opponent's exile
        bear = next(x for x in self.a.battlefield if x.card.name == BEAR.name)
        self.assertIs(bear.owner, self.b)                      # still the opponent's card, under our control


if __name__ == "__main__":
    unittest.main()
