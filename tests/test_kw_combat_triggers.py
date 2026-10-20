"""Real-card regression tests for combat keywords and cast-chain mechanics."""
import random
import unittest
from pathlib import Path

from mtgsim import kw_combat
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import Effect, card_from_scryfall
from mtgsim.engine import Game, Permanent, Player, StackItem


@unittest.skipUnless(Path('mtgsim/data/cards.sqlite3').exists(), 'card database not built')
class CombatKeywordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 1, 'main1'
        for p in (self.a, self.b):
            p.library = [self.db.get('Forest')] * 30

    def perm(self, name, player=None):
        p = player or self.a
        x = Permanent(self.db.get(name), p)
        p.battlefield.append(x)
        x.sick = False
        return x

    def resolve_pending(self):
        # Resolve without giving the AI an opportunity to cast unrelated cards.
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.flush_triggers()

    def hit(self, source, target, amount):
        self.g.deal_damage(target, amount, by=source.controller, source=source)

    def test_parser_real_cards(self):
        for name in ['Akrasan Squire', 'Devoted Retainer', 'Scab-Clan Mauler',
                     'Benalish Cavalry', 'Craw Giant', 'Weaponcraft Enthusiast',
                     'Arcbound Worker', 'Glistener Elf', 'Puncture Blast',
                     'Bilious Skulldweller', 'Thrummingbird', 'Hunting Pack',
                     'Bloodbraid Elf', 'Boon-Bringer Valkyrie']:
            with self.subTest(name=name):
                c = self.db.get(name)
                self.assertEqual(c.unsupported, [])
                self.assertEqual(c.approximations, [])

    def test_unknown_keyword_list_remains_visible(self):
        c = card_from_scryfall(dict(name='Test', type_line='Creature', power='1', toughness='1',
                                   oracle_text='Flying, toxic 2, unknown ability'))
        self.assertTrue(c.unsupported)
        self.assertEqual(c.combat_mechanics, ())

    def test_exalted_multiple_sources_and_attacker_identity(self):
        self.perm('Akrasan Squire')
        self.perm('Akrasan Squire')
        attacker = self.perm('Grizzly Bears')
        self.g.fire(self.a, 'attacks_alone', context=attacker)
        self.resolve_pending()
        self.assertEqual((attacker.power, attacker.toughness), (4, 4))

    def test_bushido_once_per_becoming_blocked_and_each_blocker(self):
        a = self.perm('Devoted Retainer')
        b = self.perm('Devoted Retainer', self.b)
        c = self.perm('Devoted Retainer', self.b)
        kw_combat.blockers(self.g, [a], {a: [b, c]})
        self.resolve_pending()
        self.assertEqual([x.power for x in (a, b, c)], [2, 2, 2])

    def test_flanking_only_affects_blockers_without_flanking(self):
        a = self.perm('Benalish Cavalry')
        b = self.perm('Grizzly Bears', self.b)
        c = self.perm('Benalish Cavalry', self.b)
        kw_combat.blockers(self.g, [a], {a: [b, c]})
        self.resolve_pending()
        self.assertEqual((b.power, c.power), (1, 2))

    def test_rampage_counts_blockers_at_resolution(self):
        a = self.perm('Craw Giant')
        blockers = [self.perm('Grizzly Bears', self.b) for _ in range(3)]
        self.g.blocks = {a: blockers}
        kw_combat.blockers(self.g, [a], self.g.blocks)
        self.b.battlefield.remove(blockers[-1])
        self.resolve_pending()
        self.assertEqual(a.power, 8)

    def test_bloodthirst_requires_damage_instead_of_life_loss(self):
        self.b.life -= 2
        plain = self.g.enter_battlefield(self.a, self.db.get('Scab-Clan Mauler'))
        self.assertEqual(plain.p1, 0)
        self.g.deal_damage(self.b, 1, by=self.a)
        blood = self.g.enter_battlefield(self.a, self.db.get('Scab-Clan Mauler'))
        self.assertEqual(blood.p1, 2)
        self.g.deal_damage(self.b, 0, by=self.a)
        self.assertTrue(self.b.damaged_turn)

    def test_soulshift_exact_graveyard_target_and_limit(self):
        spirit = self.db.get('Kami of False Hope')
        self.a.graveyard.append(spirit)
        src = self.perm('Thief of Hope')
        self.g.dies(src)
        self.resolve_pending()
        self.assertIn(spirit, self.a.hand)
        self.assertIn(src.card, self.a.graveyard)
        self.assertNotIn(src.card, self.a.hand)  # mana value 3 exceeds soulshift 2

    def test_fabricate_resolves_after_source_leaves(self):
        src = self.g.enter_battlefield(self.a, self.db.get('Weaponcraft Enthusiast'))
        self.g.dies(src)
        self.resolve_pending()
        servos = [x for x in self.a.creatures if 'Servo' in x.card.subtypes]
        self.assertEqual(len(servos), 2)
        self.assertTrue(all(x.card.is_artifact and x.power == 1 for x in servos))

    def test_modular_entry_and_transfer_only_to_artifact_creature(self):
        src = self.g.enter_battlefield(self.a, self.db.get('Arcbound Worker'))
        bear = self.perm('Grizzly Bears')
        dest = self.perm('Plague Myr')
        self.assertEqual(src.p1, 1)
        self.g.dies(src)
        self.resolve_pending()
        self.assertEqual((dest.p1, bear.p1), (1, 0))

    def test_modular_uses_last_known_counters_when_minus_counters_kill(self):
        src = self.g.enter_battlefield(self.a, self.db.get('Arcbound Worker'))
        dest = self.perm('Plague Myr')
        src.counters['-1/-1'] = 1
        self.g.state_based_actions()
        self.resolve_pending()
        self.assertEqual(dest.p1, 1)

    def test_infect_poison_loss_and_no_life_loss(self):
        elf = self.perm('Glistener Elf')
        self.hit(elf, self.b, 10)
        self.g.state_based_actions()
        self.assertEqual(self.b.life, 20)
        self.assertEqual(self.b.counters['poison'], 10)
        self.assertTrue(self.b.lost)
        self.assertTrue(self.b.damaged_turn)
        self.assertFalse(self.b.lost_life_turn)

    def test_infect_and_wither_creature_damage(self):
        elf = self.perm('Glistener Elf')
        bear = self.perm('Grizzly Bears', self.b)
        self.hit(elf, bear, 1)
        self.assertEqual((bear.m1, bear.damage, bear.toughness), (1, 0, 1))
        blast = self.db.get('Puncture Blast')
        self.g.deal_damage(bear, 1, by=self.a, source=blast)
        self.assertEqual(bear.m1, 2)
        self.g.state_based_actions()
        self.assertNotIn(bear, self.b.battlefield)

    def test_wither_player_damage_is_normal(self):
        self.g.deal_damage(self.b, 3, by=self.a, source=self.db.get('Puncture Blast'))
        self.assertEqual(self.b.life, 17)
        self.assertEqual(self.b.counters.get('poison', 0), 0)

    def test_toxic_only_combat_players_and_infect_is_additive(self):
        src = self.perm('Bilious Skulldweller')
        self.hit(src, self.b, 2)
        self.assertEqual(self.b.counters.get('poison', 0), 0)
        src.temp_kw.add('infect')
        self.g.combat_damage(self.a, self.b, [src], {}, lambda c: True)
        self.assertEqual(self.b.counters['poison'], 2)  # 1 infect + toxic 1
        self.assertEqual(self.b.life, 18)

    def test_infect_lifelink_deathtouch_and_planeswalker(self):
        src = self.perm('Glistener Elf')
        src.temp_kw.update({'lifelink', 'deathtouch'})
        self.hit(src, self.b, 2)
        self.assertEqual(self.a.life, 22)
        bear = self.perm('Grizzly Bears', self.b)
        self.hit(src, bear, 1)
        self.g.state_based_actions()
        self.assertNotIn(bear, self.b.battlefield)
        pw = self.perm('Liliana of the Veil', self.b)
        pw.counters['loyalty'] = 3
        self.hit(src, pw, 1)
        self.assertEqual(pw.loyalty, 2)
        self.assertEqual(pw.m1, 0)

    def test_proliferate_every_counter_kind_once_and_zero_untouched(self):
        src = self.perm('Thrummingbird')
        ally = self.perm('Grizzly Bears')
        ally.counters.update({'+1/+1': 2, 'shield': 1, 'charge': 0})
        enemy = self.perm('Grizzly Bears', self.b)
        enemy.counters.update({'-1/-1': 1, 'stun': 1})
        self.b.counters['poison'] = 2
        self.g.fire(self.a, 'combat_damage_player', src)
        self.resolve_pending()
        self.assertEqual(ally.counters, {'+1/+1': 3, 'shield': 2, 'charge': 0})
        self.assertEqual(enemy.counters, {'-1/-1': 2, 'stun': 2})
        self.assertEqual(self.b.counters['poison'], 3)
        self.assertEqual(self.a.counters, {})

    def test_storm_counts_both_players_and_copies_are_not_cast(self):
        self.g.spells_cast = {'turn': 1, 'a': 1, 'b': 2}
        card = self.db.get('Hunting Pack')
        item = StackItem(self.a, card.spell_effects, [None], card=card)
        kw_combat.cast(self.g, self.a, item)
        self.resolve_pending()
        self.assertEqual(len(self.a.creatures), 2)  # two prior spells, two copies
        self.assertEqual(self.g.spells_cast, {'turn': 1, 'a': 1, 'b': 2})

    def test_cascade_exiles_then_bottoms_and_casts_one_eligible_spell(self):
        elf = self.db.get('Bloodbraid Elf')
        bear = self.db.get('Grizzly Bears')
        forest = self.db.get('Forest')
        self.a.library = [self.db.get('Island'), bear, elf, forest]
        item = StackItem(self.a, [], [], card=elf)
        self.g.stack.append(item)
        self.g.spells_cast = {'turn': 1, 'a': 1}
        kw_combat.cast(self.g, self.a, item)
        self.g.flush_triggers()
        self.g.resolve_top()
        self.assertEqual([x.card.name for x in self.g.stack], ['Bloodbraid Elf', 'Grizzly Bears (free)'])
        self.assertEqual(len(self.a.library), 3)
        self.assertEqual(self.a.exile, [])
        self.resolve_pending()
        self.assertEqual({x.card.name for x in self.a.creatures}, {'Bloodbraid Elf', 'Grizzly Bears'})

    def test_backup_other_target_grants_below_only(self):
        dest = self.perm('Grizzly Bears')
        src = self.g.enter_battlefield(self.a, self.db.get('Boon-Bringer Valkyrie'))
        effect = next(e for t in src.triggers for e in t.effects if e.kind == 'kw_backup')
        self.g.pending.clear()
        self.g.resolve(self.a, effect, dest, StackItem(self.a, [effect], [dest], source=src))
        self.assertEqual(dest.p1, 1)
        self.assertTrue(all(dest.has(k) for k in ['flying', 'first strike', 'lifelink']))
        self.assertFalse(kw_combat.values(dest, 'backup'))
        dest.backup_grants.clear()
        self.assertFalse(dest.has('flying'))
        self.assertEqual(dest.p1, 1)

    def test_backup_self_does_not_duplicate_abilities(self):
        src = self.g.enter_battlefield(self.a, self.db.get('Boon-Bringer Valkyrie'))
        effect = next(e for t in src.triggers for e in t.effects if e.kind == 'kw_backup')
        self.g.resolve(self.a, effect, src, StackItem(self.a, [effect], [src], source=src))
        self.assertEqual(src.p1, 1)
        self.assertEqual(src.backup_grants, [])

    def test_soulscar_only_replaces_noncombat_damage(self):
        self.perm('Soul-Scar Mage')
        attacker = self.perm('Grizzly Bears')
        blocker = self.perm('Grizzly Bears', self.b)
        self.g.combat_damage(self.a, self.b, [attacker], {attacker: [blocker]}, lambda c: True)
        self.assertEqual(blocker.m1, 0)
        self.assertNotIn(blocker, self.b.battlefield)

    def test_cascade_declines_without_legal_target_or_additional_cost(self):
        for name in ['Path to Exile', 'Fling']:
            with self.subTest(card=name):
                hit = self.db.get(name)
                self.a.library = [hit]
                effect = Effect('kw_cascade', 4)
                self.g.resolve(self.a, effect, None)
                self.assertEqual(self.a.library, [hit])
                self.assertEqual(self.a.exile, [])
                self.assertEqual(self.a.hand, [])
                self.assertEqual(self.g.stack, [])

    def test_storm_trigger_survives_original_being_countered(self):
        card = self.db.get('Empty the Warrens')
        item = StackItem(self.a, card.spell_effects, [None], card=card)
        self.g.spells_cast = {'turn': 1, 'a': 2, 'b': 1}
        kw_combat.cast(self.g, self.a, item)
        # The original is absent from the stack, but the trigger retains its characteristics.
        self.resolve_pending()
        self.assertEqual(len(self.a.creatures), 4)

    def test_backup_grants_trigger_below_it(self):
        dest = self.perm('Grizzly Bears')
        src = self.g.enter_battlefield(self.a, self.db.get('Hangar Scrounger'))
        self.g.pending.clear()
        effect = next(e for t in src.triggers for e in t.effects if e.kind == 'kw_backup')
        self.g.resolve(self.a, effect, dest, StackItem(self.a, [effect], [dest], source=src))
        self.assertEqual([t.event for t in dest.triggers], ['becomes_tapped'])
        self.a.hand = [self.db.get('Forest')]
        self.g.fire(self.a, 'becomes_tapped', dest)
        self.resolve_pending()
        self.assertIn(self.db.get('Forest'), self.a.graveyard)
        self.assertEqual(len(self.a.hand), 1)

    def test_backup_grants_activated_ability_and_expires_at_cleanup(self):
        raw = dict(name='Backup fixture', type_line='Creature — Human', mana_cost='{W}',
                   cmc=1, power='1', toughness='1',
                   oracle_text='Flying\nBackup 1\n{1}: Draw a card.')
        src = self.g.enter_battlefield(self.a, card_from_scryfall(raw))
        dest = self.perm('Grizzly Bears')
        self.g.pending.clear()
        effect = next(e for t in src.triggers for e in t.effects if e.kind == 'kw_backup')
        self.g.resolve(self.a, effect, dest, StackItem(self.a, [effect], [dest], source=src))
        self.assertFalse(dest.has('flying'))  # printed ABOVE backup
        self.assertEqual(len(dest.abilities), 1)
        self.perm('Plains')
        self.assertTrue(self.g.activate_ability(self.a, dest, 0))
        self.resolve_pending()
        self.assertEqual(len(self.a.hand), 1)
        self.g.main_phase = lambda p: None
        self.g.combat = lambda p, opp: None
        self.g.take_turn(self.a)
        self.assertEqual(dest.abilities, [])
        self.assertEqual(dest.p1, 1)

    def test_proliferate_in_larger_effect_line(self):
        card = self.db.get('Contentious Plan')
        self.b.counters['poison'] = 9
        effects = card.spell_effects
        self.assertEqual([e.kind for e in effects], ['proliferate', 'draw'])
        self.g.stack.append(StackItem(self.a, effects, [None, None], card=card))
        self.g.resolve_top()
        self.assertEqual(self.b.counters['poison'], 10)
        self.assertTrue(self.b.lost)

    def test_counter_cancellation_on_survivor(self):
        bear = self.perm('Grizzly Bears')
        bear.counters.update({'+1/+1': 3, '-1/-1': 2})
        self.g.state_based_actions()
        self.assertEqual((bear.p1, bear.m1, bear.power), (1, 0, 3))

    def test_storm_counts_same_name_seats_once(self):
        self.b.name = self.a.name
        self.g.spells_cast = {'turn': 1, 'a': 3}
        card = self.db.get('Empty the Warrens')
        item = StackItem(self.a, card.spell_effects, [None], card=card)
        kw_combat.cast(self.g, self.a, item)
        self.resolve_pending()
        self.assertEqual(len(self.a.creatures), 4)
