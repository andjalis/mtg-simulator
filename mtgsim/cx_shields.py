"""Damage prevention and redirection rules:

    Prevent all damage that would be dealt to creatures this turn.             (Blinding Fog)
    Prevent all combat damage that would be dealt by target attacking creature this turn.     (Restrain)
    Prevent all combat damage that would be dealt to and dealt by ~ this turn.  (Deftblade Elite)
    Prevent all damage that would be dealt to you this turn by attacking creatures.          (Deep Wood)
    {1}: The next time a red source of your choice would deal damage to you this turn, prevent that damage.   (CoP: Red)
    Prevent all damage a source of your choice would deal to you this turn.    (Auriok Replica)
    {0}: The next 1 damage that would be dealt to ~ this turn is dealt to target creature you control instead.
    Prevent all damage that would be dealt to creatures you control.           (Inner Sanctum, a static)
    If a source an opponent controls would deal damage to you, prevent 1 of that damage.     (Guardian Seraph)
    All damage that would be dealt to you is dealt to ~ instead.               (Empyrial Archangel)
    Damage can't be prevented.     Damage that would be dealt by ~ can't be prevented.

A rule is a dict: ``combat`` (None, True or False), ``to`` and ``by`` (what the damage is dealt to and by), ``n`` (prevent
only that much of each damage event), ``uses`` (events it applies to), ``bind`` (the first source it stops is the one
chosen), ``dest`` and ``budget`` (redirection). Spells and abilities add rules for the turn to ``game._cx_shields``;
statics are ``advanced_rules["cx_prevent"]`` on the permanent's card. ``apply`` runs in Game.deal_damage.

A subject is a tuple: ("you",), ("self",), ("prev",), ("target",), ("host",), ("players",), ("any",),
("blocking",) for "creatures it's blocking", ("blocked_by",) for "creatures blocking it", or ("group", selector)."""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _subject(text: str, static: bool):
    """(subject, target kind, target data) for a "to ..." or "by ..." phrase, or None."""
    from .permanent_templates import selector
    text = text.strip()
    low = text.lower()
    if low == "you":
        return ("you",), None, None
    if low in ("~", "him", "her"):
        return ("self",), None, None
    if low in ("enchanted creature", "equipped creature"):
        return (("host",), None, None) if static else None
    if low in ("players", "each player"):
        return ("players",), None, None
    if low in ("creatures it's blocking", "creatures blocking it"):
        return ((("blocking",) if "it's" in low else ("blocked_by",)), None, None) if static else None
    if static:
        pass
    elif low in ("it", "that creature"):
        return ("prev",), None, None
    elif low.startswith(("target ", "another target ")):
        m = re.fullmatch(r"(another )?target (attacking |artifact )?(creature|player)( you control)?", low)
        if not m:
            return None
        if m[3] == "player":
            return (("target",), "player", {}) if not (m[1] or m[2] or m[4]) else None
        data: dict = {}
        if m[1]:
            data["other"] = True
        kind = "creature_mine" if m[4] else "creature"
        if m[2] == "artifact ":
            data["selector"] = {"types_all": ["artifact", "creature"]}
        return ("target",), kind, (data, "attacking" if m[2] == "attacking " else "")
    m = re.fullmatch(r"(.+?) sources", text)
    if m:
        words = m[1].split()
        if all(w.lower() in _COLORS or w.lower() == "artifact" for w in words):
            spec = {}
            for w in words:
                if w.lower() == "artifact":
                    spec["types_all"] = ["artifact"]
                else:
                    spec.setdefault("colors", []).append(_COLORS[w.lower()])
            return ("group", spec), None, None
        return None
    spec = selector(text, plural=True)
    if spec is None or "keyword" in spec and spec["keyword"][0] not in ("flying",):
        return None
    return ("group", spec), None, None


def _rule_effect(combat, to_text, by_text, static=False):
    """An Effect (one-shot) or a rule tuple (static) for a prevention phrase, or None."""
    to = by = (("any",), None, None)
    if to_text:
        to = _subject(to_text, static)
    if by_text:
        by = _subject(by_text, static)
    if to is None or by is None or to[1] and by[1]:
        return None
    rule = {"combat": combat, "to": to[0], "by": by[0]}
    if static:
        return rule
    kind, extra = to[1] or by[1], to[2] or by[2]
    if not kind:
        return _effect("cx_shield", data={"rule": rule})
    data, flt = extra if isinstance(extra, tuple) else (extra, "")
    side = "theirs" if by[1] else "mine"
    return _effect("cx_shield", target=kind, filter=flt, data=dict(data, rule=rule, side=side))


_COMBAT = {"combat ": True, "noncombat ": False, None: None, "": None}


def _prevent_all(m):
    from .cards.model import NO_MATCH
    rest = m["rest"]
    if "this turn" not in rest:
        return NO_MATCH
    rest = re.sub(r" ?this turn ?", " ", rest).strip()
    p = re.fullmatch(r"(?:to (?P<to>.+?))? ?(?:by (?P<by>.+?))?", rest)
    if not p or not (p["to"] or p["by"]):
        return NO_MATCH
    eff = _rule_effect(_COMBAT[m["c"]], p["to"], p["by"])
    return eff if eff is not None else NO_MATCH


def _would_deal(m):
    from .cards.model import NO_MATCH
    eff = _rule_effect(_COMBAT[m["c"]], None, m["by"])
    return eff if eff is not None else NO_MATCH


def _to_and_by(m):
    from .cards.model import NO_MATCH
    eff = _rule_effect(True, m["w"], None)
    if eff is None:
        return NO_MATCH
    eff.data["rule"]["both"] = True
    return eff


def _next_time(m):
    by = ("any",)
    col = (m["col"] or "").strip().lower()
    if col == "artifact":
        by = ("group", {"types_all": ["artifact"]})
    elif col:
        by = ("group", {"colors": [_COLORS[col]]})
    return _effect("cx_shield", data={"rule": {"combat": None, "to": ("you",), "by": by, "uses": 1, "bind": True}})


def _redirect(m):
    return _effect("cx_shield", target="creature_mine",
                   data={"rule": {"combat": None, "to": ("self",), "by": ("any",), "budget": int(m["n"]),
                                  "dest": "target"}, "side": "mine"})


EFFECT_PATTERNS = [
    (r"prevent all combat damage that would be dealt to and dealt by (?P<w>~|it|that creature|target creature) "
     r"this turn", _to_and_by),
    (r"prevent all (?P<c>combat |noncombat )?damage that would be dealt (?P<rest>.+)", _prevent_all),
    (r"prevent all (?P<c>combat )?damage (?P<by>~|it|that creature|target (?:attacking )?creature) would deal this turn",
     _would_deal),
    (r"the next time an? (?P<col>white |blue |black |red |green |artifact )?source of your choice would deal damage "
     r"to you this turn, prevent that damage", _next_time),
    (r"prevent all damage (?:that )?a source of your choice would deal to you this turn",
     lambda m: _effect("cx_shield", data={"rule": {"combat": None, "to": ("you",), "by": ("any",), "bind": True}})),
    (r"the next (?P<n>\d+) damage that would be dealt to ~ this turn is dealt to target creature you control instead",
     _redirect),
]


# ---------------------------------------------------------------------------
# Static lines
# ---------------------------------------------------------------------------

_STATIC = re.compile(r"Prevent all (?P<c>combat |noncombat )?damage that would be dealt (?:to (?P<to>.+?))?"
                     r"(?: by (?P<by>.+?))?\.")
_REDUCE = re.compile(r"If a source (?P<by>an opponent controls |you don't control )?would deal damage to "
                     r"(?P<to>you|~), prevent (?P<n>\d+) of that damage\.")
_REDIRECT = re.compile(r"All damage that would be dealt to you is dealt to (?P<d>~|enchanted creature) instead\.")
_UNPREVENT = {"Damage can't be prevented.": "all", "Damage that would be dealt by ~ can't be prevented.": "self",
              "Combat damage that would be dealt by creatures you control can't be prevented.": "mine"}


def parse_line(line: str, st) -> bool:
    rules = None
    m = _STATIC.fullmatch(line)
    if m and (m["to"] or m["by"]) and "this turn" not in line:
        rule = _rule_effect(_COMBAT[m["c"]], m["to"], m["by"], static=True)
        if rule is None:
            return False
        rules = (rule,)
    m = None if rules else _REDUCE.fullmatch(line)
    if m:
        by = ("any",) if not m["by"] else ("opp",)
        rules = ({"combat": None, "to": ("you",) if m["to"] == "you" else ("self",), "by": by, "n": int(m["n"])},)
    m = None if rules else _REDIRECT.fullmatch(line)
    if m:
        rules = ({"combat": None, "to": ("you",), "by": ("any",), "dest": "self" if m["d"] == "~" else "host"},)
    if rules:
        adv = st.extra.setdefault("advanced_rules", {})
        adv["cx_prevent"] = adv.get("cx_prevent", ()) + rules
        return True
    if line in _UNPREVENT:
        st.extra.setdefault("advanced_rules", {})["cx_unprevent"] = _UNPREVENT[line]
        return True
    return False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def add_rule(game, p, rule, source, target=None, prev=None):
    bound = dict(rule, owner=p, src=source, turn=game.turn)
    for key in ("to", "by"):
        kind = rule[key][0]
        if kind in ("target", "prev", "self"):
            obj = {"target": target, "prev": prev, "self": source}[kind]
            if obj is None:
                return False
            bound[key] = ("obj", obj)
    if rule.get("both"):
        bound["by"] = bound["to"]
    if rule.get("dest") == "target":
        if target is None:
            return False
        bound["dest"] = target
    if not hasattr(game, "_cx_shields"):
        game._cx_shields = []
    game._cx_shields.append(bound)
    return True


def _hit(game, subject, obj, owner, src, by=None) -> bool:
    from .engine.state import Permanent, Player
    from .cards.model import CardDef
    kind = subject[0]
    if kind == "any":
        return True
    if kind == "you":
        return obj is owner
    if kind == "opp":
        return by is not None and by is not owner
    if kind in ("obj", "self"):
        return obj is (subject[1] if kind == "obj" else src)
    if kind == "host":
        return src is not None and obj is getattr(src, "attached_to", None)
    if kind == "players":
        return isinstance(obj, Player)
    if kind == "blocking":
        return isinstance(obj, Permanent) and src in game.blocks.get(obj, ())
    if kind == "blocked_by":
        return isinstance(obj, Permanent) and obj in game.blocks.get(src, ())
    if kind == "group":
        spec = subject[1]
        if isinstance(obj, Permanent):
            from .permanent_templates import matches
            return matches(game, obj, spec, owner, src)
        if isinstance(obj, CardDef) and set(spec) <= {"controller", "types_all", "colors"}:
            if spec.get("controller") and (spec["controller"] == "mine") != (by is owner):
                return False
            return all(t.capitalize() in obj.types for t in spec.get("types_all", ()) if t != "permanent") and \
                all(c in obj.colors for c in spec.get("colors", ()))
    return False


def _statics(game):
    for pl in game.players:
        for x in pl.battlefield:
            rules = x.card.advanced_rules.get("cx_prevent") if x.card.advanced_rules else None
            if rules and not x.abilities_suppressed:
                for rule in rules:
                    yield dict(rule, owner=pl, src=x)


def _live(game):
    rules = getattr(game, "_cx_shields", None)
    if not rules:
        return []
    alive = [r for r in rules if r["turn"] == game.turn and r.get("uses", 1) > 0 and r.get("budget", 1) > 0]
    if len(alive) != len(rules):
        game._cx_shields = alive
    return alive


def _applies(game, rule, target, source, by, combat) -> bool:
    if rule["combat"] is not None and rule["combat"] != combat:
        return False
    if rule.get("bound") is not None and rule["bound"] is not source:
        return False
    owner, src = rule["owner"], rule["src"]
    if rule.get("both"):
        return _hit(game, rule["to"], target, owner, src) or _hit(game, rule["to"], source, owner, src)
    return _hit(game, rule["to"], target, owner, src) and _hit(game, rule["by"], source, owner, src, by)


_REDIRECTING: set = set()


def apply(game, target, amount: int, by, source, combat: bool, preventable: bool) -> int:
    """The damage left after the prevention and redirection rules (redirected damage is dealt here)."""
    rules = _live(game)
    statics = list(_statics(game)) if any(p.battlefield for p in game.players) else []
    if not rules and not statics:
        return amount
    for rule in rules + statics:
        if amount <= 0:
            break
        if not _applies(game, rule, target, source, by, combat):
            continue
        dest = rule.get("dest")
        if dest is not None:
            dest = {"self": rule["src"], "host": getattr(rule["src"], "attached_to", None)}.get(dest, dest)
            if dest is None or dest is target or id(dest) in _REDIRECTING or \
                    getattr(dest, "controller", None) is not None and dest not in dest.controller.battlefield:
                continue
            moved = min(amount, rule["budget"]) if "budget" in rule else amount
            if "budget" in rule:
                rule["budget"] -= moved
            amount -= moved
            game.log(f"{moved} damage is dealt to {dest} instead", rule["owner"])
            _REDIRECTING.add(id(target))
            try:
                game.deal_damage(dest, moved, by, source=source, combat=combat)
            finally:
                _REDIRECTING.discard(id(target))
            continue
        if not preventable:
            continue
        if rule.get("bind"):
            rule["bound"] = source
        stop = min(amount, rule["n"]) if rule.get("n") else amount
        amount -= stop
        if "uses" in rule:
            rule["uses"] -= 1
        game.log(f"{stop} damage to {target} is prevented", rule["owner"])
    return amount


def unpreventable(game, source) -> bool:
    for pl in game.players:
        for x in pl.battlefield:
            mode = x.card.advanced_rules.get("cx_unprevent") if x.card.advanced_rules else None
            if mode and (mode == "all" or mode == "self" and source is x or
                         mode == "mine" and getattr(source, "controller", None) is pl and source.is_creature):
                return True
    return False
