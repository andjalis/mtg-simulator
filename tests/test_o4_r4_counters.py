"""O4 round 4: Corpse Appraiser targeting, hone counters, Ajani's token, Interceptor, team keywords, coven, base P/T."""
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import StackItem
from tests.test_templates import BEAR, DRAGON3, ISLAND, PLAINS, SHOCK, Base, card

DB = CardDB()
MOON = DB.get("Moonshadow")
APPRAISER = card("Test Appraiser", "{2}{B}", "Creature — Vampire", "When this creature enters, exile up to one target "
                 "creature card from a graveyard. If a card is put into exile this way, look at the top three cards of "
                 "your library, then put one of those cards into your hand and the rest into your graveyard.", 2, 2)
DWALIN = card("Test Dwalin", "{2}{R}", "Legendary Creature — Dwarf", "First strike\nWhenever Test Dwalin enters or attacks, "
              "put a hone counter on each Equipment you control. (Each hone counter on an Equipment grants +1/+0 to "
              "equipped creature.)", 2, 2)
BLADE = card("Test Blade", "{1}", "Artifact — Equipment", "Equipped creature gets +1/+1.\nEquip {1}")
AJANI = card("Test Ajani", "{3}{W}", "Legendary Planeswalker — Ajani", "0: You gain 1 life.\n−4: Create a 2/2 white Cat "
             "Soldier creature token named Ajani's Pridemate with \"Whenever you gain life, put a +1/+1 counter on this "
             "token.\"\n−10: You get an emblem with \"Creatures you control get +2/+2.\"", cmc=4)
INTERCEPTOR = card("Test Interceptor", "{1}{U}{U}", "Creature — Bird", "Flash\nLifelink\nWhen this creature enters, it "
                   "connives. When it connives this way, return up to one target spell to its owner's hand.", 2, 2)
ARDYN = card("Test Ardyn", "{4}{B}{B}", "Legendary Creature — Elf Noble", "Demons you control have menace, lifelink, and "
             "haste.", 4, 4)
DEMON = card("Test Demon", "{3}{B}", "Creature — Demon", "", 3, 3)
FARMHAND = card("Test Farmhand", "{1}{W}", "Creature — Human Peasant", "Coven — {1}{W}{W}: Transform this creature. "
                "Activate only if you control three or more creatures with different powers.", 1, 1)
IDENTITY = card("Test Identity", "{1}{W}", "Instant", "Choose one —\n• Conceal — Until end of turn, target creature you "
                "control becomes a Citizen with base power and toughness 1/1 and gains hexproof.\n• Reveal — Until end "
                "of turn, target creature you control becomes a Hero with base power and toughness 3/4 and gains flying "
                "and vigilance.")
# Not matched: other conditions and keywords.
NOT_COVEN = card("Test Plain Transformer", "{1}{W}", "Creature — Human", "{1}{W}{W}: Transform this creature. Activate only "
                 "if you control a Human.", 1, 1)
SINGLE_KW = card("Test Other", "{4}", "Creature — Elf", "Demons you control have first strike and a bad ability.", 1, 1)


def p1(perm):
    return perm.counters.get("+1/+1", 0)


class Parsing(Base):
    def test_templates(self):
        for c in (APPRAISER, DWALIN, INTERCEPTOR, ARDYN, FARMHAND):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(APPRAISER.etb_effects[0].target, "graveyard_creature_any")
        self.assertEqual(len(AJANI.unsupported), 1)                    # the emblem stays unsupported
        self.assertEqual(sorted(k for _, k, _ in ARDYN.keyword_sub), ["haste", "lifelink", "menace"])

    def test_unsupported_shapes_stay_unsupported(self):
        for c in (NOT_COVEN, SINGLE_KW):
            with self.subTest(card=c.name):
                self.assertTrue(c.unsupported)

    def test_identity_is_flagged_as_simplified(self):
        self.assertEqual(IDENTITY.unsupported, [])
        self.assertEqual(len(IDENTITY.approximations), 2)
        self.assertEqual({e.kind for m in IDENTITY.modes for e in m}, {"become_base"})

    def test_real_cards(self):
        db = CardDB(offline=True)
        if db.lookup("Secret Identity") is None:
            self.skipTest("card database not built")
        for name in ("Dwalin, Weaponmaster", "Obscura Interceptor", "Ambitious Farmhand", "Secret Identity"):
            with self.subTest(card=name):
                self.assertEqual(db.get(name).unsupported, [])
        self.assertEqual(len(db.get("Ajani Resolute").unsupported), 1)
        self.assertEqual(len(db.get("Ardyn, the Usurper").unsupported), 1)    # Starscourge only
        self.assertEqual(db.get("Corpse Appraiser").unsupported, [])


class AppraiserTargeting(Base):
    def enter(self):
        self.game.enter_battlefield(self.a, APPRAISER)
        self.game.flush_triggers()
        return self.game.stack[-1]

    def test_graveyard_card_is_targeted_when_the_trigger_goes_on_the_stack(self):
        self.b.graveyard.append(DRAGON3)
        self.a.graveyard.append(BEAR)
        item = self.enter()
        self.assertEqual([t.name for t in item.targets], ["Big Dragon"])     # an opposing card first
        self.assertEqual(len(item.graveyard_targets), 1)

    def test_target_gone_on_resolution_exiles_and_digs_nothing(self):
        self.b.graveyard.append(DRAGON3)
        self.a.library = [ISLAND, ISLAND, BEAR, BEAR]
        item = self.enter()
        target = item.targets[0]
        self.game.move_card(target, self.b.graveyard, self.b.exile)             # exiled in response ...
        self.game.move_card(target, self.b.exile, self.b.graveyard)             # ... and back: a new object
        self.game.resolve_top()
        self.assertEqual((len(self.a.hand), len(self.a.library), len(self.b.exile)), (0, 4, 0))

    def test_no_creature_card_means_no_target_and_no_dig(self):
        self.a.library = [ISLAND] * 4
        self.game.enter_battlefield(self.a, APPRAISER)
        self.game.settle()
        self.assertEqual((len(self.a.hand), len(self.a.library)), (0, 4))

    def test_resolution_exiles_the_card_and_digs(self):
        self.b.graveyard.append(DRAGON3)
        self.a.library = [ISLAND, BEAR, DRAGON3, ISLAND]
        self.enter()
        self.game.resolve_top()
        self.assertEqual((len(self.b.graveyard), len(self.b.exile), len(self.a.hand)), (0, 1, 1))
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertEqual(len(self.a.library), 1)

    def test_moonshadow_loses_a_counter_when_permanent_cards_are_binned(self):
        moon = self.game.enter_battlefield(self.a, MOON)
        self.b.graveyard.append(DRAGON3)
        self.a.library = [ISLAND, BEAR, BEAR, DRAGON3]       # top three: Dragon, Bear, Bear
        self.enter()
        self.game.resolve_top()
        self.game.settle()
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertEqual(moon.m1, 5)                          # one batch of permanent cards: one counter


class Interactions(Base):
    def test_dwalin_hones_equipment_on_enter_and_attack(self):
        blade = self.perm(BLADE, self.a)
        bear = self.perm(BEAR, self.a)
        blade.attached_to = bear
        self.assertEqual(bear.power, 3)
        dwalin = self.game.enter_battlefield(self.a, DWALIN)
        self.game.settle()
        self.assertEqual((blade.counters.get("hone"), bear.power, bear.toughness), (1, 4, 3))
        self.game.fire(self.a, "attacks", dwalin)
        self.game.settle()
        self.assertEqual((blade.counters.get("hone"), bear.power), (2, 5))

    def test_dwalin_ignores_other_artifacts_and_opposing_equipment(self):
        theirs = self.perm(BLADE, self.b)
        rock = self.perm(card("Rock", "{1}", "Artifact", ""), self.a)
        self.game.enter_battlefield(self.a, DWALIN)
        self.game.settle()
        self.assertEqual((theirs.counters.get("hone"), rock.counters.get("hone")), (None, None))

    def test_ajani_token_grows_whenever_you_gain_life(self):
        ajani = self.perm(AJANI, self.a)
        ajani.counters["loyalty"] = 5
        self.assertTrue(self.game.activate_loyalty(self.a, ajani, 1))
        self.game.settle()
        cat = next(x for x in self.a.creatures if "Cat" in x.card.subtypes)
        self.assertEqual((cat.power, cat.toughness), (2, 2))
        self.game.change_life(self.a, 3, "test")
        self.game.settle()
        self.assertEqual(p1(cat), 1)
        self.game.change_life(self.b, 3, "test")
        self.game.settle()
        self.assertEqual(p1(cat), 1)

    def test_interceptor_connives_then_returns_a_spell(self):
        self.a.library = [BEAR] * 5
        self.a.hand = [ISLAND]
        spell = StackItem(self.b, SHOCK.spell_effects, [self.a], card=SHOCK, kind="spell")
        self.game.stack.append(spell)
        self.game.enter_battlefield(self.a, INTERCEPTOR)
        self.game.flush_triggers()
        self.game.resolve_top()                                   # the enters trigger: connive
        self.game.flush_triggers()
        self.assertEqual(len(self.a.hand), 1)                     # drew a card, discarded a card
        self.assertEqual(self.game.stack[-1].effects[0].kind, "bounce_spell")      # the reflexive trigger
        self.game.resolve_top()
        self.assertNotIn(spell, self.game.stack)
        self.assertIn(SHOCK, self.b.hand)

    def test_interceptor_without_a_spell_just_connives(self):
        self.a.library = [BEAR] * 5
        self.a.hand = [ISLAND]
        self.game.enter_battlefield(self.a, INTERCEPTOR)
        self.game.flush_triggers()
        self.game.resolve_top()
        self.assertEqual(self.game.stack, [])
        self.assertEqual(len(self.a.hand), 1)

    def test_ardyn_grants_keywords_to_demons_only(self):
        self.perm(ARDYN, self.a)
        mine, other = self.perm(DEMON, self.a), self.perm(BEAR, self.a)
        theirs = self.perm(DEMON, self.b)
        self.assertEqual([mine.has(k) for k in ("menace", "lifelink", "haste")], [True] * 3)
        self.assertEqual([other.has(k) for k in ("menace", "lifelink", "haste")], [False] * 3)
        self.assertEqual([theirs.has(k) for k in ("menace", "lifelink", "haste")], [False] * 3)

    def test_coven_needs_three_different_powers(self):
        farmhand = self.perm(FARMHAND, self.a)
        for _ in range(3):
            self.perm(PLAINS, self.a)
        self.perm(BEAR, self.a)                                    # powers 1, 2
        self.assertFalse(self.game.can_activate(self.a, farmhand, 0))
        self.perm(BEAR, self.a)                                    # still 1, 2
        self.assertFalse(self.game.can_activate(self.a, farmhand, 0))
        self.perm(DRAGON3, self.a)                                 # 1, 2, 3
        self.assertTrue(self.game.can_activate(self.a, farmhand, 0))

    def test_identity_sets_base_power_and_toughness_and_keywords_until_end_of_turn(self):
        bear = self.perm(BEAR, self.a)
        bear.counters["+1/+1"] = 1
        reveal = IDENTITY.modes[1][0]
        self.game.resolve(self.a, reveal, bear)
        self.assertEqual((bear.power, bear.toughness), (4, 5))     # base 3/4 plus the counter
        self.assertTrue(bear.has("flying") and bear.has("vigilance"))
        self.game.expire_continuous_effects()
        self.assertEqual((bear.power, bear.toughness), (3, 3))
        self.assertFalse(bear.has("flying"))

    def test_identity_conceal_gives_hexproof(self):
        dragon = self.perm(DRAGON3, self.a)
        self.game.resolve(self.a, IDENTITY.modes[0][0], dragon)
        self.assertEqual((dragon.power, dragon.toughness, dragon.has("hexproof")), (1, 1, True))


if __name__ == "__main__":
    unittest.main()
