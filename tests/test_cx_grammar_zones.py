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
                  "Destroy all lands or all creatures.",                           # a choice
                  "Destroy target creature that dealt damage this turn.",          # history
                  "Exile that creature.",                                          # back-reference round
                  "Destroy all creatures of the creature type of your choice.",
                  "Return target creature to its owner's hand until end of turn."):
            self.assertIsNone(parse_sentence(s), s)

    def test_unless_riders_are_conditions(self):
        for s, kind in (("Destroy target creature unless its controller pays {2}.", "destroy"),
                        ("~ deals 2 damage to you unless you pay {1}.", "lose_life")):
            effects = parse_sentence(s)
            self.assertEqual([e.kind for e in effects], ["cx_unless", kind], s)
            self.assertEqual(effects[1].cond, 'lib:["unless_unpaid"]', s)


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


class QualifiedRemovalWordings(Base):
    """Qualifiers the old core.json removal entries swallowed ("nonblack", "tapped", "an opponent controls") are
    now read, and "exile" no longer destroys."""
    def legal(self, text, perm):
        spell = self.spell(text)
        return self.game.legal_target(self.a, spell.spell_effects[0], perm)

    def test_nonblack(self):
        black = self.perm(card("Test Black", "{B}", "Creature — Zombie", "", 2, 2), self.b)
        self.assertFalse(self.legal("Destroy target nonblack creature.", black))
        self.assertTrue(self.legal("Destroy target nonblack creature.", self.perm(BEAR, self.b)))

    def test_controller_and_tapped(self):
        mine, theirs, untapped = self.perm(BEAR, self.a), self.perm(BEAR, self.b), self.perm(BEAR, self.b)
        mine.tapped = theirs.tapped = True
        text = "Destroy target tapped creature an opponent controls."
        self.assertEqual([self.legal(text, x) for x in (mine, theirs, untapped)], [False, True, False])
        self.assertFalse(self.legal("Exile target creature an opponent controls.", mine))
        self.assertFalse(self.legal("~ deals 2 damage to target tapped creature an opponent controls.", mine))

    def test_exile_does_not_destroy(self):
        bear = self.perm(BEAR, self.b)
        self.game.attackers.append(bear)
        self.cast(self.spell("Exile target attacking or blocking creature."), [bear])
        self.assertEqual([c.name for c in self.b.exile], [BEAR.name])
        self.assertEqual(self.b.graveyard, [])

    def test_artifact_or_enchantment_can_be_your_own(self):
        rock = self.perm(ROCK, self.a)
        self.assertTrue(self.legal("Destroy target artifact or enchantment.", rock))

DIER = card("Test Dier", "{1}{B}", "Creature — Zombie", "When this creature dies, you gain 3 life.", 2, 2)
ARTIST = card("Test Artist", "{1}{B}", "Creature — Vampire", "Whenever another creature dies, you gain 1 life.", 0, 1)


class Library(Base):
    """Putting a permanent into its owner's library never passes through the graveyard."""
    def setUp(self):
        super().setUp()
        self.perm(ARTIST, self.a)
        self.life = (self.a.life, self.b.life)

    def tuck(self, text, victim):
        self.cast(self.spell(text), [victim])
        self.game.flush_triggers()
        while self.game.stack:
            self.game.resolve_top()

    def assert_no_death(self):
        self.assertEqual((self.a.life, self.b.life), self.life)
        self.assertEqual(self.b.graveyard, [])

    def test_top_fires_no_dies_triggers(self):
        dier = self.perm(DIER, self.b)
        self.tuck("Put target creature on top of its owner's library.", dier)          # the old tuck_top kind
        self.assertIs(self.b.library[-1], dier.front)
        self.assert_no_death()

    def test_grammar_top_bottom_and_shuffle(self):
        land, dier, other = self.perm(HILL, self.b), self.perm(DIER, self.b), self.perm(DIER, self.b)
        self.tuck("Put target land on top of its owner's library.", land)
        self.assertIs(self.b.library[-1], land.front)
        self.tuck("Put target nonland permanent on the bottom of its owner's library.", dier)
        self.assertIs(self.b.library[0], dier.front)
        self.tuck("Shuffle target creature into its owner's library.", other)
        self.assertIn(other.front, self.b.library)
        self.assertEqual(len(self.b.library), 23)
        self.assert_no_death()

    def test_stolen_permanent_goes_to_its_owners_library(self):
        dier = self.perm(DIER, self.b)
        self.b.battlefield.remove(dier)
        dier.controller = self.a
        self.a.battlefield.append(dier)
        self.tuck("Put target creature on top of its owner's library.", dier)
        self.assertIs(self.b.library[-1], dier.front)
        self.assertNotIn(dier.front, self.a.library)

    def test_token_ceases_to_exist(self):
        token = self.perm(dataclasses.replace(DIER, is_token=True), self.b)
        self.tuck("Put target nonland permanent on the bottom of its owner's library.", token)
        self.assertNotIn(token, self.b.battlefield)
        self.assertEqual(len(self.b.library), 20)
        self.assert_no_death()

    def test_group_to_the_bottom(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(DIER, self.b)
        self.cast(self.spell("Put all creatures on the bottom of their owners' libraries.", "Sorcery"))
        self.assertEqual((self.a.library[0].name, self.b.library[0].name), (BEAR.name, DIER.name))
        self.assertNotIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_ai_tucks_the_opponents_permanent(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        spell = card("Test Spell", "{U}", "Sorcery", "Put target nonland permanent on the bottom of its owner's library.")
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)


class GraveyardCards(Base):
    """Cards moved out of an exact graveyard by a card noun phrase."""
    def test_parsing(self):
        effs = parse_sentence("Return up to two target creature cards with power 2 or less from your graveyard to "
                              "the battlefield.")
        self.assertEqual([(e.kind, e.target) for e in effs], [("cx_card_move", "graveyard_card")] * 2)
        self.assertTrue(effs[0].data["optional_target"] and effs[0].data["distinct"])
        for s in ("Return target creature card with infect from your graveyard to your hand.",     # unknown words
                  "Return target creature card with lesser mana value from your graveyard to the battlefield.",
                  "Return target creature card from a graveyard to the battlefield.",   # under whose control?
                  "Return target card from an opponent's graveyard to your hand.",
                  "Put two target cards from a graveyard on top of their owners' libraries.",
                  "Exile target card from that player's graveyard."):
            self.assertIsNone(parse_sentence(s), s)

    def test_zone_is_exact(self):
        mine, theirs = self.a.graveyard, self.b.graveyard
        mine.append(BEAR)
        theirs.append(GREEN)
        spell = self.spell("Return target card from an opponent's graveyard to their hand.")
        self.assertEqual(self.game.legal_targets(self.a, spell.spell_effects[0]), [theirs[0]])
        self.cast(spell, [theirs[0]])
        self.assertEqual([c.name for c in self.b.hand], [GREEN.name])

    def test_card_noun_is_checked(self):
        self.a.graveyard.extend([BEAR, ROCK])
        spell = self.spell("Return target creature card with power 2 or less from your graveyard to the battlefield.")
        self.assertEqual([c.name for c in self.game.legal_targets(self.a, spell.spell_effects[0])], [BEAR.name])
        self.cast(spell, [self.a.graveyard[0]])
        self.assertEqual([x.card.name for x in self.a.battlefield], [BEAR.name])

    def test_to_owners_hand_from_any_graveyard(self):
        self.b.graveyard.append(ROCK)
        self.cast(self.spell("Return target artifact or enchantment card from a graveyard to its owner's hand."),
                  [self.b.graveyard[0]])
        self.assertEqual(([c.name for c in self.b.hand], self.a.hand), ([ROCK.name], []))

    def test_onto_the_battlefield_under_your_control(self):
        self.b.graveyard.append(GREEN)
        self.cast(self.spell("Put target creature card from a graveyard onto the battlefield under your control.",
                             "Sorcery"), [self.b.graveyard[0]])
        self.assertEqual([x.card.name for x in self.a.battlefield], [GREEN.name])
        self.assertEqual(self.a.battlefield[0].owner, self.b)

    def test_exile_and_bottom_of_library(self):
        self.b.graveyard.extend([ROCK, GREEN])
        self.cast(self.spell("Exile target artifact card from a graveyard."), [self.b.graveyard[0]])
        self.assertEqual([c.name for c in self.b.exile], [ROCK.name])
        self.cast(self.spell("Put target card from a graveyard on the bottom of its owner's library."),
                  [self.b.graveyard[0]])
        self.assertEqual((self.b.library[0].name, self.b.graveyard), (GREEN.name, []))

    def test_ai_casts_a_reanimation(self):
        self.a.graveyard.append(BEAR)
        self.b.graveyard.append(GREEN)
        spell = card("Test Spell", "{U}", "Sorcery",
                     "Return target creature card with power 2 or less from your graveyard to the battlefield.")
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertIn(BEAR.name, [x.card.name for x in self.a.battlefield])
        self.assertEqual(len(self.b.graveyard), 1)

    def test_ai_aims_by_side(self):
        self.a.graveyard.append(BEAR)
        self.b.graveyard.append(GREEN)
        for text, owner in (("Return target creature card from a graveyard to its owner's hand.", self.a),
                            ("Exile target creature card from a graveyard.", self.b)):
            eff = parse_sentence(text)[0]
            tgt = self.a.ai.choose_target(self.game, self.a, eff, self.spell(text))
            self.assertTrue(any(c is tgt for c in owner.graveyard), text)

if __name__ == "__main__":
    unittest.main()
