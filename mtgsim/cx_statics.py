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
    anthem_if: ((code, scope, spec, other, power, toughness, keywords), ...)   scope "you", "opp" or "all"

``pt_bonus`` and ``grants`` are called from ``Permanent._pt_bonus`` and ``Permanent.has``."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .cx_conditions import _KEYWORDS

_EXTRA = r"can't be blocked|can't block|can't attack|attacks each combat if able|blocks each combat if able"
_KW = rf"(?:{_KEYWORDS}|{_EXTRA})"
_KWS = rf"{_KW}(?:(?:, | and |, and ){_KW})*"
_PT = r"([+-]\d+)/([+-]\d+)"
_LABEL = r"(?:[A-Z][\w' ]* — )?"
_HOST = re.compile(rf"{_LABEL}(Enchanted|Equipped) creature (?:gets (?:an additional )?{_PT}(?: and (?:has )?({_KWS}))?|"
                   rf"(?:has )?({_KWS}))(?: as long as (.+?))?\.(?: Otherwise, it gets {_PT}\.)?")
_ANTHEM = re.compile(rf"{_LABEL}(?:Each |All )?(?P<s>[\w ,-]+?) (?:get|gets) (?:an additional )?(?P<p>[+-]\d+)/"
                     rf"(?P<t>[+-]\d+)(?: and (?:have|has) (?P<k>{_KWS}))? as long as (?P<c>.+?)\.")
_ANTHEM_KW = re.compile(rf"{_LABEL}(?:Each |All )?(?P<s>[\w ,-]+?) (?:have|has) (?P<k>{_KWS}) as long as (?P<c>.+?)\.")
_ALIAS_KW = {"can't be blocked": "unblockable", "can't block": "cant_block_now", "can't attack": "cant_attack_now",
             "attacks each combat if able": "must_attack_now", "blocks each combat if able": "must_block_now"}


def aura_parser_takes(line: str, st) -> bool:
    """Whether the Aura / Equipment line parser (auras.py, run later) reads this line itself."""
    from . import auras
    scratch = dict(st.extra, _subtypes=st.type_line)
    return bool(auras.parse_line(line, scratch, st.types))


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
    m = re.fullmatch(r"(.+?) your opponents control", text)
    if m:                       # Mindwhisker: only creatures controlled by the source's opponents
        scope, text = "opp", m[1]
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
    per = re.fullmatch(rf"{_LABEL}~ gets ([+-]\d+)/([+-]\d+) for each (.+?) as long as (.+?)\.", line)
    if per:
        from .cx_grammar_quantity import quantity
        from .cx_conditions import _code
        spec, code = quantity("the number of " + per[3]), _code(per[4])
        if spec is None or code is None:
            return False
        rules = extra.setdefault("advanced_rules", {})
        rules["pt_per_if"] = rules.get("pt_per_if", ()) + ((code, int(per[1]), int(per[2]), spec),)
        return True
    lead = re.fullmatch(rf"({_LABEL})As long as (.+?), ((?:Each |All )?[\w ,-]+? (?:get|gets|have|has) .+)\.", line)
    if lead and not lead[3].startswith(("~", "Enchanted", "Equipped")):
        line = f"{lead[1]}{lead[3]} as long as {lead[2]}."        # "As long as C, S gets X." is "S gets X as long as C."
    line = re.sub(r" can't (be blocked|block) as long as", r" has can't \1 as long as", line)
    m = _HOST.fullmatch(line)
    if m:
        is_aura = bool(extra.get("aura"))
        if (m[1] == "Enchanted") != is_aura or m[1] == "Equipped" and "Equipment" not in st.type_line:
            return False
        restriction = any(k in _ALIAS_KW for k in re.split(r", and |, | and ", m[4] or m[5] or ""))
        if m[6] is None and (m[7] or not restriction or aura_parser_takes(line, st)):
            return False            # unconditional: only the forms the Aura / Equipment parser leaves (a P/T plus a restriction)
        code = _cond(m[6]) if m[6] else ""
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
    if not code:
        return True
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
                    if rule[1] == "you" and pl is not perm.controller or rule[1] == "opp" and pl is perm.controller \
                            or rule[3] and x is perm:
                        continue
                    yield x, rule


def _applies(source, rule, perm) -> bool:
    from .cx_condlib import _card_ok
    return _card_ok(perm.card, rule[2], perm) and _holds(source, rule[0], perm)


def _attached(perm):
    return list(perm.auras) + list(perm.equipment)


def pt_bonus(perm):
    bp = bt = 0
    if not perm.abilities_suppressed:
        game = getattr(perm.controller, "_game", None)
        if game is not None:
            from .engine.state import StackItem
            for code, pp, tt, spec in perm.card.advanced_rules.get("pt_per_if", ()):
                if perm.condition(code):
                    n = game.x_quantity(perm.controller, spec, StackItem(perm.controller, [], [], source=perm), None)
                    bp, bt = bp + pp * n, bt + tt * n
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


def _pump_group(m):
    from .cards.model import NO_MATCH
    from .permanent_templates import build
    eff = build("linked_pump", m["f"], data={"duration": _mode(m["d"]),
                "pt": [int(m["p"] or 0), int(m["t"] or 0)], "kws": list(_keywords(m["k"] or m["k2"]))})
    return eff if eff is not None and eff.kind == "permanent_group" else NO_MATCH


_RESTRICT = {"attack or block": ("cant_attack_now", "cant_block_now"), "attack": ("cant_attack_now",),
             "block": ("cant_block_now",)}


def restrict_rider(s, effects) -> bool:
    """"That creature can't attack or block for as long as you control ~" right after a linked control effect (the
    stolen creature is the referent); after any other effect the referent isn't tracked, so it stays unmatched."""
    m = re.fullmatch(r"(?:that|the chosen) creature can't (?P<what>attack or block|attack|block) "
                     r"for as long as (?P<d>you control ~)", s, re.I)
    if not m or not effects or effects[-1].kind != "control_linked" or effects[-1].data["duration"] != "controlled":
        return False
    effects.append(_restrict(dict(m.groupdict(), who=True, what=m["what"].lower(), d=m["d"].lower())))
    return True


def _restrict(m):
    """"That creature can't attack or block for as long as you control ~": the restriction is a linked grant, so it
    ends as soon as the source leaves the battlefield or changes controller."""
    from .cards.model import Effect
    g = m if isinstance(m, dict) else m.groupdict()
    return Effect("linked_restrict", target="prev" if g.get("who") else "creature",
                  data={"duration": _mode(g["d"]), "kws": list(_RESTRICT[g["what"]]),
                        "optional_target": bool(g.get("up"))})


EFFECT_PATTERNS = [
    (r"(?P<up>up to one )?target creature can't (?P<what>attack or block|attack|block) "
     r"for as long as (?P<d>you control ~)", lambda m: _restrict(dict(m.groupdict(), who=None))),
    (rf"(?:you may )?gain control of (?P<up>up to one )?target (?P<f>[\w ,'~-]+?) {_DUR}", _control),
    (rf"(?P<other>another )?target (?P<f>[\w ,'~-]+?) {_PT_KWS} {_DUR}", _pump),
    (rf"(?P<f>(?:all|each) [\w ,'~-]+?|(?:other )?creatures you control) {_PT_KWS.replace('gets ', 'get ')} {_DUR}",
     _pump_group),
]


@dataclass(frozen=True)
class LinkedStatic:
    source: object
    target: object
    mode: str
    giver: object
    pt: tuple = (0, 0)
    kws: tuple = ()
    effects: tuple = ()
    triggers: tuple = ()


def counter_rider(sentence, effects):
    """Attach a duration to the counter placement that identifies its permanent.

    Refuse untracked referents and unsupported payloads instead of swallowing a
    duration. These are resolving effects, so losing the last counter ends them
    permanently, even if a counter of that name is added again later.
    """
    if not effects or effects[-1].kind != "add_counter" or effects[-1].target != "permanent":
        return False
    m = re.fullmatch(r"(?:if you do, )?(?:that creature|it) has base power and toughness (\d+)/(\d+) "
                     rf"and has ({_KWS}) for as long as it has an? ([\w-]+) counter on it", sentence, re.I)
    data = None
    if m:
        data = {"base": (int(m[1]), int(m[2])), "keywords": _keywords(m[3].lower()),
                "counter": m[4].lower(), "placed": sentence.lower().startswith("if you do")}
    m = re.fullmatch(r'for as long as that (?:creature|land) has an? ([\w-]+) counter on it, it has "(.+)"',
                     sentence, re.I)
    if m:
        from .cards.parse import _parse_trigger
        # The older self-damage wording is simplified to life loss. A granted
        # land ability must retain damage (prevention, lifelink and its source).
        damage = re.fullmatch(r"at the beginning of your upkeep, ~ deals (\d+) damage to you\.?", m[2], re.I)
        if damage:
            from .cards.model import Effect, Trigger
            triggers = (Trigger("upkeep", [Effect("cx_players", data={"who": "you", "effects":
                        [Effect("damage", int(damage[1]), target="that_controller")]})]),)
            data = {"triggers": triggers, "counter": m[1].lower()}
        elif not re.search(r"\bdamage\b", m[2], re.I):
            parsed = _parse_trigger(m[2].rstrip(".") + ".")
            if parsed and parsed[0] and not parsed[1] and parsed[2] is None:
                data = {"triggers": tuple(parsed[0]), "counter": m[1].lower()}
    if not data or data["counter"] != effects[-1].data.get("counter"):
        return False
    effects[-1] = replace(effects[-1], data=dict(effects[-1].data, counter_duration=data))
    return True


def link_counter(game, p, target, data, placed):
    from .continuous import ContinuousEffect
    name = data["counter"]
    if target.counters.get(name, 0) <= 0 or data.get("placed") and not placed:
        return
    stamp = game.next_effect_timestamp()
    changes = []
    if "base" in data:
        changes.append(ContinuousEffect(stamp, target, "set_base", stamp, *data["base"]))
    for kw in data.get("keywords", ()):
        stamp = game.next_effect_timestamp()
        changes.append(ContinuousEffect(stamp, target, "grant", stamp, keyword=kw))
    link = LinkedStatic(None, target, "counter:" + name, p, effects=tuple(changes),
                        triggers=data.get("triggers", ()))
    if not hasattr(game, "_linked_statics"):
        game._linked_statics = []
    game._linked_statics.append(link)


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
    alive = [x for x in links if x.target in x.target.controller.battlefield and
             (x.target.counters.get(x.mode[8:], 0) > 0 if x.mode.startswith("counter:") else
              linked_ok(x.source, x.mode, x.giver))]
    if len(alive) != len(links):
        game._linked_statics = alive
    return alive


def linked_bonus(perm):
    game = getattr(perm.controller, "_game", None)
    bp = bt = 0
    for link in _linked(game):
        if link.target is perm:
            bp, bt = bp + link.pt[0], bt + link.pt[1]
    return bp, bt


def linked_grants(perm, kw) -> bool:
    game = getattr(perm.controller, "_game", None)
    return any(x.target is perm and kw in x.kws for x in _linked(game))


def linked_effects(perm):
    game = getattr(perm.controller, "_game", None)
    return [e for x in _linked(game) if x.target is perm for e in x.effects]


def linked_triggers(perm):
    game = getattr(perm.controller, "_game", None)
    return [t for x in _linked(game) if x.target is perm for t in x.triggers]


def counter_changed(perm, name):
    """Expire immediately, including removal and replacement within one resolution."""
    game = getattr(perm.controller, "_game", None)
    links = getattr(game, "_linked_statics", ())
    if perm.counters.get(name, 0) > 0 or not links:
        return
    removed = [x for x in links if x.target is perm and x.mode == "counter:" + name]
    if removed:
        game._linked_statics = [x for x in links if x not in removed]


def on_untap(game, source):
    """"~ remains tapped" ends for good when ~ untaps, even if it's tapped again later."""
    links = getattr(game, "_linked_statics", None)
    if links:
        game._linked_statics = [x for x in links if not (x.source is source and "tapped" in x.mode)]
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
