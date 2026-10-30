"""Token family templates: named artifact tokens the token table knows how to build, and
"Create X <desc> tokens" with X the paid amount (or an xq the token kind evaluates).

Joined at the end of ``cards/__init__.py``. The token blueprint itself (name, activated
ability) lives in cards/tokens.py TOKEN_ABILITIES / make_token.
"""
from __future__ import annotations

import dataclasses
import re


def _xtoken(m):
    from .cards import NO_MATCH, _parse_effects
    desc = m[1]
    singular = re.sub(r" tokens\b", " token", desc)
    effects, bad = _parse_effects("Create one " + singular + ".")
    if bad or not effects:
        return NO_MATCH
    return [dataclasses.replace(e, data=dict(e.data, x=True)) if e.kind == "token" else e
            for e in effects]


EFFECT_PATTERNS = [
    (r"create (a|one|two|three|four|five|six|seven|eight|nine|ten|\d+) junk tokens?",
     lambda m: _e("token", _num(m[1]), data={"kind": "junk"})),
    # "Create X 1/1 ... creature tokens." — X is the X paid for the spell or ability
    # (the token kind reads item.x via data "x"; the ", where X is ..." variants are
    # already handled by the shared X-quantity rules in _parse_effects).
    (r"XTOKEN (.+)", _xtoken),
]


def _xtoken_sub(m):
    if ", where" in m[1] or " token" not in m[1]:
        return m[0]
    return f"XTOKEN {m[1]}."


SUBS = [
    # "Create X <desc> tokens." — the shared ", where X is ..." rules in _parse_effects
    # already size those variants, so those sentences are left alone.
    (re.compile(r"create X ([^.]+)\.?", re.I), _xtoken_sub),
]


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _num(word):
    from .cards import _num as number
    return number(word)
