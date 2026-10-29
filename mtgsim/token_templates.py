"""Token family templates: named artifact tokens the token table knows how to build.

Joined at the end of ``cards/__init__.py``. The token blueprint itself (name, activated
ability) lives in cards/tokens.py TOKEN_ABILITIES / make_token.
"""
from __future__ import annotations


EFFECT_PATTERNS = [
    (r"create (a|one|two|three|four|five|six|seven|eight|nine|ten|\d+) junk tokens?",
     lambda m: _e("token", _num(m[1]), data={"kind": "junk"})),
]

SUBS = []


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _num(word):
    from .cards import _num as number
    return number(word)
