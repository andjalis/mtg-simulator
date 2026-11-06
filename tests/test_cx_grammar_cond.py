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
        self.assertEqual(parse("that land is a Mountain"), 'lib:["prev_is",{"sub":["Mountain"]}]')
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

    def scrapper(self, colors):
        scrapper = self.db.get("Gruul Scrapper")
        self.game.stack.append(StackItem(self.a, [], [], card=scrapper, name=scrapper.name))
        self.game.stack[-1].mana_colors = colors
        self.game.resolve_top()
        while self.game.flush_triggers() or self.game.stack:
            self.game.resolve_top()
        return next(x for x in self.a.battlefield if x.card.name == "Gruul Scrapper")

    def test_gruul_scrapper_needs_red_spent(self):
        perm = self.scrapper({"R", "G"})
        self.assertEqual(perm.mana_colors, frozenset({"R", "G"}))
        self.assertTrue(perm.has("haste"))
        self.assertFalse(self.scrapper({"G"}).has("haste"))

    def test_sphinxs_insight_main_phase(self):
        self.game.active_idx = 0
        hand = len(self.a.hand)
        self.cast(self.db.get("Sphinx's Insight"))
        self.assertEqual(len(self.a.hand) - hand, 2)
        self.assertEqual(self.a.life, 22)
