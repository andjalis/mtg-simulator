"""Real-database functional scenarios with both pilots, not strength measurements."""
import json
import random
import re
from pathlib import Path

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import make_token
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, PLAINS, card

re._MAXCACHE = 32768


def setup(pilot):
    a, b = Player('a', [], pilot()), Player('b', [], pilot())
    game = Game(a, b, random.Random(11))
    game.turn, game.step = 2, 'main2'
    for player in (a, b):
        player.library = [ISLAND] * 60
    return game, a, b


def main():
    db = CardDB(offline=True)
    checks = []
    try:
        for pilot in (HeuristicAI, BaselineAI):
            g, a, b = setup(pilot)
            source = g.enter_battlefield(a, db.get('Harvester of Souls'))
            victim = g.enter_battlefield(b, BEAR)
            g.destroy(victim)
            g.settle()
            assert len(a.hand) == 1 and source in a.battlefield

            g, a, b = setup(pilot)
            land = g.enter_battlefield(a, FOREST)
            g._aura_host = land
            g.enter_battlefield(a, db.get('Abundant Growth'))
            g.settle()
            assert g.pay(a, {'W': 1}) is not None and land.tapped

            g, a, b = setup(pilot)
            g.enter_battlefield(a, db.get('Acidic Sliver'))
            recipient = g.enter_battlefield(a, card('Sliver recipient', '', 'Creature — Sliver', '', 1, 1))
            for _ in range(2):
                g.enter_battlefield(a, FOREST)
            assert g.activate_ability(a, recipient, 0, [b])
            assert b.life == 18 and recipient not in a.battlefield

            g, a, b = setup(pilot)
            a.graveyard.append(db.get('Opt'))
            b.graveyard.append(db.get('Shock'))
            elite = g.enter_battlefield(a, db.get('Academy Elite'))
            assert elite.p1 == 2

            g, a, b = setup(pilot)
            donor = g.enter_battlefield(a, BEAR, counters={'+1/+1': 3})
            recipient = g.enter_battlefield(a, BEAR)
            g.enter_battlefield(a, FOREST)
            a.hand.append(db.get('Bioshift'))
            g.main_phase(a)
            assert (donor.p1, recipient.p1) == (0, 3)

            g, a, b = setup(pilot)
            source = g.enter_battlefield(a, db.get('Abuelo, Ancestral Echo'))
            target = g.enter_battlefield(a, BEAR)
            for land in (PLAINS, ISLAND, FOREST):
                g.enter_battlefield(a, land)
            assert g.activate_ability(a, source, 0, [target])
            assert target.front in a.exile
            g.begin_end_step(a)
            g.settle()
            assert any(x.front is target.front for x in a.battlefield)

            g, a, b = setup(pilot)
            g.enter_battlefield(a, db.get('Abiding Grace'))
            a.graveyard.append(db.get('Savannah Lions'))
            g.begin_end_step(a)
            g.settle()
            assert any(x.card.name == 'Savannah Lions' for x in a.creatures)

            g, a, b = setup(pilot)
            source = g.enter_battlefield(a, db.get('Arms Dealer'))
            donor = g.enter_battlefield(a, make_token('Goblin', 1, 1))
            victim = g.enter_battlefield(b, BEAR)
            for land in (MOUNTAIN, FOREST):
                g.enter_battlefield(a, land)
            g.main_phase(a)
            assert donor not in a.battlefield and victim not in b.battlefield and source in a.battlefield

            g, a, b = setup(pilot)
            ajani = g.enter_battlefield(a, db.get('Ajani Resolute'))
            ajani.counters['loyalty'] = 10
            index = next(i for i, (_, effects) in enumerate(ajani.card.loyalty_abilities)
                         if any(e.data.get('token_name') for e in effects))
            assert g.activate_loyalty(a, ajani, index)
            token = next(x for x in a.creatures if x.card.is_token)
            assert token.card.name == "Ajani's Pridemate"
            g.change_life(a, 1, 'smoke')
            g.settle()
            assert token.p1 == 1

            g, a, b = setup(pilot)
            first = g.enter_battlefield(a, BEAR)
            g._aura_host = first
            aura = g.enter_battlefield(a, card('Fixture Aura', '', 'Enchantment — Aura', 'Enchant creature'))
            g.enter_battlefield(a, BEAR)
            g.enter_battlefield(a, db.get('Glamer Spinners'))
            g.settle()
            assert aura.aura_host is not first and aura.aura_host.controller is a

            g, a, b = setup(pilot)
            g.enter_battlefield(b, db.get('Silent Arbiter'))
            attackers = [g.enter_battlefield(a, BEAR) for _ in range(3)]
            for obj in attackers:
                obj.sick = False
            a.ai.choose_attackers = lambda *args: attackers
            g.combat(a, b)
            assert len(g.attackers) <= 1

            g, a, b = setup(pilot)
            for land in (PLAINS, FOREST):
                g.enter_battlefield(a, land)
            a.hand.append(db.get('Abeyance'))
            assert g.cast(a, db.get('Abeyance'), [b])
            b.hand.append(db.get('Shock'))
            g.enter_battlefield(b, MOUNTAIN)
            assert not g.can_cast_now(b, db.get('Shock'))
            assert g.pay(b, {'R': 1}) is not None
            checks.append({'pilot': pilot.__name__, 'all_ten_capability_scenarios': True,
                           'automatic_bioshift': True, 'automatic_grace_mode': True,
                           'automatic_subtype_sacrifice': True, 'automatic_aura_targeting': True,
                           'mana_exception_during_lock': True})
    finally:
        db._all.close()
    report = {'scope': 'Real-database deterministic functional checks with both pilots; no win-rate claim.',
              'checks': checks}
    Path('results/roadmap_batch/smoke.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
