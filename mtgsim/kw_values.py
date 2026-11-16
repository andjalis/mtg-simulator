"""#633: the numbers of granted valued keywords ("ward:2", "toxic:1"; see cx_grammar_kwvalue).

``amounts(perm, name)`` lists the values of every ``name:N`` keyword the permanent has. Candidates come from the
permanent's own temporary / permanent keywords and from every keyword string any battlefield card carries (its
static grants, Equipment / Aura keywords and gated or conditional rules, found once per card definition and
cached); ``Permanent.has`` then decides, so a grant counts only while its condition, selector and layers allow.
"""
from __future__ import annotations

import re

_RX = re.compile(r"(ward|toxic):(\d+)")
_CACHE: dict = {}


def _strings(obj, out, depth=0):
    if depth > 8:
        return
    if isinstance(obj, str):
        if _RX.fullmatch(obj):
            out.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _strings(v, out, depth + 1)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            _strings(v, out, depth + 1)


def _card_strings(card) -> frozenset:
    key = id(card)
    hit = _CACHE.get(key)
    if hit is None or hit[0] is not card:
        out: set = set()
        for field in ("static_keyword_grants", "equip_keywords", "cond_keywords", "keywords", "advanced_rules"):
            _strings(getattr(card, field, None), out)
        hit = _CACHE[key] = (card, frozenset(out))
    return hit[1]


def amounts(perm, name: str) -> list:
    game = getattr(perm.controller, "_game", None)
    cands = set()
    _strings((perm.temp_kw, perm.perm_kw), cands)
    for pl in (game.players if game is not None else (perm.controller,)):
        for x in pl.battlefield:
            cands |= _card_strings(x.card)
    out = []
    for s in cands:
        m = _RX.fullmatch(s)
        if m[1] == name and perm.has(s):
            out.append(int(m[2]))
    return out
