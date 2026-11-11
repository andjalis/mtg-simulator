"""#333 recipient selectors for "Prevent the next N damage that would be dealt to <who> this turn".

mtgsim/prevent_next_templates.py extends the plain ``prevent_next`` recipients (cards/patterns.py) with
qualified targets ("target artifact creature", "target legendary creature", "target creature you control"),
the bound "it" of an ability's own source (Balduvian Hydra), "enchanted creature" (Fylgja), the "each ..."
plurals (Kitsune Palliator, Samite Censer-Bearer) and X-sized amounts (Alabaster Potion, Panacea, Festival
of the Guildpact; X is the X paid, sized by resolve's shared amount rules from ``item.x``).

Source filters ("dealt by ~", "by a source of your choice"), "any number of targets, divided as you choose"
and granted abilities stay unmatched on purpose — see the refusal tests. The engine side is the existing
shield pool: deal_damage consumes it, the cleanup step expires it, and the damage_prevented event carries
the prevented amount.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.auras import attach
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from mtgsim.engine.policy import protective_ability
from tests.test_batch1 import Batch1
from tests.test_templates import BEAR, ISLAND, card

SMITH = card("Test Smith", "{2}{W}", "Creature — Human Artificer",
             "{T}: Prevent the next 2 damage that would be dealt to target artifact creature this turn.", 2, 2)
CASTLE = card("Test Castle", "", "Land", "{W}, {T}: Prevent the next 2 damage that would be dealt to target "
            "legendary creature this turn.")
HYDRA = card("Test Hydra", "{2}{R}", "Creature — Hydra",
             "Remove a +1/+0 counter from this creature: Prevent the next 1 damage that would be dealt to it "
             "this turn.", 1, 1)
AURA = card("Test Aura", "{1}{W}", "Enchantment — Aura", "Enchant creature\nRemove a healing counter from this "
            "Aura: Prevent the next 1 damage that would be dealt to enchanted creature this turn.")
PALLIATOR = card("Test Palliator", "{2}{W}", "Creature — Fox Cleric",
                 "{T}: Prevent the next 1 damage that would be dealt to each creature and each player this turn.",
                 1, 2)
CENSER = card("Test Censer", "{1}{W}", "Creature — Human Cleric",
              "{W}, Sacrifice this creature: Prevent the next 1 damage that would be dealt to each creature "
              "you control this turn.", 1, 1)
POTION = card("Test Potion", "{X}{W}", "Instant", "Choose one —\n• Target player gains X life.\n"
             "• Prevent the next X damage that would be dealt to any target this turn.")
PANACEA = card("Test Panacea", "{2}", "Artifact",
               "{X}{X}, {T}: Prevent the next X damage that would be dealt to any target this turn.")
FESTIVAL = card("Test Festival", "{X}{1}{W}", "Instant", "Prevent the next X damage that would be dealt to you "
                "this turn.\nDraw a card.")
GOLEM = card("Test Golem", "{3}", "Artifact Creature — Golem", "", 2, 3)
LEGEND = card("Test Legend", "{1}{W}", "Legendary Creature — Human", "", 2, 2)
BOLT = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")
RED = card("Test Red", "{1}{R}", "Creature — Elemental", "", 2, 2)

ARTIFACT_LINE = "Prevent the next 2 damage that would be dealt to target artifact creature this turn."
LEGENDARY_LINE = "Prevent the next 2 damage that would be dealt to target legendary creature this turn."


class RecipientParse(unittest.TestCase):
    def parse(self, text):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        return effects

    def test_qualified_target_selectors(self):
        (eff,) = self.parse(ARTIFACT_LINE)
        self.assertEqual((eff.kind, eff.amount, eff.target), ("prevent_next", 2, "creature"))
        self.assertEqual(eff.data["selector"], {"types_all": ["artifact", "creature"]})
        (eff,) = self.parse(LEGENDARY_LINE)
        self.assertEqual(eff.data["selector"], {"types_all": ["creature"], "traits": ["legendary"]})
        (eff,) = self.parse("Prevent the next 4 damage that would be dealt this turn to target creature you "
                            "control.")
        self.assertEqual((eff.kind, eff.amount, eff.target), ("prevent_next", 4, "creature_mine"))

    def test_x_amounts(self):
        for text, target in [("Prevent the next X damage that would be dealt to any target this turn.", "any"),
                             ("Prevent the next X damage that would be dealt to you this turn.", "none"),
                             ("Prevent the next X damage that would be dealt to target creature this turn.",
                              "creature")]:
            (eff,) = self.parse(text)
            self.assertEqual((eff.kind, eff.amount, eff.target, eff.data["x"]), ("prevent_next", 0, target, True))

    def test_bound_it_and_enchanted_creature(self):
        (eff,) = self.parse("Prevent the next 1 damage that would be dealt to it this turn.")
        self.assertEqual((eff.kind, eff.amount, eff.target), ("prevent_next", 1, "self"))
        (eff,) = self.parse("Prevent the next 1 damage that would be dealt to enchanted creature this turn.")
        self.assertEqual(eff.target, "host")

    def test_each_plurals(self):
        effs = self.parse("Prevent the next 1 damage that would be dealt to each creature and each player this "
                          "turn.")
        self.assertEqual([(e.target, e.amount) for e in effs], [("each_creature", 1), ("each_player", 1)])
        (eff,) = self.parse("Prevent the next 1 damage that would be dealt to each creature you control this turn.")
        self.assertEqual(eff.target, "each_creature")
        self.assertEqual(eff.data["selector"], {"types_all": ["creature"], "controller": "mine"})

    def test_cards_parse_fully(self):
        for c in (SMITH, CASTLE, HYDRA, AURA, PALLIATOR, CENSER, POTION, PANACEA, FESTIVAL):
            self.assertEqual(c.unsupported, [], c.name)
        (act,) = SMITH.activated
        self.assertEqual((act.effects[0].kind, act.effects[0].amount, act.effects[0].target),
                         ("prevent_next", 2, "creature"))
        (act,) = [a for a in HYDRA.activated if "dealt to it" in a.text]
        self.assertEqual(act.effects[0].target, "self")
        self.assertEqual(len(POTION.modes), 2)
        self.assertEqual(POTION.modes[1][0].data["x"], True)
        self.assertEqual((PANACEA.activated[0].cost.get("X"), PANACEA.activated[0].effects[0].data["x"]), (2, True))
        self.assertEqual(FESTIVAL.spell_effects[0].data["x"], True)

    def test_refusals_stay_unmatched(self):
        refused = [
            "Prevent the next 1 damage that would be dealt by ~ this turn.",                      # Barbed Wire: source filter
            "Prevent the next 3 damage that would be dealt to any target this turn by a source of "
            "your choice.",                                                                      # Healing Grace
            "Prevent the next 4 damage that would be dealt this turn to any number of targets, "
            "divided as you choose.",                                                            # Embolden
            "Prevent the next 2 damage that would be dealt to target Cleric or Wizard creature "
            "this turn.",                                                                        # subtype union
            "Prevent the next 2 damage that would be dealt to you or ~ this turn.",               # shared pool
            "Prevent the next 4 damage that would be dealt to that permanent or player this turn.",
        ]
        for text in refused:
            _, bad = _parse_effects(text)
            self.assertTrue(bad, text)


class RecipientShieldBehavior(Batch1):
    def shield(self, text, target=None, x=0, source=None):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        targets = [target] + [None] * (len(effects) - 1)
        item = StackItem(self.a, effects, targets, source=source)
        if x:
            item.x = x
        for eff, tgt in zip(effects, targets):
            self.g.resolve(self.a, eff, tgt, item)
        return item

    def test_two_damage_events_consume_only_the_remaining_shield(self):
        bear = self.put(BEAR)
        self.shield("Prevent the next 3 damage that would be dealt to target creature this turn.", bear)
        self.g.deal_damage(bear, 2, by=self.b, cause="test")
        self.assertEqual((bear.damage, bear.prevent_next), (0, 1))
        self.g.deal_damage(bear, 2, by=self.b, cause="test")
        self.assertEqual((bear.damage, bear.prevent_next), (1, 0))       # only 1 of the 2 prevented
        self.g.deal_damage(bear, 1, by=self.b, cause="test")
        self.assertEqual(bear.damage, 2)                                 # the shield is gone

    def test_shield_covers_combat_and_noncombat_damage(self):
        bear = self.put(BEAR)
        self.shield("Prevent the next 2 damage that would be dealt to target creature this turn.", bear)
        self.g.deal_damage(bear, 1, by=self.b, cause="test", combat=True)
        self.g.deal_damage(bear, 5, by=self.b, cause="test", combat=False)
        self.assertEqual((bear.damage, bear.prevent_next), (4, 0))

    def test_damage_that_cannot_be_prevented_ignores_the_shield(self):
        bear = self.put(BEAR)
        self.shield("Prevent the next 2 damage that would be dealt to target creature this turn.", bear)
        self.g.no_prevention_turn = True
        self.g.deal_damage(bear, 3, by=self.b, cause="test")
        self.assertEqual((bear.damage, bear.prevent_next), (3, 2))       # Skullcrack wording
        self.g.no_prevention_turn = False
        self.g.deal_damage(bear, 3, by=self.b, cause="test")
        self.assertEqual((bear.damage, bear.prevent_next), (4, 0))

    def test_damage_prevented_event_carries_the_prevented_amount(self):
        bear = self.put(BEAR)
        seen = []
        self.g.rule_events.listeners.append(lambda e: seen.append(e) if e.kind == "damage_prevented" else None)
        self.shield("Prevent the next 2 damage that would be dealt to target creature this turn.", bear)
        self.g.deal_damage(bear, 3, by=self.b, cause="test")
        self.assertEqual([(e.player, e.amount, e.context) for e in seen],
                         [(self.a, 2, None)])

    def test_recipient_shield_applies_whatever_the_source(self):
        bear = self.put(BEAR)
        red = self.put(RED, self.b)
        self.shield("Prevent the next 2 damage that would be dealt to target creature this turn.", bear)
        self.g.deal_damage(bear, 2, by=self.b, cause="test", source=red)
        self.assertEqual((bear.damage, bear.prevent_next), (0, 0))

    def test_source_filtered_shield_only_matches_its_source(self):
        bear = self.put(BEAR)
        red = self.put(RED, self.b)
        effects, bad = _parse_effects("Prevent all damage that would be dealt to ~ by red sources this turn.")
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [None], source=bear)
        self.g.resolve(self.a, effects[0], None, item)
        self.g.deal_damage(bear, 2, by=self.b, cause="test", source=red)          # red source: prevented
        self.assertEqual(bear.damage, 0)
        self.g.deal_damage(bear, 2, by=self.b, cause="test", source=bear)         # not red: dealt in full
        self.assertEqual(bear.damage, 2)

    def test_artifact_creature_selector_targets_only_artifact_creatures(self):
        golem = self.put(GOLEM)
        bear = self.put(BEAR)
        effects, bad = _parse_effects(ARTIFACT_LINE)
        self.assertFalse(bad, bad)
        (eff,) = effects
        self.assertIn(golem, self.g.legal_targets(self.a, eff))
        self.assertNotIn(bear, self.g.legal_targets(self.a, eff))

    def test_legendary_selector_targets_only_legendaries(self):
        legend = self.put(LEGEND)
        bear = self.put(BEAR)
        effects, bad = _parse_effects(LEGENDARY_LINE)
        self.assertFalse(bad, bad)
        (eff,) = effects
        self.assertIn(legend, self.g.legal_targets(self.a, eff))
        self.assertNotIn(bear, self.g.legal_targets(self.a, eff))

    def test_it_shields_the_abilitys_source(self):
        hydra = self.put(HYDRA)
        bear = self.put(BEAR)
        self.shield("Prevent the next 1 damage that would be dealt to it this turn.", source=hydra)
        self.assertEqual((hydra.prevent_next, bear.prevent_next), (1, 0))

    def test_enchanted_creature_shields_the_auras_host(self):
        aura = self.put(AURA)
        bear = self.put(BEAR)
        attach(self.g, aura, bear)
        self.shield("Prevent the next 1 damage that would be dealt to enchanted creature this turn.", source=aura)
        self.assertEqual(bear.prevent_next, 1)

    def test_each_creature_and_each_player(self):
        mine = self.put(BEAR)
        theirs = self.put(BEAR, self.b)
        self.shield("Prevent the next 1 damage that would be dealt to each creature and each player this turn.")
        self.assertEqual((mine.prevent_next, theirs.prevent_next, self.a.prevent_next, self.b.prevent_next),
                         (1, 1, 1, 1))

    def test_each_creature_you_control(self):
        mine = self.put(BEAR)
        theirs = self.put(BEAR, self.b)
        self.shield("Prevent the next 1 damage that would be dealt to each creature you control this turn.")
        self.assertEqual((mine.prevent_next, theirs.prevent_next), (1, 0))

    def test_x_shield_is_sized_from_the_paid_x(self):
        bear = self.put(BEAR)
        self.shield("Prevent the next X damage that would be dealt to target creature this turn.", bear, x=3)
        self.assertEqual(bear.prevent_next, 3)
        self.g.deal_damage(bear, 5, by=self.b, cause="test")
        self.assertEqual((bear.damage, bear.prevent_next), (2, 0))

    def test_shield_expires_at_cleanup(self):
        bear = self.put(BEAR)
        self.shield("Prevent the next 2 damage that would be dealt to target creature this turn.", bear)
        self.assertEqual(bear.prevent_next, 2)
        self.g.take_turn(self.a)
        self.assertEqual(bear.prevent_next, 0)


class RecipientShieldAI(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 1
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def test_artifact_creature_shield_saves_from_exact_damage(self):
        golem = self.put(self.a, GOLEM)
        self.put(self.a, SMITH)
        self.game.stack.append(StackItem(self.b, list(BOLT.spell_effects), [golem], card=BOLT))
        self.game.run_priority()
        self.assertIn(golem, self.a.battlefield)
        self.assertEqual(golem.damage, 1)                    # 3 damage, 2 prevented

    def test_protective_ability_offers_the_qualified_target(self):
        golem = self.put(self.a, GOLEM)
        smith = self.put(self.a, SMITH)
        item = StackItem(self.b, list(BOLT.spell_effects), [golem], card=BOLT)
        action = protective_ability(self.game, self.a, item, golem)
        self.assertIsNotNone(action)
        self.assertEqual(action[:3], ("activate", smith, "ability:0"))
        self.assertEqual(action[3][0], golem)


if __name__ == "__main__":
    unittest.main()
