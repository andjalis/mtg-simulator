"""Targeted graveyard returns and reanimation: targets chosen on cast/activation/trigger, rechecked on
resolution without retargeting, exact graveyard entries for shared CardDefs."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, GraveyardTarget, Permanent, Player

from tests.test_templates import ISLAND, MOUNTAIN, card

RAISE = card("Test Raise", "{R}", "Instant", "Return target creature card from your graveyard to your hand.")
REANIMATE = card("Test Reanimate", "{R}", "Instant",
                 "Return target creature card from your graveyard to the battlefield.")
REGROW_ANY = card("Test Regrowth", "{R}", "Instant", "Return target card from your graveyard to your hand.")
REGROW_PERM = card("Test Recover", "{R}", "Instant",
                   "Return up to one target permanent card from your graveyard to your hand.")
TWO_UPTO = card("Test Recall", "{R}", "Instant",
                "Return up to two target creature cards from your graveyard to your hand.")
TWO = card("Test Pair Raise", "{R}", "Instant", "Return two target creature cards from your graveyard to your hand.")
SMALL = card("Test Small Reanimate", "{R}", "Instant",
             "Return target creature card with mana value 2 or less from your graveyard to the battlefield.")
X_REANIMATE = card("Test X Reanimate", "{X}{R}", "Sorcery",
                   "Return target creature card with mana value X or less from your graveyard to the battlefield.")
THIEF = card("Test Grave Thief", "{R}", "Instant", "Return target creature card from an opponent's graveyard to "
             "the battlefield under your control.")
ANY_GY = card("Test Any Grave", "{R}", "Instant",
              "Return target creature card from a graveyard to the battlefield under your control.")
NONLEG = card("Test Nonlegend Reanimate", "{R}", "Instant",
              "Return target nonlegendary creature card from your graveyard to the battlefield.")
PERM_HAND = card("Test Permanent Raise", "{R}", "Instant",
                 "Return target permanent card from your graveyard to your hand.")
X_COUNT = card("Test X Recall", "{X}{R}", "Sorcery", "Return X target creature cards from your graveyard to your hand.")
SHOCK_RECOVER = card("Test Shock Recover", "{R}", "Instant", "Test Shock Recover deals 2 damage to target creature. "
                     "Return up to one target permanent card from your graveyard to your hand. Draw a card.")
HASTE_RAISE = card("Test Haste Raise", "{R}", "Instant", "Return target creature card from your graveyard to the "
                   "battlefield. It gains haste until end of turn.")
COUNTER_RAISE = card("Test Counter Raise", "{R}", "Instant", "Return target creature card from your graveyard to "
                     "the battlefield. Put a +1/+1 counter on it.")
LEGEND_RAISE = card("Test Legend Raise", "{R}", "Instant",
                    "Return target legendary creature card from your graveyard to your hand.")
SOL_RING = card("Test Sol Ring", "{1}", "Artifact", "{T}: Add {C}{C}.")
UNTARGETED = card("Test Dig Up", "{R}", "Instant", "Return a creature card from your graveyard to your hand.")
DIGGER = card("Test Gravedigger", "{R}", "Creature — Zombie",
              "When this creature enters, return target creature card from your graveyard to your hand.", 1, 1)
MOURNER = card("Test Mourner", "{R}", "Creature — Zombie",
               "When this creature dies, return target creature card from your graveyard to your hand.", 1, 1)
SHOVEL = card("Test Shovel Lich", "{R}", "Creature — Zombie",
              "{T}: Return target creature card from your graveyard to your hand.", 1, 1)
COMMAND = card("Test Command", "{R}", "Instant", "Choose one —\n• Return target creature card from your graveyard "
               "to your hand.\n• Draw a card.")
SELF_REGROW = card("Test Echo Regrowth", "{R}", "Instant",
                   "Return target card from your graveyard to your hand.\nFlashback {R}")
RESTORE = card("Test Restoration", "{R}", "Enchantment — Saga",
               "(As this Saga enters and after your draw step, add a lore counter.)\nI — You may discard a card. "
               "When you do, return target permanent card with mana value 2 or less from your graveyard to the "
               "battlefield tapped.\nII — Draw a card.")
LAST_RAISE = card("Test Last Raise", "{R}", "Enchantment — Saga",
                  "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after I.)\n"
                  "I — Return target creature card from your graveyard to your hand.")

BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
LEGEND = card("Test Legend", "{1}{W}", "Legendary Creature — Human", "", 2, 2)
ROCK = card("Test Rock", "{1}", "Artifact", "")
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
SPELLS = (RAISE, REANIMATE, REGROW_ANY, REGROW_PERM, TWO_UPTO, TWO, SMALL, X_REANIMATE, THIEF, ANY_GY, NONLEG,
          PERM_HAND, UNTARGETED, COMMAND, X_COUNT, SHOCK_RECOVER,
          HASTE_RAISE, COUNTER_RAISE, LEGEND_RAISE)


def card_of(t):
    return getattr(t, "card", t)


def flat(targets):
    out = []
    for t in targets:
        out += list(t) if isinstance(t, tuple) else [t]
    return [card_of(t) for t in out if t is not None]


class GraveyardReturnTargets(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 20, HeuristicAI())
        self.b = Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for pl in (self.a, self.b):
            pl.library = [ISLAND] * 20
        self.seen = []

    def lands(self, n=1):
        for _ in range(n):
            self.a.battlefield.append(Permanent(MOUNTAIN, self.a))

    def ready(self, spell, *graveyard, lands=1):
        self.a.graveyard.extend(graveyard)
        self.lands(lands)
        self.a.hand = [spell]

    def gy(self):
        """a's graveyard without the resolved spell itself."""
        return [c for c in self.a.graveyard if c not in SPELLS]

    def on_bf(self, c, who=None):
        return [x for x in (who or self.a).battlefield if x.card is c]

    def respond_once(self, response=None, when=None):
        """b answers the first stack item matching ``when``: ``response(item)`` runs as a side effect."""
        def respond(game, me):
            if game.stack and not self.seen and (when is None or when(game.stack[-1])):
                item = game.stack[-1]
                self.seen.append((item, list(item.targets)))
                if response:
                    response(item)
            return None
        self.b.ai.respond = respond

    def remove_slot(self, slot, gy=None):
        """A response that exiles the graveyard card in one exact slot."""
        def go(item):
            zone = gy if gy is not None else self.a.graveyard
            self.a.exile.append(zone.pop(slot))
        return go

    def remove_bound(self, item):
        """A response that exiles every graveyard card the item targets."""
        for t in item.targets:
            for g in (t if isinstance(t, tuple) else (t,)):
                if isinstance(g, GraveyardTarget) and g.index() is not None:
                    self.a.exile.append(g.controller.graveyard.pop(g.index()))

    def fizzled(self):
        return any("fizzles" in line for line in self.game.events)

    # ------------------------------------------------------------------ templates
    def test_targeted_templates_are_supported_and_targeted(self):
        for c in (RAISE, REANIMATE, REGROW_ANY, REGROW_PERM, TWO_UPTO, TWO, SMALL, X_REANIMATE, THIEF, ANY_GY,
                  NONLEG, PERM_HAND, DIGGER, MOURNER, SHOVEL, COMMAND):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
                effects = (c.spell_effects + [e for t in c.triggers for e in t.effects]
                           + [e for a in c.activated for e in a.effects] + [e for m in c.modes for e in m])
                self.assertTrue(any(e.target == "graveyard_card" for e in effects), effects)

    def test_untargeted_templates_stay_untargeted(self):
        self.assertEqual(UNTARGETED.unsupported, [])
        self.assertFalse(any(e.target == "graveyard_card" for e in UNTARGETED.spell_effects))

    # ------------------------------------------------------------------ cast time
    def test_target_is_bound_when_cast(self):
        for spell, dest in ((RAISE, "hand"), (REANIMATE, "bf"), (REGROW_ANY, "hand")):
            with self.subTest(spell=spell.name):
                self.setUp()
                self.ready(spell, ELF, OGRE)
                self.respond_once(when=lambda item: item.card is spell)
                self.assertTrue(self.game.cast(self.a, spell, [ELF]))     # not the highest mana value
                self.assertEqual(flat(self.seen[0][1]), [ELF])
                self.assertIn(OGRE, self.a.graveyard)
                if dest == "hand":
                    self.assertEqual(self.a.hand, [ELF])
                else:
                    self.assertEqual(len(self.on_bf(ELF)), 1)

    def test_auto_target_is_bound_before_resolution(self):
        self.ready(RAISE, ELF, OGRE)
        self.respond_once(when=lambda item: item.card is RAISE)
        self.assertTrue(self.game.cast(self.a, RAISE))
        self.assertTrue(all(isinstance(t, GraveyardTarget) for t in self.seen[0][1] if t is not None))
        self.assertEqual(len(flat(self.seen[0][1])), 1)

    def test_no_legal_target_means_no_cast_and_no_payment(self):
        for spell in (RAISE, REANIMATE, TWO, SMALL, NONLEG):
            with self.subTest(spell=spell.name):
                self.setUp()
                self.ready(spell, BOLT, ISLAND)
                self.assertFalse(self.game.can_cast_now(self.a, spell))
                self.assertFalse(self.game.cast(self.a, spell))
                self.assertEqual(self.a.hand, [spell])
                self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_explicit_illegal_targets_are_rejected_before_costs(self):
        cases = [
            (RAISE, [BOLT], "wrong card type"),
            (RAISE, [OGRE], "not in the graveyard"),
            (SMALL, [OGRE], "mana value too high"),
            (NONLEG, [LEGEND], "legendary"),
            (PERM_HAND, [BOLT], "not a permanent card"),
            (REANIMATE, [ROCK], "not a creature"),
        ]
        for spell, targets, why in cases:
            with self.subTest(why=why):
                self.setUp()
                self.ready(spell, BEAR, BOLT, LEGEND, ROCK)
                if why == "not in the graveyard":
                    self.a.graveyard.remove(BEAR)
                self.assertFalse(self.game.cast(self.a, spell, targets))
                self.assertEqual(self.a.hand, [spell])
                self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_permanent_and_nonlegendary_filters(self):
        self.ready(PERM_HAND, BOLT, ROCK)
        effect = PERM_HAND.spell_effects[0]
        self.assertEqual([card_of(t) for t in self.game.legal_targets(self.a, effect)], [ROCK])
        self.setUp()
        self.ready(NONLEG, LEGEND, BEAR)
        effect = NONLEG.spell_effects[0]
        self.assertEqual([card_of(t) for t in self.game.legal_targets(self.a, effect)], [BEAR])
        self.assertTrue(self.game.cast(self.a, NONLEG))
        self.assertEqual((len(self.on_bf(BEAR)), self.on_bf(LEGEND)), (1, []))

    def test_positive_legendary_filter(self):
        self.ready(LEGEND_RAISE, LEGEND, BEAR)
        effect = LEGEND_RAISE.spell_effects[0]
        self.assertEqual([card_of(t) for t in self.game.legal_targets(self.a, effect)], [LEGEND])
        self.assertFalse(self.game.cast(self.a, LEGEND_RAISE, [BEAR]))
        self.assertTrue(self.game.cast(self.a, LEGEND_RAISE))
        self.assertEqual((self.a.hand, self.gy()), ([LEGEND], [BEAR]))

    def test_reanimated_creature_is_the_followup_target(self):
        self.ready(HASTE_RAISE, BEAR)
        self.assertTrue(self.game.cast(self.a, HASTE_RAISE))
        self.assertTrue(self.on_bf(BEAR)[0].has("haste"))
        self.setUp()
        self.ready(COUNTER_RAISE, BEAR)
        self.assertTrue(self.game.cast(self.a, COUNTER_RAISE))
        self.assertEqual(self.on_bf(BEAR)[0].counters.get("+1/+1"), 1)

    def test_lost_reanimation_target_skips_the_followup(self):
        self.ready(COUNTER_RAISE, BEAR)
        bear = Permanent(BEAR, self.a)
        self.a.battlefield.append(bear)                                   # another Bear already in play
        self.respond_once(self.remove_slot(0), when=lambda item: item.card is COUNTER_RAISE)
        self.assertTrue(self.game.cast(self.a, COUNTER_RAISE))
        self.assertEqual(bear.counters.get("+1/+1", 0), 0)

    def test_ai_hook_may_answer_with_carddefs(self):
        self.ready(RAISE, ELF, OGRE)
        self.a.ai.choose_target = lambda game, me, eff: ELF               # not the default highest mana value
        self.respond_once(when=lambda item: item.card is RAISE)
        self.assertTrue(self.game.cast(self.a, RAISE))
        self.assertEqual((flat(self.seen[0][1]), self.a.hand), ([ELF], [ELF]))
        self.setUp()
        self.ready(TWO_UPTO, ELF, BEAR, OGRE)
        self.a.ai.choose_target = lambda game, me, eff: (ELF, BEAR)
        self.assertTrue(self.game.cast(self.a, TWO_UPTO))
        self.assertEqual((sorted(c.name for c in self.a.hand), self.gy()), (sorted([ELF.name, BEAR.name]), [OGRE]))

    def test_ai_hook_with_an_illegal_answer_falls_back(self):
        self.ready(RAISE, ELF, BOLT)
        self.a.ai.choose_target = lambda game, me, eff: BOLT              # not a creature card
        self.assertTrue(self.game.cast(self.a, RAISE))
        self.assertEqual(self.a.hand, [ELF])

    def test_owner_restrictions(self):
        self.b.graveyard.append(OGRE)
        self.ready(RAISE)
        self.assertFalse(self.game.cast(self.a, RAISE))                  # "your graveyard" only
        self.assertFalse(self.game.cast(self.a, RAISE, [OGRE]))
        self.setUp()
        self.a.graveyard.append(BEAR)
        self.b.graveyard.append(OGRE)
        self.ready(THIEF)
        effect = THIEF.spell_effects[0]
        self.assertEqual([card_of(t) for t in self.game.legal_targets(self.a, effect)], [OGRE])
        self.assertFalse(self.game.cast(self.a, THIEF, [BEAR]))
        self.assertTrue(self.game.cast(self.a, THIEF, [OGRE]))
        self.assertEqual((len(self.on_bf(OGRE)), list(self.b.graveyard), self.gy()), (1, [], [BEAR]))
        self.assertIs(self.on_bf(OGRE)[0].controller, self.a)
        self.game.destroy(self.on_bf(OGRE)[0])
        self.assertEqual((self.gy(), list(self.b.graveyard)), ([BEAR], [OGRE]))   # dies to its owner's graveyard

    def test_any_graveyard_target_from_either_player(self):
        self.a.graveyard.append(ELF)
        self.b.graveyard.append(OGRE)
        self.ready(ANY_GY)
        effect = ANY_GY.spell_effects[0]
        self.assertEqual(sorted(c.name for c in map(card_of, self.game.legal_targets(self.a, effect))),
                         sorted([ELF.name, OGRE.name]))
        self.assertTrue(self.game.cast(self.a, ANY_GY, [ELF]))
        self.assertEqual((len(self.on_bf(ELF)), list(self.b.graveyard)), (1, [OGRE]))

    def test_targeting_an_opponents_graveyard_is_a_crime(self):
        crimes = []
        fire = self.game.fire

        def spy(p, event, *args, **kw):
            if event == "crime":
                crimes.append(p)
            return fire(p, event, *args, **kw)
        self.game.fire = spy
        self.a.graveyard.append(ELF)
        self.ready(ANY_GY, lands=2)
        self.a.hand.append(ANY_GY)
        self.b.graveyard.append(OGRE)
        self.assertTrue(self.game.cast(self.a, ANY_GY, [ELF]))
        self.assertEqual(crimes, [])
        self.assertTrue(self.game.cast(self.a, ANY_GY, [OGRE]))
        self.assertEqual(crimes, [self.a])

    def test_x_mana_value_is_checked_against_the_chosen_x(self):
        self.ready(X_REANIMATE, BEAR, OGRE, lands=3)                     # X = 2
        self.assertFalse(self.game.cast(self.a, X_REANIMATE, [OGRE]))
        self.assertEqual(self.a.hand, [X_REANIMATE])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))
        self.assertTrue(self.game.cast(self.a, X_REANIMATE, [BEAR]))
        self.assertEqual((len(self.on_bf(BEAR)), self.gy()), (1, [OGRE]))

    def test_x_target_count_follows_x(self):
        self.ready(X_COUNT, BEAR, OGRE, ELF, lands=3)                    # X = 2
        self.respond_once(when=lambda item: item.card is X_COUNT)
        self.assertTrue(self.game.cast(self.a, X_COUNT))
        self.assertEqual(len(flat(self.seen[0][1])), 2)                  # two targets, bound before resolution
        self.assertEqual((len(self.a.hand), len(self.gy())), (2, 1))

    def test_x_target_count_is_limited_by_legal_targets(self):
        self.ready(X_COUNT, BEAR, BOLT, lands=4)                         # three mana for X, one creature card
        self.assertTrue(self.game.cast(self.a, X_COUNT))
        self.assertEqual((self.a.hand, self.gy()), ([BEAR], [BOLT]))

    def test_x_target_count_with_the_wrong_number_of_targets_is_rejected(self):
        self.ready(X_COUNT, BEAR, OGRE, ELF, lands=3)                    # X = 2, so one target is too few
        self.assertFalse(self.game.cast(self.a, X_COUNT, [(BEAR,)]))
        self.assertEqual(self.a.hand, [X_COUNT])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_x_mana_value_with_no_card_small_enough(self):
        self.ready(X_REANIMATE, OGRE, lands=2)                           # X = 1, the Ogre has mana value 3
        self.assertFalse(self.game.cast(self.a, X_REANIMATE))
        self.assertEqual(self.a.hand, [X_REANIMATE])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_x_with_a_multi_mana_source(self):
        self.ready(X_REANIMATE, ELF, BEAR, OGRE, lands=1)
        self.a.battlefield.append(Permanent(SOL_RING, self.a))           # {R} from the Mountain, X = 2 from the Ring
        self.assertTrue(self.game.cast(self.a, X_REANIMATE, [BEAR]))
        self.assertEqual((len(self.on_bf(BEAR)), sorted(c.name for c in self.gy())), (1, sorted([ELF.name, OGRE.name])))
        self.assertTrue(all(x.tapped for x in self.a.battlefield if x.card in (MOUNTAIN, SOL_RING)))

    def test_x_with_a_multi_mana_source_rejects_a_too_big_target_unpaid(self):
        self.ready(X_REANIMATE, OGRE, lands=1)
        self.a.battlefield.append(Permanent(SOL_RING, self.a))           # X = 2, the Ogre has mana value 3
        self.assertFalse(self.game.cast(self.a, X_REANIMATE, [OGRE]))
        self.assertEqual(self.a.hand, [X_REANIMATE])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_x_count_with_a_multi_mana_source(self):
        self.ready(X_COUNT, ELF, BEAR, OGRE, lands=1)
        self.a.battlefield.append(Permanent(SOL_RING, self.a))           # X = 2
        self.assertTrue(self.game.cast(self.a, X_COUNT))
        self.assertEqual((len(self.a.hand), len(self.gy())), (2, 1))

    def test_flashback_regrowth_cannot_target_its_own_entry(self):
        self.a.graveyard.append(SELF_REGROW)
        self.lands()
        option = next(o for o in self.game.spell_options(self.a) if o.name.startswith(SELF_REGROW.name + " ("))
        self.assertFalse(self.game.cast(self.a, option))
        self.assertEqual(self.gy(), [SELF_REGROW])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))
        self.a.graveyard.append(BEAR)
        self.assertTrue(self.game.cast(self.a, option))
        self.assertEqual((self.a.hand, list(self.a.exile)), ([BEAR], [SELF_REGROW]))

    # ------------------------------------------------------------- multiple targets
    def test_two_targets_need_two_distinct_cards(self):
        self.ready(TWO, BEAR)
        self.assertFalse(self.game.cast(self.a, TWO))
        self.assertFalse(self.game.cast(self.a, TWO, [(BEAR, BEAR)]))    # one card can't be both targets
        self.assertEqual(self.a.hand, [TWO])
        self.a.graveyard.append(BEAR)                                    # a second copy of the same CardDef
        self.assertTrue(self.game.cast(self.a, TWO, [(BEAR, BEAR)]))
        self.assertEqual((self.a.hand, self.gy()), ([BEAR, BEAR], []))

    def test_up_to_two_targets(self):
        self.ready(TWO_UPTO, BEAR, OGRE, ELF)
        self.respond_once(when=lambda item: item.card is TWO_UPTO)
        self.assertTrue(self.game.cast(self.a, TWO_UPTO, [(BEAR, ELF)]))
        self.assertEqual(sorted(c.name for c in flat(self.seen[0][1])), sorted([BEAR.name, ELF.name]))
        self.assertEqual((sorted(c.name for c in self.a.hand), self.gy()),
                         (sorted([BEAR.name, ELF.name]), [OGRE]))

    def test_up_to_targets_may_be_declined(self):
        for spell in (TWO_UPTO, REGROW_PERM):
            with self.subTest(spell=spell.name):
                self.setUp()
                self.ready(spell, BEAR)
                self.assertTrue(self.game.cast(self.a, spell, [()]))
                self.assertEqual((self.a.hand, self.gy()), ([], [BEAR]))
                self.setUp()
                self.ready(spell)                                        # nothing to target: still castable
                self.assertTrue(self.game.cast(self.a, spell))
                self.assertFalse(self.fizzled())

    def test_up_to_with_no_target_ignores_cards_added_in_response(self):
        self.ready(REGROW_PERM)
        self.respond_once(lambda item: self.a.graveyard.append(BEAR), when=lambda item: item.card is REGROW_PERM)
        self.assertTrue(self.game.cast(self.a, REGROW_PERM))
        self.assertTrue(self.seen)
        self.assertEqual((self.a.hand, self.gy()), ([], [BEAR]))         # no target was chosen on cast

    def test_zero_graveyard_targets_and_a_lost_other_target_fizzles(self):
        ogre = Permanent(OGRE, self.b)
        self.b.battlefield.append(ogre)
        self.ready(SHOCK_RECOVER, BEAR)
        self.respond_once(lambda item: self.game.leave_battlefield(ogre, "hand"),
                          when=lambda item: item.card is SHOCK_RECOVER)
        self.assertTrue(self.game.cast(self.a, SHOCK_RECOVER, [ogre, ()]))
        self.assertTrue(self.seen)
        self.assertEqual((self.a.hand, self.gy()), ([], [BEAR]))         # no draw: every chosen target was illegal
        self.assertTrue(self.fizzled())

    def test_zero_graveyard_targets_with_a_legal_other_target_resolves(self):
        ogre = Permanent(OGRE, self.b)
        self.b.battlefield.append(ogre)
        self.ready(SHOCK_RECOVER, BEAR)
        self.assertTrue(self.game.cast(self.a, SHOCK_RECOVER, [ogre, ()]))
        self.assertEqual((ogre.damage, self.a.hand, self.gy()), (2, [ISLAND], [BEAR]))
        self.assertFalse(self.fizzled())

    def test_one_of_two_targets_lost_still_returns_the_other(self):
        self.ready(TWO_UPTO, BEAR, OGRE)
        self.respond_once(self.remove_slot(0), when=lambda item: item.card is TWO_UPTO)
        self.assertTrue(self.game.cast(self.a, TWO_UPTO, [(BEAR, OGRE)]))
        self.assertEqual((self.a.hand, list(self.a.exile)), ([OGRE], [BEAR]))

    def test_all_targets_lost_fizzles(self):
        self.ready(TWO_UPTO, BEAR, OGRE, ELF)

        def both(item):
            self.remove_slot(0)(item)
            self.remove_slot(0)(item)
        self.respond_once(both, when=lambda item: item.card is TWO_UPTO)
        self.assertTrue(self.game.cast(self.a, TWO_UPTO, [(BEAR, OGRE)]))
        self.assertEqual((self.a.hand, self.gy()), ([], [ELF]))   # no retarget to the Elf
        self.assertTrue(self.fizzled())

    # ------------------------------------------------------- recheck on resolution
    def test_target_leaving_in_response_fizzles_without_retargeting(self):
        for spell in (RAISE, REANIMATE, REGROW_ANY, SMALL):
            with self.subTest(spell=spell.name):
                self.setUp()
                self.ready(spell, ELF, BEAR)
                self.respond_once(self.remove_slot(0), when=lambda item: item.card is spell)
                self.assertTrue(self.game.cast(self.a, spell, [ELF]))
                self.assertEqual((self.a.hand, self.gy(), self.on_bf(BEAR)), ([], [BEAR], []))
                self.assertTrue(self.fizzled())

    def test_type_and_mana_value_are_rechecked_on_the_same_entry(self):
        for spell, change in ((RAISE, "types"), (SMALL, "cmc")):
            with self.subTest(change=change):
                self.setUp()
                shifty = card("Test Shifty", "{1}{G}", "Creature — Shapeshifter", "", 2, 2)   # isolated CardDef
                self.ready(spell, shifty)

                def mutate(item):
                    if change == "types":
                        shifty.types = frozenset({"Instant"})
                    else:
                        shifty.cmc = 5
                self.respond_once(mutate, when=lambda item: item.card is spell)
                self.assertTrue(self.game.cast(self.a, spell, [shifty]))
                self.assertEqual((self.a.hand, self.on_bf(shifty), self.gy()), ([], [], [shifty]))
                self.assertTrue(self.fizzled())

    def test_opponents_card_moved_to_my_graveyard_is_a_new_object(self):
        for spell in (THIEF, ANY_GY):
            with self.subTest(spell=spell.name):
                self.setUp()
                self.b.graveyard.append(OGRE)
                self.ready(spell)

                def move(item):
                    self.a.graveyard.append(self.b.graveyard.pop(0))
                self.respond_once(move, when=lambda item: item.card is spell)
                self.assertTrue(self.game.cast(self.a, spell, [OGRE]))
                self.assertEqual((self.on_bf(OGRE), self.gy()), ([], [OGRE]))
                self.assertTrue(self.fizzled())

    def test_untargeted_control_picks_on_resolution(self):
        self.ready(UNTARGETED, OGRE, BEAR)
        self.respond_once(self.remove_slot(0), when=lambda item: item.card is UNTARGETED)
        self.assertTrue(self.game.cast(self.a, UNTARGETED))
        self.assertEqual(self.a.hand, [BEAR])                            # no target, so nothing to lose
        self.assertFalse(self.fizzled())

    def test_untouched_target_survives_a_response(self):
        self.ready(RAISE, ELF, OGRE)
        self.respond_once(self.remove_slot(1), when=lambda item: item.card is RAISE)
        self.assertTrue(self.game.cast(self.a, RAISE, [ELF]))
        self.assertEqual(self.a.hand, [ELF])

    def test_target_reordered_in_the_graveyard_is_still_found(self):
        self.ready(RAISE, ELF, OGRE)
        self.respond_once(lambda item: self.a.graveyard.reverse(), when=lambda item: item.card is RAISE)
        self.assertTrue(self.game.cast(self.a, RAISE, [ELF]))
        self.assertEqual((self.a.hand, self.gy()), ([ELF], [OGRE]))

    # ---------------------------------------------------------- same-name copies
    def test_the_exact_targeted_copy_is_returned(self):
        effect = RAISE.spell_effects[0]
        for slot in (0, 1):
            with self.subTest(slot=slot):
                self.setUp()
                self.ready(RAISE, BEAR, BEAR)                           # the same shared CardDef twice
                targets = self.game.legal_targets(self.a, effect)
                other = targets[1 - slot].entry
                self.assertTrue(self.game.cast(self.a, RAISE, [targets[slot]]))
                self.assertEqual((self.a.hand, self.gy()), ([BEAR], [BEAR]))
                self.assertIs(self.a.graveyard.entries[0], other)        # the untargeted copy stays

    def test_same_name_copy_entering_is_a_new_object(self):
        self.ready(RAISE, BEAR)

        def swap(item):     # the targeted Bear leaves and the same CardDef comes back as a new card
            self.remove_slot(0)(item)
            self.a.graveyard.append(BEAR)
        self.respond_once(swap, when=lambda item: item.card is RAISE)
        self.assertTrue(self.game.cast(self.a, RAISE, [BEAR]))
        self.assertEqual((self.a.hand, self.gy()), ([], [BEAR]))
        self.assertTrue(self.fizzled())

    def test_duplicate_copies_lose_only_the_removed_slot(self):
        effect = REANIMATE.spell_effects[0]
        for slot, survives in ((0, False), (1, True)):
            with self.subTest(slot=slot):
                self.setUp()
                self.ready(REANIMATE, BEAR, BEAR)
                target = self.game.legal_targets(self.a, effect)[slot]
                self.respond_once(self.remove_slot(0), when=lambda item: item.card is REANIMATE)
                self.assertTrue(self.game.cast(self.a, REANIMATE, [target]))
                self.assertEqual(len(self.on_bf(BEAR)), int(survives))
                self.assertEqual(len(self.gy()), 1 - int(survives))

    # --------------------------------------------------- triggers and abilities
    def test_etb_trigger_binds_when_put_on_the_stack(self):
        self.a.graveyard.extend([ELF, OGRE])
        self.respond_once(self.remove_slot(1), when=lambda item: not item.is_spell)
        self.game.enter_battlefield(self.a, DIGGER)
        self.game.settle()
        self.assertTrue(self.seen)
        bound = flat(self.seen[0][1])
        self.assertEqual(len(bound), 1)
        self.assertEqual(self.a.hand, [] if bound == [OGRE] else bound)  # lost target: no retarget

    def test_trigger_without_a_target_is_skipped(self):
        self.a.graveyard.append(BOLT)
        self.respond_once(when=lambda item: not item.is_spell)
        self.game.enter_battlefield(self.a, DIGGER)
        self.game.settle()
        self.assertEqual(self.seen, [])
        self.assertFalse(self.fizzled())

    def test_dies_trigger_may_target_the_dying_card(self):
        perm = self.game.enter_battlefield(self.a, MOURNER)
        self.game.settle()
        self.respond_once(when=lambda item: not item.is_spell)
        self.game.destroy(perm)
        self.game.settle()
        self.assertTrue(self.seen)
        self.assertEqual(flat(self.seen[0][1]), [MOURNER])
        self.assertEqual(self.a.hand, [MOURNER])

    def test_activated_ability_needs_a_target_before_tapping(self):
        lich = Permanent(SHOVEL, self.a)
        lich.sick = False
        self.a.battlefield.append(lich)
        self.assertFalse(self.game.activate_ability(self.a, lich, 0))
        self.assertFalse(lich.tapped)
        self.a.graveyard.extend([ELF, OGRE])
        self.respond_once(self.remove_slot(0), when=lambda item: not item.is_spell)
        self.assertTrue(self.game.activate_ability(self.a, lich, 0, [ELF]))
        self.assertTrue(lich.tapped)
        self.assertEqual((self.a.hand, self.gy()), ([], [OGRE]))   # cost stays paid, no retarget

    def test_modal_return_mode_targets_on_cast(self):
        self.ready(COMMAND, ELF, OGRE)
        self.respond_once(self.remove_bound, when=lambda item: item.card is COMMAND)
        self.a.ai.choose_modes = lambda game, me, modes, n, up_to: [
            i for i, m in enumerate(modes) if any(e.target == "graveyard_card" for e in m)][:n]
        self.assertTrue(self.game.cast(self.a, COMMAND))
        bound = flat(self.seen[0][1])
        self.assertEqual(len(bound), 1)
        self.assertEqual(self.a.hand, [])                                # the bound card left: no retarget
        self.assertEqual(len(self.gy()), 1)

    def test_modal_without_a_graveyard_target_picks_another_mode(self):
        self.ready(COMMAND, BOLT)
        self.assertTrue(self.game.cast(self.a, COMMAND))
        self.assertEqual(self.a.hand, [ISLAND])                          # drew instead
        self.assertEqual(self.gy(), [BOLT])

    # ------------------------------------------------------------------- sagas
    def test_reflexive_chapter_targets_after_the_discard(self):
        self.a.hand = [ROCK, ISLAND, ISLAND, ISLAND]                    # the discard is cheap for the AI
        self.a.ai.choose_discard = lambda game, me: ROCK
        self.game.enter_battlefield(self.a, RESTORE)
        self.game.settle()
        rock = self.on_bf(ROCK)
        self.assertEqual(len(rock), 1)                                   # the card just discarded came back
        self.assertTrue(rock[0].tapped)
        self.assertNotIn(ROCK, self.a.hand)

    def test_reflexive_chapter_without_the_discard_does_nothing(self):
        self.a.graveyard.append(ROCK)
        self.a.hand = []
        self.game.enter_battlefield(self.a, RESTORE)
        self.game.settle()
        self.assertEqual((self.on_bf(ROCK), self.gy()), ([], [ROCK]))

    def test_final_chapter_without_a_target_still_sacrifices_the_saga(self):
        self.a.graveyard.append(BOLT)
        self.game.enter_battlefield(self.a, LAST_RAISE)
        self.game.settle()
        self.assertEqual(self.on_bf(LAST_RAISE), [])
        self.assertIn(LAST_RAISE, self.a.graveyard)

    def test_final_chapter_with_a_target_returns_it(self):
        self.a.graveyard.append(BEAR)
        self.game.enter_battlefield(self.a, LAST_RAISE)
        self.game.settle()
        self.assertEqual((self.a.hand, self.on_bf(LAST_RAISE)), ([BEAR], []))


if __name__ == "__main__":
    unittest.main()
