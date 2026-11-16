"""Face states (#635): transform conditions and destinations, turning face up / down, more manifest and cloak.

    Remove an ice counter from ~. Then if it has no ice counters on it, transform it.        (Thing in the Ice)
    When ~ deals combat damage to a player, transform it.                                     (Uninvited Geist)

"Then if <condition>, <effects>" is the plain "If <condition>, <effects>" (the "then" only orders the sentence after
the one before, as sentences already are); "transform it" is ``transform_it`` (the previous object or the permanent
the trigger fired on, else ~; wordings core.json).
"""
from __future__ import annotations

import re

_TRANSFORM_BODY = (r"(?:untap (?:~|it),? (?:and|then) |(?:you may )?remove (?:those|them|all of them|those counters)"
                   r"(?: counters)? and )?transform (?:it|~|her|him)")
def _counters_then_transform(m):
    """"Then if there are N or more X counters on it, [remove those counters and] transform it" (and "~ has ...,
    remove them and transform ~"): the transform first, then the removal, so both read the condition before the
    counters go (the transform keeps them)."""
    # the object holding the counters is the card itself in every such sentence: name it, so a token the ability
    # just made (Wedding Announcement's Human) is never "it"
    n, kind, remove = m["n"], m["kind"], m["remove"]
    text = f"If ~ has {n} or more {kind} counters on it, transform ~"
    return text + (f" and remove all {kind} counters from ~" if remove else "")


SUBS = [
    (re.compile(r"(?:^|(?<=\. ))Then if (?:there are (?P<n>\w+) or more (?P<kind>[\w+/-]+) counters on (?P<obj>it|~)|"
                r"(?P<obj2>it|~) has (?P<n2>\w+) or more (?P<kind2>[\w+/-]+) counters on it), "
                r"(?P<remove>remove (?:those|them|all of them)(?: counters)?,? and )?transform (?P<what>it|~)(?=\.|$)", re.I),
     lambda m: _counters_then_transform({"obj": m["obj"] or m["obj2"], "n": m["n"] or m["n2"],
                                         "kind": m["kind"] or m["kind2"], "remove": m["remove"], "what": m["what"]})),
    # only a transform body: other "Then if ..." sentences have their own templates (Golbez, Iymrith)
    (re.compile(r"(?:^|(?<=\. ))Then if ([^.]+?), (" + _TRANSFORM_BODY + r")(?=\.|$)", re.I), r"If \1, \2"),
]


def _target_transform(m):
    """"Transform [up to one] target <Subtype> [token] you control" (Waxing Moon, Seedpod Caretaker)."""
    from .cards import Effect
    sel = {"controller": "mine", "subtypes": [m["sub"].lower()], "types_any": ["permanent"]}
    if m["token"]:
        sel["token"] = True
    data = {"selector": sel}
    if m["upto"]:
        data["optional_target"] = True
    return Effect("transform", target="permanent", data=data)


EFFECT_PATTERNS = [
    (r"transform (?P<upto>up to one )?target (?P<sub>[A-Z][a-z]+)(?P<token> token)? you control", _target_transform),
]


def transform_incubator(game, perm) -> None:
    """An Incubator token's back face: a 0/0 Phyrexian artifact creature (as its own ability does, kinds/batch1.py)."""
    import dataclasses
    perm.card = dataclasses.replace(perm.card, name="Phyrexian token", types=frozenset({"Artifact", "Creature"}),
                                    subtypes=frozenset({"Phyrexian"}), power=0, toughness=0, activated=[])
    game.log("incubator transforms into a Phyrexian", perm.controller)


# ------------------------------------------------------------------ turning face up and face down

def _face_up(m):
    """"Turn target face-down creature [an opponent controls / you control] face up" (Break Open, Ixidor)."""
    from .cards import Effect
    sel = {"types_all": ["creature"], "traits": ["face-down"]}
    if m["who"]:
        sel["controller"] = "opp" if "opponent" in m["who"] else "mine"
    return Effect("turn_face_up", target="permanent", data={"selector": sel})


def _face_down_self(m):
    from .cards import Effect
    return Effect("turn_face_down", target="self")


def _face_down_target(m):
    """"[You may] turn target creature with a morph ability face down" (Backslide, Master of the Veil)."""
    from .cards import Effect
    eff = Effect("turn_face_down", target="permanent",
                 data={"selector": {"types_all": ["creature"], "traits": ["morph", "face-up"]}})
    return [Effect("pay_gate", data={"gate": ("may", "")}), eff] if m["may"] else eff


EFFECT_PATTERNS += [
    (r"turn target face-down creature(?: (?P<who>an opponent controls|you control))? face up", _face_up),
    (r"turn (?:~|it) face down", _face_down_self),
    (r"(?P<may>you may )?turn target creature with a morph ability face down", _face_down_target),
]


def turn_up(game, perm) -> bool:
    """Turn a face-down permanent face up for free (an effect, not its morph cost). A manifested instant or sorcery
    stays face down (CR 701.40g)."""
    real = getattr(perm, "hidden", None)
    if real is None or perm not in perm.controller.battlefield or real.is_instant or real.is_sorcery:
        return False
    perm.card, perm.hidden = real, None
    game.log(f"turns {real.name} face up", perm.controller)
    game.fire(perm.controller, "turned_face_up", perm)
    return True


def turn_down(game, perm) -> bool:
    """Turn a face-up permanent face down: a 2/2 nameless creature with no text, the card kept hidden (CR 708.2).
    A token or a double-faced permanent can't be turned face down."""
    from .manifest import _face_down_def
    if getattr(perm, "hidden", None) is not None or perm not in perm.controller.battlefield or perm.card.is_token \
            or getattr(perm, "front_face", None) is not None or perm.card.back is not None:
        return False
    game.log(f"turns {perm.card.name} face down", perm.controller)
    perm.hidden, perm.card = perm.card, _face_down_def()
    return True
