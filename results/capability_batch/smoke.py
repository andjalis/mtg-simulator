"""Real-database functional checks; run from the repository root with PYTHONPATH=."""
import json
import random
import re
from pathlib import Path

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, FOREST, ISLAND

re._MAXCACHE = 32768


def setup(pilot):
    a, b = Player('a', [], pilot()), Player('b', [], pilot())
    game = Game(a, b, random.Random(17))
    game.turn, game.step = 2, 'main2'
    for player in (a, b):
        player.library = [ISLAND] * 40
        player.ai.choose_graft = lambda *args: False
    return game, a, b


def main():
    db = CardDB(offline=True)
    records = []
    try:
        for pilot in (HeuristicAI, BaselineAI):
            game, a, b = setup(pilot)
            automaton = game.enter_battlefield(a, db.get('Mindless Automaton'))
            game.settle()
            game.main_phase(a)
            assert automaton not in a.battlefield and len(a.hand) == 1

            game, a, b = setup(pilot)
            land = game.enter_battlefield(b, ISLAND)
            slime = db.get('Acidic Slime')
            assert not slime.unsupported
            game.enter_battlefield(a, slime)
            game.settle()
            assert land not in b.battlefield and land.front in b.graveyard

            game, a, b = setup(pilot)
            memorial = db.get("Akroma's Memorial")
            assert not memorial.unsupported
            game.enter_battlefield(a, memorial)
            ally = game.enter_battlefield(a, BEAR)
            assert all(ally.has(kw) for kw in ('flying', 'first strike', 'vigilance', 'trample',
                                             'haste', 'protection from black', 'protection from red'))

            game, a, b = setup(pilot)
            source = game.enter_battlefield(a, db.get('Vorel of the Hull Clade'))
            source.sick = False
            target = game.enter_battlefield(a, db.get('Darksteel Forge'), counters={'charge': 3})
            game.enter_battlefield(a, FOREST)
            game.enter_battlefield(a, ISLAND)
            game.settle()
            game.main_phase(a)
            assert target.counters['charge'] == 6
            records.append({'pilot': pilot.__name__, 'automatic_automaton_counter_draw': True,
                            'automatic_slime_land_target': True, 'memorial_keyword_list': True,
                            'automatic_vorel_counter_doubling': True})
    finally:
        db._all.close()
    report = {'scope': 'Deterministic functional checks using real database cards; no win-rate claim.',
              'checks': records}
    Path('results/capability_batch/smoke.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
