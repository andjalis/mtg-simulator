"""Condition riders: cx_condlib phrases for casting facts, the source's type, the previous object and turn history."""
import unittest

from mtgsim.cx_condlib import parse
from mtgsim.engine import StackItem

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class Parsing(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(parse("you cast ~ during your main phase"), 'lib:["main_cast"]')
        self.assertEqual(parse("this spell was cast from a graveyard"), 'lib:["cast_zone","graveyard"]')
        self.assertEqual(parse("{G} was spent to cast it"), 'lib:["spent_color","G"]')
        self.assertEqual(parse("~ is an enchantment"), 'lib:["src_is",{"types":["enchantment"]}]')
        self.assertEqual(parse("that land is a Mountain"), 'lib:["ref_is","land",{"sub":["Mountain"]}]')
        self.assertEqual(parse("it's a Zombie card"), 'lib:["prev_is",{"sub":["Zombie"]}]')
        self.assertTrue(parse("you had a land enter the battlefield under your control this turn").startswith(
            'lib:["hist"'))

    def test_rejects(self):
        for phrase in ("~ is a creature card", "{G}{G} was spent to cast it", "you cast it from anywhere other than "
                       "your hand", "you cast ~ during an opponent's turn"):
            self.assertEqual(parse(phrase), "", phrase)


class Resolving(Base):
    def resolve(self, text, setup=None):
        c = self.spell(text, "Sorcery")
        effects = list(c.spell_effects)
        item = StackItem(self.a, effects, [None] * len(effects), card=c, name=c.name)
        if setup:
            setup(item)
        self.game.stack.append(item)
        life = self.a.life
        self.game.resolve_top()
        return self.a.life - life

    def test_main_phase_cast(self):
        text = "You gain 1 life. If you cast this spell during your main phase, you gain 2 life."
        self.game.active_idx = 0
        self.assertEqual(self.resolve(text), 3)
        self.game.step = "combat"
        self.assertEqual(self.resolve(text), 1)
        self.game.step, self.game.active_idx = "main1", 1      # the opponent's main phase is not yours
        self.assertEqual(self.resolve(text), 1)

    def test_cast_zone_and_colour_spent(self):
        text = "If this spell was cast from a graveyard, you gain 2 life."
        self.assertEqual(self.resolve(text, lambda i: setattr(i, "cast_zone", "graveyard")), 2)
        self.assertEqual(self.resolve(text, lambda i: setattr(i, "cast_zone", "hand")), 0)
        text = "If {G} was spent to cast this spell, you gain 2 life."
        self.assertEqual(self.resolve(text, lambda i: setattr(i, "mana_colors", {"G", "R"})), 2)
        self.assertEqual(self.resolve(text, lambda i: setattr(i, "mana_colors", {"R"})), 0)

    def test_land_entered_this_turn(self):
        text = "If you had a land enter the battlefield under your control this turn, you gain 2 life."
        self.spell(text, "Sorcery")                      # parsing registers the history head before the event
        self.assertEqual(self.resolve(text), 0)
        self.game.enter_battlefield(self.a, FOREST)
        self.assertEqual(self.resolve(text), 2)
        self.game.turn += 1
        self.assertEqual(self.resolve(text), 0)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)

    def test_cards_come_out_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Arrester's Admonition", "Return to Dust", "Ruthless Negotiation", "Gruul Scrapper",
                     "Cemetery Recruitment", "Sphinx's Insight"):
            row = card_coverage(self.db.get(name))
            self.assertEqual(row.status, "full", (name, row.ignored))

    def enter(self, name, colors=(), kicks=0):
        """Cast a creature (its payment recorded as given), resolve it and its ETB trigger; the new permanent."""
        c = self.db.get(name)
        item = StackItem(self.a, [], [], card=c, name=c.name)
        item.mana_colors, item.kicks = set(colors), kicks
        self.game.stack.append(item)
        self.game.resolve_top()
        perm = self.a.battlefield[-1]
        while self.game.flush_triggers() or self.game.stack:
            self.game.resolve_top()
        return perm

    def test_gruul_scrapper_needs_red_spent(self):
        perm = self.enter("Gruul Scrapper", "RG")
        self.assertEqual(perm.mana_colors, frozenset({"R", "G"}))
        self.assertTrue(perm.has("haste"))
        self.assertFalse(self.enter("Gruul Scrapper", "G").has("haste"))

    def test_it_in_a_self_etb_trigger_is_the_permanent(self):
        """"When ~ enters, if it was kicked, it gains haste": "it" is the creature that entered (the etb trigger's
        context), not nothing."""
        self.assertTrue(self.enter("Scorch Rider", kicks=1).has("haste"))
        self.assertFalse(self.enter("Scorch Rider").has("haste"))
        iconoclast = self.enter("Yavimaya Iconoclast", kicks=1)
        self.assertTrue(iconoclast.has("haste"))
        self.assertEqual(iconoclast.power, 4)

    def test_sphinxs_insight_main_phase(self):
        self.game.active_idx = 0
        hand = len(self.a.hand)
        self.cast(self.db.get("Sphinx's Insight"))
        self.assertEqual(len(self.a.hand) - hand, 2)
        self.assertEqual(self.a.life, 22)


class Instead(Base):
    def parse(self, text):
        from mtgsim.cards import parse as P
        return P._parse_effects(text)

    def test_replaces_the_previous_effect(self):
        effects, bad = self.parse("Draw two cards. If you have the city's blessing, draw three cards instead.")
        self.assertEqual(bad, [])
        self.assertEqual([(e.kind, e.amount) for e in effects], [("draw", 2), ("draw", 3)])
        self.assertEqual(effects[0].cond, 'lib:["not","city_blessing"]')
        self.assertEqual(effects[1].cond, "city_blessing")

    def test_rejects_what_it_cannot_tie(self):
        for text in ("If a creature died this turn, you gain 8 life instead.",          # nothing before it
                     "Draw a card. If a creature died this turn, you gain 8 life instead."):  # a different effect
            effects, bad = self.parse(text)
            self.assertTrue(bad, text)
            self.assertFalse(any(e.data.get("cx_instead") for e in effects))

    def test_resolves_one_or_the_other(self):
        text = "You gain 2 life. If a creature died this turn, you gain 8 life instead."
        spell = self.spell(text, "Sorcery")
        self.cast(spell)
        self.assertEqual(self.a.life, 22)
        self.game.destroy(self.perm(BEAR, self.b))
        self.cast(spell)
        self.assertEqual(self.a.life, 30)

    def test_elided_damage_hits_the_same_target(self):
        spell = self.spell("~ deals 2 damage to any target. If a creature died this turn, it deals 5 damage instead.")
        self.assertEqual([e.target for e in spell.spell_effects], ["any", "prev"])
        victim = self.perm(card("Big", "{4}", "Creature — Giant", "", 9, 9), self.b)
        self.game.destroy(self.perm(BEAR, self.b))
        self.cast(spell, targets=[victim, None])
        self.assertEqual(victim.damage, 5)
        self.cast(spell, targets=[self.b, None])
        self.assertEqual(self.b.life, 15)

    def test_suffix_form(self):
        effects, bad = self.parse("Draw a card. Draw three cards instead if you control a Jace planeswalker.")
        self.assertEqual(bad, [])
        self.assertEqual([e.amount for e in effects], [1, 3])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class ThatLand(Base):
    def test_that_land_is_the_land_that_entered_not_the_damage_target(self):
        from mtgsim.carddb import CardDB
        from tests.test_templates import MOUNTAIN
        self.perm(CardDB(offline=True).get("Akoum Hellkite"), self.a)
        self.perm(BEAR, self.b)

        def dealt(land):
            before = self.b.life - sum(x.damage for x in self.b.battlefield)
            self.game.enter_battlefield(self.a, land)
            while self.game.flush_triggers() or self.game.stack:
                self.game.resolve_top()
            return before - (self.b.life - sum(x.damage for x in self.b.battlefield if x in self.b.battlefield))
        self.assertEqual(dealt(MOUNTAIN), 2)
        self.assertEqual(dealt(FOREST), 1)


class Unless(Base):
    def setUp(self):
        super().setUp()
        from tests.test_templates import ISLAND
        self.island = ISLAND

    def parse(self, text):
        from mtgsim.cards import parse as P
        return P._parse_effects(text)

    def test_payers_and_costs(self):
        cases = {"Destroy target creature unless its controller pays {3}.": "controller",
                 "Destroy that creature unless its controller pays {2}.": "prev_controller",
                 "That player loses 2 life unless they pay {2}.": "context",
                 "Each opponent loses 2 life unless they pay {2}.": "opponent",
                 "Target player mills three cards unless they pay 3 life.": "target",
                 "That player loses 2 life unless they sacrifice a creature.": "context"}
        for text, payer in cases.items():
            effects, bad = self.parse(text)
            self.assertEqual(bad, [], text)
            self.assertEqual((effects[0].kind, effects[0].data["payer"]), ("cx_unless", payer), text)
            self.assertTrue(all(e.cond == 'lib:["unless_unpaid"]' for e in effects[1:]), text)

    def test_rejects(self):
        for text in ("You gain 3 life unless any player pays {1}.",            # any player: not modelled
                     "Draw a card unless they pay {2}.",                       # "they": no player named
                     "Target player loses 2 life unless its controller pays {1}.",
                     "Destroy target creature unless its controller pays {X}."):
            effects, bad = self.parse(text)
            self.assertTrue(bad, text)

    def test_condition_form(self):
        effects, bad = self.parse("Draw two cards unless there are seven or more cards in your graveyard.")
        self.assertEqual(bad, [])
        self.assertTrue(effects[0].cond.startswith('lib:["not"'))

    def test_opponent_pays_when_able_else_the_effect_happens(self):
        spell = self.spell("Destroy target creature unless its controller pays {1}.", "Sorcery")
        bear = self.perm(BEAR, self.b)
        land = self.perm(self.island, self.b)
        self.cast(spell, targets=[None, bear])
        self.assertIn(bear, self.b.battlefield)               # paid with the Island
        self.assertTrue(land.tapped)
        self.cast(spell, targets=[None, bear])
        self.assertNotIn(bear, self.b.battlefield)            # no untapped mana left: destroyed

    def test_life_and_sacrifice_costs(self):
        spell = self.spell("Target player mills two cards unless they pay 3 life.", "Sorcery")
        self.cast(spell, targets=[None, self.b])
        self.assertEqual((self.b.life, len(self.b.graveyard)), (17, 0))
        self.b.life = 5                                       # 5 - 3 would leave 2: they don't pay
        self.cast(spell, targets=[None, self.b])
        self.assertEqual((self.b.life, len(self.b.graveyard)), (5, 2))
        spell = self.spell("Each opponent loses 2 life unless they sacrifice a creature.", "Sorcery")
        bear = self.perm(BEAR, self.b)
        self.cast(spell)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.life, 5)
        self.cast(spell)
        self.assertEqual(self.b.life, 3)

    def test_ai_casts_it_at_the_opponent(self):
        theirs, mine = self.perm(BEAR, self.b), self.perm(BEAR, self.a)
        spell = card("Test Spell", "{U}", "Sorcery", "Destroy target creature unless its controller pays {2}.")
        self.assertEqual(spell.unsupported, [])
        self.perm(self.island, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertNotIn(theirs, self.b.battlefield)          # aimed at the opponent's creature, who can't pay
        self.assertIn(mine, self.a.battlefield)
