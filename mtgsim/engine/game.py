"""The Game class: a two-player game assembled from the rules mixins in this package."""
from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

from .. import rules_events, that_much
from .abilities import AbilitiesMixin
from .battlefield import BattlefieldMixin
from .combat import CombatMixin
from .costs import CostsMixin
from .effects import EffectsMixin
from .play import PlayMixin
from .policy import DEFAULTS
from .resolve import ResolveMixin
from .stack import StackMixin
from .targets import TargetsMixin
from .turns import TurnsMixin

if TYPE_CHECKING:
    from .state import Permanent, Player, StackItem


class Game(CostsMixin, TargetsMixin, TurnsMixin, StackMixin, PlayMixin, AbilitiesMixin, BattlefieldMixin,
           ResolveMixin, EffectsMixin, CombatMixin):
    def __init__(self, p1: Player, p2: Player, rng: random.Random, max_turns: int = 60, log: bool = False):
        self.end_cleanup: list = []   # (token, "sacrifice" | "exile"): goes away at the beginning of the next end step
        self.blinked: list = []       # (card, owner): returns at the beginning of the next end step
        self.control_effects: list = []  # timestamped (target, controller, source, until_eot)
        self.players = [p1, p2]       # p1 is on the play
        self.effect_clock = 0
        self.continuous_effects = []
        p1._game = p2._game = self
        p1.foe, p2.foe = p2, p1
        p1.opponent, p2.opponent = p2, p1
        self.rng = rng
        self.max_turns = max_turns
        self.turn = 0
        self.creature_died_turn = False
        self.active_idx = 0
        self.winner: Player | None = None
        self.log_enabled = log
        self.events: list[str] = []
        self.rule_events = rules_events.EventBus(capture=log)
        self.step = "main1"
        self.stack: list[StackItem] = []
        self.no_lifegain_turn: set[Player] = set()   # "players can't gain life this turn" (Skullcrack family)
        self.no_prevention_turn = False              # "damage can't be prevented this turn"
        self.pending: list[tuple] = []   # triggered abilities waiting to be put on the stack
        self.delayed_upkeep: list[tuple] = []  # (controller, amount, source, name, scope)
        self.delayed_end_step: list[tuple] = []
        self.extra_combats = 0
        self.rebound_upkeep: list[tuple] = []  # (controller, exiled card, zone version)
        self.extra_turns: list = []                # players who take an extra turn after this one
        self.end_combat_effects: list[tuple] = []  # (controller, effects, source, that creature): "at end of combat"
        self.delayed_end_combat: list[tuple] = []  # (trigger controller, exact permanent to sacrifice)
        self.attackers: list[Permanent] = []
        self.attack_targets: dict = {}   # attacker -> Player or planeswalker Permanent
        self.blocks: dict = {}
        self._priority_depth = 0
        self._variants: dict = {}

    def log(self, msg, who: "Player | None" = None):
        if self.log_enabled:
            self.events.append(f"T{self.turn} {(who or self.players[self.active_idx]).name}: {msg}")

    def audit(self, event, **fields):
        """Machine-readable records alongside prose; seats are indices in players."""
        if self.log_enabled:
            self.events.append("AUDIT " + json.dumps(
                {"event": event, "player_turn": self.turn, **fields}, ensure_ascii=False))

    def change_life(self, player, delta, cause):
        before = player.life
        if delta > 0:
            if player in self.no_lifegain_turn:      # turn-scoped: the statics below can also block the gain
                return
            from ..batch1_templates import lifegain_blocked
            if lifegain_blocked(self, player):
                return
            delta = that_much.gain_amount(self, player, delta)
        elif delta < 0:
            delta = -that_much.loss_amount(self, player, -delta)
        player.life += delta
        delta = player.life - before
        if delta > 0:
            player.life_gained_turn += delta
            self.event_amount = delta
            self.fire(player, "gain_life")
            # the other player's "whenever an opponent gains life" listeners (Punishing Fire cluster)
            self.fire(self.opponent(player), "opp_gain_life", context=player)
            self.event_amount = None
        elif delta < 0:
            self.event_amount = -delta
            self.fire(self.opponent(player), "opp_loses_life")
            self.event_amount = None
        if delta < 0 and player is not self.active and self.active.speed_turn != self.turn and \
                0 < self.active.speed < 4:
            self.active.speed += 1               # an opponent lost life on your turn
            self.active.speed_turn = self.turn
        if delta and self.log_enabled:
            self.audit("life", seat=self.players.index(player), before=before,
                       delta=delta, after=player.life, cause=cause)

    def opponent(self, p: Player) -> Player:
        return self.players[1] if p is self.players[0] else self.players[0]

    def named_cast_banned(self, card) -> bool:
        """"Spells with the chosen name can't be cast" (Meddling Mage): whether any permanent
        on the battlefield chose this card's name. Consulted by the cast-legality check."""
        name = getattr(card, "name", "")
        return bool(name) and any(x.chosen_name == name for pl in self.players for x in pl.battlefield
                                 if not x.abilities_suppressed)

    @property
    def active(self) -> Player: return self.players[self.active_idx]

    @property
    def over(self): return any(p.lost for p in self.players)

    def hook(self, p: Player, name: str):
        """p's AI hook ``name`` if it defines one, else the default policy below."""
        return getattr(p.ai, name, None) or (lambda game, me, *a: DEFAULTS[name](game, me, *a))
