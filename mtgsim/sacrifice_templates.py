"""Sacrifice family templates: optional self-sacrifice payoffs and edict wording variants.

Joined at the end of ``cards/__init__.py``. "You may sacrifice it. If you do, <payoff>"
becomes a SACSELF effect: the handler sacrifices the source when the trigger resolves and
then queues the payoff. "Sacrifices a <permanent> of their choice" is the plain edict
wording the existing templates implement, so SUBS normalizes it away.
"""
from __future__ import annotations

import re


EFFECT_PATTERNS = [
    (r"SACSELF (.+)", lambda m: _sac_self(m)),
    # "At the beginning of your upkeep, sacrifice ~ unless you discard a card." (Masticore cycle)
    (r"sacrifice (?:~|it|this card|this creature) unless you discard (a|one|two) cards?",
     lambda m: _e("sac_unless_discard", _num(m[1]))),
]

SUBS = [
    # "Each player sacrifices a creature of their choice" is the plain edict wording.
    (re.compile(r"(sacrifices? [a-z][^.;\n]*?) of their choice", re.I), r"\1"),
    # "You may sacrifice it. If you do, <payoff>" / "Sacrifice it. When you do, <payoff>".
    (re.compile(r"(you may sacrifice (?:it|~|this (?:card|creature|land|artifact|enchantment|permanent))"
                r"\. (?:if|when) you do, )(.+)", re.I), lambda m: _gate_sub(m)),
    (re.compile(r"(sacrifice (?:it|~|this (?:card|creature|land|artifact|enchantment|permanent))\. "
                r"when you do, )(.+)", re.I), lambda m: _gate_sub(m)),
]


def _gate_sub(m):
    """Rewrite into the SACSELF sentinel only when the payoff parses; leave the original
    wording (so it stays a readable ignored line) when it does not."""
    from .cards import _parse_effects
    effects, bad = _parse_effects(m[2])
    if not effects or bad:
        return m[0]
    return f"SACSELF {m[2]}"


def _sac_self(m):
    """Wrap the payoff in a sac_self_payoff effect: sacrifice the source, then run it."""
    from .cards import NO_MATCH, Effect, _parse_effects
    body = m[1].strip()
    effects, bad = _parse_effects(body[0].upper() + body[1:])
    if not effects or bad:
        return NO_MATCH
    return Effect("sac_self_payoff", data={"effects": effects})


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _num(word):
    from .cards import _num as number
    return number(word)
