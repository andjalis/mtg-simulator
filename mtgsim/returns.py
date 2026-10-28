"""Counter riders on effects that return cards to the battlefield."""
from __future__ import annotations

import dataclasses
import re

_RIDER = re.compile(r"(.+?) with (?:a (finality) counter|"
                    r"(an?|one|two|three|four|five|six|seven|\d+|X)(?: additional)? \+1/\+1 counters?) "
                    r"on (?:it|him|her|them)", re.I)


def parse_rider(text):
    """Parse the base effect too, so an unknown return is never marked supported."""
    from .cards import _num, _parse_effects
    m = _RIDER.fullmatch(text)
    if not m:
        return None
    effects, bad = _parse_effects(m[1] + ".")
    if bad or not effects or any(e.kind not in ("gy_move", "reanimate_one", "return_self_gy", "mill_pick") or
                               e.data.get("dest", "bf") not in ("bf", "battlefield") for e in effects):
        return None
    kind = "finality" if m[2] else "+1/+1"
    n = 1 if m[2] else "x" if m[3].lower() == "x" else _num(m[3])
    return [dataclasses.replace(e, data=dict(e.data, entry_counters={kind: n})) for e in effects]


def entry_counters(eff, item):
    return {kind: getattr(item, "x", 0) if n == "x" else n
            for kind, n in eff.data.get("entry_counters", {}).items()}
