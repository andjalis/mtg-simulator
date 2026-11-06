""""Target player draws N cards" targets a player (issue #286): any player can be chosen, the AI chooses itself."""
import unittest

from tests.test_cx_grammar import DB_FILE, Base


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class TargetPlayerDraws(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB()

    def test_opponent_can_be_the_target(self):
        recall = self.db.get("Ancestral Recall")
        self.assertEqual((recall.spell_effects[0].target, recall.spell_effects[0].data["side"]), ("player", "mine"))
        hand = len(self.b.hand)
        self.cast(recall, [self.b])
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, hand + 3))

    def test_blood_pact_the_drawing_player_loses_life(self):
        self.cast(self.db.get("Blood Pact"), [self.b, None])
        self.assertEqual((self.a.life, self.b.life, len(self.b.hand)), (20, 18, 2))

    def test_ai_draws_for_itself_at_the_end_step(self):
        for name in ("Ancestral Recall", "Blood Pact"):
            spell = self.db.get(name)
            self.perm(self.db.get("Swamp"), self.a)
            self.perm(self.db.get("Island"), self.a)
            self.a.hand = [spell]
            self.game.step = "end_step"
            card, targets = self.a.ai.end_of_turn(self.game, self.a, [spell])
            self.assertIs(card, spell)
            self.assertIs(targets[0], self.a, name)


if __name__ == "__main__":
    unittest.main()
