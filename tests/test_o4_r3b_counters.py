"""O4 round 3b: sacrifice-count counters, graveyard blitz, delayed counters, Gev, Corpse Appraiser, Fireglass Mentor."""
import unittest

from mtgsim.carddb import CardDB
from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, Base, card

PURSUIT = card("Test Pursuit", "{1}{B}", "Enchantment", "Whenever you attack, put X +1/+1 counters on target attacking "
               "creature, where X is the number of permanents you've sacrificed this turn. If X is three or more, that "
               "creature gains lifelink until end of turn.")
PURSUIT_OTHER = card("Test Pursuit Two", "{1}{B}", "Enchantment", "Whenever you attack, put X +1/+1 counters on target "
                     "attacking creature, where X is the number of creatures that died this turn.")
KUMANO = card("Test Kumano", "{1}{R}", "Enchantment — Saga", "(As this Saga enters and after your draw step, add a lore "
              "counter.)\nI — This Saga deals 1 damage to each opponent.\nII — When you next cast a creature spell this "
              "turn, that creature enters with an additional +1/+1 counter on it.\nIII — Draw a card.")
GEV = card("Test Gev", "{2}{B}{R}", "Legendary Creature — Lizard Warlock", "Other creatures you control enter with an "
           "additional +1/+1 counter on them for each opponent who lost life this turn.", 3, 3)
GEV_YOURS_ONLY = card("Test Gev Two", "{2}{B}{R}", "Legendary Creature — Lizard", "Other creatures enter with an "
                      "additional +1/+1 counter on them for each opponent who lost life this turn.", 3, 3)
APPRAISER = card("Test Appraiser", "{2}{B}", "Creature — Vampire", "When this creature enters, exile up to one target "
                 "creature card from a graveyard. If a card is put into exile this way, look at the top three cards of "
                 "your library, then put one of those cards into your hand and the rest into your graveyard.", 2, 2)
MENTOR = card("Test Mentor", "{2}{R}", "Creature — Dragon", "At the beginning of your second main phase, if an opponent "
              "lost life this turn, exile the top two cards of your library. Choose one of them. Until end of turn, you "
              "may play that card.", 3, 3)
MENTOR_ALL = card("Test Mentor Two", "{2}{R}", "Creature — Dragon", "At the beginning of your second main phase, if an "
                  "opponent lost life this turn, exile the top two cards of your library. Choose one of them. Until end "
                  "of your next turn, you may play that card.", 3, 3)
UNDERDOG = card("Test Underdog", "{1}{B}", "Creature — Human Warrior", "Blitz—{2}{B}{B}, Pay 2 life. (If you cast this "
                "spell for its blitz cost, it gains haste and \"When this creature dies, draw a card.\" Sacrifice it at "
                "the beginning of the next end step.)\nYou may cast this card from your graveyard using its blitz "
                "ability.", 3, 2)
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
RAT = card("Test Rat", "{R}", "Creature — Rat", "", 1, 1)
OGRE = card("Test Ogre", "{3}{R}", "Creature — Ogre", "", 4, 4)


def p1(perm):
    return perm.counters.get("+1/+1", 0)


class Parsing(Base):
    def test_templates(self):
        for c in (PURSUIT, KUMANO, GEV, APPRAISER, MENTOR, UNDERDOG):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(GEV.others_enter_counters, "opp_lost_life")
        self.assertEqual([a.zone for a in UNDERDOG.alt_costs], ["hand+graveyard"])
        self.assertEqual(KUMANO.chapters[1][0].kind, "next_creature_counter")
        self.assertTrue(MENTOR.triggers[0].effects[1].data["one"])

    def test_nearby_shapes_stay_unsupported(self):
        for c in (PURSUIT_OTHER, MENTOR_ALL):
            with self.subTest(card=c.name):
                self.assertTrue(c.unsupported)

    def test_real_cards(self):
        db = CardDB(offline=True)
        if db.lookup("Corpse Appraiser") is None:
            self.skipTest("card database not built")
        for name in ("Obsessive Pursuit", "Tenacious Underdog", "Kumano Faces Kakkazan", "Gev, Scaled Scorch",
                     "Corpse Appraiser", "Fireglass Mentor"):
            with self.subTest(card=name):
                self.assertEqual(db.get(name).unsupported, [])


class Interactions(Base):
    def attack_trigger(self, attackers):
        self.game.attackers = list(attackers)
        self.game.fire(self.a, "you_attack")
        self.game.settle()

    def test_pursuit_counts_sacrifices_and_grants_lifelink_from_three(self):
        self.perm(PURSUIT, self.a)
        bear, idle = self.perm(BEAR, self.a), self.perm(DRAGON3, self.a)
        self.a.sacrificed_turn = 2
        self.attack_trigger([bear])
        self.assertEqual((p1(bear), p1(idle), bear.has("lifelink")), (2, 0, False))
        self.a.sacrificed_turn = 3
        self.attack_trigger([bear])
        self.assertEqual((p1(bear), bear.has("lifelink")), (5, True))

    def test_pursuit_without_sacrifices_does_nothing(self):
        self.perm(PURSUIT, self.a)
        bear = self.perm(BEAR, self.a)
        self.attack_trigger([bear])
        self.assertEqual((p1(bear), bear.has("lifelink")), (0, False))

    def test_pursuit_only_targets_an_attacker(self):
        self.perm(PURSUIT, self.a)
        idle = self.perm(BEAR, self.a)
        self.a.sacrificed_turn = 2
        self.attack_trigger([])
        self.assertEqual(p1(idle), 0)

    def test_underdog_blitzed_from_the_graveyard(self):
        for _ in range(4):
            self.perm(SWAMP, self.a)
        self.a.graveyard = [UNDERDOG]
        blitz = next(c for c in self.game.spell_options(self.a) if "blitz" in c.name)
        life = self.a.life
        self.assertTrue(self.game.cast(self.a, blitz))
        self.game.settle()
        dog = next(x for x in self.a.creatures if x.card.name == "Test Underdog")
        self.assertEqual((self.a.life, dog.blitz, dog.has("haste")), (life - 2, True, True))
        self.game.dies(dog)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)                    # "when this creature dies, draw a card"

    def test_underdog_in_hand_still_blitzes_and_other_cards_are_not_castable_from_graveyard(self):
        for _ in range(4):
            self.perm(SWAMP, self.a)
        self.a.graveyard = [BEAR]
        self.assertFalse([c for c in self.game.spell_options(self.a) if c.name == BEAR.name])
        self.a.graveyard = []
        self.a.hand = [UNDERDOG]
        self.assertTrue(any("blitz" in c.name for c in self.game.spell_options(self.a)))

    def test_kumano_chapter_two_buffs_only_the_next_creature_spell(self):
        for _ in range(4):
            self.perm(MOUNTAIN, self.a)
        self.game.resolve(self.a, KUMANO.chapters[1][0], None)
        self.a.hand = [RAT, RAT]
        self.game.cast(self.a, RAT)
        self.game.settle()
        self.game.cast(self.a, RAT)
        self.game.settle()
        self.assertEqual(sorted(p1(x) for x in self.a.creatures), [0, 1])

    def test_gev_gives_counters_only_after_an_opponent_lost_life(self):
        self.perm(GEV, self.a)
        first = self.game.enter_battlefield(self.a, BEAR)
        self.assertEqual(p1(first), 0)
        self.b.life -= 1
        second = self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, BEAR)
        gev2 = self.game.enter_battlefield(self.a, GEV)
        self.assertEqual((p1(second), p1(theirs), p1(gev2)), (1, 0, 1))       # a second Gev is an "other creature"

    def test_gev_does_not_buff_noncreatures(self):
        self.perm(GEV, self.a)
        self.b.life -= 1
        land = self.game.enter_battlefield(self.a, MOUNTAIN)
        self.assertEqual(p1(land), 0)

    def test_appraiser_exiles_a_creature_card_and_keeps_the_best_of_three(self):
        self.b.graveyard.append(DRAGON3)
        self.a.graveyard.append(BEAR)
        self.a.library = [ISLAND, ISLAND, ISLAND, OGRE, BEAR, ISLAND]      # top of library is the end of the list
        self.a.library[-3:] = [ISLAND, OGRE, BEAR]
        before = len(self.a.library)
        self.game.enter_battlefield(self.a, APPRAISER)
        self.game.settle()
        self.assertEqual(self.b.exile.count(DRAGON3), 1)
        self.assertEqual(self.a.graveyard.count(BEAR), 2)               # kept BEAR plus the one binned from the top
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(len(self.a.library), before - 3)
        self.assertEqual(len(self.a.graveyard), 3)

    def test_appraiser_without_a_creature_card_does_not_dig(self):
        self.a.library = [ISLAND] * 5
        self.game.enter_battlefield(self.a, APPRAISER)
        self.game.settle()
        self.assertEqual((len(self.a.hand), len(self.a.library)), (0, 5))

    def test_mentor_lets_you_play_only_one_of_the_two_exiled_cards(self):
        self.perm(MENTOR, self.a)
        self.a.library = [BEAR, OGRE, BEAR]
        self.b.life -= 1
        self.game.fire(self.a, "main2_begin")
        self.game.settle()
        self.assertEqual(len(self.a.exile), 2)
        playable = self.game.impulse_cards(self.a)
        self.assertEqual(len(playable), 1)
        self.assertIn(playable[0], self.a.exile)
        self.game.turn += 1
        self.assertEqual(self.game.impulse_cards(self.a), [])

    def test_mentor_needs_an_opponent_to_have_lost_life(self):
        self.perm(MENTOR, self.a)
        self.a.library = [BEAR, OGRE, BEAR]
        self.game.fire(self.a, "main2_begin")
        self.game.settle()
        self.assertEqual((len(self.a.exile), len(self.a.library)), (0, 3))


if __name__ == "__main__":
    unittest.main()
