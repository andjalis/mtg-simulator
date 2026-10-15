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
    play_draw_known: bool = True   # True only when every game's first player is known
    games_a_on_draw: int = 0
    wins_a_on_draw: int = 0
    draws_a_on_play: int = 0
    draws_a_on_draw: int = 0
    game_metadata: list = field(default_factory=list)

    def add_game(self, winner, first_player, player_turns, **metadata):
        """Seats: 0=A, 1=B, None=unknown (or draw for winner)."""
        self.games += 1
        self.wins_a += winner == 0
        self.wins_b += winner == 1
        self.draws += winner is None
        if first_player == 0:
            self.games_a_on_play += 1
            self.wins_a_on_play += winner == 0
            self.draws_a_on_play += winner is None
        elif first_player == 1:
            self.games_a_on_draw += 1
            self.wins_a_on_draw += winner == 0
            self.draws_a_on_draw += winner is None
        else:
            self.play_draw_known = False
        if player_turns is not None:
            self.turns.append(player_turns)
        self.game_metadata.append(dict(winner=winner, first_player=first_player,
                                       player_turns=player_turns, **metadata))

    @property
    def win_rate_a(self) -> float:
        """Draws count as half a win."""
        return (self.wins_a + 0.5 * self.draws) / self.games if self.games else 0.0

    def summary(self) -> str:
        lo, hi = wilson(self.wins_a + 0.5 * self.draws, self.games)
        avg_turns = sum(self.turns) / len(self.turns) if self.turns else 0
        lines = [
            f"{self.deck_a} vs {self.deck_b}: {self.games} games",
            f"  {self.deck_a} wins {self.wins_a}, {self.deck_b} wins {self.wins_b}, draws {self.draws}",
            f"  {self.deck_a} score {self.win_rate_a:.1%} (draws count half; approximate 95% interval {lo:.1%} to {hi:.1%})",
        ]
        if self.games_a_on_play + self.games_a_on_draw:
            lines += [
                f"  {self.deck_a} on the play {self.wins_a_on_play}/{self.games_a_on_play}, "
                f"on the draw {self.wins_a_on_draw}/{self.games_a_on_draw} wins; "
                f"draws {self.draws_a_on_play}/{self.draws_a_on_draw}, "
                f"unknown first player {self.games - self.games_a_on_play - self.games_a_on_draw}",
            ]
        if self.turns:
            lines.append(f"  average game length {avg_turns:.1f} player-turns "
                         f"({len(self.turns)}/{self.games} games known)")
        return "\n".join(lines)


def run_match(name_a, deck_a, name_b, deck_b, games=1000, seed=None, ai_a=None, ai_b=None,
              log_first=False, on_game=None, log_game=None) -> tuple[MatchResult, list[str]]:
    """on_game(res), if given, is called with the running MatchResult after every game."""
    rng = random.Random(seed)
    res = MatchResult(name_a, name_b)
    first_log: list[str] = []
    for i in range(games):
        a = Player(name_a, deck_a, ai_a or HeuristicAI())
        b = Player(name_b, deck_b, ai_b or HeuristicAI())
        a_on_play = i % 2 == 0
        game = Game(*((a, b) if a_on_play else (b, a)), rng=rng,
                    log=log_game is not None or (log_first and i == 0))
        winner = game.play()
        if i == 0:
            first_log = game.events
        res.add_game(0 if winner is a else 1 if winner is b else None,
                     0 if a_on_play else 1, game.turn, game_number=i + 1)
        if log_game is not None:
            log_game(i + 1, game.events)
        if on_game:
            on_game(res)
    return res, first_log


def unsupported_report(name: str, deck: list[CardDef]) -> list[str]:
    seen, lines = set(), []
    for card in deck:
        if card.unsupported and card.name not in seen:
            seen.add(card.name)
            lines.append(f"  {name}: {card.name} — ignored text: {' | '.join(card.unsupported)}")
    return lines
