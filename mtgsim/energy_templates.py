"""Energy pay gates: "you may pay {E}{E}. If you do, ..." riders (Conduit Goblin,
Glint-Sleeve Siphoner, T-45 Power Armor).

Energy is a player counter (``p.counters["energy"]``, gained through the ``energy`` kind
in kinds/advanced.py); activated-ability costs like "Pay {E}{E}:" already work
(cards/parse.py extra costs). The missing piece was the trigger-rider gate: "you may pay
{E}... If you do, <X>" inside a triggered ability. The SUBS rewrite below folds the pair
into a PAYE sentinel whose builder returns a ``pay_energy`` gate effect (it checks and
deducts the counters and sets item.gate_paid, the pay_gate pattern) followed by the
payoff effects carrying cond "paid".
"""
from __future__ import annotations

import dataclasses
import re

SUBS = [
    # "you may pay {E}{E}. If you do, <payoff>." — also "When you do".
    (re.compile(r"you may pay ((?:\{E\})+)\. (?:if|when) you do, ([^.]+)\.", re.I),
     lambda m: f"PAYE {m[1].count('{E}')} {m[2]}."),
]


def _pay(m):
    from .cards import Effect, NO_MATCH, _parse_effects
    payoff, bad = _parse_effects(m[2][0].upper() + m[2][1:] + ".")
    if bad or not payoff:
        return NO_MATCH
    return [Effect("pay_energy", int(m[1]))] + [
        dataclasses.replace(e, cond=e.cond or "paid") for e in payoff]


EFFECT_PATTERNS = [
    (r"PAYE (\d+) (.+)", _pay),
]
