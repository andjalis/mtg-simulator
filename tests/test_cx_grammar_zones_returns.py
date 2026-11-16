"""Qualified graveyard returns (#328): named entry counters, legendary/nonlegendary/historic and keyword card
nouns, and "For each color, return up to one target card of that color"."""
import dataclasses
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cx_grammar import parse_sentence
from mtgsim.cx_grammar_zones import card_fits, card_noun, entry_counters

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, card

LEGEND = dataclasses.replace(card("Test Legend", "{2}{B}", "Legendary Creature — Human", "", 3, 3), legendary=True)
INFECT = card("Test Infect", "{1}{B}", "Creature — Horror", "Infect", 2, 2)
WHITE = card("Test White", "{W}", "Creature — Human", "", 1, 1)
AZORIUS = card("Test Azorius", "{W}{U}", "Creature — Human", "", 2, 2)
RED = card("Test Red", "{R}", "Instant", "")
ETB = card("Test Etb", "{2}", "Creature — Goblin", "When ~ enters, you gain 2 life.", 2, 2)


class Parsing(unittest.TestCase):
    def test_entry_counters(self):
        self.assertEqual(entry_counters(" with a finality counter on it"), {"finality": 1})
        self.assertEqual(entry_counters(" with a hexproof counter and an indestructible counter on it"),
                         {"hexproof": 1, "indestructible": 1})
        self.assertEqual(entry_counters(" with two +1/+1 counters on it"), {"+1/+1": 2})
        for text in (" with a shield counter on it", " with a lore counter on it", " with x +1/+1 counters on it",
                     " with a flying counter and a flying counter on it"):
            self.assertIsNone(entry_counters(text), text)

    def test_card_nouns(self):
        self.assertEqual(card_noun("nonlegendary creature card"), {"types": ["creature"], "legend": "nonlegendary"})
        self.assertEqual(card_noun("creature card with infect"), {"types": ["creature"], "keyword": "infect"})
        self.assertEqual(card_noun("historic card")["legend"], "historic")
        for text in ("creature card with landfall", "creature card with a cycling ability", "legendary nonlegendary card"):
            self.assertIsNone(card_noun(text), text)
        self.assertFalse(card_fits(LEGEND, card_noun("nonlegendary creature card")))
        self.assertTrue(card_fits(LEGEND, card_noun("legendary creature card")))
        self.assertTrue(card_fits(INFECT, card_noun("creature card with infect")))
        self.assertFalse(card_fits(BEAR, card_noun("creature card with infect")))

    def test_sentences(self):
        effs = parse_sentence("Return target permanent card from your graveyard to the battlefield with a hexproof "
                              "counter and an indestructible counter on it.")
        self.assertEqual([(e.kind, e.data["counters"]) for e in effs],
                         [("cx_card_move", {"hexproof": 1, "indestructible": 1})])
        effs = parse_sentence("For each color, return up to one target card of that color from your graveyard to "
                              "your hand.")
        self.assertEqual([e.data["cx_card"]["color"] for e in effs], ["white", "blue", "black", "red", "green"])
        self.assertTrue(all(e.data["optional_target"] and e.data["distinct"] for e in effs))
        for text in ("Return target creature card from your graveyard to your hand with a finality counter on it.",
                     "Return target creature card from your graveyard to the battlefield with a shield counter on it.",
                     "Return target creature card from a graveyard to the battlefield with a finality counter on it.",
                     "For each color, return up to one target card of that color from a graveyard to your hand.",
                     "For each color, return target card of that color from your graveyard to your hand.",
                     "For each opponent, return up to one target card of that color from your graveyard to your hand."):
            self.assertIsNone(parse_sentence(text), text)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        db = CardDB(offline=True)
        for name in ("Persist", "Perennation", "Unbreakable Bond", "Corpse Cur", "All Suns' Dawn", "Rogues' Gallery",
                     "Grim Reaper, Lethal Legionnaire", "Metamorphosis Fanatic"):
            with self.subTest(name=name):
                self.assertEqual(db.get(name).unsupported, [])
        # "power less than ~'s" (no stat named after the possessive) stays visible
        self.assertTrue(db.get("Mirko, Obsessive Theorist").unsupported)


class Resolving(Base):
    def test_persist_returns_a_nonlegendary_creature_with_a_counter(self):
        spell = self.spell("Return target nonlegendary creature card from your graveyard to the battlefield with a "
                           "-1/-1 counter on it.", "Sorcery")
        self.a.graveyard.extend([LEGEND, ETB])
        eff = spell.spell_effects[0]
        self.assertEqual([c.name for c in self.game.legal_targets(self.a, eff)], [ETB.name])
        life = self.a.life
        self.cast(spell, [self.a.graveyard[1]])
        self.game.settle()
        back = [x for x in self.a.battlefield if x.card.name == ETB.name]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].counters.get("-1/-1"), 1)
        self.assertEqual(self.a.life, life + 2)        # a new object: its enters ability triggers
        self.assertEqual([c.name for c in self.a.graveyard if c.name != "Test Spell"], [LEGEND.name])

    def test_keyword_counters_grant_keywords(self):
        spell = self.spell("Return target permanent card from your graveyard to the battlefield with a hexproof "
                           "counter and an indestructible counter on it.", "Sorcery")
        self.a.graveyard.append(BEAR)
        self.cast(spell, [self.a.graveyard[0]])
        bear = self.a.battlefield[0]
        self.assertTrue(bear.has("hexproof") and bear.has("indestructible"))

    def test_finality_counter_exiles_it_when_it_would_die(self):
        spell = self.spell("Return target creature card from your graveyard to the battlefield with a finality "
                           "counter on it.", "Sorcery")
        self.a.graveyard.append(BEAR)
        self.cast(spell, [self.a.graveyard[0]])
        bear = self.a.battlefield[0]
        self.game.destroy(bear) if hasattr(self.game, "destroy") else self.game.leave_battlefield(bear, "graveyard")
        self.game.settle()
        self.assertEqual(([c.name for c in self.a.exile], [c for c in self.a.graveyard if c.name != "Test Spell"]),
                         ([BEAR.name], []))

    def test_each_color_one_card_per_color_never_twice(self):
        spell = self.spell("For each color, return up to one target card of that color from your graveyard to your "
                           "hand.", "Sorcery")
        self.a.graveyard.extend([WHITE, AZORIUS, RED, BEAR])
        effs = spell.spell_effects
        white_legal = [c.name for c in self.game.legal_targets(self.a, effs[0])]
        self.assertEqual(sorted(white_legal), sorted([WHITE.name, AZORIUS.name]))
        targets = [self.a.graveyard[0], self.a.graveyard[1], None, self.a.graveyard[2], None]
        self.cast(spell, targets)
        self.assertEqual(sorted(c.name for c in self.a.hand), sorted([WHITE.name, AZORIUS.name, RED.name]))
        self.assertEqual([c.name for c in self.a.graveyard if c.name != "Test Spell"], [BEAR.name])

    def test_each_color_ai_targets_are_distinct(self):
        spell = self.spell("For each color, return up to one target card of that color from your graveyard to your "
                           "hand.", "Sorcery")
        self.a.graveyard.extend([AZORIUS, RED])
        with self.game.targeting(spell):
            targets = self.game.auto_targets(self.a, spell.spell_effects)
        chosen = [t for t in targets if t is not None]
        self.assertEqual(len(chosen), len({id(t) for t in chosen}))
        self.assertEqual(sorted(c.name for c in chosen), sorted([AZORIUS.name, RED.name]))

    def test_ai_reanimates_with_persist(self):
        spell = card("Test Persist", "{B}", "Sorcery", "Return target nonlegendary creature card from your graveyard "
                     "to the battlefield with a -1/-1 counter on it.")
        from tests.test_templates import ISLAND
        swamp = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
        self.perm(swamp, self.a)
        self.a.graveyard.extend([LEGEND, ETB])
        self.b.graveyard.append(BEAR)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual([x.card.name for x in self.a.battlefield if x.is_creature], [ETB.name])
        self.assertIsNotNone(ISLAND)



@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class LesserThanTheEventCreature(Base):
    """"with lesser mana value / toughness": than the creature the trigger is about, fixed as it queues (LKI)."""
    def setUp(self):
        super().setUp()
        self.db = CardDB(offline=True)

    def real(self, name, owner):
        return self.perm(self.db.get(name), owner)

    def test_havi_returns_a_smaller_legend_tapped_also_on_its_own_death(self):
        for own in (False, True):
            with self.subTest(own=own):
                self.setUp()
                havi = self.real("Havi, the All-Father", self.a)
                kaalia = self.real("Kaalia of the Vast", self.a)        # mana value 4
                self.a.graveyard.extend([self.db.get("Isamaru, Hound of Konda"), self.db.get("Grizzly Bears"),
                                         self.db.get("Avacyn, Angel of Hope")])
                self.game.dies(havi if own else kaalia)
                self.game.settle()
                isamaru = [x for x in self.a.battlefield if x.card.name == "Isamaru, Hound of Konda"]
                self.assertEqual(len(isamaru), 1)
                self.assertTrue(isamaru[0].tapped)
                self.assertNotIn("Avacyn, Angel of Hope", [x.card.name for x in self.a.battlefield])

    def test_havi_ignores_a_nonlegendary_death(self):
        self.real("Havi, the All-Father", self.a)
        bear = self.perm(BEAR, self.a)
        self.a.graveyard.append(self.db.get("Isamaru, Hound of Konda"))
        self.game.dies(bear)
        self.game.settle()
        self.assertEqual(len(self.a.graveyard), 2)

    def test_colfenor_lesser_toughness_to_hand(self):
        self.real("Colfenor, the Last Yew", self.a)
        mid = self.perm(card("Test Mid", "{3}", "Creature — Elf", "", 3, 3), self.a)
        small, big = card("Test Small", "{1}", "Creature — Elf", "", 2, 2), card("Test Big", "{6}", "Creature — Giant",
                                                                                  "", 6, 6)
        self.a.graveyard.extend([small, big])
        self.game.dies(mid)
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Test Small"])

    def test_riveteers_reads_the_sacrificed_creature(self):
        self.real("Riveteers Ascendancy", self.a)
        mid = self.perm(card("Test Mid", "{3}", "Creature — Elf", "", 3, 3), self.a)
        self.a.graveyard.extend([card("Test Two", "{2}", "Creature — Elf", "", 2, 2),
                                 card("Test Three", "{3}", "Creature — Elf", "", 1, 1)])
        self.game.sacrifice(mid)
        self.game.settle()
        back = [x for x in self.a.battlefield if x.card.name == "Test Two"]
        self.assertEqual(len(back), 1)
        self.assertTrue(back[0].tapped)

    def test_no_event_creature_nothing_qualifies(self):
        spell = self.spell("Return target creature card with lesser mana value from your graveyard to your hand.")
        self.a.graveyard.append(BEAR)
        self.assertEqual(self.game.legal_targets(self.a, spell.spell_effects[0]), [])

    def test_copies_fits_reads_legendary_words(self):
        from mtgsim import copies
        self.assertTrue(copies.fits(LEGEND, "legendary creature"))
        self.assertFalse(copies.fits(LEGEND, "nonlegendary creature"))
        self.assertTrue(copies.fits(BEAR, "nonlegendary creature"))
        self.assertFalse(copies.fits(BEAR, "legendary creature"))



AURA = card("Test Aura", "{1}{W}", "Enchantment — Aura", "Enchant creature")
CLERIC = card("Test Cleric", "{1}{W}", "Creature — Human Cleric", "", 1, 1)
SHAPE = card("Test Shape", "{3}{U}", "Creature — Shapeshifter", "Changeling", 2, 2)


class SubtypesAndRandom(Base):
    def test_subtype_nouns(self):
        self.assertEqual(card_noun("Aura or Equipment card"), {"types": [], "subtypes": ["Aura", "Equipment"]})
        self.assertEqual(card_noun("Bird and/or Cleric permanent cards"),
                         {"types": ["permanent"], "subtypes": ["Bird", "Cleric"]})
        for text in ("card named Bob", "Cleric card named ~", "cleric card"):
            self.assertIsNone(card_noun(text), text)
        self.assertTrue(card_fits(CLERIC, card_noun("Cleric card")))
        self.assertFalse(card_fits(BEAR, card_noun("Cleric card")))
        self.assertTrue(card_fits(SHAPE, card_noun("Cleric card")))           # changeling: every creature type
        self.assertFalse(card_fits(SHAPE, card_noun("Aura card")))            # ... but not Aura
        self.assertTrue(card_fits(AURA, card_noun("Aura or Equipment card")))

    def test_return_a_subtype_card(self):
        text = "Return target Aura or Equipment card from your graveyard to your hand."
        # (a card with this text alone still parses through the older untargeted gy_move template first)
        spell = dataclasses.replace(card("Test Spell", "{1}", "Instant", ""), spell_effects=parse_sentence(text))
        self.a.graveyard.extend([BEAR, AURA])
        self.assertEqual([c.name for c in self.game.legal_targets(self.a, spell.spell_effects[0])], [AURA.name])
        self.cast(spell, [self.a.graveyard[1]])
        self.assertEqual([c.name for c in self.a.hand], [AURA.name])

    def test_at_random(self):
        effs = parse_sentence("Return two cards at random from your graveyard to your hand.")
        self.assertIsNotNone(effs)
        self.assertIsNone(parse_sentence("Return up to two cards at random from your graveyard to your hand."))
        spell = self.spell("Return two creature cards at random from your graveyard to your hand.", "Sorcery")
        self.a.graveyard.extend([BEAR, CLERIC, SHAPE, AURA])
        self.cast(spell)
        self.assertEqual(len(self.a.hand), 2)
        self.assertTrue(all(c.is_creature for c in self.a.hand))
        self.assertIn(AURA.name, [c.name for c in self.a.graveyard])
        seen = set()
        for seed in range(12):          # random: different seeds take different cards
            self.setUp()
            self.game.rng.seed(seed)
            self.a.graveyard.extend([BEAR, CLERIC, SHAPE])
            self.cast(spell)
            seen.add(tuple(sorted(c.name for c in self.a.hand)))
        self.assertGreater(len(seen), 1)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards(self):
        db = CardDB(offline=True)
        for name in ("Make a Wish", "Orah, Skyclave Hierophant"):
            self.assertEqual(db.get(name).unsupported, [], name)


if __name__ == "__main__":
    unittest.main()
