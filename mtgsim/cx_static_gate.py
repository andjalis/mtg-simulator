"""Grammar static lines with a condition gate or a quantity scale (#398, #401). See docs/coverage-push/plans/static-gate.md.

    As long as you have the city's blessing, Detectives you control can't be blocked.     (a gate)
    During your turn, other historic creatures you control have double strike.
    ~ has protection from each color as long as you control three or more artifacts.
    ~ gets +1/+1 for each creature your opponents control.                                 (a scale)
    Equipped creature gets +X/+0, where X is the number of rev counters on ~.

The gate's condition is read by ``cx_conditions._code`` (its table, then ``cx_condlib.as_static``), the scale's quantity by ``cx_grammar._count_spec`` ("for
each Q") or ``cards.clauses._xq`` ("where X is Q"); the static itself by the grammar (``cx_grammar._clauses`` with the
"static" duration): pumps, keyword grants and ``cx_static`` family rules on ~, the enchanted / equipped creature, or
a group. Anything unread keeps the line ignored.

Each payload is one row of ``advanced_rules["gated"]``: ``(code, scope, spec, payload)`` with scope ``self``,
``host`` or ``group`` (spec: the grammar group spec), payload ``("pt", p, t, xq)``, ``("kw", keywords)`` or
``("rule", name, value)``. The engine reads the rows in ``cx_statics.pt_bonus`` / ``grants`` and
``cx_grammar.static_rules``; the condition is checked from the source's point of view with "it" the affected
permanent (``cx_statics._holds``)."""
from __future__ import annotations

import re

_LABEL = re.compile(r"^[A-Z][\w' ,-]* — ")
_KW_WORDS = re.compile(r"\b(?:flying|first strike|double strike|deathtouch|trample|vigilance|haste|lifelink|reach|menace|"
                       r"hexproof|indestructible|shroud|defender|protection|ward|keyword|abilit(?:y|ies))\b", re.I)


# ---------------------------------------------------------------- parsing

def _cond(text: str) -> str:
    """The code for a static's condition: cx_conditions' table (the city's blessing, ...), else cx_condlib."""
    from .cx_conditions import _code
    return _code(text) or ""


def _gates(s: str):
    """(condition code or "", body, condition text) readings of a line; codes are "" for no gate."""
    out = []
    m = re.fullmatch(r"As long as this card is in your graveyard(?: and (.+?))?, (.+)", s)
    if m:       # Anger: a static that works only from its owner's graveyard
        from .cx_condlib import as_static
        code = as_static(m[1]) if m[1] else ""
        return [("@gy" + code, m[2], m[1] or "")] if code or not m[1] else []
    m = re.fullmatch(r"During your turn, (.+)", s)
    if m:
        out.append((_cond("it's your turn"), m[1], "turn"))
    m = re.fullmatch(r"(.+) during your turn", s)
    if m:
        out.append((_cond("it's your turn"), m[1], "turn"))
    m = re.match(r"As long as ", s)
    if m:
        rest = s[m.end():]
        for comma in re.finditer(r", ", rest):        # the condition may hold commas: try each split
            cond, body = rest[:comma.start()], rest[comma.end():]
            code = _cond(cond)
            if code:
                out.append((code, body, cond))
                break
    m = re.fullmatch(r"(.+?) (?<!for )as long as (.+)", s)
    if m and not s.startswith("As long as"):
        code = _cond(m[2])
        if code:
            out.append((code, m[1], m[2]))
    if not out and not re.search(r"\b(?:as long as|during)\b", s, re.I):
        out.append(("", s, ""))
    return out


def _it(body: str, cond: str) -> str:
    """After a leading gate, "it" is what the condition named: ~ (or the enchanted / equipped creature). "That
    creature" after "you control exactly one creature" is the one creature you control."""
    body = re.sub(r"\bgets an additional\b", "gets", body)
    one = re.fullmatch(r"you control exactly one (creature|artifact|enchantment|land)", cond)
    if one:
        return re.sub(rf"^that {one[1]}\b", f"{one[1]}s you control", body)
    host = re.match(r"(enchanted|equipped) creature\b", cond, re.I)
    if host:
        return re.sub(r"^(?:it|they)\b", host[1].capitalize() + " creature", body)
    if re.match(r"(?:~|it)\b", cond) or "~" in cond or not cond:
        return re.sub(r"^it\b", "~", body)
    return body


_PT = r"[+-](?:\d+|X)/[+-](?:\d+|X)"


def _scale(body: str):
    """(body with a plain pump, quantity spec or None) or None when the scale can't be read."""
    from .cx_grammar import _count_spec
    m = re.fullmatch(r"(.+), where X is (.+)", body)
    if m:
        from .cards.clauses import _xq
        pts = re.findall(r"([+-])(X|\d+)/([+-])(X|\d+)", m[1])
        if len(pts) != 1 or "X" not in pts[0] or re.search(r"\bX\b", re.sub(_PT, "", m[1])):
            return None
        sp, p, st, t = pts[0]
        if p != "X" and p != "0" or t != "X" and t != "0":
            return None             # "+X/+1": only part of the pump scales
        new = f"{sp}{1 if p == 'X' else 0}/{st}{1 if t == 'X' else 0}"
        return re.sub(_PT, new, m[1], count=1), _quantity(_xq(m[2]), m[2], strict=False)    # _xq's own table
    m = re.fullmatch(rf"(.*\bgets? {_PT}) for each (.+?)((?:,| and|, and) (?:has|have|gets?|is|can|attacks)\b.*)?", body)
    if m:
        return m[1] + (m[3] or ""), _quantity(_count_spec(m[2]), m[2])
    if re.search(r"\b(?:for each|where X is)\b|\bX\b", body):
        return None
    return body, None


# x_quantity kinds that read the resolving item (the spell, the cost paid, what was revealed): no referent in a static.
_CONTEXT = ("spell", "stat", "sac", "sac_plus", "tap", "revealed", "exiled_gy", "subj_counters", "this_way", "arith")


def _quantity(spec, text: str, strict: bool = True):
    """The spec, or False when a static can't read it: a referent that isn't fixed ("it", that spell, the sacrificed
    creature) or one that reads power / toughness (it would read the bonus it gives)."""
    if spec is None or re.search(r"\b(?:it|its|that|those|them)\b", text, re.I) \
            or re.search(r"power|toughness", text + repr(spec), re.I) or spec[0] in _CONTEXT \
            or not _trusted(spec, text, strict):
        return False
    return spec


def _singular(word: str) -> str:
    from .cx_grammar_quantity import _singular as singular
    return singular(word)


def _fits_words(what: str) -> bool:
    """Whether copies.fits (which counting.count uses for "count" / "gy" specs) understands every word: an unknown
    word makes it count nothing ("instant and sorcery", "legendary creature")."""
    from .copies import _TYPES
    what = re.sub(r"^other ", "", what.strip())
    known = set(_TYPES) | {"permanent", "nonlegendary", "token", "nontoken", "nonland", "noncreature",
                           "nonartifact", "basic"}
    return all(w.lower() in known or w[:1].isupper() and w.isalpha() or w.lower().startswith("non-")
               for alt in re.split(r",? or |, ", what) for w in alt.split())


def _trusted(spec, text: str, strict: bool = True) -> bool:
    """Whether the quantity reader's spec says what the words say. The "for each" reader pluralises a word and asks
    the ", where X is" table, which can stop at the first noun ("artifact token you control" -> all artifacts,
    "land you control and each land card in your graveyard" -> a graveyard count); and a "count" / "gy" spec holds
    words copies.fits must understand. Only kinds checked here count."""
    kind = spec[0]
    t = re.sub(r"^the number of ", "", text.strip(), flags=re.I)
    if kind in ("life", "speed", "hand", "party", "colors_among", "devotion"):
        return True
    if kind == "counters":
        return bool(re.fullmatch(rf"{re.escape(spec[1])} counters? on ~", t, re.I))
    if kind in ("count", "gy"):
        if not isinstance(spec[1], str) or not _fits_words(spec[1]) or spec[1].lower().startswith("other") \
                and kind == "gy":
            return False
        if not strict:
            return True
        if kind == "count":
            m = re.fullmatch(r"([A-Za-z]+) you control", t)
            return bool(m) and _singular(m[1]).lower() == spec[1].lower()
        m = re.fullmatch(r"(?:([A-Za-z]+) )?cards? in your graveyard", t)
        return bool(m) and _singular(m[1] or "").lower() == spec[1].lower()
    if kind == "cxq":
        desc = next((x["cx_desc"] for x in spec[1:] if isinstance(x, dict) and "cx_desc" in x), "")
        return not re.search(r"\b(?:and|or)\b", desc)
    return not strict and kind in ("domain", "named_lands", "greatest_perm", "greatest")

def _nouns(value) -> set:
    """The type / subtype words a spec (or a group spec) names, lower case."""
    out = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("types_all", "types_any", "subtypes", "types", "sub", "any"):
                out |= {w.lower() for w in v}
            elif k in ("selector", "group") or isinstance(v, dict):
                out |= _nouns(v)
            elif k == "cx_desc":
                out |= {w.lower().rstrip("s") for w in v.split()}
    elif isinstance(value, (tuple, list)):
        for v in value:
            out |= _nouns(v)
    elif isinstance(value, str):
        out |= {w.lower().rstrip("s") for w in value.split() if w.lower() != "other"}
    return out


def _other(xq, scope: str, spec, st):
    """For a scaled group / host bonus whose Q says "other": "" (other than the static's source: it can be one of
    them, Ancestral Mask's "other enchantment"), "recipient" (other than the permanent getting the bonus: Skeletal
    Swarming's "other Skeletons" on each Skeleton), or None when either could be meant."""
    if scope == "self" or not re.search(r"\bother\b|'other'", repr(xq)):
        return ""
    words = _nouns(xq[1:] if xq[0] == "cxq" else xq[1])
    words = words - {"permanent"} if len(words) > 1 else words      # the grammar's marker beside a subtype
    own = {t.lower() for t in st.types} | {w.lower() for w in st.type_line.split("—")[-1].split()} \
        if "—" in st.type_line else {t.lower() for t in st.types}
    receivers = {"creature"} if scope == "host" else _nouns(spec) or {"permanent"}
    receivers = receivers - {"permanent"} if len(receivers) > 1 else receivers
    source_fits = "permanent" in words or bool(words & own)
    receiver_fits = "permanent" in words or "permanent" in receivers or bool(words & receivers) \
        or "creature" in words and "creature" in receivers
    if source_fits and receiver_fits:
        return None
    return "" if source_fits else "recipient"


def _parts(body: str, st):
    """(Subject, Parts) of a static body, or None."""
    from . import cx_grammar as g
    split = g._split(body)
    if split is None:
        return None
    subj = g.subject(split[0])
    if subj is None or subj.kind not in ("group", "host", "permanent") or subj.kind == "group" and subj.target != "none" \
            or subj.kind == "permanent" and subj.target != "self":
        return None
    if subj.kind == "host" and (subj.text.lower().startswith("equipped") and "Equipment" not in st.type_line
                                or subj.text.lower().startswith("enchanted") and not st.extra.get("aura")):
        return None
    parts = g._clauses(split[1], subj, "static")
    if parts is None and subj.kind == "permanent":
        # "~ has hexproof": the static keyword verbs name groups and hosts; ~ reads the same.
        import dataclasses
        parts = g._clauses(split[1], dataclasses.replace(subj, kind="host"), "static")
    if parts is None or any(p.kind not in ("pump", "grant", "cx_temp_kw", "cx_static") for p in parts) \
            or sum(p.kind == "pump" for p in parts) > 1:
        return None
    return subj, parts


def parse_line(line: str, st) -> bool:
    """The parse_static hook for a line with "as long as", "during your turn", "for each" or "where X is"."""
    from . import cx_grammar as g
    from .cards.model import KEYWORDS
    s = _LABEL.sub("", line.strip()[:-1])
    for code, body, cond in _gates(s):
        graveyard = code.startswith("@gy")
        code = code[3:] if graveyard else code
        if re.search(r"\b(?:as long as|during|until|this turn|if(?! able)|except|unless)\b", body, re.I):
            continue                    # another condition or a duration left in the static
        body = _it(body, cond if cond != "turn" else "")
        scaled = _scale(body)
        if scaled is None or scaled[1] is False:
            continue
        body, xq = scaled
        if not code and xq is None and not graveyard:
            continue                    # neither gate nor scale: not this module's line
        read = _parts(body, st)
        if read is None:
            continue
        subj, parts = read
        has_pt = any(p.kind == "pump" for p in parts)
        kws = tuple(k for p in parts if p.kind in ("grant", "cx_temp_kw")
                    for k in ([p.data["keyword"]] if p.kind == "grant" else sorted(p.data["keywords"])))
        if xq is not None and not has_pt:
            continue
        if has_pt and re.search(r"power|toughness", cond, re.I):
            continue                    # the condition would read the bonus it gates
        if any(k in KEYWORDS for k in kws) and _KW_WORDS.search(cond):
            continue                    # a keyword grant gated on keywords
        scope = {"permanent": "self", "host": "host", "group": "group"}[subj.kind]
        if graveyard:
            if scope != "group":
                continue
            scope = "gy_group"
        if scope != "self" and code and not code.startswith("lib:") and re.search(r"\bit(?:s|'s)?\b", cond):
            from .cx_condlib import as_static
            code = as_static(cond)      # "it" is the affected permanent: cx_condlib's codes read it as the ref
            if not code:
                continue
        spec = None
        if scope in ("group", "gy_group"):
            spec = subj.group["selector"] if "selector" in subj.group else dict(subj.group)
            if g._stat_conditioned(spec) and has_pt:
                continue
            if g._condition_keywords(spec) and any(k in KEYWORDS for k in kws):
                continue
        other = _other(xq, scope, spec, st) if xq is not None else ""
        if other is None:
            continue
        rows = []
        for p in parts:
            if p.kind == "pump":
                rows.append((code, scope, spec, ("pt", p.amount, p.amount2, xq) + ((other,) if other else ())))
            elif p.kind == "cx_static":
                rows.append((code, scope, spec, ("rule", p.data["rule"], p.data["value"])))
        if kws:
            rows.append((code, scope, spec, ("kw", kws)))
        if scope == "host" and st.extra.get("aura") and any(p.kind == "pump" and (p.amount < 0 or p.amount2 < 0) for p in parts):
            st.extra["gate_hostile"] = True     # "Enchanted creature gets -1/-1 for each Swamp you control": auras.finish
        rules = st.extra.setdefault("advanced_rules", {})
        rules["gated"] = tuple(rules.get("gated", ())) + tuple(rows)
        return True
    return False


# ---------------------------------------------------------------- engine

def _rows(perm, what: str):
    """(source, code, payload) for every gated row of kind ``what`` that reaches perm, before its condition."""
    from .permanent_templates import matches
    if not perm.abilities_suppressed:
        for code, scope, _spec, payload in perm.card.advanced_rules.get("gated", ()):
            if scope == "self" and payload[0] == what:
                yield perm, code, payload
    for x in list(perm.auras) + list(perm.equipment):
        for code, scope, _spec, payload in x.card.advanced_rules.get("gated", ()):
            if scope == "host" and payload[0] == what and perm.is_creature:
                yield x, code, payload
    game = getattr(perm.controller, "_game", None)
    if game is None:
        return
    for pl in game.players:
        for x in pl.battlefield:
            rows = x.card.advanced_rules.get("gated", ()) if x.card.advanced_rules else ()
            if not rows or x.abilities_suppressed:
                continue
            for code, scope, spec, payload in rows:
                if scope == "group" and payload[0] == what and matches(game, perm, spec, x.controller, x):
                    yield x, code, payload
        for c in pl.graveyard:
            for code, scope, spec, payload in (c.advanced_rules.get("gated", ()) if c.advanced_rules else ()):
                if scope == "gy_group" and payload[0] == what:
                    owner = _InGraveyard(pl, c)
                    if matches(game, perm, spec, pl, owner):
                        yield owner, code, payload


class _InGraveyard:
    """The source of a graveyard static (Anger): its owner is "you"."""
    abilities_suppressed = False
    auras = equipment = ()

    def __init__(self, owner, card):
        self.controller = self.owner = owner
        self.card = card
        self.counters = {}


def _on(source, code, perm) -> bool:
    if not code:
        return True
    if not code.startswith("lib:"):
        return source.condition(code)        # cx_conditions' codes: the source's own point of view
    from .cx_statics import _holds
    return _holds(source, code, perm)


def _count(source, spec, perm, recipient=False) -> int:
    """Q from the static's controller's point of view, with the static's source as the count's source ("counters on
    ~", "other enchantment" on Ancestral Mask), or the permanent getting the bonus when the row says "recipient"
    ("the number of other Skeletons you control" on each Skeleton: see _other)."""
    from .engine.state import StackItem
    game = getattr(source.controller, "_game", None)
    if game is None:
        return 0
    ref = perm if recipient else source
    return game.x_quantity(source.controller, spec, StackItem(source.controller, [], [], source=ref), None)


def pt_bonus(perm):
    bp = bt = 0
    for source, code, (_, p, t, xq, *ref) in _rows(perm, "pt"):
        if _on(source, code, perm):
            n = 1 if xq is None else _count(source, xq, perm, bool(ref and ref[0] == "recipient"))
            bp, bt = bp + p * n, bt + t * n
    return bp, bt


def grants(perm, kw: str) -> bool:
    return any(kw in payload[1] and _on(source, code, perm) for source, code, payload in _rows(perm, "kw"))


def rules(game, perm, rule: str) -> list:
    """The gated values of a cx_static family rule that apply to perm now (cx_grammar.static_rules)."""
    return [payload[2] for source, code, payload in _rows(perm, "rule")
            if payload[1] == rule and _on(source, code, perm)]
