"""Run many AI-vs-AI games between decks and summarise the results."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .ai import HeuristicAI
from .carddb import CardDB
from .cards import CardDef
from .engine import Game, Player


def build_deck(db: CardDB, counts: dict[str, int]) -> list[CardDef]:
    db.ensure(counts)
    return [db.get(name) for name, n in counts.items() for _ in range(n)]


def wilson(wins: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / d, (c + r) / d


@dataclass
class MatchResult:
    deck_a: str
    deck_b: str
    games: int = 0
    wins_a: int = 0
    wins_b: int = 0
    draws: int = 0
    wins_a_on_play: int = 0
    games_a_on_play: int = 0
    turns: list = field(default_factory=list)
    play_draw_known: bool = True   # Forge doesn't report who went first or game length

    @property
    def win_rate_a(self) -> float:
        """Draws count as half a win."""
        return (self.wins_a + 0.5 * self.draws) / self.games if self.games else 0.0

    def summary(self) -> str:
        lo, hi = wilson(self.wins_a + 0.5 * self.draws, self.games)
        on_draw = self.games - self.games_a_on_play
        wins_on_draw = self.wins_a - self.wins_a_on_play
        avg_turns = sum(self.turns) / len(self.turns) if self.turns else 0
        lines = [
            f"{self.deck_a} vs {self.deck_b}: {self.games} games",
            f"  {self.deck_a} wins {self.wins_a}, {self.deck_b} wins {self.wins_b}, draws {self.draws}",
            f"  {self.deck_a} win rate {self.win_rate_a:.1%} (95% CI {lo:.1%} to {hi:.1%})",
        ]
        if self.play_draw_known:
            lines += [
                f"  {self.deck_a} on the play {self.wins_a_on_play}/{self.games_a_on_play}, "
                f"on the draw {wins_on_draw}/{on_draw}",
                f"  average game length {avg_turns:.1f} turns ({avg_turns / 2:.1f} per player)",
            ]
        return "\n".join(lines)


def run_match(name_a, deck_a, name_b, deck_b, games=1000, seed=None, ai_a=None, ai_b=None,
              log_first=False) -> tuple[MatchResult, list[str]]:
    rng = random.Random(seed)
    res = MatchResult(name_a, name_b)
    first_log: list[str] = []
    for i in range(games):
        a = Player(name_a, deck_a, ai_a or HeuristicAI())
        b = Player(name_b, deck_b, ai_b or HeuristicAI())
        a_on_play = i % 2 == 0
        game = Game(*((a, b) if a_on_play else (b, a)), rng=rng, log=log_first and i == 0)
        winner = game.play()
        if i == 0:
            first_log = game.events
        res.games += 1
        res.turns.append(game.turn)
        res.games_a_on_play += a_on_play
        if winner is a:
            res.wins_a += 1
            res.wins_a_on_play += a_on_play
        elif winner is b:
            res.wins_b += 1
        else:
            res.draws += 1
    return res, first_log


def unsupported_report(name: str, deck: list[CardDef]) -> list[str]:
    seen, lines = set(), []
    for card in deck:
        if card.unsupported and card.name not in seen:
            seen.add(card.name)
            lines.append(f"  {name}: {card.name} — ignored text: {' | '.join(card.unsupported)}")
    return lines
