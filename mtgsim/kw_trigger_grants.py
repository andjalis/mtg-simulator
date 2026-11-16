"""#633: triggered keywords granted to groups and hosts.

    Other creatures you control have melee.                  (Adriana, Captain of the Guard)
    Artifact creatures you control have afflict 3.           (Cyberman Patrol)
    Equipped creature gets +2/+0 and has afflict 1.          (Dagger of the Worthy)
    Other creatures you control have evolve.                 (Tyranid Prime)

A keyword is granted this way only when it is a purely triggered keyword in this engine: a blank creature whose only
text is the keyword parses with nothing but triggers added (``_keyword_triggers`` checks it once per keyword). Those
triggers are recorded as ``trigger_grants`` (cx_trigger_grants), so the recipient really has them: "~" in them is
the recipient, a permanent joining the group gains them and one leaving loses them. Exalted, training, dethrone
and riot, which the engine reads from the permanent itself, become ordinary static keyword grants instead (counted
by ``Permanent.keyword_instances``, and riot checked as a creature enters). Other keywords that set fields
(outlast, myriad), aren't implemented, or parse to nothing keep the line unmatched.
"""
from __future__ import annotations

import dataclasses
import re

_HOST = re.compile(r"(Enchanted|Equipped) creature (?:gets (?P<p>[+-]\d+)/(?P<t>[+-]\d+) and )?has (?P<k>.+)\.")
_GROUP = re.compile(r"(?:All )?(?P<s>.+?) (?:have|has) (?P<k>.+)\.")
_CACHE: dict = {}
_KW = re.compile(r"[a-z]+(?: [a-z]+)?(?: \d+)?")


def _probe(text):
    from .cards import card_from_scryfall
    return card_from_scryfall({"name": "Keyword Probe", "type_line": "Creature — Probe", "oracle_text": text,
                               "power": "1", "toughness": "1", "mana_cost": "{1}", "cmc": 1})


def _keyword_triggers(kw: str):
    """The triggers a printed keyword gives in this engine, or None when it isn't purely triggered."""
    if kw in _CACHE:
        return _CACHE[kw]
    out = None
    if _KW.fullmatch(kw):
        base, card = _probe(""), _probe(kw[0].upper() + kw[1:])
        changed = {f.name for f in dataclasses.fields(card) if getattr(card, f.name) != getattr(base, f.name)}
        if not card.unsupported and changed == {"oracle", "triggers"} and card.triggers:
            out = tuple(card.triggers)
    _CACHE[kw] = out
    return out


def _all_triggers(text: str):
    out = []
    for piece in re.split(r",? and |, ", text):
        got = _keyword_triggers(piece.strip())
        if got is None:
            return None
        out += got
    return out


def parse_line(line: str, st) -> bool:
    from .cx_trigger_grants import _record
    m = _HOST.fullmatch(line)
    if m:
        if m[1] == "Enchanted" and not st.extra.get("aura") or m[1] == "Equipped" and "Equipment" not in st.type_line:
            return False
        triggers = _all_triggers(m["k"])
        if not triggers or m["p"] and st.extra.get("equip_bonus"):
            return False
        if m["p"]:
            st.extra["equip_bonus"] = (int(m["p"]), int(m["t"]))
        _record(st, {"host": True}, list(triggers))
        return True
    m = _GROUP.fullmatch(line)
    if not m or re.match(r"(?:enchanted|equipped)\b", m["s"], re.I):
        return False
    triggers = _all_triggers(m["k"])
    counted = None if triggers else _counted(m["k"])
    if not triggers and not counted:
        return False
    from .permanent_templates import selector
    spec = selector(m["s"], plural=True)
    if spec is None or "keyword" in spec:
        return False
    if counted:          # read where the engine reads the keyword (Permanent.has / keyword_instances)
        st.extra["static_keyword_grants"] = st.extra.get("static_keyword_grants", ()) + ((spec, tuple(counted)),)
        return True
    _record(st, spec, list(triggers))
    return True


# Keywords the engine reads from the permanent itself rather than as triggers: exalted (keyword_instances builds its
# attacks-alone triggers), training and dethrone (has + keyword_instances), riot (checked as the creature enters).
_COUNTED = ("exalted", "training", "dethrone", "riot")


def _counted(text: str):
    kws = [k.strip() for k in re.split(r",? and |, ", text)]
    return kws if kws and all(k in _COUNTED for k in kws) else None
