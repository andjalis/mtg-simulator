"""Modal spells, triggers and abilities.

Covers the mode headers of current Standard: "Choose one —", "Choose two —", "Choose three.",
"Choose one or both —", "Choose one or more —", "Choose any number —", "Choose up to N —",
"choose one that hasn't been chosen [this turn] —", "You may choose the same mode more than once."
and pawprint modes ("Choose up to five {P} worth of modes." with "{P}{P} — EFFECT" lines). Named
modes ("• Puff Piece — EFFECT") lose their name. An upgrade sentence ("If this spell was cast
using teamwork, choose both instead.") is played without the upgrade and reported as simplified.

`cards.py` parses headers and bullet lines with `parse_header` / `parse_bullet` and keeps the
modes in a `Modes` list, which carries its `ModeSpec`. The engine calls `pick` when a modal spell,
trigger or ability goes on the stack, and `value` to judge whether one is worth casting. The
simple case (at most N modes, each once) goes through the player's ``choose_modes`` hook, so an
AI can override it; repeated and pawprint modes are chosen here greedily by `_mode_value`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ANY = 99      # "choose one or more" / "any number": capped at the number of modes

_COUNT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "both": 2}


@dataclass
class ModeSpec:
    most: int = 1                 # most modes to choose
    least: int = 1                # fewest ("choose up to" / "any number": 0)
    repeat: bool = False          # "You may choose the same mode more than once."
    unique: str = ""              # "turn" / "ever": a mode that was chosen can't be chosen again
    budget: int = 0               # pawprint: total {P} to spend
    costs: list = field(default_factory=list)    # pawprint cost of each mode


class Modes(list):
    """The modes of a spell or ability (one effect list each), with how to choose among them."""

    def __init__(self, items=(), spec: ModeSpec | None = None):
        super().__init__(items)
        self.spec = spec or ModeSpec()


def spec_of(modes, n: int = 1, least: int | None = None) -> ModeSpec:
    """The ModeSpec of modes; a plain list means "choose n" (or "up to n" with least=0)."""
    spec = getattr(modes, "spec", None)
    return spec if spec is not None else ModeSpec(most=n, least=n if least is None else least)


# ---------------------------------------------------------------- parsing

_HEAD = re.compile(
    r"(?:[A-Z][\w' ]*?(?: \d+)? — )?"           # ability word: "Descend 8 — ", "Delirium — "
    r"choose (?P<n>one|two|three|four|five|any number|up to (?:one|two|three|four|five))"
    r"(?P<more> or both| or more)?(?P<uniq> that hasn't been chosen(?P<turn> this turn)?)?"
    r" ?(?P<end>—|-|\.)(?P<rest>.*)", re.I | re.S)
_PAW = re.compile(r"Choose up to (\w+) \{P\} worth of modes\.(?P<rest>.*)", re.I | re.S)
_UPGRADE = re.compile(r"If .+, (?:you may )?choose (?:both|one or more|two|three) instead\.", re.I)
_BULLET = re.compile(r"(?:• ?(?P<paw1>(?:\{P\})+ — )?|(?P<paw2>(?:\{P\})+) — )"
                     r"(?:[A-Z][\w' ,!-]{0,30}? — )?(?P<body>.+)", re.S)


def parse_header(line: str):
    """(ModeSpec, simplification notes) for a mode header line, else None."""
    m = _PAW.fullmatch(line.strip())
    if m:
        if m[1].lower() not in _COUNT:
            return None
        spec = ModeSpec(most=ANY, least=1, budget=_COUNT[m[1].lower()])
    else:
        m = _HEAD.fullmatch(line.strip())
        if not m or (m["end"] == "." and m["uniq"]):
            return None
        n = m["n"].lower()
        if n == "any number":
            spec = ModeSpec(most=ANY, least=0)
        elif n.startswith("up to "):
            spec = ModeSpec(most=_COUNT[n[6:]], least=0)
        elif m["more"]:
            spec = ModeSpec(most=2 if "both" in m["more"] else ANY, least=1)
        else:
            spec = ModeSpec(most=_COUNT[n], least=_COUNT[n])
        if m["uniq"]:
            spec.unique = "turn" if m["turn"] else "ever"
    notes = []
    for sentence in re.split(r"(?<=\.)\s+", m["rest"].strip()):
        if not sentence:
            continue
        if sentence == "You may choose the same mode more than once.":
            spec.repeat = True
        elif _UPGRADE.fullmatch(sentence):
            notes.append(f"never upgraded: {sentence}")
        else:
            return None
    return spec, notes


def parse_bullet(line: str):
    """(pawprint cost, effect text) for a mode line ("• EFFECT", "{P}{P} — EFFECT"), else None."""
    m = _BULLET.fullmatch(line.strip())
    if not m:
        return None
    paw = m["paw1"] or m["paw2"] or ""
    return paw.count("{P}"), m["body"]


def add_mode(modes, effects: list, cost: int = 0):
    modes.append(effects)
    if isinstance(modes, Modes) and modes.spec.budget:
        modes.spec.costs.append(cost or 1)


# ---------------------------------------------------------------- choosing

def _used_key(modes, i):
    return ("mode", id(modes), i)


def _available(game, modes, spec, source) -> list[int]:
    idx = list(range(len(modes)))
    if spec.unique and source is not None:
        turns = source.ability_turns
        idx = [i for i in idx if (k := _used_key(modes, i)) not in turns
               or (spec.unique == "turn" and turns[k] != game.turn)]
    return idx


def _greedy(game, me, modes, spec, avail) -> list[int]:
    """Repeated or pawprint modes: the best value per {P} each time, a mode worth less each
    time it is picked again (its targets are likely taken)."""
    from .engine import _mode_value
    base = {i: _mode_value(game, me, modes[i]) for i in avail}
    cost = {i: (spec.costs[i] if spec.budget and i < len(spec.costs) else 1) for i in avail}
    left = spec.budget or min(spec.most, ANY)
    picked: list[int] = []
    while left > 0 and (spec.budget or len(picked) < spec.most):
        opts = [i for i in avail if cost[i] <= left and (spec.repeat or i not in picked)]
        scored = [(base[i] / (1 + picked.count(i)) / cost[i], i) for i in opts]
        scored = [s for s in scored if s[0] > 0]
        if not scored:
            break
        i = max(scored)[1]
        picked.append(i)
        left -= cost[i]
    while len(picked) < spec.least and avail:      # must choose: the least harmful
        rest = [i for i in avail if spec.repeat or i not in picked]
        if not rest:
            break
        picked.append(max(rest, key=lambda i: (base[i], -cost[i])))
    return picked


def select(game, me, modes, source=None, n: int = 1, least: int | None = None) -> list[int]:
    """Indices of the modes to choose (a mode may repeat). Doesn't record anything."""
    spec = spec_of(modes, n, least)
    avail = _available(game, modes, spec, source)
    if not avail:
        return []
    if spec.repeat or spec.budget:
        return _greedy(game, me, modes, spec, avail)
    sub = [modes[i] for i in avail]
    hook = game.hook(me, "choose_modes")
    most = min(spec.most, len(sub))
    picks = hook(game, me, sub, most, True)
    if len(picks) < spec.least:
        picks = hook(game, me, sub, min(spec.least, len(sub)), False)
    return [avail[i] for i in picks]


def pick(game, me, modes, source=None, n: int = 1, least: int | None = None) -> list:
    """The effects of the chosen modes, in printed order; records "hasn't been chosen" modes."""
    chosen = sorted(select(game, me, modes, source, n, least))
    spec = spec_of(modes, n, least)
    if spec.unique and source is not None:
        for i in chosen:
            source.ability_turns[_used_key(modes, i)] = game.turn
    if chosen:
        game.log(f"chooses mode{'s' if len(chosen) > 1 else ''} {', '.join(str(i + 1) for i in chosen)}", me)
    return [e for i in chosen for e in modes[i]]


def value(game, me, modes, source=None, n: int = 1, least: int | None = None) -> float:
    """What choosing modes now is worth (the modes `select` would choose), -1 if none."""
    from .engine import _mode_value
    chosen = select(game, me, modes, source, n, least)
    if not chosen:
        return -1
    return sum(_mode_value(game, me, modes[i]) / (1 + chosen[:k].count(i)) for k, i in enumerate(chosen))
