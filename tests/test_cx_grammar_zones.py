"""Grammar zone-change verbs (mtgsim.cx_grammar_zones): destroy, exile and return to hand as imperatives."""
import dataclasses
import unittest

from mtgsim.cx_grammar import parse_sentence

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

GREEN = card("Test Green", "{G}", "Creature — Elf", "", 2, 2)
ROCK = card("Test Rock", "{2}", "Artifact", "")
AURA_FREE = card("Test Totem", "{1}{W}", "Enchantment", "")
HILL = card("Test Hill", "", "Land", "")
TOUGH = card("Test Wall", "{1}{G}", "Creature — Wall", "Indestructible", 0, 4)


class Parsing(unittest.TestCase):
    def kinds(self, s):
        effs = parse_sentence(s)
        return None if effs is None else [e.kind for e in effs]

    def test_targets_groups_and_lists(self):
        self.assertEqual(self.kinds("Destroy target creature or planeswalker that's green or white."), ["destroy"])
        self.assertEqual(self.kinds("Exile target creature or planeswalker that's black or red."),
                         ["exile_permanent"])
        self.assertEqual(self.kinds("Destroy target creature and target land."), ["destroy", "destroy"])
        self.assertEqual(self.kinds("Destroy all artifacts, creatures, and lands."), ["cx_group"])
        self.assertEqual(self.kinds("Destroy all creatures you don't control and all planeswalkers you don't control."),
                         ["cx_group"] * 2)
        self.assertEqual(self.kinds("Return all nonblue creatures to their owners' hands."), ["cx_group"])
        self.assertEqual(self.kinds("Return target creature an opponent controls to its owner's hand."), ["bounce"])
        effs = parse_sentence("Destroy target creature and target land.")
        self.assertEqual([e.target for e in effs], ["permanent", "permanent"])

    def test_player_sacrifices(self):
        effs = parse_sentence("Each player sacrifices two lands.")
        self.assertEqual([e.kind for e in effs], ["cx_players"])
        self.assertEqual([(e.kind, e.amount) for e in effs[0].data["effects"]], [("cx_edict", 2)])
        self.assertEqual(self.kinds("Each opponent sacrifices a creature or planeswalker."), ["cx_players"])
        for s in ("Each player sacrifices a creature you control.",
                  "Each opponent sacrifices a creature with the greatest power among creatures they control.",
                  "Each player sacrifices two land."):
            self.assertIsNone(parse_sentence(s), s)

    def test_rejects_what_it_cannot_execute(self):
        for s in ("Exile target creature until ~ leaves the battlefield.",         # linked exile
                  "Destroy target creature unless its controller pays {2}.",       # condition (gcond)
                  "Destroy all lands or all creatures.",                           # a choice
                  "Destroy target creature that dealt damage this turn.",          # history
                  "Exile target card from a graveyard.",                           # another zone
                  "Exile that creature.",                                          # back-reference round
                  "Destroy all creatures of the creature type of your choice.",
                  "Return target creature to its owner's hand until end of turn."):
            self.assertIsNone(parse_sentence(s), s)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Noxious Grasp", "Devout Decree", "Jokulhaups", "Fumarole", "Inundate", "Churning Eddy",
                     "Grip of Desolation", "Decimate", "Fated Retribution"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


class Resolving(Base):
    def test_destroy_colour_target_respects_indestructible(self):
        elf, wall = self.perm(GREEN, self.b), self.perm(TOUGH, self.b)
        spell = self.spell("Destroy target creature or planeswalker that's green or white.")
        self.cast(spell, [elf])
        self.assertNotIn(elf, self.b.battlefield)
        self.assertIn(GREEN.name, [c.name for c in self.b.graveyard])
        self.cast(spell, [wall])
        self.assertIn(wall, self.b.battlefield)

    def test_colour_target_is_checked(self):
        red = self.perm(card("Test Red", "{R}", "Creature — Human", "", 2, 2), self.b)
        spell = self.spell("Destroy target creature or planeswalker that's green or white.")
        self.assertFalse(self.game.legal_target(self.a, spell.spell_effects[0], red))
        self.assertTrue(self.game.legal_target(self.a, spell.spell_effects[0], self.perm(BEAR, self.b)))

    def test_destroy_all_list(self):
        keep = self.perm(AURA_FREE, self.b)
        gone = [self.perm(BEAR, self.a), self.perm(ROCK, self.b), self.perm(HILL, self.b)]
        self.cast(self.spell("Destroy all artifacts, creatures, and lands.", "Sorcery"))
        self.assertEqual(self.a.battlefield + self.b.battlefield, [keep])
        self.assertTrue(all(x not in self.a.battlefield + self.b.battlefield for x in gone))

    def test_bounce_goes_to_owners_hand(self):
        stolen = self.perm(BEAR, self.b)
        self.b.battlefield.remove(stolen)
        stolen.controller = self.a
        self.a.battlefield.append(stolen)
        hand = len(self.b.hand)
        self.cast(self.spell("Return all nonblue creatures to their owners' hands.", "Sorcery"))
        self.assertNotIn(stolen, self.a.battlefield)
        self.assertEqual(len(self.b.hand), hand + 1)

    def test_exile_pair_goes_to_owners_exile(self):
        bear, hill = self.perm(BEAR, self.b), self.perm(HILL, self.b)
        self.cast(self.spell("Exile target creature and target land.", "Sorcery"), [bear, hill])
        self.assertEqual(sorted(c.name for c in self.b.exile), sorted([BEAR.name, HILL.name]))

    def test_exiled_token_ceases_to_exist(self):
        token = self.perm(dataclasses.replace(card("Test Token", "", "Creature — Soldier", "", 1, 1), is_token=True),
                          self.b)
        self.cast(self.spell("Exile target creature or planeswalker that's black or red."), [token])
        self.assertIn(token, self.b.battlefield)        # not a legal target: it's colourless
        self.cast(self.spell("Exile all creatures and planeswalkers.", "Sorcery"))
        self.assertNotIn(token, self.b.battlefield)
        self.assertEqual(self.b.exile, [])

    def test_each_player_sacrifices_two_lands(self):
        for p in (self.a, self.b):
            for _ in range(3):
                self.perm(HILL, p)
        bear = self.perm(BEAR, self.b)
        self.cast(self.spell("Each player sacrifices two lands.", "Sorcery"))
        self.assertEqual([len([x for x in p.battlefield if x.card.is_land]) for p in (self.a, self.b)], [1, 1])
        self.assertIn(bear, self.b.battlefield)

    def test_opponent_sacrifices_token_first(self):
        token = self.perm(dataclasses.replace(card("Test Token", "", "Creature — Soldier", "", 1, 1), is_token=True),
                          self.b)
        bear, mine = self.perm(BEAR, self.b), self.perm(BEAR, self.a)
        self.cast(self.spell("Each opponent sacrifices a creature or planeswalker."))
        self.assertNotIn(token, self.b.battlefield)
        self.assertIn(bear, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)


class DefaultAI(Base):
    """HeuristicAI casts these spells in its main phase and aims them at the opponent."""
    def main_phase(self, text, types="Sorcery"):
        spell = card("Test Spell", "{U}", types, text)
        self.assertEqual(spell.unsupported, [], text)
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand, text)
        return spell

    def test_destroys_the_opponents_creature(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(GREEN, self.b)
        self.main_phase("Destroy target creature or planeswalker that's green or white.")
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_target_pair_hits_the_opponent(self):
        mine, theirs, hill = self.perm(BEAR, self.a), self.perm(BEAR, self.b), self.perm(HILL, self.b)
        self.main_phase("Destroy target creature and target land.")
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertNotIn(hill, self.b.battlefield)

    def test_exiles_the_opponents_permanent(self):
        theirs = self.perm(GREEN, self.b)
        self.main_phase("Exile target creature or planeswalker that's green or white.")
        self.assertEqual([c.name for c in self.b.exile], [GREEN.name])
        self.assertNotIn(theirs, self.b.battlefield)

    def test_opponent_sacrifices(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.main_phase("Each opponent sacrifices a creature or planeswalker.")
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_target_opponent_sacrifices(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.main_phase("Target opponent sacrifices a nontoken creature.")
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_casts_a_sweeper_that_favours_it(self):
        theirs = [self.perm(BEAR, self.b) for _ in range(3)]
        self.main_phase("Destroy all creatures and planeswalkers.")
        self.assertFalse(any(x in self.b.battlefield for x in theirs))

    def test_holds_a_sweeper_that_hurts_it(self):
        for _ in range(3):
            self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        spell = card("Test Spell", "{U}", "Sorcery", "Return all nonblue creatures to their owners' hands.")
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(spell, self.a.hand)


if __name__ == "__main__":
    unittest.main()
