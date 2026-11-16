"""#646 slice 1: semicolon keyword lists, flavor-worded Equip, typecycling / double landcycling / artifact landcycling
(mtgsim.kw_lines, engine.turns.cycle_spare)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, can_block
from mtgsim.engine.policy import equip_all
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, PLAINS, SWAMP, card

POUNCER = card("Test Pouncer", "{4}{B}{R}", "Creature — Elemental",
               "Haste\nSwampcycling {2}, mountaincycling {2}", 5, 6)
STEP = card("Test Step", "{3}{U}", "Sorcery", "Return two target creatures to their owners' hands.\nWizardcycling {2}")
COMPANION = card("Test Companion", "{7}", "Artifact Creature — Salamander", "Artifact landcycling {2}", 4, 4)
WIZARD = card("Test Wizard", "{1}{U}", "Creature — Human Wizard", "", 1, 1)
SEAT = card("Test Seat", types="Artifact Land", text="{T}: Add {B}.")
LU_BU = card("Test Lu Bu", "{3}{R}{R}", "Legendary Creature — Human Soldier Warrior", "Haste; horsemanship", 4, 3)
KATANA = card("Test Katana", "{2}", "Artifact — Equipment", "Equipped creature gets +2/+2.\nMurasame — Equip {1}")


class Parsing(unittest.TestCase):
    def test_semicolon_keyword_lists(self):
        c = card("X", "{1}", "Creature — Ape", "Trample; rampage 2 (Whenever this creature becomes blocked, it gets "
                 "+2/+2 until end of turn for each creature blocking it beyond the first.)", 2, 2)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.keywords, {"trample"})
        self.assertEqual(len(c.triggers), 1)                    # rampage
        self.assertEqual(LU_BU.keywords, {"haste", "horsemanship"})

    def test_unknown_keyword_stays_ignored_on_its_own(self):
        c = card("X", "{1}", "Creature — Elephant", "Trample; banding", 3, 3)
        self.assertEqual(c.keywords, {"trample"})
        self.assertEqual(c.unsupported, ["Banding"])

    def test_sentences_with_semicolons_are_not_split(self):
        for text in ("Destroy target creature; draw a card.", "Flying; ~ can't block."):
            c = card("X", "{1}", "Creature — Bird", text, 1, 1)
            self.assertNotEqual(c.unsupported, [], text)

    def test_flavor_word_equip(self):
        self.assertEqual(KATANA.unsupported, [])
        self.assertEqual(KATANA.equip_cost, {"generic": 1})
        c = card("X", "{1}", "Artifact — Equipment", "Chaosbringer — Equip—Pay {3} or discard a card.")
        self.assertTrue(c.unsupported)                          # an "or" equip cost is still not read

    def test_cycling_specs(self):
        self.assertEqual(POUNCER.cycling, {"cost": {"generic": 2}, "land": "Swamp|Mountain"})
        self.assertEqual(STEP.cycling, {"cost": {"generic": 2}, "land": "", "type": "Wizard"})
        self.assertEqual(COMPANION.cycling, {"cost": {"generic": 2}, "land": "artifact"})

    def test_cycling_refusals(self):
        for text in ("Swampcycling {2}, mountaincycling {3}",     # different costs
                     "Affinitycycling {2}",                       # not a subtype
                     "Swampcycling {2}, swampcycling {2}",
                     "Wizardcycling {2}, swampcycling {2}"):      # a land type and a creature type
            c = card("X", "{5}", "Creature — Elemental", text, 1, 1)
            self.assertIsNone(c.cycling, text)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def cycle(self, c, library, lands=()):
        self.a.hand = [c] + [BEAR] * 7                          # a full hand: the AI cycles what it won't cast
        self.a.library = list(library)
        self.a.battlefield = [Permanent(x, self.a) for x in lands]
        self.game.cycle_spare(self.a)
        return [x.name for x in self.a.hand]

    def test_double_landcycling_fetches_the_type_we_have_fewer_of(self):
        """CR 702.29e: each typecycling ability searches for its own type; with Swamps out we take the Mountain."""
        hand = self.cycle(POUNCER, [SWAMP, ISLAND, MOUNTAIN, PLAINS], lands=[SWAMP, SWAMP])
        self.assertNotIn("Test Pouncer", hand)
        self.assertIn("Mountain", hand)
        self.assertIn("Test Pouncer", [c.name for c in self.a.graveyard])

    def test_wizardcycling_fetches_a_wizard_card(self):
        """CR 702.29e: "Wizardcycling" searches for a card with subtype Wizard, not a land."""
        hand = self.cycle(STEP, [ISLAND, BEAR, WIZARD, ISLAND], lands=[ISLAND, ISLAND])
        self.assertIn("Test Wizard", hand)
        self.assertNotIn("Test Step", hand)

    def test_artifact_landcycling_skips_basic_lands(self):
        """CR 702.29: "Artifact landcycling" searches for an artifact land card."""
        self.a.hand = [COMPANION]
        self.a.library = [ISLAND, SEAT, MOUNTAIN]
        self.a.battlefield = [Permanent(ISLAND, self.a) for _ in range(2)]
        self.game.cycle_spare(self.a)
        self.assertEqual([c.name for c in self.a.hand], ["Test Seat"])

    def test_horsemanship_from_a_semicolon_list(self):
        """CR 702.31b: a creature with horsemanship can't be blocked except by creatures with horsemanship."""
        lu = Permanent(LU_BU, self.a)
        self.assertFalse(can_block(Permanent(BEAR, self.b), lu))
        self.assertTrue(lu.has("haste"))

    def test_ai_equips_a_flavor_worded_equipment(self):
        """CR 702.6a: Equip [cost] attaches to target creature you control; the flavor word changes nothing."""
        self.game.step = "main1"
        bear = Permanent(BEAR, self.a)
        bear.sick = False
        katana = Permanent(KATANA, self.a)
        self.a.battlefield = [Permanent(MOUNTAIN, self.a), bear, katana]
        equip_all(self.game, self.a)
        self.assertIs(katana.attached_to, bear)
        self.assertEqual((bear.power, bear.toughness), (4, 4))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Abomination of Llanowar", "Aether Membrane", "Bayou Dragonfly", "Giant Solifuge",
                     "Gorilla Berserkers", "Knight of Sursi", "Lu Bu, Master-at-Arms", "Phobian Phantasm",
                     "Teeka's Dragon", "Traproot Kami", "Bard's Bow", "Dragoon's Lance", "Machinist's Arsenal",
                     "Samurai's Katana", "Igneous Pouncer", "Jhessian Zombies", "Pale Recluse", "Sanctum Plowbeast",
                     "Valley Rannet", "Step Through", "Vedalken Aethermage", "Sojourner's Companion"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))

    def test_near_misses_stay_partial(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Noble Elephant", "Bloodthorn Flail", "Sojourner's Enforcermite"):
            self.assertEqual(card_coverage(db.get(name)).status, "partial", name)


if __name__ == "__main__":
    unittest.main()
