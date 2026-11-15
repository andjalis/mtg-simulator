"""Untargeted graveyard choices in #508."""
import unittest

from mtgsim.carddb import CardDB
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card


class GraveyardReturnChoices(Base):
    def test_repeated_subtypes_choose_again_after_each_return(self):
        spell = self.spell("Return a Pirate card from your graveyard to your hand, "
                           "then do the same for Vampire, Dinosaur, and Merfolk.")
        pirate = card("Pirate", "{1}", "Creature — Pirate", "", 1, 1)
        vampire = card("Vampire", "{2}", "Creature — Vampire", "", 1, 1)
        multi = card("Multi", "{5}", "Creature — Pirate Vampire Dinosaur Merfolk", "", 1, 1)
        self.a.graveyard.extend([pirate, vampire, multi])
        self.a.ai.choose_dig = lambda game, player, pool, n: [pool[0]]
        self.cast(spell)
        self.assertEqual(len(self.a.hand), 3)
        self.assertEqual([c.name for c in self.a.graveyard], ["Test Spell"])

    def test_changeling_counts_and_mandatory_choice_cannot_be_declined(self):
        spell = self.spell("Return a Pirate card from your graveyard to your hand, then do the same for Merfolk.")
        changeling = card("Shifter", "{1}", "Creature — Shapeshifter", "Changeling", 1, 1)
        self.a.graveyard.append(changeling)
        self.a.ai.choose_dig = lambda *args: []
        self.cast(spell)
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual([c.name for c in self.a.graveyard], ["Test Spell"])

    def test_unknown_subtype_remains_unmatched(self):
        spell = card("Unknown", "{1}", "Sorcery", "Return a Pirate card from your graveyard to your hand, "
                     "then do the same for Frob and Merfolk.")
        self.assertTrue(spell.unsupported)

    def test_distinct_values_chosen_before_any_cards_move(self):
        spell = self.spell("Return any number of cards with different mana values from your graveyard to your hand.")
        cards = [card("First", "{1}", "Artifact", ""), card("Second", "{1}", "Artifact", ""),
                 card("Third", "{2}", "Artifact", ""), card("Land", "", "Land", "")]
        self.a.graveyard.extend(cards)
        sizes = []
        def choose(game, player, pool, count):
            sizes.append(len(player.graveyard))
            return [pool[0]]
        self.a.ai.choose_dig = choose
        self.cast(spell)
        self.assertEqual(sizes, [4, 4, 4])
        self.assertEqual(sorted(c.cmc for c in self.a.hand), [0, 1, 2])

    def test_distinct_values_can_choose_none(self):
        spell = self.spell("Return any number of cards with different mana values from your graveyard to your hand.")
        self.a.graveyard.append(card("First", "{1}", "Artifact", ""))
        self.a.ai.choose_dig = lambda *args: []
        self.cast(spell)
        self.assertFalse(self.a.hand)

    def test_spell_places_itself_on_library_bottom(self):
        spell = self.spell("Return any number of cards with different mana values from your graveyard to your hand. "
                           "Put ~ on the bottom of its owner's library.", types="Sorcery")
        self.a.graveyard.append(card("First", "{1}", "Artifact", ""))
        self.cast(spell)
        self.assertEqual(self.a.library[0].name, "Test Spell")
        self.assertFalse(any(c.name == "Test Spell" for c in self.a.graveyard))

    def test_copy_does_not_put_original_in_library(self):
        from mtgsim.engine import StackItem
        spell = self.spell("Put ~ on the bottom of its owner's library.", types="Sorcery")
        original_bottom = self.a.library[0]
        item = StackItem(self.a, spell.spell_effects, [None], card=spell, kind="copy")
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertIs(self.a.library[0], original_bottom)
        self.assertFalse(any(c.name == "Test Spell" for c in self.a.graveyard))

    @unittest.skipUnless(DB_FILE.exists(), "offline card database missing")
    def test_database_cards_are_full(self):
        db = CardDB(DB_FILE)
        for name in ("Grim Captain's Call", "Seasons Past"):
            with self.subTest(name=name):
                self.assertEqual(db.get(name).unsupported, [])


if __name__ == "__main__":
    unittest.main()
