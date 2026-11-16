"""Attack, damage, targeting and counter heads for the cx_events trigger grammar (#404 slice 3):

    Whenever equipped creature attacks alone | a Rogue you control attacks and isn't blocked
    Whenever a creature attacks enchanted player | deals combat damage to enchanted player     (Curses)
    Whenever ~ becomes the target of a spell [you control]
    Whenever ~ deals damage to a Dinosaur | to one or more creatures | deals 6 or more damage to an opponent
    Whenever a source an opponent controls deals damage to you
    Whenever one or more +1/+1 counters are put on another creature you control
    Whenever you put one or more +1/+1 counters on a creature you control

cx_events keeps the verb table; this module reads the verbs' own arguments (``verb_arg``), checks their flags
(``flag_ok``) and parses the counter heads (``counter_head``), whose subject is the permanent the counters go on.
"""
from __future__ import annotations

import re

from . import cx_events

FLAGS = {"att", "alone", "atk_cursed", "dmg_cursed", "tg_spell", "tg_spell_mine", "dmg_n", "dmgd", "you_put"}


def verb_arg(flag: str, text: str, subject: dict):
    """Read the argument of a verb into the subject spec; None refuses the head."""
    if flag == "att":
        m = re.search(r"attached to (.+)$", text)
        host = cx_events._object_subject(m[1], head=True)
        if host is None or host["host"] or host["batch"] or host["other"] or host["self"] and m[1] != "~":
            return None
        if subject["self"] or subject["host"] or not subject["alts"] or \
                not all(any(w == "Aura" for w in ws) for ws in subject["alts"]):
            return None         # only Auras fire the event (auras.attach); Equipment attach elsewhere
        subject["att"] = host
        return True
    if flag == "dmg_n":
        m = re.search(r"(\d+) or more damage", text)
        subject["dmg_n"] = int(m[1])
        return True
    m = re.search(r"damage to (an?|one or more) (.+)$", text)
    if not m or m[2] in ("player", "opponent", "creature", "player or planeswalker"):
        return None             # the fixed verbs read those
    alts = cx_events._desc_alts(m[2], plural=m[1] == "one or more")
    if alts is None:
        return None
    subject["dmgd"] = alts
    if m[1] == "one or more":
        subject["batch"] = True     # once per damage step / resolution, however many it hit
    return True


def flag_ok(game, flag, spec, perm, obj, context) -> bool:
    from .engine.state import Permanent
    if flag == "att":         # obj: the Aura; context: what it became attached to
        return isinstance(context, Permanent) and cx_events._subject_ok(game, spec["att"], perm, context)
    if flag == "alone":
        return len(game.attackers) == 1
    if flag == "atk_cursed":
        cursed = getattr(perm, "curse_target", None)
        return cursed is not None and game.attack_targets.get(obj) is cursed
    if flag == "dmg_cursed":
        cursed = getattr(perm, "curse_target", None)
        return cursed is not None and context is cursed
    if flag in ("tg_spell", "tg_spell_mine"):
        item = getattr(game, "event_targeter", None)
        if item is None or not item.is_spell:
            return False
        return flag == "tg_spell" or item.controller is perm.controller
    if flag == "dmg_n":
        return context is not perm.controller and (getattr(game, "event_amount", None) or 0) >= spec["dmg_n"]
    if flag == "dmgd":
        return isinstance(context, Permanent) and cx_events._perm_fits(game, context, spec["dmgd"])
    if flag == "you_put":
        item = getattr(game, "resolving_item", None)
        return (item.controller if item is not None else obj.controller) is perm.controller
    return True


_COUNTER = re.compile(r"(?:one or more (?P<k1>[+-]1/[+-]1) counters are put on|"
                      r"(?P<you>you put one or more (?P<k2>[+-]1/[+-]1) counters on)) (?P<s>.+)")


def counter_head(body: str):
    """"one or more +1/+1 counters are put on <subject>" -> (raws, spec), or None."""
    m = _COUNTER.fullmatch(body)
    if not m:
        return None
    kind = m["k1"] or m["k2"]
    if kind not in ("+1/+1", "-1/-1"):
        return None
    raw = "p1_added" if kind == "+1/+1" else "m1_added"
    if m["s"] in ("it", "this creature") or m["s"] == "~" and raw == "p1_added":
        return None             # the base table's "p1_added" self head
    subject = cx_events._object_subject(m["s"], head=True)
    if subject is None or subject["batch"] or subject["host"]:
        return None
    subject["flags"] = {raw: "you_put" if m["you"] else ""}
    subject["by"] = None
    return (raw,), subject


# "a source an opponent controls deals damage to you": the damaged player is you, the damage came from them
cx_events._PLAYER_SUBJ["a source an opponent controls"] = "src_opp"
cx_events._PLAYER_VERBS[0:0] = [
    (r"deals? damage to you", "src_dmg_me"),
    # "Whenever you become the target of a spell [or ability] [an opponent controls]": engine/stack.check_ward fires
    # player_targeted for each targeted player, with the targeting item as context
    (r"becomes? the target of a spell or ability an opponent controls", "ptg_opp"),
    (r"becomes? the target of a spell an opponent controls", "ptg_spell_opp"),
    (r"becomes? the target of a spell or ability", "ptg_any"),
    (r"becomes? the target of a spell", "ptg_spell"),
    (r"taps? ~ for mana", "tap_self"),
    (r"taps? (an?) ([\w ]+?) for mana", "tap_mana"),
]
cx_events._PLAYER_RAW.update({"src_dmg_me": ("player_damaged",), "ptg_opp": ("player_targeted",),
                              "ptg_spell_opp": ("player_targeted",), "ptg_any": ("player_targeted",),
                              "ptg_spell": ("player_targeted",), "tap_self": ("tapped_for_mana",),
                              "tap_mana": ("tapped_for_mana",)})
cx_events._OBSERVED.update({"p1_added", "m1_added", "unblocked", "player_targeted", "tapped_for_mana",
                            "aura_attached"})


def player_arg(kind, vm, spec) -> bool:
    """Read a player verb's own argument into the spec; False refuses the head."""
    if kind == "activate":
        from .cx_trig_activate import parse
        return parse(vm, spec)
    if kind == "tap_mana":
        alts = cx_events._desc_alts(vm[2])
        if alts is None or not all(any(_is_land_word(w) for w in ws) for ws in alts):
            return False
        spec["alts"] = alts
    return True


def _is_land_word(w: str) -> bool:
    from .permanent_templates import _SUBTYPE_TYPES
    return w.lower() == "land" or "land" in _SUBTYPE_TYPES.get(w.lower(), ())


def tapped_ok(game, spec, source, perm) -> bool:
    """The tapped permanent fits "~" / "a <land desc>"."""
    if spec["kind"] == "tap_self":
        return source is perm
    return source is not None and cx_events._perm_fits(game, source, spec["alts"])


def subject_takes(who: str, kind: str) -> bool:
    """The source subjects take only their damage verbs ("a source you control draws a card" is no head)."""
    if who == "src_opp":
        return kind == "src_dmg_me"
    if who == "src_you":
        return kind == "src_noncombat"
    return True


def player_ok(game, spec, actor, me) -> bool:
    if spec["kind"].startswith("ptg_"):
        item = getattr(game, "event_targeter", None)
        if item is None or spec["kind"] in ("ptg_spell", "ptg_spell_opp") and not item.is_spell:
            return False
        return not spec["kind"].endswith("opp") or item.controller is not me
    if spec["kind"] == "src_dmg_me":
        by = getattr(game, "event_dmg_by", None)
        return spec["player"] == "src_opp" and actor is me and by is not None and by is not me
    if spec["player"] == "src_opp":
        return False            # no other verb takes this subject
    return True
