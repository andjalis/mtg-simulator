"""#627: "Choose a card name, then reveal / mill ... If that card has the chosen name, ..." (mtgsim.cx_card_name),
with the name taken only from information the player has."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cx_card_name import name_for
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Cursed Scroll", "Magus of the Scroll", "Mise", "Foreshadow", "Diviner's Lockbox")
OGRE = card("Ogre", "{3}{R}", "Creature — Ogre", "", 4, 4)
BOLT = card("Bolt", "{R}", "Instant", "Bolt deals 3 damage to any target.")
ELF = card("Elf", "{G}", "Creature — Elf", "", 1, 1)
SCROLL = card("Test Scroll", "{1}", "Artifact", "{3}, {T}: Choose a card name, then reveal a card at random from your "
              "hand. If that card has the chosen name, ~ deals 2 damage to any target.")
MISE = card("Test Mise", "{U}", "Instant", "Choose a nonland card name, then reveal the top card of your library. If "
            "that card has the chosen name, you draw three cards.")
FORESHADOW = card("Test Foreshadow", "{1}{U}", "Instant", "Choose a card name, then target opponent mills a card. If a "
                  "card with the chosen name was milled this way, you draw a card.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c in (SCROLL, MISE, FORESHADOW):
            self.assertEqual(c.unsupported, [], c.name)
        effs = SCROLL.activated[0].effects
        self.assertEqual([(e.kind, e.target, e.cond) for e in effs], [("name_guess", "none", ""), ("damage", "any", "paid")])
        self.assertEqual(FORESHADOW.spell_effects[0].data["where"], "mill")

    def test_refusals(self):
        for text in (
            # the reward is about the milled card itself ("its" would name the targeted player)
            "Choose a card name, then target player mills a card. If a card with the chosen name was milled this way, "
            "you gain life equal to its mana value.",
            # a different check
            "Choose a card name, then reveal the top card of your library. If that card is a land, draw a card.",
        ):
            self.assertTrue(card("Test Odd", "{U}", "Sorcery", text).unsupported, text)


class Names(unittest.TestCase):
    def test_hand_names_the_most_copies(self):
        g, a, b = game()
        a.hand = [BOLT, OGRE, BOLT]
        self.assertEqual(name_for(g, a, "hand", False), "Bolt")

    def test_library_guess_is_decklist_minus_seen_never_the_top_card(self):
        g, a, b = game()
        a.deck = [OGRE] * 3 + [BOLT] * 2 + [ISLAND] * 10
        a.hand = [OGRE, OGRE]                       # seen: one Ogre left, two Bolts left
        a.library = [OGRE, BOLT, ISLAND]            # the real top card is an Island, then...
        self.assertEqual(name_for(g, a, "top", True), "Bolt")
        a.library = [BOLT, ISLAND, OGRE]            # ... reordering the library changes nothing
        self.assertEqual(name_for(g, a, "top", True), "Bolt")

    def test_opponent_guess_ignores_their_hidden_hand_and_library(self):
        picks = []
        for hidden in ([], [ELF] * 15):
            g, a, b = game()
            g.enter_battlefield(b, OGRE)
            b.hand = list(hidden)
            b.library = list(hidden) + [ISLAND] * 3
            b.deck = list(hidden) + [OGRE] * 4
            picks.append(name_for(g, a, "mill", False, b))
        self.assertEqual(picks, ["Ogre", "Ogre"])

    def test_nothing_known_names_nothing(self):
        g, a, b = game()
        b.hand = [ELF] * 7
        self.assertEqual(name_for(g, a, "mill", False, b), "")


class Resolve(unittest.TestCase):
    def test_scroll_hits_with_one_card_in_hand_and_ai_aims_at_the_opponent(self):
        g, a, b = game()
        scroll = g.enter_battlefield(a, SCROLL)
        a.hand = [OGRE]
        effects = list(SCROLL.activated[0].effects)
        targets = g.auto_targets(a, effects, scroll)
        self.assertIs(targets[1], b)
        g.stack.append(StackItem(a, effects, targets, source=scroll, name="scroll"))
        g.resolve_top()
        self.assertEqual(b.life, 18)

    def test_heuristic_ai_activates_the_scroll_in_its_main_phase(self):
        from tests.test_templates import MOUNTAIN
        g, a, b = game()
        g.step = "main2"                              # general abilities are used in the second main phase
        for _ in range(3):
            g.enter_battlefield(a, MOUNTAIN)
        scroll = g.enter_battlefield(a, SCROLL)
        a.hand = [card("Ogre", "{9}", "Creature — Ogre", "", 4, 4)]       # one card: a sure hit
        g.main_phase(a)
        g.settle()
        self.assertTrue(scroll.tapped)
        self.assertEqual(b.life, 18)

    def test_mise_draws_three_only_on_a_hit(self):
        g, a, b = game()
        a.deck = [OGRE] * 4 + [ISLAND] * 6
        a.library = [ISLAND] * 5 + [OGRE]
        effects = list(MISE.spell_effects)
        g.stack.append(StackItem(a, effects, [None] * len(effects), card=MISE, name=MISE.name))
        g.resolve_top()
        self.assertEqual(len(a.hand), 3)
        g2, a2, b2 = game()
        a2.deck = [OGRE] * 4 + [ISLAND] * 6
        a2.library = [OGRE] + [ISLAND] * 5           # an Island on top: a miss
        g2.stack.append(StackItem(a2, list(effects), [None] * len(effects), card=MISE, name=MISE.name))
        g2.resolve_top()
        self.assertEqual(len(a2.hand), 0)

    def test_foreshadow_mills_and_draws_on_a_public_guess(self):
        g, a, b = game()
        g.enter_battlefield(b, OGRE)
        b.library = [ISLAND] * 3 + [OGRE]
        effects = list(FORESHADOW.spell_effects)
        g.stack.append(StackItem(a, effects, [b, None], card=FORESHADOW, name=FORESHADOW.name))
        g.resolve_top()
        self.assertEqual([c.name for c in b.graveyard], ["Ogre"])
        self.assertEqual(len(a.hand), 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
