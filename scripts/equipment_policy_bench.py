"""Reproducible Equip policy comparisons, offline and stdlib only.

python3 -m scripts.equipment_policy_bench --games 400 --jobs 2 --output /tmp/equip.json

Controlled 60-card fixtures, not tournament deck recommendations. Opponents keep
the previous Equipment policy, including BaselineAI, to isolate the intervention.
Every game has its own seed and starts alternate; no early stopping. Draws count
half, with approximate Wilson 95% score intervals. Synthetic mixed-cost Equipment
is explicitly identified. No claim about untested ladder decks follows from this.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import random

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Player, choose_equip_cost
from mtgsim.runner import wilson


def previous_cost(game, me, equipment, target, reserve):
    choices = game.equip_choices(me, equipment, target, reserve=reserve, keep_target=True)
    return choices[0] if choices else None


class MeasuredPolicy:
    def choose_equip_cost(self, game, me, equipment, target, reserve):
        choice = (choose_equip_cost if self.new_policy else previous_cost)(game, me, equipment, target, reserve)
        self.counts["decisions"] += 1
        if choice is None:
            self.counts["declined"] += 1
        else:
            idx, victim = choice
            self.counts["sacrifice" if victim is not None else "mana_only"] += 1
            self.counts["mana_chosen"] += sum(game.equip_cost(equipment, target, idx).values())
        return choice


class MeasuredHeuristic(MeasuredPolicy, HeuristicAI):
    def __init__(self, new_policy, counts):
        super().__init__()
        self.new_policy, self.counts = new_policy, counts


class MeasuredBaseline(MeasuredPolicy, BaselineAI):
    def __init__(self, counts):
        self.new_policy, self.counts = False, counts


FIXTURES = {
    "hauberk_bodies": {"Forest": 24, "Demonmail Hauberk": 4, "Grizzly Bears": 8,
                       "Elvish Visionary": 8, "Llanowar Elves": 4,
                       "Centaur Courser": 8, "Giant Growth": 4},
    "tools_fodder": {"Plains": 24, "Demonmail Hauberk": 4, "Dissection Tools": 4,
                     "Leonin Scimitar": 4, "Savannah Lions": 4, "Doomed Traveler": 4,
                     "Garrison Cat": 4, "Raise the Alarm": 4, "Serra Angel": 4,
                     "Silvercoat Lion": 4},
    "synthetic_cost_choice": {"Plains": 24, "Policy Benchmark Blade": 4,
                              "Savannah Lions": 8, "Doomed Traveler": 8,
                              "Raise the Alarm": 8, "Serra Angel": 4, "Silvercoat Lion": 4},
}


def fixture_deck(name):
    db = CardDB(offline=True)
    synthetic = card_from_scryfall({"name": "Policy Benchmark Blade", "mana_cost": "{2}", "cmc": 2,
                                   "type_line": "Artifact — Equipment",
                                   "oracle_text": "Equipped creature gets +3/+3.\nEquip {6}\nEquip—Sacrifice a creature."})
    cards = {n: synthetic if n == synthetic.name else db.get(n) for n, count in FIXTURES[name].items() if count}
    for c in cards.values():
        if c.unsupported:
            raise ValueError(f"Unsupported fixture text: {c.name}: {c.unsupported}")
    deck = [cards[n] for n, count in FIXTURES[name].items() for _ in range(count)]
    assert len(deck) == 60
    return deck


def measure(args):
    fixture, matchup, games, seed = args
    deck = fixture_deck(fixture)
    scores, counts_a, counts_b = [], Counter(), Counter()
    wins = losses = draws = 0
    play_points = draw_points = 0
    for i in range(games):
        new_policy = matchup != "previous_vs_baseline"
        ai_a = MeasuredHeuristic(new_policy, counts_a)
        ai_b = MeasuredHeuristic(False, counts_b) if matchup == "new_vs_previous" else MeasuredBaseline(counts_b)
        a, b = Player("A", deck, ai_a), Player("B", deck, ai_b)
        game = Game(*((a, b) if i % 2 == 0 else (b, a)), rng=random.Random(seed + i))
        winner = game.play()
        wins += winner is a
        losses += winner is b
        draws += winner is None
        score = 1 if winner is a else 0 if winner is b else 0.5
        scores.append(score)
        if i % 2 == 0:
            play_points += score
        else:
            draw_points += score
    result = dict(fixture=fixture, matchup=matchup, games=games, seed=seed, wins=wins, losses=losses, draws=draws,
                  score=sum(scores) / games, ci95=wilson(sum(scores), games),
                  play_points=play_points, draw_points=draw_points,
                  policy_a=dict(counts_a), policy_b=dict(counts_b), scores=scores)
    print(f"{fixture} {matchup}: {result['score']:.1%}, 95% {result['ci95'][0]:.1%}–{result['ci95'][1]:.1%}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=400)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=182000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.games < 2 or args.games % 2:
        parser.error("--games must be positive and even, for balanced starts")
    work = [(name, matchup, args.games, args.seed + n * 100000)
            for n, name in enumerate(FIXTURES)
            for matchup in ("new_vs_previous", "new_vs_baseline", "previous_vs_baseline")]
    if args.jobs == 1:
        results = list(map(measure, work))
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(measure, work))
    deltas = []
    for name in FIXTURES:
        after = next(r for r in results if r["fixture"] == name and r["matchup"] == "new_vs_baseline")
        before = next(r for r in results if r["fixture"] == name and r["matchup"] == "previous_vs_baseline")
        diffs = [a - b for a, b in zip(after["scores"], before["scores"])]
        mean = sum(diffs) / len(diffs)
        se = (sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1) / len(diffs)) ** 0.5
        deltas.append(dict(fixture=name, paired_score_delta=mean, approximate_paired_ci95=[mean - 1.96 * se, mean + 1.96 * se]))
    args.output.write_text(json.dumps(dict(games_per_cell=args.games, fixtures=FIXTURES, results=results,
                                         paired_baseline_deltas=deltas), indent=2) + "\n")


if __name__ == "__main__":
    main()
