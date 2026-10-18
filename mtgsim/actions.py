"""Shared action entry point and engine-state transactions.

Card definitions and policy objects are inputs, not rollback participants. Policy
hooks must return choices without writing external state. Events are published
only after an action commits; priority/resolution runs after the transaction.
"""
from dataclasses import dataclass, fields
from functools import wraps

from .cards import CardDef
from .identity import CardInstance

_DEFINITION_FIELDS = frozenset(f.name for f in fields(CardDef))


class Transaction:
    def __init__(self, game):
        self.game = game
        self.saved = []
        self.seen = set()
        self.commit = False

    def capture(self, obj):
        if id(obj) in self.seen:
            return
        self.seen.add(id(obj))
        if isinstance(obj, (list, dict, set)):
            contents = obj.copy() if isinstance(obj, (dict, set)) else list(obj)
            self.saved.append((obj, 'container', contents))
            values = list(obj.values()) if isinstance(obj, dict) else list(obj)
            for value in values:
                self.capture(value)
            if hasattr(obj, '__dict__'):
                self.capture_dict(obj)
        elif isinstance(obj, tuple):
            for value in obj:
                self.capture(value)
        elif isinstance(obj, CardInstance):
            self.capture_dict(obj, _DEFINITION_FIELDS | {'definition'})
        elif isinstance(obj, CardDef):
            self.capture_dict(obj, _DEFINITION_FIELDS)
        elif type(obj).__module__.startswith('mtgsim.engine.'):
            self.capture_dict(obj)

    def capture_dict(self, obj, skip=frozenset()):
        state = dict(obj.__dict__)
        self.saved.append((obj, 'object', state))
        for key, value in state.items():
            if key not in skip:
                self.capture(value)

    def __enter__(self):
        self.capture(self.game)
        self.rng_state = self.game.rng.getstate()
        self.game._action_depth = getattr(self.game, '_action_depth', 0) + 1
        self.game.rule_events.begin()
        return self

    def __exit__(self, kind, error, tb):
        success = self.commit and kind is None
        # The bus is deliberately outside the captured runtime graph.
        if not success:
            self.game.rule_events.finish(False)
        if not success:
            for obj, category, state in reversed(self.saved):
                if category == 'object':
                    obj.__dict__.clear()
                    obj.__dict__.update(state)
                elif isinstance(obj, list):
                    list.__setitem__(obj, slice(None), state)
                elif isinstance(obj, dict):
                    dict.clear(obj)
                    dict.update(obj, state)
                else:
                    set.clear(obj)
                    set.update(obj, state)
            self.game.rng.setstate(self.rng_state)
        else:
            self.game._action_depth -= 1
            self.game.rule_events.finish(True)
        return False


def atomic_action(method):
    @wraps(method)
    def run(game, *args, **kwargs):
        with Transaction(game) as tx:
            tx.capture(args)
            tx.capture(kwargs)
            result = method(game, *args, **kwargs)
            tx.commit = bool(result)
        if result:
            game.settle()
        return result
    return run


@dataclass(frozen=True)
class Action:
    kind: str
    source: object
    option: object = None
    targets: object = None

    @classmethod
    def from_legacy(cls, action):
        if isinstance(action, cls):
            return action
        if action[0] in ('loyalty', 'activate'):
            return cls(action[0], action[1], action[2], action[3] if len(action) > 3 else None)
        return cls('cast', action[0], targets=action[1])


@atomic_action
def perform(game, player, action):
    action = Action.from_legacy(action)
    if action.kind == 'cast':
        return game.can_cast_now(player, action.source) and game.cast(player, action.source, action.targets)
    if action.kind == 'loyalty':
        return game.activate_loyalty(player, action.source, action.option, action.targets)
    if action.kind == 'activate':
        return game.activate(player, action.source, action.option, action.targets)
    if action.kind == 'equip':
        return game.equip(player, action.source, action.targets)
    return False


def can_perform(game, player, action):
    """Probe the same payment/choice path, restoring engine state and RNG."""
    action = Action.from_legacy(action)
    with Transaction(game) as transaction:
        transaction.capture(action.source)
        transaction.capture(action.targets)
        return bool(perform(game, player, action))
