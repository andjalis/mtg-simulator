"""#723: HeuristicAI casts Force of Despair, Icy Blast, Send to Sleep and Caught in the Crossfire at the opponent's end
step and aims them at the opponent's side: instant sweepers (destroy or damage a group), "tap X target creatures" and
taps whose "doesn't untap" rider holds now."""
import unittest

from tests.test_ai_716 import BEAR, WURM, Base, card, db

ROGUE = card("Test Rogue", "{1}{B}", "Creature — Human Rogue", "", 2, 2)


class EndStep(Base):
    def cast(self, choice):
        self.assertTrue(self.game.cast(self.a, choice[0], choice[1]))
        self.game.settle()


class ForceOfDespair(EndStep):
    def test_destroys_what_entered_this_turn(self):
        self.lands("B", 3)
        wurm, bear = self.game.enter_battlefield(self.b, WURM), self.game.enter_battlefield(self.b, BEAR)
        mine = self.game.enter_battlefield(self.a, BEAR)
        mine.entered_turn = self.game.turn - 1          # mine is older: only theirs entered this turn
        self.their_end_step()
        _, choice = self.eot("Force of Despair")
        self.assertIsNotNone(choice)
        self.cast(choice)
        self.assertNotIn(wurm, self.b.battlefield)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)

    def test_held_when_it_would_hit_mine_too(self):
        self.lands("B", 3)
        self.game.enter_battlefield(self.b, BEAR)
        self.game.enter_battlefield(self.a, WURM)        # entered this turn too: a net loss
        self.their_end_step()
        _, choice = self.eot("Force of Despair")
        self.assertIsNone(choice)


class IcyBlast(EndStep):
    def test_taps_theirs_when_ferocious_locks_them(self):
        self.lands("U", 3)
        wurm, bear = self.game.enter_battlefield(self.b, WURM), self.game.enter_battlefield(self.b, BEAR)
        mine = self.game.enter_battlefield(self.a, WURM)     # power 6: ferocious
        self.their_end_step()
        _, choice = self.eot("Icy Blast")
        self.assertIsNotNone(choice)
        self.assertEqual(set(map(id, choice[1][0])), {id(wurm), id(bear)})
        self.cast(choice)
        self.assertTrue(wurm.tapped and bear.tapped)
        self.assertFalse(mine.tapped)

    def test_held_without_ferocious(self):
        self.lands("U", 3)
        self.game.enter_battlefield(self.b, WURM)
        self.game.enter_battlefield(self.b, BEAR)
        self.their_end_step()
        _, choice = self.eot("Icy Blast")
        self.assertIsNone(choice)


class SendToSleep(EndStep):
    def test_taps_theirs_with_spell_mastery(self):
        self.lands("U", 2)
        self.a.graveyard.extend([db("Shock"), db("Divination")])
        wurm, bear = self.game.enter_battlefield(self.b, WURM), self.game.enter_battlefield(self.b, BEAR)
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.their_end_step()
        _, choice = self.eot("Send to Sleep")
        self.assertIsNotNone(choice)
        self.assertEqual({id(t) for t in choice[1] if t is not None}, {id(wurm), id(bear)})
        self.cast(choice)
        self.assertTrue(wurm.tapped and bear.tapped)
        self.assertFalse(mine.tapped)


class CaughtInTheCrossfire(EndStep):
    def test_picks_the_mode_that_hits_their_side(self):
        self.lands("R", 4)
        rogues = [self.game.enter_battlefield(self.b, ROGUE) for _ in range(2)]
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.their_end_step()
        _, choice = self.eot("Caught in the Crossfire")
        self.assertIsNotNone(choice)
        self.cast(choice)
        self.assertTrue(all(r not in self.b.battlefield for r in rogues))
        self.assertIn(mine, self.a.battlefield)

    def test_non_outlaw_mode_spares_my_rogue(self):
        self.lands("R", 4)
        bears = [self.game.enter_battlefield(self.b, BEAR) for _ in range(2)]
        mine = self.game.enter_battlefield(self.a, ROGUE)
        self.their_end_step()
        _, choice = self.eot("Caught in the Crossfire")
        self.assertIsNotNone(choice)
        self.cast(choice)
        self.assertTrue(all(b not in self.b.battlefield for b in bears))
        self.assertIn(mine, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()
