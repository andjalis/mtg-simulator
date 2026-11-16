"""Replacement effects that change how many counters are put on a permanent (#407, first slice).

    If one or more +1/+1 counters would be put on a creature you control, twice that many +1/+1 counters are put
    on it instead.                                                                       (Corpsejack Menace)
    If one or more counters would be put on an artifact or creature you control, that many plus one of each of
    those kinds of counters are put on that permanent instead.                           (Winding Constrictor)
    If one or more -1/-1 counters would be put on a creature you control, that many -1/-1 counters minus one are
    put on it instead.                                                                   (Vizier of Remedies)
    If you would put one or more counters on a permanent you control, put twice that many ... instead.
    If an effect would put one or more counters on a permanent you control, it puts twice that many ... instead.

Each line becomes a step in ``advanced_rules["counter_mods"]``: ``{"counter": kind or "", "obj": [specs], "self":
bool, "other": bool, "op": "add" | "mul", "n": int}``. ``counter_amount`` (advanced_templates, which every
``Counters.__setitem__`` increase goes through) applies the steps of every permanent on the battlefield whose
object matches. Several steps: additions (and subtractions) first, then doublings. That order is the affected
player's best choice (more of the counters they get, fewer -1/-1 counters), so it stands in for their choice.

The engine doesn't record who puts a counter, or whether a cost or an effect puts it. The "If you would put"
and "If an effect would put" wordings are played on every counter put on a matching permanent, and are recorded
as simplifications. Counters on players, the "until end of turn" forms and anything else stay unmatched.
"""
from __future__ import annotations

import re

_KIND = r"(?:\+1/\+1|-1/-1|[a-z]+)"
_REF = r"(?:it|that creature|that permanent|that artifact|that land|~)"


def _objects(text: str):
    """(specs, self, other) for "a creature you control", "another creature you control", "an Army, Goblin, or Orc
    you control", "~", "a creature" (anyone's), or None."""
    from .cx_condlib import _filter
    t = text.strip()
    if t == "~":
        return {"obj": [], "self": True, "other": False, "mine": True}
    m = re.fullmatch(r"(?:a|an|another) (.+?)( you control| your team controls)?", t)
    if not m:
        return None
    other = t.startswith("another ")
    words = re.split(r", or |, | or ", m[1])
    specs = []
    for w in words:
        spec = _filter(w, plural=False)
        if spec is None or set(spec) - {"types", "sub"}:
            return None
        specs.append(spec)
    return {"obj": specs, "self": False, "other": other, "mine": bool(m[2])}


def _step(q: str, kind: str):
    """("add" | "mul", n) for "twice that many", "that many plus one", "that many <kind> counters minus one"."""
    q = q.strip()
    if q.startswith("twice that many"):
        return "mul", 2
    m = re.fullmatch(r"that many(?: " + re.escape(kind) + r" counters)? (plus|minus) one", q) if kind else \
        re.fullmatch(r"that many (plus|minus) one", q)
    if m:
        return "add", 1 if m[1] == "plus" else -1
    return None


_PASSIVE = re.compile(
    rf"If one or more (?:(?P<kind>{_KIND}) )?counters would be put on (?P<obj>.+?), (?P<q>twice that many|that many"
    rf"(?: {_KIND} counters)?(?: plus one| minus one)?)(?:(?: of each of those kinds of)?(?: (?P<kind2>{_KIND}))? "
    rf"counters)? are put on {_REF} instead\.")
_ACTIVE = re.compile(
    rf"If (?P<who>you|an effect) would put one or more (?:(?P<kind>{_KIND}) )?counters on (?P<obj>.+?), "
    rf"(?:it puts|put) (?P<q>twice that many|that many plus one)(?: of each of those kinds of counters| of those "
    rf"counters| (?P<kind2>{_KIND}) counters) on {_REF} instead\.")


_PLAYER = re.compile(r"If you would get one or more counters, you get (?P<q>twice that many|that many plus one) of each of "
                     r"those kinds of counters instead\.")
_OR_YOU = re.compile(r"(?P<head>If you would put one or more counters on (?P<obj>.+?)) or on yourself, put (?P<q>twice "
                     r"that many|that many plus one) of each of those kinds of counters on that permanent or player "
                     r"instead\.")


def parse_mod(line: str):
    """(step dict, note) or None; a step for counters on you carries "player": True (no permanent object)."""
    m = _PLAYER.fullmatch(line)
    if m:
        op, n = _step(m["q"], "")
        return {"player": True, "obj": [], "self": False, "other": False, "mine": True, "counter": "",
                "op": op, "n": n}, ""
    m = _OR_YOU.fullmatch(line)
    if m:       # one line, two steps: the permanents (as the line without "or on yourself") and you
        got = _parse_one(f"{m['head']}, put {m['q']} of each of those kinds of counters on that permanent instead.")
        if got is None:
            return None
        mod, note = got
        return dict(mod, also_player=True), note
    return _parse_one(line)


def _parse_one(line: str):
    """(step dict, simplification note or "") for a counter-amount replacement line, or None."""
    m = _PASSIVE.fullmatch(line) or _ACTIVE.fullmatch(line)
    if not m:
        return None
    kind = (m["kind"] or "").lower()
    kind2 = (m["kind2"] or "").lower()
    q = m["q"]
    if kind2 and kind2 != kind:
        return None             # "counters ... are put on it": the same kind, or each of those kinds
    if not kind and not re.search(r"of each of those kinds|of those counters", line):
        return None
    if kind and re.search(r"of each of those kinds", line):
        return None
    if "minus one" in q and not kind:
        return None
    obj = _objects(m["obj"])
    step = _step(q.replace(f" {kind} counters", "") if kind else q, "")
    if obj is None or step is None:
        return None
    note = ""
    if m.re is _ACTIVE:
        note = ("who puts the counters is not checked" if m["who"] == "you" else
                "counters put as a cost are changed too")
    return dict(obj, counter=kind, op=step[0], n=step[1]), note


def face_line(st, line):
    """Face-line parser (put first in cards/parse.py's list by cards/__init__.py)."""
    tok = parse_token_line(line)
    if tok is not None:
        rules = st.extra.setdefault("advanced_rules", {})
        if tok[0] == "double_all":
            rules["token_double_all"] = True
        else:
            rules.setdefault("token_adders", []).append(tok[1])
        return None
    got = parse_mod(line)
    if got is None:
        return line
    mod, note = got
    st.extra.setdefault("advanced_rules", {}).setdefault("counter_mods", []).append(mod)
    if note:
        st.approximations.append(f"{note}: {line}")
    return None


def modify_player(player, name: str, amount: int) -> int:
    """Counters ``player`` gets after "you get that many plus one ... instead" steps of their own permanents."""
    adds, muls = 0, 1
    for x in player.battlefield:
        if x.abilities_suppressed:
            continue
        for mod in x.card.advanced_rules.get("counter_mods", ()):
            if mod.get("player") or mod.get("also_player"):
                if mod["op"] == "add":
                    adds += mod["n"]
                else:
                    muls *= mod["n"]
    return max(0, (amount + adds) * muls) if amount > 0 else amount


def _matches(mod, holder, perm) -> bool:
    from .cx_condlib import _card_ok
    if mod.get("player"):
        return False
    if mod["self"]:
        return perm is holder
    if mod["mine"] and perm.controller is not holder.controller:
        return False
    if mod["other"] and perm is holder:
        return False
    return any(_card_ok(perm.card, spec, perm) for spec in mod["obj"])


def modify(perm, name: str, amount: int, extra_add: int = 0) -> int:
    """The number of ``name`` counters put on ``perm`` after every matching counter_mods step on the battlefield
    (and ``extra_add``, the older fixed "plus one" rule): additions first, then doublings, never below 0."""
    game = getattr(perm.controller, "_game", None)
    players = game.players if game is not None else [perm.controller]
    adds, muls = extra_add, 1
    for pl in players:
        for x in pl.battlefield:
            if x.abilities_suppressed:
                continue
            for mod in x.card.advanced_rules.get("counter_mods", ()):
                if mod["counter"] and mod["counter"] != name or not _matches(mod, x, perm):
                    continue
                if mod["op"] == "add":
                    adds += mod["n"]
                else:
                    muls *= mod["n"]
    return max(0, (amount + adds) * muls) if amount > 0 else amount

# ---------------------------------------------------------------------------------------------------------------
# Tokens (#407, second slice)
#
#     If one or more tokens would be created, twice that many of those tokens are created instead.   (Primal Vigor)
#     If one or more artifact tokens would be created under your control, those tokens plus an additional 1/1
#     colorless Thopter artifact creature token with flying are created instead.                (Stridehangar Automaton)
#     If you would create one or more Treasure tokens, instead create those tokens plus an additional Treasure token.
#
# Doublings stay where the engine counts tokens (``token_multiplier``, used by every path that already doubled for
# ``token_double``); Primal Vigor's "any player" doubling is ``token_double_all``. An adder is
# ``advanced_rules["token_adders"]``: (kind filter, the extra token's Effect), applied once per creation event,
# an entry batch or a lone token entering outside one (``tokens_created``). The extra token is itself created
# through the doublers, which gives the affected player's best order: add, then double ((n + 1) * 2).
# ---------------------------------------------------------------------------------------------------------------

_TOKEN_KIND = r"(?:(?P<what>artifact|creature|Treasure|Food|Clue|Map) )?"
_ADDER = [
    re.compile(rf"If one or more {_TOKEN_KIND}tokens would be created under your control, those tokens plus "
               rf"(?:an additional |a |an )(?P<extra>.+? token(?: with [^.]+?)?) are created instead\."),
    re.compile(rf"If you would create one or more {_TOKEN_KIND}tokens, instead create those tokens plus "
               rf"(?:an additional |a |an )(?P<extra>.+? token(?: with [^.]+?)?)\."),
]


def parse_token_line(line: str):
    """("double_all", None) | ("adder", (what, Effect)) | None."""
    if line == "If one or more tokens would be created, twice that many of those tokens are created instead.":
        return "double_all", None
    for rx in _ADDER:
        m = rx.fullmatch(line)
        if not m:
            continue
        from .cards import _parse_effects
        extra = m["extra"]
        effects, bad = _parse_effects(f"Create {'an' if extra[0].lower() in 'aeiou' else 'a'} {extra}.")
        if bad or len(effects) != 1 or effects[0].kind not in ("token", "cx_token") or effects[0].amount != 1 or \
                effects[0].cond or effects[0].target != "none":
            return None
        return "adder", ((m["what"] or "").lower(), effects[0])
    return None


def token_multiplier(game, p) -> int:
    """How many tokens p gets for each one an effect would create: 2 for every doubling replacement that applies."""
    own = sum(bool(x.card.token_double) for x in p.battlefield if not x.abilities_suppressed)
    players = game.players if game is not None else [p]
    anyone = sum(bool(x.card.advanced_rules.get("token_double_all")) for pl in players for x in pl.battlefield
                 if not x.abilities_suppressed)
    return 2 ** (own + anyone)


def _kind_ok(what: str, perm) -> bool:
    if not what:
        return True
    if what in ("artifact", "creature"):
        return what.capitalize() in perm.card.types
    return what.lower() == (getattr(perm.card, "token_kind", "") or "").lower() or what in perm.card.subtypes


def tokens_created(game, perms) -> None:
    """One creation event's tokens just entered: each controller's matching adders create their extra token once."""
    if getattr(game, "_token_adding", False):
        return                  # the extra tokens are part of the same event
    by_player = {}
    for perm in perms:
        if getattr(perm.card, "is_token", False) and perm in perm.controller.battlefield:
            by_player.setdefault(id(perm.controller), (perm.controller, []))[1].append(perm)
    if not by_player:
        return
    game._token_adding = True
    try:
        for p, made in by_player.values():
            for source in list(p.battlefield):
                if source.abilities_suppressed:
                    continue
                for what, extra in source.card.advanced_rules.get("token_adders", ()):
                    if any(_kind_ok(what, x) for x in made):
                        game.resolve(p, extra, None, None)
                        game.log(f"{source.card.name} adds a token", p)
    finally:
        game._token_adding = False
