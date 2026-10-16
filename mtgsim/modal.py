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
import dataclasses
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
    upgrades: list = field(default_factory=list)  # (condition, most) from "If X, choose both instead."


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
_UPGRADE = re.compile(r"If (?P<cond>.+), (?:you may )?choose (?P<k>both|one or more|two|three) instead\.", re.I)
# Conditions of "If X, choose both instead." by wording; the value says what is checked in upgrade_active.
# "never" conditions can't hold in this simulator (no commanders), so they need no simplification note.
_UP_COND = [
    (r"(?:this spell|~) was cast using teamwork", "teamwork"),
    (r"you have no cards in hand", "no_hand"),
    (r"there are four or more card types among cards in your graveyard", "delirium"),
    (r"there are eight or more permanent cards in your graveyard as you cast (?:this spell|~)", "gy8"),
    (r"you control (?:a|an) (\w+) as you cast (?:this spell|~)", "subtype"),
    (r"you control six or more lands", "lands6"),
    (r"you control a commander(?: as you cast (?:this spell|~))?", "never"),
]
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
        elif (up := _UPGRADE.fullmatch(sentence)):
            cond = next(((c, re.fullmatch(rx, up["cond"], re.I)) for rx, c in _UP_COND
                         if re.fullmatch(rx, up["cond"], re.I)), None)
            if cond is None:
                notes.append(f"never upgraded: {sentence}")
            else:
                kind, mm = cond
                if kind == "subtype":
                    kind = "subtype:" + mm[1].capitalize()
                spec.upgrades.append((kind, ANY if up["k"].lower() == "one or more" else _COUNT[up["k"].lower()]))
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


def upgrade_active(game, me, cond: str, flags=()) -> bool:
    """Whether the condition of an "If X, choose both instead." sentence holds (checked as the spell is cast)."""
    if cond == "teamwork":
        return "teamwork" in flags
    if cond == "no_hand":
        return not me.hand
    if cond == "delirium":
        types = set()
        for c in me.graveyard:
            types |= {t for t in c.types if t in _CARD_TYPES}
        return len(types) >= 4
    if cond == "gy8":
        return sum(1 for c in me.graveyard if c.is_permanent) >= 8
    if cond.startswith("subtype:"):
        return any(cond[8:] in x.card.subtypes for x in me.battlefield)
    if cond == "lands6":
        return sum(1 for x in me.battlefield if x.card.is_land) >= 6
    return False


_CARD_TYPES = {"Artifact", "Battle", "Creature", "Enchantment", "Instant", "Land", "Planeswalker", "Sorcery",
               "Kindred", "Tribal"}


def _upgraded(game, me, spec, flags) -> ModeSpec:
    """spec with the mode count raised by the first "choose both instead" whose condition holds."""
    for cond, most in spec.upgrades:
        if upgrade_active(game, me, cond, flags):
            return dataclasses.replace(spec, most=most, least=min(spec.least, 1) if most == ANY else spec.least,
                                       upgrades=[])
    return spec


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


def select(game, me, modes, source=None, n: int = 1, least: int | None = None, flags=()) -> list[int]:
    """Indices of the modes to choose (a mode may repeat). Doesn't record anything."""
    spec = _upgraded(game, me, spec_of(modes, n, least), flags)
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


def pick(game, me, modes, source=None, n: int = 1, least: int | None = None, flags=()) -> list:
    """The effects of the chosen modes, in printed order; records "hasn't been chosen" modes."""
    chosen = sorted(select(game, me, modes, source, n, least, flags))
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
