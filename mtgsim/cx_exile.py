"""Single-permanent blink wording using existing physical-card move handlers.

Only returns under the owner's control are supported here. Caster-control,
multi-target, tapped-return and transformed-return clauses stay unsupported.
"""
from __future__ import annotations

import re

_SUBJECT = r'(?:~|(?:another |up to one |up to one other )?target [\w ,/-]+?)'
_RETURN = r'return (?:it|that card) to the battlefield'
_OWNER = r"under (?:its|their) owner's control"


def _blink(match):
    from .cards.model import NO_MATCH
    from .permanent_templates import build
    return build('flicker', match['what']) or NO_MATCH


def _join(match):
    from .cards.model import NO_MATCH
    # A normalization must not replace an unsupported selector with a marker.
    return match[0] if _blink(match) is NO_MATCH else 'CXOWNERBLINK ' + match['what'] + '.'


EFFECT_PATTERNS = [
    (rf'exile (?P<what>{_SUBJECT}), then {_RETURN} {_OWNER}', _blink),
    (rf'CXOWNERBLINK (?P<what>{_SUBJECT})', _blink),
]
SUBS = [
    (re.compile(rf'exile (?P<what>{_SUBJECT})\. {_RETURN} {_OWNER}\.', re.I), _join),
]
