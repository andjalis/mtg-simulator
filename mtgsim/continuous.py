"""Scoped continuous effects: keywords (6), base P/T (7b), modifiers and
counters (7c), and switching (7d). This is not the complete CR 613 system:
copy, control, text, type, color and characteristic-defining effects remain outside.
Dependencies are explicit inputs; Oracle dependency inference is not implemented.
"""
from dataclasses import dataclass

LAYERS = {'grant': (6, 0), 'remove': (6, 0), 'set_base': (7, 1),
          'modify': (7, 2), 'switch': (7, 3)}


@dataclass(frozen=True)
class ContinuousEffect:
    id: int
    target: object
    operation: str
    timestamp: int
    power: int = 0
    toughness: int = 0
    keyword: str = ''
    depends_on: tuple = ()
    source: object = None
    until_eot: bool = False

    @property
    def layer(self):
        return LAYERS[self.operation]


def ordered(effects):
    """Layer first, then explicit same-layer dependencies and timestamps.

    When dependency ordering has a cycle, ignore dependencies within that cycle
    and order those effects by timestamp; dependents still follow the cycle.
    """
    result = []
    for layer in sorted({e.layer for e in effects}):
        remaining = {e.id: e for e in effects if e.layer == layer}
        def reaches(start, current, seen):
            for dep in remaining[current].depends_on:
                if dep == start:
                    return True
                if dep in remaining and dep not in seen and reaches(start, dep, seen | {dep}):
                    return True
            return False
        # Ignore internal edges of each strongly connected dependency component.
        dependencies = {e.id: {d for d in e.depends_on if d in remaining and
                         not reaches(e.id, d, {d})} for e in remaining.values()}
        while remaining:
            ready = [e for e in remaining.values() if not (dependencies[e.id] & remaining.keys())]
            effect = min(ready, key=lambda e: (e.timestamp, e.id))
            result.append(effect)
            del remaining[effect.id]
    return result


def active(permanent):
    game = getattr(permanent.controller, '_game', None)
    if game is None:
        return []
    return [e for e in game.continuous_effects if e.target is permanent and
            permanent in permanent.controller.battlefield and (e.source is None or
            e.source in e.source.controller.battlefield)]


def base_effects(permanent):
    effects = []
    animation = permanent.animated
    if animation and animation.kind == 'animate':
        stamp = getattr(permanent, 'animation_timestamp', 0)
        effects.append(ContinuousEffect(-1, permanent, 'set_base', stamp,
                                        animation.power, animation.toughness))
    for i, aura in enumerate(permanent.auras):
        if 'base_1_1' in aura.card.aura_flags:
            effects.append(ContinuousEffect(-2-i, permanent, 'set_base',
                getattr(aura, 'attachment_timestamp', 0), 1, 1))
    return effects


def pt(permanent):
    p, t = permanent.card.power or 0, permanent.card.toughness or 0
    effects = active(permanent)
    for effect in ordered(base_effects(permanent) + [e for e in effects if e.operation == 'set_base']):
        p, t = effect.power, effect.toughness
    bp, bt = permanent._pt_bonus()
    p += bp + permanent.pump_p
    t += bt + permanent.pump_t
    for effect in ordered([e for e in effects if e.operation == 'modify']):
        p += effect.power
        t += effect.toughness
    counters = permanent.counters.get('+1/+1', 0) - permanent.counters.get('-1/-1', 0)
    p, t = p + counters, t + counters
    for effect in ordered([e for e in effects if e.operation == 'switch']):
        p, t = t, p
    return p, t


def keyword(permanent, kw, initial):
    value = initial
    for effect in ordered([e for e in active(permanent) if e.layer == (6, 0) and e.keyword == kw]):
        value = effect.operation == 'grant'
    return value


def add(game, target, operation, *, power=0, toughness=0, keyword='', depends_on=(), source=None, until_eot=False):
    if operation not in LAYERS:
        raise ValueError('unsupported continuous-effect operation')
    existing = {e.id: e for e in game.continuous_effects}
    if any(d not in existing or existing[d].layer != LAYERS[operation] for d in depends_on):
        raise ValueError('dependencies must name existing effects in the same layer')
    stamp = game.next_effect_timestamp()
    effect = ContinuousEffect(stamp, target, operation, stamp, power, toughness,
                              keyword, tuple(depends_on), source, until_eot)
    game.continuous_effects.append(effect)
    return effect
