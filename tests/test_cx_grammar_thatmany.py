"""#337: "<player> <puts cards away>, then draw(s) that many cards [plus/minus N]" (mtgsim.cx_grammar_thatmany)."""
import unittest

from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card



def inner(s):
    effs = parse_sentence(s)
    if effs is None:
        return None
    assert len(effs) == 1 and effs[0].kind == "cx_players"
    return effs[0].data["who"], [(e.kind, e.data.get("mode"), e.data.get("delta")) for e in effs[0].data["effects"]]


class Parsing(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(inner("Discard all the cards in your hand, then draw that many cards plus one."),
                         ("you", [("cx_away", "discard_hand", None), ("cx_draw_that_many", "discard_hand", 1)]))
        self.assertEqual(inner("Each player discards all the cards in their hand, then draws that many cards minus one.")[1][1],
                         ("cx_draw_that_many", "discard_hand", -1))
        for s, who, mode in [
                ("Discard any number of cards, then draw that many cards.", "you", "discard_any"),
                ("Target player discards their hand, then draws that many cards.", "target", "discard_hand"),
                ("Each player shuffles the cards from their hand into their library, then draws that many cards.",
                 "each", "shuffle_hand"),
                ("Shuffle any number of cards from your hand into your library, then draw that many cards.",
                 "you", "shuffle_any"),
                ("That player puts the cards in their hand on the bottom of their library in any order, then draws "
                 "that many cards.", "that_player", "bottom_hand"),
                ("Put any number of cards from your hand on the bottom of your library, then draw that many cards "
                 "plus one.", "you", "bottom_any"),
                ("Defending player discards all the cards in their hand, then draws that many cards.", "defending",
                 "discard_hand")]:
            got = inner(s)
            self.assertIsNotNone(got, s)
            self.assertEqual((got[0], got[1][0][1]), (who, mode), s)

    def test_target_player_side(self):
        self.assertEqual(parse_sentence("Target player discards all the cards in their hand, then draws that many "
                                        "cards.")[0].data["side"], "mine")
        self.assertEqual(parse_sentence("Target opponent discards all the cards in their hand, then draws that many "
                                        "cards.")[0].data["side"], "theirs")

    def test_refusals(self):
        for s in ("Target player discards all the cards in your hand, then draws that many cards.",   # whose hand
                  "Discard all the cards in your hand, then draws that many cards.",                  # verb form
                  "Each player discards their hand, then draw that many cards.",
                  "Each friend discards all cards from their hand, then draws that many cards plus one.",
                  "Discard all the cards in your hand, then draw that many cards plus four.",
                  "Each player shuffles all cards from their hand and all permanents they own into their library, "
                  "then draws that many cards.",
                  "Discard all the cards in your hand, then draw that many cards, or draw a card.",
                  "Target player exiles all cards from their hand face down, then draws that many cards.",   # #389
                  "Target player discards their hand, then draws cards equal to the greatest number of cards a player "
                  "discarded this way."):
            self.assertIsNone(parse_sentence(s), s)

    def test_fixed_amounts_unchanged(self):
        self.assertEqual([e.kind for e in parse_sentence("Target player draws two cards.")[0].data["effects"]],
                         ["draw"])


class Behaviour(Base):
    def library(self, p, n=20):
        p.library = [ISLAND] * n

    def test_discard_hand_plus_one(self):
        self.a.hand = [BEAR] * 3
        self.cast(self.spell("Discard all the cards in your hand, then draw that many cards plus one.", "Sorcery"))
        self.assertEqual(len(self.a.hand), 4)
        self.assertEqual(len(self.a.graveyard), 4)          # three discarded bears and the spell
        self.assertTrue(all(c.name == "Island" for c in self.a.hand))
        self.assertEqual(len(self.b.hand), 0)

    def test_empty_hand_plus_one_draws_one_and_zero_draws_none(self):
        self.a.hand = []
        self.cast(self.spell("Discard all the cards in your hand, then draw that many cards plus one."))
        self.assertEqual(len(self.a.hand), 1)
        self.a.hand = []
        self.cast(self.spell("Discard all the cards in your hand, then draw that many cards."))
        self.assertEqual(len(self.a.hand), 0)

    def test_each_player_counts_per_player_minus_one(self):
        self.a.hand, self.b.hand = [BEAR] * 2, [BEAR] * 5
        self.cast(self.spell("Each player discards all the cards in their hand, then draws that many cards minus one."))
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 4))
        self.assertEqual((len(self.a.graveyard), len(self.b.graveyard)), (3, 5))

    def test_each_player_puts_away_before_anyone_draws(self):
        # with one shared library-free order: every hand goes before the draws, so b's draws aren't discarded
        self.a.hand, self.b.hand = [BEAR] * 1, [BEAR] * 2
        self.cast(self.spell("Each player shuffles the cards from their hand into their library, then draws that many "
                             "cards."))
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 2))
        self.assertEqual((len(self.a.library), len(self.b.library)), (20, 20))

    def test_target_player_is_the_one_who_draws(self):
        self.a.hand, self.b.hand = [BEAR] * 1, [BEAR] * 3
        c = self.spell("Target player discards all the cards in their hand, then draws that many cards.")
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [self.b], card=c, name=c.name))
        self.game.resolve_top()
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 3))
        self.assertTrue(all(x.name == "Island" for x in self.b.hand))
        self.assertEqual(len(self.b.graveyard), 3)

    def test_bottom_of_library(self):
        self.a.hand = [BEAR] * 2
        self.cast(self.spell("Put the cards in your hand on the bottom of your library in any order, then draw that "
                             "many cards."))
        self.assertEqual([c.name for c in self.a.hand], ["Island", "Island"])
        self.assertEqual([c.name for c in self.a.library[:2]], ["Grizzly Bears"] * 2)    # the bottom

    def test_any_number_discards_only_dead_cards(self):
        for _ in range(5):
            self.perm(ISLAND, self.a)
        big = card("Huge Thing", "{9}{G}", "Creature — Beast", "", 9, 9)
        self.a.hand = [ISLAND, ISLAND, BEAR, big]
        self.cast(self.spell("Discard any number of cards, then draw that many cards."))
        # policy.choose_rummage: with 5 lands out, all lands but one, and the uncastable 10-drop
        self.assertEqual(sorted(c.name for c in self.a.graveyard if c.name != "Test Spell"),
                         ["Huge Thing", "Island"])
        self.assertEqual(len(self.a.hand), 4)

    def test_draw_replacement_applies_to_each_card(self):
        # "that many" is the count put away; each draw is a real draw (an empty library loses on the next SBA check)
        self.a.hand = [BEAR] * 3
        self.a.library = [ISLAND] * 2
        self.cast(self.spell("Discard all the cards in your hand, then draw that many cards."))
        self.assertEqual(len(self.a.hand), 2)

    def test_trigger_that_player_is_the_damaged_player(self):
        shocker = self.perm(card("Test Shocker", "{1}{R}", "Creature — Insect",
                                 "Whenever Test Shocker deals damage to a player, that player discards all the cards "
                                 "in their hand, then draws that many cards.", 1, 1), self.a)
        self.assertEqual(shocker.card.unsupported, [])
        self.a.hand, self.b.hand = [BEAR] * 2, [BEAR] * 3
        self.game.deal_damage(self.b, 1, self.a, source=shocker)
        self.game.flush_triggers()
        while self.game.stack:
            self.game.resolve_top()
        self.assertEqual(len(self.b.graveyard), 3)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (2, 3))


    def test_windfall_draws_the_greatest_count(self):
        self.a.hand, self.b.hand = [BEAR] * 1, [BEAR] * 4
        self.cast(self.spell("Each player discards their hand, then draws cards equal to the greatest number of cards "
                             "a player discarded this way.", "Sorcery"))
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (4, 4))
        self.assertEqual(len(self.b.graveyard), 4)

    def test_each_draw_step_trigger_is_the_drawing_player(self):
        box = self.perm(card("Test Box", "{4}", "Artifact",
                             "At the beginning of each player's draw step, that player puts the cards in their hand "
                             "on the bottom of their library in any order, then draws that many cards."), self.a)
        self.assertEqual(box.card.unsupported, [])
        self.a.hand, self.b.hand = [BEAR] * 2, [BEAR] * 3
        self.game.fire(self.a, "each_draw_step", context=self.b)
        self.game.flush_triggers()
        while self.game.stack:
            self.game.resolve_top()
        self.assertEqual([c.name for c in self.b.hand], ["Island"] * 3)
        self.assertEqual([c.name for c in self.a.hand], ["Grizzly Bears"] * 2)


class DefaultAI(Base):
    def test_casts_wheel_plus_one_on_a_dead_hand(self):
        for _ in range(5):
            self.perm(ISLAND, self.a)
        spell = card("Test Spell", "{1}", "Sorcery",
                     "Discard all the cards in your hand, then draw that many cards plus one.")
        self.assertEqual(spell.unsupported, [])
        self.a.hand = [spell, ISLAND, ISLAND, ISLAND]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)

    def test_target_opponent_minus_one_aims_at_the_opponent(self):
        self.perm(ISLAND, self.a)
        spell = card("Test Spell", "{U}", "Sorcery",
                     "Target player discards all the cards in their hand, then draws that many cards minus one.")
        self.assertEqual(spell.unsupported, [])
        self.a.hand = [spell, BEAR]
        self.b.hand = [BEAR] * 4
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual(len(self.b.hand), 3)
        self.assertIn(BEAR, self.a.hand)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Barbed Shocker", "Cavalier of Flame", "Collective Defiance", "Colossus of the Blood Age",
                     "Dark Deal", "Flux", "Heartwarming Redemption", "Incendiary Command",
                     "Robber Fly", "Shocker", "Steal the Show", "Teferi's Puzzle Box", "Whirlpool Warrior",
                     "Winds of Change", "Valakut Awakening", "Credit Voucher", "Windfall", "Whispering Madness",
                     "Jace's Archivist"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)

    def test_still_partial(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Sycorax Commander", "Khorvath's Fury", "The Great Aurora", "Fervent Mastery",
                     "Induced Amnesia"):     # its return trigger can't fire yet (#389)
            self.assertNotEqual(card_coverage(db.get(name)).ignored, [], name)


if __name__ == "__main__":
    unittest.main()
