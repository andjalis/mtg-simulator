"""#625 slice 4: "as though it/they had flash" for filtered spell groups and for ~ under a condition.

    You may cast Spirit spells as though they had flash.                       (static, on a permanent)
    You may cast artifact, creature, and enchantment spells as though they had flash.
    {2}, {T}: You may cast creature spells this turn as though they had flash.  (this turn)
    You may cast ~ as though it had flash if you control a Faerie.             (~, gated by a condition)
    If there are two or more instant and/or sorcery cards in your graveyard, you may cast ~ as though it had flash.

"As long as <condition>, you may cast <kind> spells as though they had flash." and "Any player may cast <kind> spells
as though they had flash." store ``(specs, condition, any player)`` in ``advanced_rules["flash_gated"]`` (#625).
A static line stores filter specs in ``advanced_rules["flash_specs"]`` (the condition library's filter dialect);
"this turn" is a ``cx_player_flag`` named ``flash_filter`` carrying the specs; a gated ~ stores a condition code in
``advanced_rules["flash_self"]``. ``flash_allowed`` is what ``Game.can_cast`` asks. A condition the library doesn't
read, a spell filter it doesn't know ("with enchant creature") or a rider keeps the line unmatched.
"""
from __future__ import annotations

import re

_ALT = re.compile(r", and |, | and ")


def specs_for(text: str):
    """The filter specs of "Spirit", "artifact, creature, and enchantment" or "" (every spell); None if unread."""
    from .cx_condlib import _filter
    text = text.strip()
    if not text:
        return [{}]
    out = []
    for alt in _ALT.split(re.sub(r"\bspells?\b", "", text).replace("  ", " ").strip()):
        spec = _filter(alt.strip())
        if not spec:
            return None
        out.append(spec)
    return out


_GATED = re.compile(r"(?:[A-Z][\w' ]* — )?(?:As long as (?P<c>.+?), you|(?P<any>Any player)) may cast "
                    r"(?:(?P<k>[^.]+?) )?spells as though they had flash\.")
_STATIC = re.compile(r"You may cast (?:(.+?) )?spells as though they had flash\.")
_SELF = (re.compile(r"You may cast ~ as though it had flash if (.+)\."),
         re.compile(r"(?:If|As long as) (.+?), you may cast ~ as though it had flash\."),
         re.compile(r"As long as (.+?), you may cast ~ as though it had flash\."))


def parse_line(st, line: str):
    """Face-line handler: returns None once the line is handled, else the line."""
    line = re.sub(r" \(You may cast it any time you could cast an instant\.\)$", "", line)
    g = _GATED.fullmatch(line)
    if g:               # "As long as <condition>, you may cast ..." / "Any player may cast ..." (#625)
        specs = specs_for(g["k"] or "")
        cond = ""
        if g["c"]:
            from .cx_condlib import parse
            cond = parse(g["c"])
        if specs and (cond or g["any"]):
            rules = st.extra.setdefault("advanced_rules", {})
            rules["flash_gated"] = tuple(rules.get("flash_gated", ())) + ((specs, cond, bool(g["any"])),)
            return None
        return line
    m = _STATIC.fullmatch(line)
    if m and (m[1] or "").lower() not in ("", "sorcery"):      # the unfiltered forms are cx_night_aura's
        specs = specs_for(m[1])
        if specs:
            rules = st.extra.setdefault("advanced_rules", {})
            rules["flash_specs"] = list(rules.get("flash_specs", [])) + specs
            return None
    body = re.sub(r"^[A-Z][\w' ]+ — ", "", line) if line.count(" — ") == 1 else line     # "Ferocious — If ..."
    for rx in _SELF:
        m = rx.fullmatch(body)
        if m:
            from .cx_condlib import parse
            code = parse(m[1])
            if code and "~" not in m[1]:
                st.extra.setdefault("advanced_rules", {})["flash_self"] = code
                return None
    return line


def flash_allowed(game, p, card) -> bool:
    """May p cast this card at instant speed because of a flash permission?"""
    from .cx_condlib import _card_ok, check
    from .cx_next_turn import flags
    code = card.advanced_rules.get("flash_self")
    if code and check(game, p, code):
        return True
    for x in p.battlefield:
        if x.abilities_suppressed:
            continue
        if any(_card_ok(card, s) for s in x.card.advanced_rules.get("flash_specs", ())):
            return True
    if any(_card_ok(card, s) for f in flags(game, p, "flash_filter") for s in f.data["specs"]):
        return True
    for pl in game.players:
        for x in pl.battlefield:
            for specs, cond, anyone in () if x.abilities_suppressed else x.card.advanced_rules.get("flash_gated", ()):
                if (anyone or pl is p) and any(_card_ok(card, s) for s in specs) and \
                        (not cond or _holds(game, pl, cond, x)):
                    return True
    return False


def _holds(game, p, code, source) -> bool:
    """A condition read with the permission's permanent as its source ("as long as ~ is tapped")."""
    from types import SimpleNamespace
    from .cx_condlib import _eval_any
    item = SimpleNamespace(source=source, context=None, card=source.card, controller=p, targets=[])
    return bool(_eval_any(game, p, code, item, source))


def _this_turn(m):
    from .cards.model import NO_MATCH, Effect
    kind = (m["kind"] or "") if "kind" in m.re.groupindex else ""
    specs = specs_for(kind)
    if not specs:
        return NO_MATCH
    return Effect("cx_player_flag", 0, data={"flag": "flash_filter", "who": "you", "specs": specs})


EFFECT_PATTERNS = [
    (r"you may cast (?:(?P<kind>[^.]+?) )?spells this turn as though they had flash", _this_turn),
]
