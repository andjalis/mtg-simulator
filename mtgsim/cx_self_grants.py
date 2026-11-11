"""Threshold-style quoted abilities on their own permanent.

A granted ability exists only while its static condition holds. Triggers are
selected before departure, so the normal last-known trigger snapshot also works
for a granted dies ability. The condition is not an intervening-if clause.
"""
from __future__ import annotations

import re

from .cx_conditions import _LABEL, _KWS, _code, _ALIAS

_LINE = re.compile(rf'{_LABEL}As long as (.+?), ~ (.*?)has "([^\"]+)"\.?')


def parse_line(line, st):
    m = _LINE.fullmatch(line)
    if not m:
        return False
    code = _code(m[1])
    if code is None or not code.startswith('cx:gy>='):
        # Conditions depending on a departing *other* permanent need a snapshot
        # of every observer before the event (e.g. the last Cleric and Relic
        # Vial). Leave that broader family unmatched until that support exists.
        return False
    pt, color, kws = None, None, ()
    # Consume every modifier before accepting the quoted ability.
    prefix = re.sub(r'(?:,? and |, )$', '', m[2])
    for part in re.split(r', and |, | and ', prefix) if prefix else ():
        pump = re.fullmatch(r'gets ([+-]\d+)/([+-]\d+)', part)
        col = re.fullmatch(r'is (white|blue|black|red|green)', part)
        kw = re.fullmatch(rf'has ({_KWS})', part)
        if pump and pt is None:
            pt = int(pump[1]), int(pump[2])
        elif col and color is None and code.startswith('cx:gy>='):
            # This subset has no dependencies on other color/type effects.
            color = {'white': 'W', 'blue': 'U', 'black': 'B', 'red': 'R', 'green': 'G'}[col[1]]
        elif kw and not kws:
            kws = tuple(_ALIAS.get(k, k) for k in re.split(r', and |, | and ', kw[1]))
        else:
            return False
    from .cards.parse import _parse_ability, _parse_trigger
    approximations = []
    act = _parse_ability(m[3], approximations)
    triggers = ()
    if act is None:
        parsed = _parse_trigger(m[3])
        if parsed is None or not parsed[0] or parsed[1] or parsed[2] is not None:
            return False
        triggers = tuple(parsed[0])
    if approximations:
        return False
    extra = st.extra
    rules = extra.setdefault('advanced_rules', {})
    rules['self_abilities_if'] = rules.get('self_abilities_if', ()) + ((code, (act,) if act else (), triggers),)
    if color:
        rules['self_colors_if'] = rules.get('self_colors_if', ()) + ((code, frozenset({color})),)
    if pt:
        extra['pt_if'] = extra.get('pt_if', ()) + ((code, *pt),)
    extra['cond_keywords'] = extra.get('cond_keywords', ()) + tuple((k, code) for k in kws)
    return True


def abilities(perm, triggered=False):
    if perm.abilities_suppressed:
        return []
    return [ability for code, acts, triggers in perm.card.advanced_rules.get('self_abilities_if', ())
            if perm.condition(code) for ability in (triggers if triggered else acts)]
