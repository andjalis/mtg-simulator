"""Grammar verbs: who can block whom ("can't be blocked by Walls", "can't be blocked by creatures with power 2 or
less this turn", "can't be blocked except by black creatures", "can't block creatures with flying"), as statics
on ~, an Aura's or Equipment's host or a group, or for this turn. See mtgsim/GRAMMAR.md.

The rules are ``cx_evade`` (("by" | "except", noun spec) on the attacker) and ``cx_block_limit`` (noun spec on the
blocker: what it can't block), read through cx_grammar.static_rules by ``block_forbidden``, which
engine/state.can_block asks."""
from __future__ import annotations

from .cx_grammar import Part, _noun, static_rules, verb

_SUBJECTS = ("permanent", "group", "host")


def _spec(text: str):
    noun = _noun(text, plural=True) or _noun(text, plural=False)
    if noun is None:
        return None
    return noun["selector"] if "selector" in noun else noun


def _part(clause, rule, value):
    if clause.duration == "static":
        return [Part("cx_static", data={"rule": rule, "value": value})]
    if clause.duration in ("turn", "eot", "combat") and clause.subject.kind != "host":
        return [Part("cx_rule_turn", data={"rule": rule, "value": value,
                                           "side": "mine" if rule == "cx_evade" else "theirs"})]
    return None


@verb(r"can't be blocked (by|except by) (.+)", heads=("can't",), subjects=_SUBJECTS)
def unblockable_by(m, clause):
    spec = _spec(m[2])
    return None if spec is None else _part(clause, "cx_evade", ("by" if m[1] == "by" else "except", spec))


@verb(r"can't block (.+)", heads=("can't",), subjects=_SUBJECTS)
def cant_block(m, clause):
    spec = _spec(m[1])
    return None if spec is None else _part(clause, "cx_block_limit", spec)


def block_forbidden(blocker, attacker) -> bool:
    """Whether a grammar evasion rule stops blocker from blocking attacker."""
    from .permanent_templates import matches
    game = getattr(attacker.controller, "_game", None)
    for mode, spec in static_rules(game, attacker, "cx_evade"):
        if matches(game, blocker, spec, attacker.controller, attacker) == (mode == "by"):
            return True
    return any(matches(game, attacker, spec, blocker.controller, blocker)
               for spec in static_rules(game, blocker, "cx_block_limit"))
