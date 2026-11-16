"""Kicker cost forms beyond a single mana kicker (#859).

* Two kickers, "Kicker {A} and/or {B}" (the Invasion Battlemages and Volvers, Illuminate, Archangel of Wrath):
  rule 702.33c lets the caster pay either, both or neither. Each paid combination is its own kicker cast option
  (``AltCost("kicker", base + paid, kicks=("{A}", ...))``). The spell remembers which kickers it paid
  (``StackItem.kicked_with``, then ``Permanent.kicked_with``), read by the condition library's
  "if it was kicked with its {A} kicker" and "if it was kicked twice", and by "for each time it was kicked".
* A kicker with a non-mana cost, "Kicker—Sacrifice a land." / "Kicker—{2}{R}, Sacrifice a land." /
  "Kicker—Pay 3 life." (rule 702.33a: any cost). The cost is read by the spell additional-cost parser
  (cx_spell_costs) and paid by its transactional payer on the kicked cast only; the mana part, if any, is
  added to the kicked cast's cost. The "if ~ was kicked" lines work as for a mana kicker.

Anything else on a kicker line ("Kicker—Forage." with a seek, three kickers, a non-mana part the cost parser
doesn't know) stays ignored.
"""
from __future__ import annotations

import re
from itertools import combinations

_MANA = r"(?:\{[0-9WUBRGC]\})+"


def face_line(st, line):
    """Face-line hook: the kicker lines this module owns; None when consumed, else the line unchanged."""
    m = re.fullmatch(rf"Kicker ({_MANA}) and/or ({_MANA})(?: \(.*\))?", line)
    if m:
        if "kicker" in st.extra or "kickers" in st.extra:
            return line
        st.extra["kickers"] = (m[1], m[2])
        return None
    m = re.fullmatch(rf"Kicker—(?:({_MANA}), )?([^{{(][^(]*?)\.?(?: \(.*\))?", line)
    if m:
        from .cx_spell_costs import parse_cost
        from .cards.model import parse_mana_cost
        text = m[2][0].lower() + m[2][1:]
        alts = parse_cost(text)
        if alts is None or len(alts) != 1 or "kicker" in st.extra or "kickers" in st.extra or \
                any(not isinstance(n, int) for _, n, _ in alts[0]):
            return line          # one fixed cost (no "or" alternatives, no X / any number of)
        st.extra["kicker"] = parse_mana_cost(m[1]) if m[1] else {"generic": 0}
        st.extra["kicker_add_cost"] = alts
        return None
    m = _KICK_ENTRY.fullmatch(line)
    if m:
        entry = _entry(m)
        if entry is not None:
            st.extra.setdefault("advanced_rules", {}).setdefault("kick_entry", []).append(entry)
            return None
    return line


_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_KICK_ENTRY = re.compile(r"If ~ was (?P<c>kicked(?: with its (?:\{[0-9WUBRGC]\})+ kicker)?), it enters with "
                         r"(?P<n>a|an|one|two|three|four|five) \+1/\+1 counters? on it and with (?P<w>\"[^\"]+\"|[^\".]+)\.?")


def _entry(m):
    """(condition code, +1/+1 counters, keywords, quoted triggers) for "If ~ was kicked [with its {A} kicker], it
    enters with N +1/+1 counters on it and with <keyword>|"<triggered ability>"" (Pouncing Kavu, the Volvers),
    or None when the ability isn't one the engine has."""
    from .cx_condlib import parse
    from .cards.model import KEYWORDS
    code = parse(m["c"].replace("kicked", "it was kicked", 1))
    if not code:
        return None
    what, kws, trigs = m["w"], (), ()
    q = re.fullmatch(r'"([^"]+)"', what)
    if q:
        from .cx_trigger_grants import quoted_triggers
        trigs = quoted_triggers(q[1])
        if not trigs:
            return None
        trigs = tuple(trigs)
    else:
        kws = tuple(w.strip() for w in re.split(r",? and |, ", what))
        if not kws or any(k not in KEYWORDS for k in kws):
            return None
    return (code, _N[m["n"]], kws, trigs)


def entry(game, p, perm):
    """Enter-the-battlefield replacement (rule 614.1c) for the kicked "it enters with ... and with ..." lines:
    the counters, the keywords for as long as it stays, and quoted triggers it has from then on."""
    from .cx_condlib import check
    for code, n, kws, trigs in perm.card.advanced_rules.get("kick_entry", ()):
        if not check(game, p, code, None, source=perm):
            continue
        perm.counters["+1/+1"] = perm.counters.get("+1/+1", 0) + n
        perm.perm_kw.update(kws)
        perm.gained_triggers = list(getattr(perm, "gained_triggers", [])) + list(trigs)


def finish(extra: dict, cost: dict, alt_costs: list, unsupported: list) -> None:
    """After the face: one kicker option per paid combination of two kickers; the non-mana kicker's cost."""
    add = extra.pop("kicker_add_cost", None)
    if add is not None:
        kick = next((a for a in alt_costs if a.kind == "kicker"), None)
        if kick is None or (extra.get("advanced_rules") or {}).get("spell_add_cost"):
            unsupported.append("Kicker with a non-mana cost on a spell that has another additional cost")
        else:
            kick.add_cost = add
    kickers = extra.pop("kickers", None)
    if kickers is None:
        return
    from .cards.model import AltCost, add_mana, parse_mana_cost
    for n in (1, 2):
        for paid in combinations(kickers, n):
            alt_costs.append(AltCost("kicker", add_mana(cost, *(parse_mana_cost(k) for k in paid)),
                                     kicks=tuple(paid)))


# ---------------------------------------------------------------- engine side

def cast_kicks(item, kind: str, alt) -> None:
    """Game.cast: which kickers the spell paid (two-kicker cards); "for each time it was kicked" reads kicks."""
    if kind == "kicker" and alt is not None and alt.kicks:
        item.kicked_with = tuple(alt.kicks)
        item.kicks = len(alt.kicks)


def kicks_paid(item, source) -> tuple:
    """The kicker costs paid for the spell a condition is about: the resolving spell, the spell a cast
    trigger fired on, or the permanent the spell became. A multikicker counts once per kick."""
    for obj in (item, getattr(item, "context", None), source):
        if obj is None:
            continue
        paid = getattr(obj, "kicked_with", ())
        if paid:
            return tuple(paid)
        n = getattr(obj, "kicks", 0)
        if n:
            return ("",) * n
        if getattr(obj, "kicked", False):
            return ("",)
        card = getattr(obj, "card", None)
        origin = getattr(card, "origin", None) if card is not None else None
        if getattr(obj, "is_spell", False) and origin and origin[1] == "kicker":
            return tuple(origin[2].kicks) if origin[2] is not None and origin[2].kicks else ("",)
    return ()


# ---------------------------------------------------------------- AI side

def _gate_on(code: str, kicked: bool, kicks: tuple) -> bool:
    """Whether a condition code that reads the kicker is true for a cast paying ``kicks`` (True for other codes)."""
    import json
    code = code or ""
    if "kicked_with" in code or '"kicks"' in code:
        neg = code.startswith("!")
        try:
            args = json.loads(code.lstrip("!")[4:])
        except ValueError:
            return False
        if args[0] == "kicked_with":
            on = args[1] in kicks
        elif args[0] == "kicks":
            on = len(kicks) >= args[1]
        else:
            return False
        return on != neg
    return kicked or "kicked" not in code


def etb_gate(game, card):
    """cond -> bool for the AI's enters-trigger valuation of this cast option (kicked, which kickers)."""
    _, kind, alt = game._origin(card)
    kicked = kind == "kicker"
    kicks = tuple(alt.kicks) if kicked and alt is not None and alt.kicks else (("",) if kicked else ())
    return lambda cond: _gate_on(cond, kicked, kicks)


def ai_kick_value(ai, game, me, card, precombat, handled) -> float:
    """Value of a kicked option's own enters effects that _etb_value doesn't price (destroy, discard, damage,
    draw, ...): what the AI's spell planner gives the same effects cast as a sorcery now; 0 when it wouldn't
    cast that sorcery (no worthwhile target). Only kicker-gated effects, so unkicked casts are unchanged."""
    if game._origin(card)[1] != "kicker":
        return 0.0
    import dataclasses
    from .cards.model import CardDef
    on = etb_gate(game, card)
    rules = card.advanced_rules or {}
    total = 1.0 * rules.get("kick_counters", 0)       # "if kicked, it enters with N +1/+1 counters"
    for code, n, kws, trigs in rules.get("kick_entry", ()):     # "... and with haste / "<trigger>""
        if on(code):
            total += n + 0.5 * (len(kws) + len(trigs))
    for t in card.triggers:     # each trigger priced on its own, as it resolves on its own
        if t.event != "etb" or not on(t.intervening_if):
            continue
        gated = "kicked" in (t.intervening_if or "")
        effects = [dataclasses.replace(e, cond="") for e in t.effects
                   if on(e.cond) and (gated or "kicked" in (e.cond or "")) and e.kind not in handled]
        if not effects:
            continue
        probe = CardDef(name=f"{card.name} (kicked enters)", mana_cost={"generic": 0}, cmc=0,
                        types=frozenset({"Sorcery"}), spell_effects=effects)
        try:
            plan = ai.plan_spell(game, me, probe, precombat)
        except Exception:      # a planner path that needs a real card: no extra value rather than a crash
            plan = None
        total += max(0.0, plan[0]) if plan else 0.0
    return total
