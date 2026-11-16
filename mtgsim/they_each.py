"""'They each ...' after counted targets (#313): the next sentence acts on each object the previous effect targeted.

    Untap up to two target creatures. They each get +2/+2 until end of turn.          (Join Forces)
    Tap one or two target untapped creatures you control. They each deal damage equal to their power to target
    creature an opponent controls.                                                    (Coordinated Clobbering)

"They" is the run of targets the effect before it chose (two or more effects of one kind, the counted-target copies
cx_multi_target and the grammar make). The sentence is read in the singular ("It gets +2/+2 until end of turn"):
- when everything it does acts on "it", it is repeated right after each target of the run (prev is that target);
- "it deals damage equal to its power to <recipient>" (cx_grammar_bite) becomes one ``bite_src`` that records
  every target of the run still legal on resolution, then the one ref_bite: each of them deals its own damage to
  the same recipient.
Anything else ("they each" with a target of its own and other verbs, a single target before it) stays unmatched.
"""
from __future__ import annotations

import dataclasses
import re


def _run(effects):
    """(start index, length) of the trailing run of distinct targeted effects of one kind, or None."""
    from .engine.state import TARGETED
    if not effects:
        return None
    last = effects[-1]
    if last.target not in TARGETED or not last.data.get("distinct"):
        return None
    group = last.data.get("group", last.kind)
    i = len(effects) - 1
    while i > 0 and effects[i - 1].kind == last.kind and effects[i - 1].target in TARGETED \
            and effects[i - 1].data.get("distinct") and effects[i - 1].data.get("group", effects[i - 1].kind) == group:
        i -= 1
    n = len(effects) - i
    return (i, n) if n >= 2 else None


def _singular(rest: str) -> str:
    first, _, tail = rest.partition(" ")
    verb = first if first.endswith("s") else ("has" if first == "have" else first + "s")
    tail = re.sub(r"\btheir\b", "its", tail)
    return f"It {verb} {tail}".strip()


def parse_rider(s, effects) -> bool:
    m = re.fullmatch(r"they each (.+)", s.strip(), re.I)
    if m is None:
        return False
    run = _run(effects)
    if run is None:
        return False
    from .cards import _parse_effects
    from .cx_grammar_bite import _SENTENCE, build
    one = _singular(m[1])
    bite = re.fullmatch(_SENTENCE, one, re.I)
    if bite and bite["subj"].lower() == "it":      # the bite grammar, not an older one-target bite template
        new = build("it", (bite["to1"] or bite["to2"] or "").strip(), 2 if bite["twice"] else 1,
                    int(bite["plus"] or 0)) if bool(bite["to1"]) != bool(bite["to2"]) else None
        bad = [] if new else [one]
    else:
        new, bad = _parse_effects(one + ".")
    if bad or not new:
        return False
    start, n = run
    if new[0].kind == "bite_src" and new[0].target == "prev" and len(new) == 2 and new[1].kind == "ref_bite":
        for i in range(start, len(effects)):     # the AI picks these as the creatures that deal the damage
            effects[i] = dataclasses.replace(effects[i], data=dict(effects[i].data, bite_run=True))
        effects.append(dataclasses.replace(new[0], target="none", data=dict(new[0].data, run=n)))
        effects.append(new[1])
        return True
    if any(e.target != "prev" for e in new):
        return False
    out = []
    for i, e in enumerate(effects):
        out.append(e)
        if start <= i:
            out += [dataclasses.replace(x) for x in new]
    effects[:] = out
    return True
