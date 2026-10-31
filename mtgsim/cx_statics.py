"""Conditional statics on other permanents: Aura / Equipment bonuses and anthems that apply "as long as" something.

    Enchanted creature gets +2/+2 as long as it's a Vampire. Otherwise, it gets -2/-2.     (Gift of Fangs)
    Equipped creature has double strike as long as two or more Equipment are attached to it.
    Threshold — Enchanted creature gets +3/+0 as long as there are seven or more cards in your graveyard.
    Creatures you control get +1/+1 as long as you control no nonartifact, nonwhite creatures.
    Other creatures you control get +1/+0 as long as you control an Equipment.
    Each land gets +2/+2 as long as it's a creature.                                            (Earth Surge)

The condition is a ``cx_condlib`` code evaluated from the static's source, with "it" meaning the enchanted, equipped
or affected permanent. Both kinds are stored in ``CardDef.advanced_rules``:

    host_if:   ((code, power, toughness, keywords, else_power, else_toughness), ...)
    anthem_if: ((code, scope, spec, other, power, toughness, keywords), ...)   scope "you" or "all"

``pt_bonus`` and ``grants`` are called from ``Permanent._pt_bonus`` and ``Permanent.has``."""
from __future__ import annotations

import re

from .cx_conditions import _KEYWORDS

_KW = rf"(?:{_KEYWORDS}|can't be blocked|can't block)"
_KWS = rf"{_KW}(?:(?:, | and |, and ){_KW})*"
_PT = r"([+-]\d+)/([+-]\d+)"
_LABEL = r"(?:[A-Z][\w' ]* — )?"
_HOST = re.compile(rf"{_LABEL}(Enchanted|Equipped) creature (?:gets (?:an additional )?{_PT}(?: and has ({_KWS}))?|"
                   rf"has ({_KWS})) as long as (.+?)\.(?: Otherwise, it gets {_PT}\.)?")
_ANTHEM = re.compile(rf"{_LABEL}(?:Each |All )?(?P<s>[\w ,-]+?) (?:get|gets) (?:an additional )?(?P<p>[+-]\d+)/"
                     rf"(?P<t>[+-]\d+)(?: and (?:have|has) (?P<k>{_KWS}))? as long as (?P<c>.+?)\.")
_ANTHEM_KW = re.compile(rf"{_LABEL}(?:Each |All )?(?P<s>[\w ,-]+?) (?:have|has) (?P<k>{_KWS}) as long as (?P<c>.+?)\.")
_ALIAS_KW = {"can't be blocked": "unblockable", "can't block": "cant_block_now"}


def _keywords(text) -> tuple:
    if not text:
        return ()
    return tuple(_ALIAS_KW.get(k, k) for k in re.split(r", and |, | and ", text) if k)


def _cond(text: str):
    from .cx_condlib import as_static
    return as_static(text) or None


def _subject(text: str):
    """(scope, spec, other) for an anthem's subject, or None."""
    from .cx_condlib import _filter
    text = text.strip()
    scope = "all"
    m = re.fullmatch(r"(.+?) you control", text)
    if m:
        scope, text = "you", m[1]
    other = False
    m = re.fullmatch(r"(?:other|each other) (.+)", text, re.I)
    if m:
        other, text = True, m[1]
    spec = _filter(text.replace(",", ""), plural=not text.endswith(("creature", "land", "permanent", "artifact")))
    if not spec or spec.get("other"):
        return None
    return scope, spec, other


def parse_line(line: str, st) -> bool:
    extra = st.extra
    line = re.sub(r" can't (be blocked|block) as long as", r" has can't \1 as long as", line)
    m = _HOST.fullmatch(line)
    if m:
        is_aura = bool(extra.get("aura"))
        if (m[1] == "Enchanted") != is_aura or m[1] == "Equipped" and "Equipment" not in extra.get("_subtypes", ()):
            return False
        code = _cond(m[6])
        if code is None:
            return False
        rules = extra.setdefault("advanced_rules", {})
        rules["host_if"] = rules.get("host_if", ()) + ((code, int(m[2] or 0), int(m[3] or 0),
                                                        _keywords(m[4] or m[5]), int(m[7] or 0), int(m[8] or 0)),)
        return True
    m = _ANTHEM.fullmatch(line) or _ANTHEM_KW.fullmatch(line)
    if not m or m["s"].startswith(("~", "Enchanted", "Equipped")):
        return False
    subject = _subject(m["s"])
    code = _cond(m["c"]) if subject else None
    if code is None:
        return False
    groups = m.groupdict()
    rules = extra.setdefault("advanced_rules", {})
    rules["anthem_if"] = rules.get("anthem_if", ()) + ((code, *subject, int(groups.get("p") or 0),
                                                        int(groups.get("t") or 0), _keywords(m["k"])),)
    return True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_ACTIVE: set = set()      # (source, target) pairs being evaluated: a condition that reads the bonus doesn't recurse


def _holds(source, code, ref) -> bool:
    key = (id(source), id(ref))
    if key in _ACTIVE:
        return False
    _ACTIVE.add(key)
    try:
        from .cx_condlib import holds_for
        return holds_for(source, code, ref)
    finally:
        _ACTIVE.discard(key)


def _anthems(perm):
    """(source, rule) for every conditional anthem that could reach perm."""
    game = getattr(perm.controller, "_game", None)
    players = game.players if game is not None else (perm.controller,)
    for pl in players:
        for x in pl.battlefield:
            rules = x.card.advanced_rules
            if rules and "anthem_if" in rules:
                for rule in rules["anthem_if"]:
                    if rule[1] == "you" and pl is not perm.controller or rule[3] and x is perm:
                        continue
                    yield x, rule


def _applies(source, rule, perm) -> bool:
    from .cx_condlib import _card_ok
    return _card_ok(perm.card, rule[2], perm) and _holds(source, rule[0], perm)


def _attached(perm):
    return list(perm.auras) + list(perm.equipment)


def pt_bonus(perm):
    bp = bt = 0
    for a in _attached(perm):
        for code, pp, tt, _kws, ep, et in a.card.advanced_rules.get("host_if", ()):
            if _holds(a, code, perm):
                bp, bt = bp + pp, bt + tt
            else:
                bp, bt = bp + ep, bt + et
    for source, rule in _anthems(perm):
        if (rule[4] or rule[5]) and _applies(source, rule, perm):
            bp, bt = bp + rule[4], bt + rule[5]
    lp, lt = linked_bonus(perm)
    return bp + lp, bt + lt


def grants(perm, kw: str) -> bool:
    for a in _attached(perm):
        if kw in a.card.advanced_rules.get("host_kws", ()):      # cx_lures: "Enchanted creature can't block."
            return True
        for code, _pp, _tt, kws, _ep, _et in a.card.advanced_rules.get("host_if", ()):
            if kw in kws and _holds(a, code, perm):
                return True
    return any(kw in rule[6] and _applies(source, rule, perm) for source, rule in _anthems(perm)) or \
        linked_grants(perm, kw)


# ---------------------------------------------------------------------------
# Durations tied to the source: "for as long as you control ~ / ~ remains tapped"
# ---------------------------------------------------------------------------

_DUR = r"for as long as (?P<d>you control ~ and ~ remains tapped|you control ~|~ remains tapped|~ remains on the battlefield)"
_PT_KWS = rf"(?:gets (?P<p>[+-]\d+)/(?P<t>[+-]\d+)(?: and (?:has|gains) (?P<k>{_KWS}))?|(?:has|gains) (?P<k2>{_KWS}))"


def _mode(text: str) -> str:
    return "+".join(m for m, word in (("controlled", "you control"), ("tapped", "remains tapped")) if word in text) \
        or "battlefield"


def _selector(text: str):
    from .permanent_templates import selector
    other = False
    m = re.fullmatch(r"(.+?) other than ~", text)
    if m:
        text, other = m[1], True
    spec = selector(text)
    if spec is not None and other:
        spec = dict(spec, other=True)
    return spec


def _control(m):
    from .cards.model import Effect, NO_MATCH
    spec = _selector(m["f"])
    if spec is None:
        return NO_MATCH
    return Effect("control_linked", target="permanent",
                  data={"selector": spec, "duration": _mode(m["d"]), "optional_target": bool(m["up"])})


def _pump(m):
    from .cards.model import Effect, NO_MATCH
    spec = _selector(m["f"])
    if spec is None:
        return NO_MATCH
    if m["other"]:
        spec = dict(spec, other=True)
    return Effect("linked_pump", target="permanent",
                  data={"selector": spec, "duration": _mode(m["d"]), "pt": [int(m["p"] or 0), int(m["t"] or 0)],
                        "kws": list(_keywords(m["k"] or m["k2"]))})


EFFECT_PATTERNS = [
    (rf"(?:you may )?gain control of (?P<up>up to one )?target (?P<f>[\w ,'~-]+?) {_DUR}", _control),
    (rf"(?P<other>another )?target (?P<f>[\w ,'~-]+?) {_PT_KWS} {_DUR}", _pump),
]


def linked_ok(source, mode: str, giver) -> bool:
    """Whether a duration tied to source still lasts."""
    if source is None or source not in source.controller.battlefield:
        return False
    if "controlled" in mode and source.controller is not giver:
        return False
    return "tapped" not in mode or bool(source.tapped)


def _linked(game):
    links = getattr(game, "_linked_statics", None)
    if not links:
        return ()
    alive = [x for x in links if linked_ok(x[0], x[2], x[3]) and x[1] in x[1].controller.battlefield]
    if len(alive) != len(links):
        game._linked_statics = alive
    return alive


def linked_bonus(perm):
    game = getattr(perm.controller, "_game", None)
    bp = bt = 0
    for source, target, _mode_, _giver, pt, _kws in _linked(game):
        if target is perm:
            bp, bt = bp + pt[0], bt + pt[1]
    return bp, bt


def linked_grants(perm, kw) -> bool:
    game = getattr(perm.controller, "_game", None)
    return any(target is perm and kw in kws for _s, target, _m, _g, _pt, kws in _linked(game))


def on_untap(game, source):
    """"~ remains tapped" ends for good when ~ untaps, even if it's tapped again later."""
    links = getattr(game, "_linked_statics", None)
    if links:
        game._linked_statics = [x for x in links if not (x[0] is source and "tapped" in x[2])]
    modes = getattr(game, "_control_modes", None)
    if modes and any(key[1] == id(source) and "tapped" in mode for key, (mode, _g) in modes.items()):
        for key in [k for k, (mode, _g) in modes.items() if k[1] == id(source) and "tapped" in mode]:
            modes[key] = ("broken", None)
        from .counter_mechanics import expire_source_control
        expire_source_control(game)


def control_lasts(game, target, source) -> bool:
    """counter_mechanics.expire_source_control: a "for as long as" control effect's own duration."""
    modes = getattr(game, "_control_modes", None)
    if not modes or source is None:
        return True
    entry = modes.get((id(target), id(source)))
    if entry is None:
        return True
    mode, giver = entry
    return mode != "broken" and linked_ok(source, mode, giver)
