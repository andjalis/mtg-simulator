"""Grammar verbs: tapping ("Tap target creature.", "Untap all lands you control.", "You may tap or untap target
permanent.", "That creature doesn't untap during its controller's next untap step.", "Islands don't untap during
their controllers' untap steps."). See mtgsim/GRAMMAR.md.

Imperative tap / untap use the existing kinds (tap, untap_prev; "tap or untap" is tap with or_untap: the
controller untaps their own and taps the opponent's). "Doesn't untap during ... next untap step" sets
Permanent.skip_untap (cx_skip_untap); the static form is the cx_no_untap rule, read in Game.untap_step."""
from __future__ import annotations


from .cx_grammar import Part, ai_value, object_phrase, verb


@verb(r"tap or untap (.+)", heads=("tap",), subjects=("imperative",))
def tap_or_untap(m, clause):
    obj = object_phrase(m[1])
    if obj is None or obj.kind not in ("permanent", "group") or clause.duration:
        return None
    return [Part("tap", data={"or_untap": True}, obj=obj)]


@verb(r"(tap|untap) (.+)", heads=("tap", "untap"), subjects=("imperative",))
def tap(m, clause):
    obj = object_phrase(m[2])
    if obj is None or obj.kind not in ("permanent", "group") or clause.duration:
        return None
    return [Part("tap" if m[1] == "tap" else "untap_prev", obj=obj)]


@verb(r"(?:doesn't|don't) untap during (its controller's|their controllers'|your) (next )?untap steps?",
      heads=("doesn't", "don't"), subjects=("permanent", "group", "host"))
def no_untap(m, clause):
    subj = clause.subject
    if m[1] == "your" and not (subj.kind == "group" and (subj.group.get("selector") or {}).get("controller") == "mine"
                               or subj.target == "self"):
        return None             # "your untap step" for something you may not control
    if m[2]:
        if clause.duration:
            return None
        return [Part("cx_skip_untap", data={"side": "theirs"})]
    if clause.duration != "static" or m[1] == "your" and subj.target == "self":
        return None             # "~ doesn't untap during your untap step" is another parser's line
    return [Part("cx_static", data={"rule": "cx_no_untap", "value": True})]


def _creature_worth(obj) -> float:
    return 1.0 + 0.2 * max(0, obj.power) if obj.is_creature else 0.3


@ai_value("tap")
def tap_value(game, me, eff, obj):
    if getattr(obj, "controller", None) is None:
        return 0.0
    if eff.data.get("or_untap") and obj.controller is me:
        return 0.3 if obj.tapped else 0.0
    if obj.tapped:
        return 0.0
    return _creature_worth(obj) * (-1.0 if obj.controller is me else 1.0)


@ai_value("untap_prev")
def untap_value(game, me, eff, obj):
    if not getattr(obj, "tapped", False):
        return 0.0
    return (0.5 if obj.controller is me else -0.5) * (2.0 if obj.card.is_land else 1.0)


@ai_value("cx_skip_untap")
def skip_value(game, me, eff, obj):
    if getattr(obj, "controller", None) is None:
        return 0.0
    return (0.5 + (0.5 if obj.tapped else 0.0)) * (-1.0 if obj.controller is me else 1.0)


