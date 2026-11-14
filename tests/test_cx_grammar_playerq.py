"""#337: player verbs whose amount counts the subject's own things ("for each creature they control")."""
import unittest

from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
RELIC = card("Test Relic", "{1}", "Artifact", "")


def rel(s):
    effs = parse_sentence(s)
    if not effs or len(effs) != 1 or not effs[0].data.get("xq_rel"):
        return None
    e = effs[0]
    return e.data["who"], e.data["xq"], [(x.kind, x.amount) for x in e.data["effects"]]


class Parsing(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(rel("Target player draws a card for each basic land type among lands they control."),
                         ("target", ("domain",), [("draw", 1)]))
        self.assertEqual(rel("Each player loses 1 life for each creature they control."),
                         ("each", ("count", "creature"), [("lose_life", 1)]))
        self.assertEqual(rel("Each player draws a card for each creature card in their graveyard."),
                         ("each", ("gy", "creature"), [("draw", 1)]))
        self.assertEqual(rel("Target opponent loses 2 life for each creature card in their graveyard."),
                         ("target", ("gy", "creature"), [("lose_life", 2)]))
        self.assertEqual(rel("Target player loses 1 life for each tapped artifact they control."),
                         ("target", ("tapped_any", ("artifact",)), [("lose_life", 1)]))
        self.assertEqual(rel("Target opponent loses life equal to the number of creatures they control."),
                         ("target", ("count", "creature"), [("lose_life", 1)]))
        self.assertEqual(rel("Target player draws cards equal to the number of cards in their hand."),
                         ("target", ("hand",), [("draw", 1)]))
        self.assertEqual(rel("Defending player mills a card for each land they control."),
                         ("defending", ("count", "land"), [("mill", 1)]))

    def test_refusals(self):
        for s in ("You gain 1 life for each creature they control.",                 # "you" subject: whose "they"?
                  "Each player loses 1 life for each creature they control and you control.",
                  "Target player draws a card for each creature that player's opponents control.",
                  "Each player loses 1 life for each spell they've cast this turn.",     # not a per-player quantity here
                  "Each player draws a card and loses 1 life for each creature they control.",
                  "Target player loses 1 life for each creature they control for each opponent."):
            self.assertIsNone(rel(s), s)

    def test_caster_relative_unchanged(self):
        effs = parse_sentence("Each player loses 1 life for each creature you control.")
        self.assertEqual(effs[0].data["xq"], ("count", "creature"))
        self.assertFalse(effs[0].data.get("xq_rel"))


class Behaviour(Base):
    def resolve(self, text, target=None):
        c = self.spell(text)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [target] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_each_player_counts_their_own(self):
        for _ in range(3):
            self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        self.resolve("Each player loses 1 life for each creature they control.")
        self.assertEqual((self.a.life, self.b.life), (17, 19))

    def test_target_player_domain_is_theirs(self):
        for land in (FOREST, FOREST, ISLAND):
            self.perm(land, self.a)
        for land in (FOREST, ISLAND, MOUNTAIN, SWAMP):
            self.perm(land, self.b)
        self.resolve("Target player draws a card for each basic land type among lands they control.", self.b)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 4))
        self.resolve("Target player draws a card for each basic land type among lands they control.", self.a)
        self.assertEqual(len(self.a.hand), 2)      # two Forests are one type

    def test_graveyard_count_is_snapshotted_per_player(self):
        self.a.graveyard.extend([BEAR] * 2)
        self.b.graveyard.extend([BEAR, ISLAND])
        self.resolve("Each player draws a card for each creature card in their graveyard.")
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (2, 1))

    def test_zero(self):
        self.resolve("Target opponent loses life equal to the number of creatures they control.", self.b)
        self.assertEqual(self.b.life, 20)

    def test_tapped_artifacts_they_control(self):
        tapped = self.perm(RELIC, self.b)
        tapped.tapped = True
        self.perm(RELIC, self.b)
        self.perm(RELIC, self.a).tapped = True
        self.resolve("Target player loses 1 life for each tapped artifact they control.", self.b)
        self.assertEqual((self.a.life, self.b.life), (20, 19))

    def test_hand_size_read_before_drawing(self):
        self.b.hand = [BEAR] * 3
        self.resolve("Target player draws cards equal to the number of cards in their hand.", self.b)
        self.assertEqual(len(self.b.hand), 6)


class DefaultAI(Base):
    def main_phase(self, text):
        spell = card("Test Spell", "{U}", "Sorcery", text)
        self.assertEqual(spell.unsupported, [], text)
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand, "the AI didn't cast it")

    def test_draw_targets_the_player_with_more_types(self):
        # the AI sizes "they control" per candidate: it draws for itself when it has the domain
        for land in (FOREST, MOUNTAIN, SWAMP):
            self.perm(land, self.a)
        self.main_phase("Target player draws a card for each basic land type among lands they control.")
        self.assertEqual(len(self.a.hand), 4)       # Forest, Mountain, Swamp, Island

    def test_life_loss_aims_at_the_opponent(self):
        for _ in range(3):
            self.perm(BEAR, self.b)
        self.main_phase("Target player loses 1 life for each creature they control.")
        self.assertEqual((self.a.life, self.b.life), (20, 17))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Allied Strategies", "Burden of Greed", "Collapsing Borders", "Emissary of Despair", "Guiltfeeder",
                     "Liliana, Death Mage", "Nature's Resurgence", "Netherborn Phalanx", "Origin of Black Widow",
                     "Stern Judge", "Stronghold Discipline", "Tomb Blade", "Villainous Wrath"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)

    def test_tomb_blade_sacrifice_or_lose_life(self):
        from mtgsim.carddb import CardDB
        blade = self.perm(CardDB(offline=True).get("Tomb Blade"), self.a)
        for _ in range(3):
            self.perm(BEAR, self.b)
        life = self.b.life
        self.game.fire(self.a, "combat_damage_player", blade, context=self.b)
        self.game.flush_triggers()
        while self.game.stack:
            self.game.resolve_top()
        sacrificed = 3 - len(self.b.creatures)
        self.assertIn((sacrificed, life - self.b.life), [(1, 0), (0, 3)])


if __name__ == "__main__":
    unittest.main()
