"""Rules behavior for edicts, life from a destroyed creature, solo restrictions and the monarch."""
import random
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.auras import attach
from mtgsim.batch1_templates import has_blessing, skips_draw
from mtgsim.engine import Game, Player, StackItem, can_block
from mtgsim.residual_templates import activation_blocked
from tests.test_combat_triggers import Scripted, BEAR
from tests.test_templates import ISLAND, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)
EMBER = card("Test Ember", "{1}{R}", "Creature — Beast", "~ can't attack or block alone.", 3, 3)
CROWN = card("Test Commodore", "{2}{U}", "Creature — Pirate", "When Test Commodore enters, you become the monarch.", 1, 1)


class Batch1(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def put(self, definition, p=None):
        perm = self.g.enter_battlefield(p or self.a, definition)
        perm.sick = False
        self.g.settle()
        return perm

    def apply(self, text, targets=()):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets)
        prev = None
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item, prev=prev)
            prev = target

    def test_target_player_sacrifices_the_weakest_creature(self):
        weak, strong = self.put(BEAR, self.b), self.put(BIG, self.b)
        self.apply("Target player sacrifices a creature.", [self.b])
        self.assertNotIn(weak, self.b.battlefield)
        self.assertIn(strong, self.b.battlefield)

    def test_each_player_sacrifices(self):
        mine, theirs = self.put(BEAR, self.a), self.put(BEAR, self.b)
        self.apply("Each player sacrifices a creature.")
        self.assertNotIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_gain_life_equal_to_destroyed_creatures_power(self):
        big = self.put(BIG, self.b)
        life = self.a.life
        self.apply("Destroy target creature. You gain life equal to its power.", [big])
        self.assertEqual(self.a.life, life + 4)

    def test_gain_life_equal_to_toughness(self):
        big = self.put(BIG, self.b)
        life = self.a.life
        self.apply("Destroy target creature. You gain life equal to its toughness.", [big])
        self.assertEqual(self.a.life, life + 5)

    def test_cant_attack_alone(self):
        ember = self.put(EMBER)
        self.a.ai.attack = (ember,)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)
        bear = self.put(BEAR)
        self.a.ai.attack = (ember, bear)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20 - 5)

    def test_cant_block_alone(self):
        ember = self.put(EMBER, self.b)
        attacker = self.put(BEAR)
        self.a.ai.attack = (attacker,)
        self.b.ai.block = {attacker: (ember,)}
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)
        self.assertEqual(ember.damage, 0)

    def test_monarch_draws_and_changes_on_combat_damage(self):
        self.put(CROWN)
        self.assertIs(self.g.monarch, self.a)
        hand = len(self.a.hand)
        self.g.begin_end_step(self.a)
        self.assertEqual(len(self.a.hand), hand + 1)
        hitter = self.put(BEAR, self.b)
        self.g.monarch = self.a
        self.b.ai.attack = (hitter,)
        self.g.combat(self.b, self.a)
        self.assertIs(self.g.monarch, self.b)

    def test_tap_and_freeze_two_creatures(self):
        x, y = self.put(BEAR, self.b), self.put(BIG, self.b)
        self.apply("Tap up to two target creatures. Those creatures don't untap during their controller's next untap step.", [x])
        self.assertTrue(x.tapped)
        self.assertEqual(x.skip_untap, 1)
        self.assertTrue(y.tapped)
        self.assertEqual(y.skip_untap, 1)

    def test_pump_then_untap(self):
        x = self.put(BEAR)
        x.tapped = True
        self.apply("Creatures you control get +1/+2 until end of turn. Untap those creatures.")
        self.assertFalse(x.tapped)
        self.assertEqual(x.power, 3)

    def test_gain_life_lost_this_way(self):
        self.apply("Each opponent loses 3 life. You gain life equal to the life lost this way.")
        self.assertEqual((self.a.life, self.b.life), (23, 17))

    def test_damaged_creature_is_exiled_instead_of_dying(self):
        bear = self.put(BEAR, self.b)
        self.apply("~ deals 3 damage to target creature. If a creature dealt damage this way would die this turn, exile it instead.", [bear])
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(len(self.b.graveyard), 0)
        self.assertEqual(len(self.b.exile), 1)

    def test_wrath_exiles_all_dying_creatures(self):
        self.put(BEAR, self.b)
        big = self.put(BIG)
        self.apply("~ deals 3 damage to each creature. If a creature dealt damage this way would die this turn, exile it instead.")
        self.assertEqual(len(self.b.exile), 1)
        self.assertIn(big, self.a.battlefield)

    def test_player_hexproof_blocks_opponent_targeting(self):
        aegis = card("Test Aegis", "{2}{W}", "Enchantment", "You have hexproof.")
        self.put(aegis, self.b)
        eff, _ = _parse_effects("~ deals 2 damage to any target.")
        self.assertNotIn(self.b, self.g.legal_targets(self.a, eff[0]))
        self.assertIn(self.b, self.g.legal_targets(self.b, eff[0]))

    def test_arrest_stops_combat_and_activation(self):
        arrest = card("Test Arrest", "{2}{W}", "Enchantment — Aura",
                      "Enchant creature\nEnchanted creature can't attack or block, and its activated abilities can't be activated.")
        ping = card("Test Pinger", "{1}", "Creature — Human", "{T}: ~ deals 1 damage to any target.", 1, 1)
        pinger = self.put(ping, self.b)
        self.assertTrue(self.g.can_activate(self.b, pinger, 0))
        aura = self.g.enter_battlefield(self.a, arrest)
        aura.attached_to = pinger
        pinger.auras.append(aura)
        self.assertFalse(self.g.can_activate(self.b, pinger, 0))

    def test_etb_damage_equal_to_power(self):
        redcap = self.put(card("Test Redcap", "{2}{R}", "Creature — Elemental", "", 2, 2), self.a)
        eff, bad = _parse_effects("it deals damage equal to its power to any target.")
        self.assertFalse(bad)
        life = self.b.life
        self.g.resolve(self.a, eff[0], self.b, StackItem(self.a, eff, [self.b], source=redcap))
        self.assertEqual(self.b.life, life - 2)

    def test_enters_tapped_with_charge_counters(self):
        vivid = card("Test Vivid", "", "Land", "~ enters tapped with two charge counters on it.\n{T}: Add {U}.")
        perm = self.g.enter_battlefield(self.a, vivid)
        self.assertTrue(perm.tapped)
        self.assertEqual(perm.counters["charge"], 2)

    def test_powerstone_mana_only_casts_artifacts(self):
        self.apply("Create a tapped Powerstone token.")
        stone = next(x for x in self.a.battlefield if x.card.token_kind == "powerstone")
        self.assertTrue(stone.tapped)
        stone.tapped = False
        self.assertEqual(stone.card.mana_restriction, "artifact")

    def test_provoke_untaps_and_forces_block(self):
        goblin = card("Test Provoker", "{2}{R}", "Creature — Goblin", "Provoke", 2, 2)
        attacker = self.put(goblin)
        wall = self.put(card("Test Wall", "{1}", "Creature — Wall", "", 0, 4), self.b)
        wall.tapped = True
        self.a.ai.attack = (attacker,)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)
        self.assertEqual(wall.damage, 2)

    def test_assign_combat_damage_as_though_unblocked(self):
        wolf = self.put(card("Test Wolf", "{2}{G}", "Creature — Wolf",
                             "You may have ~ assign its combat damage as though it weren't blocked.", 3, 3))
        wall = self.put(card("Test Wall", "{1}", "Creature — Wall", "", 0, 6), self.b)
        self.a.ai.attack = (wolf,)
        self.b.ai.block = {wolf: (wall,)}
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 17)

    def test_phantom_prevents_damage_and_loses_a_counter(self):
        phantom = self.put(card("Test Phantom", "{2}{G}", "Creature — Spirit",
                                "~ enters with three +1/+1 counters on it.\n"
                                "If damage would be dealt to ~, prevent that damage. Remove a +1/+1 counter from ~.", 0, 0))
        self.assertEqual(phantom.p1, 3)
        self.g.deal_damage(phantom, 5, by=self.b)
        self.assertEqual((phantom.damage, phantom.p1), (0, 2))

    def test_converge_counts_colors_spent(self):
        crawler = card("Test Crawler", "{2}", "Artifact Creature — Construct",
                       "Converge — ~ enters with a +1/+1 counter on it for each color of mana spent to cast it.", 0, 0)
        self.assertTrue(crawler.advanced_rules.get("sunburst"))

    def test_conditional_pump_for_basic_land_type(self):
        aven = self.put(card("Test Aven", "{1}{W}", "Creature — Bird", "~ gets +1/+1 as long as you control a Plains.", 1, 1))
        self.assertEqual(aven.power, 1)
        self.put(card("Plains", types="Basic Land — Plains"))
        self.assertEqual(aven.power, 2)

    def test_cant_be_blocked_by_walls_and_fliers(self):
        rat = self.put(card("Test Rat", "{1}", "Creature — Rat", "~ can't be blocked by Walls.", 1, 1))
        wall = self.put(card("Test Wall", "{1}", "Creature — Wall", "", 0, 4), self.b)
        bear = self.put(BEAR, self.b)
        self.assertFalse(can_block(wall, rat))
        self.assertTrue(can_block(bear, rat))

    def test_cant_block_big_attackers(self):
        orc = self.put(card("Test Orc", "{1}{R}", "Creature — Orc", "~ can't block creatures with power 2 or greater.", 2, 2), self.b)
        bear = self.put(BEAR)
        small = self.put(card("Test Mite", "{1}", "Creature — Insect", "", 1, 1))
        self.assertFalse(can_block(orc, bear))
        self.assertTrue(can_block(orc, small))

    def test_cant_attack_alone_without_block_clause(self):
        construct = self.put(card("Test Construct", "{2}", "Artifact Creature — Construct", "~ can't attack alone.", 3, 3))
        self.a.ai.attack = (construct,)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)

    def test_skip_draw_step(self):
        self.put(card("Test Appeasement", "{3}{R}", "Enchantment", "Skip your draw step."), self.a)
        self.assertTrue(skips_draw(self.g, self.a))
        self.assertFalse(skips_draw(self.g, self.b))

    def test_artifacts_cannot_be_activated(self):
        self.put(card("Test Ouphe", "{1}{G}", "Creature — Ouphe", "Activated abilities of artifacts can't be activated.", 1, 1), self.b)
        rock = self.put(card("Test Rock", "{1}", "Artifact", "{T}: Add {C}."), self.a)
        self.assertTrue(activation_blocked(self.g, rock, mana=True))

    def test_damage_each_attacking_and_opponent_creatures(self):
        mine = self.put(BEAR, self.a)
        theirs = self.put(BEAR, self.b)
        self.g.attackers = [theirs]
        self.apply("~ deals 1 damage to each attacking creature.")
        self.assertEqual((mine.damage, theirs.damage), (0, 1))
        self.apply("~ deals 1 damage to each creature your opponents control.")
        self.assertEqual((mine.damage, theirs.damage), (0, 2))

    def test_destroy_damaged_creature(self):
        fresh, hurt = self.put(BEAR, self.b), self.put(BEAR, self.b)
        hurt.damage = 1
        eff, _ = _parse_effects("Destroy target creature that was dealt damage this turn.")
        legal = self.g.legal_targets(self.a, eff[0])
        self.assertIn(hurt, legal)
        self.assertNotIn(fresh, legal)

    def test_defending_player_discards(self):
        self.b.hand = [ISLAND]
        eff, _ = _parse_effects("Defending player discards a card.")
        self.g.resolve(self.a, eff[0], None, StackItem(self.a, eff, [None], context=self.b))
        self.assertEqual(len(self.b.hand), 0)

    def test_each_player_sacrifices_a_land(self):
        mine, theirs = self.put(ISLAND, self.a), self.put(ISLAND, self.b)
        self.apply("Each player sacrifices a land.")
        self.assertNotIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_power_from_graveyard_cards(self):
        self.a.graveyard.extend([BEAR, BEAR])
        wurm = self.put(card("Test Wurm", "{3}{B}", "Creature — Wurm",
                             "~'s power and toughness are each equal to the number of creature cards in your graveyard.", 0, 0))
        self.assertEqual(wurm.power, 2)
        elite = self.put(card("Test Elite", "{1}{B}", "Creature — Zombie",
                              "~ gets +1/+1 for each creature card in your graveyard.", 1, 1))
        self.assertEqual(elite.power, 3)
        drake = self.put(card("Test Drake", "{1}{U}", "Creature — Drake",
                              "~'s power is equal to the number of instant and sorcery cards in your graveyard.", 0, 3))
        self.assertEqual(drake.power, 0)
        self.a.graveyard.append(card("Shock", "{R}", "Instant", "~ deals 2 damage to any target."))
        self.assertEqual(drake.power, 1)

    def test_pump_per_attached_aura(self):
        artisan = self.put(card("Test Artisan", "{1}{W}", "Creature — Human",
                                "~ gets +2/+2 for each Aura attached to it.", 1, 1))
        aura = self.g.enter_battlefield(self.a, card("Test Aura", "{W}", "Enchantment — Aura", "Enchant creature"))
        aura.attached_to = artisan
        artisan.auras.append(aura)
        self.assertEqual(artisan.power, 3)

    def test_aura_grants_shroud(self):
        cloak = card("Test Cloak", "{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature has shroud.")
        self.assertFalse(cloak.unsupported)

    def test_creatures_with_counters_have_trample(self):
        self.put(card("Test Ceratok", "{2}{G}", "Creature — Rhino",
                      "Each creature you control with a +1/+1 counter on it has trample.", 3, 3))
        plain, grown = self.put(BEAR), self.put(BEAR)
        grown.counters["+1/+1"] = 1
        self.assertTrue(grown.has("trample"))
        self.assertFalse(plain.has("trample"))

    def test_attacker_sacrifices_itself_at_end_of_combat(self):
        colossus = self.put(card("Test Colossus", "{4}", "Artifact Creature — Golem",
                                 "When ~ attacks, sacrifice it at end of combat.", 7, 4))
        self.a.ai.attack = (colossus,)
        self.g.combat(self.a, self.b)
        self.g.end_combat(self.a)
        self.g.settle()
        self.assertEqual(self.b.life, 13)
        self.assertNotIn(colossus, self.a.battlefield)

    def test_aura_upkeep_life_loss_for_hosts_controller(self):
        lashes = card("Test Lashes", "{2}{B}", "Enchantment — Aura", "Enchant creature\n"
                      "At the beginning of the upkeep of enchanted creature's controller, that player loses 1 life.")
        host = self.put(BEAR, self.b)
        aura = self.g.enter_battlefield(self.a, lashes)
        attach(self.g, aura, host)
        self.g.begin_upkeep(self.b)
        self.g.run_priority()
        self.assertEqual(self.b.life, 19)
        self.g.begin_upkeep(self.a)
        self.g.run_priority()
        self.assertEqual(self.b.life, 19)

    def test_land_mana_doubler_lets_two_lands_pay_four(self):
        self.put(card("Test Wake", "{3}{G}", "Enchantment",
                      "Whenever you tap a land for mana, add one mana of any type that land produced."))
        self.put(ISLAND)
        self.put(ISLAND)
        spell = card("Test Bigspell", "{2}{U}{U}", "Sorcery", "Draw a card.")
        self.a.hand = [spell]
        hand = len(self.a.hand)
        self.assertTrue(self.g.cast(self.a, spell))
        self.g.run_priority()
        self.assertEqual(len(self.a.hand), hand)      # spell left hand, drew one

    def test_attack_with_two_creatures_triggers(self):
        alliance = card("Test Alliance", "{2}{W}", "Enchantment",
                        "Whenever you attack with two or more creatures, draw a card.")
        self.put(alliance)
        x, y = self.put(BEAR), self.put(BEAR)
        hand = len(self.a.hand)
        self.a.ai.attack = (x, y)
        self.g.combat(self.a, self.b)
        self.g.run_priority()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_sacrifice_another_permanent_grows_creature(self):
        grower = self.put(card("Test Grower", "{2}{G}", "Creature — Plant",
                               "Whenever you sacrifice another permanent, put a +1/+1 counter on ~.", 1, 1))
        fodder = self.put(BEAR)
        self.g.sacrifice(fodder)
        self.g.run_priority()
        self.assertEqual(grower.p1, 1)
        self.g.sacrifice(grower)
        self.assertNotIn(grower, self.a.battlefield)

    def test_cast_trigger_for_either_subtype(self):
        altar = self.put(card("Test Altar", "{3}", "Artifact",
                              "Whenever you cast a Spirit or Arcane spell, you may put a ki counter on ~."))
        eff = altar.triggers[0]
        self.assertEqual(eff.filter, "spell:Spirit|Arcane")

    def test_melee_pumps_when_attacking(self):
        warden = self.put(card("Test Warden", "{2}{R}", "Creature — Human",
                               "Melee (Whenever this creature attacks, it gets +1/+1 until end of turn for each opponent you attacked this combat.)", 2, 2))
        self.a.ai.attack = (warden,)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 17)

    def test_enlist_taps_a_helper_and_adds_power(self):
        cavalier = self.put(card("Test Cavalier", "{2}{W}", "Creature — Human",
                                 "Enlist (As this creature attacks, you may tap a nonattacking creature you control without summoning sickness. When you do, add its power to this creature's until end of turn.)", 2, 2))
        helper = self.put(BEAR)
        self.a.ai.attack = (cavalier,)
        self.g.combat(self.a, self.b)
        self.assertTrue(helper.tapped)
        self.assertEqual(self.b.life, 16)

    def test_exploit_sacrifices_a_token_and_triggers_payoff(self):
        self.g.create_token(self.a, _parse_effects("Create a 1/1 white Soldier creature token.")[0][0])
        butcher = card("Test Butcher", "{3}{B}", "Creature — Orc",
                       "Exploit (When this creature enters, you may sacrifice a creature.)\n"
                       "When ~ exploits a creature, you gain 3 life.", 3, 3)
        self.assertFalse(butcher.unsupported)
        life = self.a.life
        self.put(butcher)
        self.g.run_priority()
        self.assertEqual(self.a.life, life + 3)
        self.assertEqual(len([c for c in self.a.creatures if c.card.is_token]), 0)

    def test_city_blessing_unlocks_activation_and_effects(self):
        arch = self.put(card("Test Arch", "", "Land",
                             "Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.)\n"
                             "{T}: Add {C}.\n{5}, {T}: Draw a card. Activate only if you have the city's blessing."))
        self.assertFalse(self.g.can_activate(self.a, arch, 1))
        for _ in range(9):
            self.put(BEAR)
        self.assertTrue(has_blessing(self.g, self.a))
        self.assertTrue(self.a.blessing)
        _, bad = _parse_effects("If you have the city's blessing, draw a card.")
        self.assertFalse(bad)

    def test_incubate_and_transform(self):
        self.apply("Incubate 3.")
        incubator = next(x for x in self.a.battlefield if "Incubator" in x.card.subtypes)
        self.assertFalse(incubator.is_creature)
        self.assertEqual(incubator.p1, 3)
        self.mana_for_two()
        self.assertTrue(self.g.can_activate(self.a, incubator, 0))
        item = StackItem(self.a, [], [], source=incubator)
        from mtgsim.cards import Effect
        self.g.resolve(self.a, Effect("incubator_transform"), None, item)
        self.assertTrue(incubator.is_creature)
        self.assertEqual((incubator.power, incubator.toughness), (3, 3))

    def mana_for_two(self):
        self.put(ISLAND)
        self.put(ISLAND)

    def test_x_pump_uses_paid_x(self):
        bear = self.put(BEAR)
        eff, bad = _parse_effects("Target creature gets +X/+0 until end of turn.")
        self.assertFalse(bad)
        item = StackItem(self.a, eff, [bear])
        item.x = 3
        self.g.resolve(self.a, eff[0], bear, item)
        self.assertEqual((bear.power, bear.toughness), (5, 2))

    def test_soulbond_pairs_and_pumps(self):
        mauler = self.put(card("Test Mauler", "{1}{R}", "Creature — Wolf", "Soulbond\nAs long as ~ is paired with another creature, both creatures have haste.", 2, 1))
        self.assertFalse(mauler.has("haste"))
        bear = self.put(BEAR)
        self.assertIs(bear.partner, mauler)
        self.assertTrue(bear.has("haste"))
        self.assertTrue(mauler.has("haste"))
        self.g.destroy(bear) if hasattr(self.g, "destroy") else self.a.battlefield.remove(bear)
        self.g.settle()
        self.assertFalse(mauler.has("haste"))

    def test_may_destroy_only_hits_the_opponent(self):
        eff, bad = _parse_effects("You may destroy target artifact.")
        self.assertFalse(bad)
        mine = self.put(card("Test Rock", "{1}", "Artifact", ""))
        theirs = self.put(card("Their Rock", "{1}", "Artifact", ""), self.b)
        item = StackItem(self.a, eff, [mine])
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertIn(mine, self.a.battlefield)
        item = StackItem(self.a, eff, [theirs])
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertNotIn(theirs, self.b.battlefield)

    def test_tap_or_untap_and_switch(self):
        mine, theirs = self.put(BEAR), self.put(BEAR, self.b)
        mine.tapped = True
        eff, bad = _parse_effects("Tap or untap target creature.")
        self.assertFalse(bad)
        self.g.resolve(self.a, eff[0], mine, StackItem(self.a, eff, [mine]))
        self.assertFalse(mine.tapped)
        self.g.resolve(self.a, eff[0], theirs, StackItem(self.a, eff, [theirs]))
        self.assertTrue(theirs.tapped)
        eff, bad = _parse_effects("Switch target creature's power and toughness until end of turn.")
        self.assertFalse(bad)
        big = self.put(card("Test Wall", "{1}", "Creature — Wall", "", 0, 5))
        self.g.resolve(self.a, eff[0], big, StackItem(self.a, eff, [big]))
        self.assertEqual((big.power, big.toughness), (5, 0))

    def test_other_keyword_anthem(self):
        eagle = self.put(card("Test Eagle", "{3}{W}", "Creature — Bird", "Flying\nOther creatures you control with flying get +1/+1.", 2, 2))
        bird = self.put(card("Test Bird", "{1}", "Creature — Bird", "Flying", 1, 1))
        ground = self.put(BEAR)
        self.assertEqual((bird.power, bird.toughness), (2, 2))
        self.assertEqual((eagle.power, eagle.toughness), (2, 2))
        self.assertEqual((ground.power, ground.toughness), (2, 2))

    def test_activation_limit_per_turn(self):
        bat = self.put(card("Test Bat", "{1}{B}", "Creature — Bat", "{B}: ~ gets +1/+0 until end of turn. Activate no more than twice each turn.", 1, 1))
        for _ in range(3):
            self.put(card("Test Swamp", "", "Basic Land — Swamp", "{T}: Add {B}."))
        self.assertTrue(self.g.activate(self.a, bat, "ability:0"))
        self.assertTrue(self.g.activate(self.a, bat, "ability:0"))
        self.assertFalse(self.g.can_activate(self.a, bat, 0))
        self.assertEqual(bat.power, 3)

    def test_one_spell_each_turn(self):
        self.put(card("Test Law", "{1}{W}", "Enchantment", "Each player can't cast more than one spell each turn."))
        spell = card("Test Zap", "", "Instant", "Test Zap deals 1 damage to any target.")
        self.a.hand.append(spell)
        self.a.hand.append(spell)
        self.assertTrue(self.g.can_cast_now(self.a, spell))
        self.g.spells_cast = {"turn": self.g.turn, self.a.name: 1}
        self.assertFalse(self.g.can_cast_now(self.a, spell))

    def test_soul_link_gains_life(self):
        bear = self.put(BEAR)
        link = self.put(card("Test Link", "{1}{W}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature deals damage, you gain that much life.\nWhenever enchanted creature is dealt damage, you gain that much life."))
        attach(self.g, link, bear)
        before = self.a.life
        self.g.deal_damage(self.b, 2, by=self.a, source=bear)
        self.assertEqual(self.a.life, before + 2)
        self.g.deal_damage(bear, 1, by=self.b)
        self.assertEqual(self.a.life, before + 3)

    def test_kicked_creature_enters_with_counters(self):
        drake = card("Test Drake", "{1}{U}", "Creature — Drake",
                     "Kicker {2}\nFlying\nIf Test Drake was kicked, it enters with two +1/+1 counters on it.", 1, 1)
        for _ in range(4):
            self.put(ISLAND)
        self.a.hand.append(drake)
        kicked = next(c for c in self.g.spell_options(self.a) if self.g._origin(c)[1] == "kicker")
        self.assertTrue(self.g.cast(self.a, kicked))
        self.g.settle()
        perm = next(x for x in self.a.battlefield if x.card.name == "Test Drake")
        self.assertEqual(perm.p1, 2)

    def test_aura_adds_extra_mana(self):
        forest = self.put(card("Test Forest", "", "Basic Land — Forest", "{T}: Add {G}."))
        grow = self.put(card("Test Growth", "{G}", "Enchantment — Aura", "Enchant land\nWhenever enchanted land is tapped for mana, its controller adds an additional {G}."))
        attach(self.g, grow, forest)
        from mtgsim.engine.mana import _amount
        self.assertEqual(_amount(forest), 2)

    def cast_curse(self, text, name="Test Curse"):
        curse = card(name, "{1}", "Enchantment — Aura Curse", "Enchant player\n" + text)
        self.a.hand.append(curse)
        self.put(ISLAND)
        self.assertTrue(self.g.cast(self.a, curse))
        self.g.settle()
        return next(x for x in self.a.battlefield if x.card.name == name)

    def test_curse_upkeep_and_statics(self):
        from mtgsim.batch1_templates import on_upkeep
        mill = self.cast_curse("At the beginning of enchanted player's upkeep, that player mills two cards.", "Test Tome")
        self.assertIs(mill.curse_target, self.b)
        before = len(self.b.library)
        on_upkeep(self.g, self.b)
        self.g.settle()
        self.assertEqual(len(self.b.library), before - 2)
        self.cast_curse("Creatures enchanted player controls get -1/-1.", "Test Hold")
        bear = self.put(BEAR, self.b)
        self.assertEqual((bear.power, bear.toughness), (1, 1))
        self.cast_curse("If a source would deal damage to enchanted player, it deals double that damage to that player instead.", "Test Blood")
        life = self.b.life
        self.g.deal_damage(self.b, 2, by=self.a, source=bear)
        self.assertEqual(self.b.life, life - 4)

    def test_outlast_adds_a_counter_at_sorcery_speed(self):
        monk = self.put(card("Test Monk", "{1}{W}", "Creature — Human Monk", "Outlast {1} ({1}, {T}: Put a +1/+1 counter on this creature. Outlast only as a sorcery.)", 1, 2))
        self.put(ISLAND)
        self.assertTrue(self.g.activate(self.a, monk, "ability:0"))
        self.g.settle()
        self.assertEqual(monk.p1, 1)
        self.assertTrue(monk.tapped)

    def test_cumulative_upkeep_pays_then_sacrifices(self):
        from mtgsim.batch1_templates import on_upkeep
        ants = self.put(card("Test Ants", "{2}{G}", "Creature — Insect", "Cumulative upkeep {1}", 2, 2))
        for _ in range(3):
            self.put(ISLAND)
        on_upkeep(self.g, self.a)
        self.assertEqual(ants.counters.get("age"), 1)
        self.assertIn(ants, self.a.battlefield)
        self.assertEqual(sum(1 for x in self.a.battlefield if x.card.is_land and x.tapped), 1)
        for x in self.a.battlefield:
            x.tapped = False
        on_upkeep(self.g, self.a)
        self.assertEqual(ants.counters.get("age"), 2)
        self.assertEqual(sum(1 for x in self.a.battlefield if x.card.is_land and x.tapped), 2)
        for x in self.a.battlefield:
            x.tapped = False
        on_upkeep(self.g, self.a)
        on_upkeep(self.g, self.a)
        self.g.settle()
        self.assertNotIn(ants, self.a.battlefield)

    def test_level_up_sets_stats_and_keywords(self):
        student = self.put(card("Test Student", "{W}", "Creature — Human Knight",
                                "Level up {W} ({W}: Put a level counter on this. Level up only as a sorcery.)\n"
                                "LEVEL 2-6\n3/3\nFirst strike\nLEVEL 7+\n4/4\nDouble strike", 1, 1))
        self.assertEqual((student.power, student.toughness), (1, 1))
        for _ in range(2):
            self.put(card("Test Plains", "", "Basic Land — Plains", "{T}: Add {W}."))
        self.assertTrue(self.g.activate(self.a, student, "ability:0"))
        self.g.settle()
        self.assertEqual((student.power, student.toughness), (1, 1))
        self.assertTrue(self.g.activate(self.a, student, "ability:0"))
        self.g.settle()
        self.assertEqual((student.power, student.toughness), (3, 3))
        self.assertTrue(student.has("first strike"))
        student.counters["level"] = 7
        self.assertEqual((student.power, student.toughness), (4, 4))
        self.assertTrue(student.has("double strike"))
        self.assertFalse(student.has("first strike"))


if __name__ == '__main__':
    unittest.main()
