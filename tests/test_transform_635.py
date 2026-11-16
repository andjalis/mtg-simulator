"""#635 TRANSFORM: "transform it" bound to the right object, conditional transforms ("Then if <condition>, transform
it", counter thresholds with "remove those counters"), targeted transforms (a Werewolf, an Incubator token), and
face-down creatures staying hidden from the opponent's AI."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_transform_it(self):
        effects, bad = _parse_effects("If it has no ice counters on it, transform it.")
        self.assertEqual(bad, [])
        self.assertEqual((effects[0].kind, effects[0].target), ("transform_it", "prev"))

    def test_counter_threshold_names_the_card(self):
        effects, bad = _parse_effects("Put a bore counter on ~. Then if there are three or more bore counters on it, "
                                      "remove those counters and transform it.")
        self.assertEqual(bad, [])
        self.assertEqual([(e.kind, e.target) for e in effects[1:]],
                         [("transform", "self"), ("cx_remove_counters", "self")])     # transform first: same check

    def test_targeted_transform(self):
        effects, bad = _parse_effects("Transform up to one target Werewolf you control.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["selector"]["subtypes"], ["werewolf"])
        self.assertTrue(effects[0].data["optional_target"])

    def test_refusals(self):
        # "you may" inside the condition's body would be dropped by the if-reader: left unread
        self.assertFalse(db("Primal Amulet // Primal Wellspring").fully_supported)
        # other "Then if ..." sentences keep their own templates (they used to be lost by a broad rewrite)
        for name in ("Golbez, Crystal Collector", "Iymrith, Desert Doom"):
            self.assertTrue(db(name).fully_supported, name)

    def test_real_cards_full(self):
        for name in ("Attentive Skywarden", "Brass's Tunnel-Grinder // Tecutlan, the Searing Rift",
                     "Civilized Scholar // Homicidal Brute", "Elvish Vatkeeper", "Geier Reach Bandit // Vildin-Pack Alpha",
                     "Grasping Shadows // Shadows' Lair", "Ludevic's Test Subject // Ludevic's Abomination",
                     "Seedpod Caretaker", "Smoldering Egg // Ashmouth Dragon", "Uninvited Geist // Unimpeded Trespasser",
                     "Waxing Moon", "Wedding Announcement // Wedding Festivity"):
            self.assertTrue(db(name).fully_supported, name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, p, name):
        x = self.game.enter_battlefield(p, db(name) if isinstance(name, str) else name)
        x.sick = False
        self.game.settle()
        return x

    def test_uninvited_geist_transforms_itself(self):
        geist = self.put(self.a, "Uninvited Geist // Unimpeded Trespasser")
        self.a.ai.choose_attackers = lambda g, p, o: [geist]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(geist.card.name, "Unimpeded Trespasser")

    def test_vildin_pack_alpha_transforms_the_entering_werewolf(self):
        alpha = self.put(self.a, "Geier Reach Bandit // Vildin-Pack Alpha")
        self.game.transform(alpha)
        newcomer = self.put(self.a, "Geier Reach Bandit // Vildin-Pack Alpha")
        self.assertEqual(newcomer.card.name, "Vildin-Pack Alpha")
        self.assertEqual(alpha.card.name, "Vildin-Pack Alpha")       # not flipped back by "transform it"

    def test_smoldering_egg_threshold(self):
        egg = self.put(self.a, "Smoldering Egg // Ashmouth Dragon")
        egg.counters["ember"] = 7
        c = db("Smoldering Egg // Ashmouth Dragon")
        effects = [e for t in c.triggers for e in t.effects if e.kind in ("transform", "cx_remove_counters")]
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects), source=egg, name="egg"))
        self.game.resolve_top()
        self.game.settle()
        self.assertEqual(egg.card.name, "Ashmouth Dragon")
        self.assertFalse(egg.counters.get("ember"))

    def test_wedding_announcement_transforms_itself_not_the_token(self):
        wedding = self.put(self.a, "Wedding Announcement // Wedding Festivity")
        wedding.counters["invitation"] = 2
        for p in (self.a, self.b):
            p.my_turn = p is self.a
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertEqual(wedding.card.name, "Wedding Festivity")

    def test_waxing_moon_transforms_my_werewolf_not_theirs(self):
        mine = self.put(self.a, "Geier Reach Bandit // Vildin-Pack Alpha")
        theirs = self.put(self.b, "Geier Reach Bandit // Vildin-Pack Alpha")
        for _ in range(2):
            self.game.enter_battlefield(self.a, FOREST)
        self.a.hand = [db("Waxing Moon")]
        self.assertTrue(self.game.cast(self.a, self.a.hand[0]))
        self.game.settle()
        self.assertEqual(mine.card.name, "Vildin-Pack Alpha")
        self.assertEqual(theirs.card.name, "Geier Reach Bandit")

    def test_incubator_token_transforms_into_a_phyrexian(self):
        inc_card = card("T Inc", "{1}", "Sorcery", "Incubate 2.")
        self.game.stack.append(StackItem(self.a, list(inc_card.spell_effects), [None], card=inc_card, name="inc"))
        self.game.resolve_top()
        token = next(x for x in self.a.battlefield if x.card.is_token)
        c = db("Seedpod Caretaker")
        mode = next(m for t in c.triggers for m in (t.modes or []) if any(e.kind == "transform" for e in m))
        self.game.stack.append(StackItem(self.a, list(mode), [token], name="seedpod"))
        self.game.resolve_top()
        self.game.settle()
        self.assertTrue(token.is_creature)
        self.assertEqual((token.power, token.toughness), (2, 2))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class HiddenInformation(unittest.TestCase):
    def board(self, hidden_name):
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 3, "main1"
        a.library = b.library = [ISLAND] * 20
        face_down = game.enter_battlefield(b, card("Face-down", "{3}", "Creature", "", 2, 2))
        face_down.hidden = db(hidden_name)
        game.enter_battlefield(b, BEAR)
        return game, a, b, face_down

    def test_the_opponents_ai_does_not_read_a_face_down_card(self):
        from mtgsim.engine.policy import default_choose_target, perm_value
        seen = []
        for hidden in ("Craw Wurm", "Grizzly Bears"):
            game, a, b, face_down = self.board(hidden)
            shock = db("Shock").spell_effects[0]
            target = default_choose_target(game, a, shock)
            seen.append((perm_value(face_down), target is face_down, a.ai.plan_spell(game, a, db("Shock"), True)))
        self.assertEqual(seen[0][:2], seen[1][:2])
        self.assertEqual(seen[0][2] is None, seen[1][2] is None)


if __name__ == "__main__":
    unittest.main()
