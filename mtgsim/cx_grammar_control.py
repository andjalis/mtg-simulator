"""Grammar verbs: control changes ("Gain control of target artifact or creature until end of turn.", "Gain control
of target legendary permanent.", "Untap target creature and gain control of it until end of turn.", "Target
opponent gains control of ~.", "That player gains control of it."). See mtgsim/GRAMMAR.md.

cx_control (engine/kinds/cx_grammar_control.py) gives the controller control of the object until end of turn or
for good (counter_mechanics.add_control); with untap it also untaps it. cx_give_control gives ~ (or the previous
object) to the player a player subject names. Durations other than end of turn ("for as long as ...") are left
for other templates."""
from __future__ import annotations

from .cx_grammar import Part, Subject, assemble, object_phrase, rider, verb


@verb(r"gain control of (.+)", heads=("gain",), subjects=("imperative",))
def gain_control(m, clause):
    obj = object_phrase(m[1])
    if obj is None or obj.kind != "permanent" or obj.target in ("self", "prev") or clause.duration not in ("eot", ""):
        return None     # "... and gain control of it": the untap-and-steal rider reads the whole sentence
    return [Part("cx_control", data={"eot": clause.duration == "eot", "side": "theirs"}, obj=obj)]


@rider(r"untap (.+) and gain control of (?:it|that creature|that permanent)( until end of turn)?")
def untap_and_steal(m, inner):
    obj = object_phrase(m[1])
    if obj is None or obj.kind != "permanent" or obj.target in ("self", "prev"):
        return None
    return assemble(Subject("imperative", who="you"),
                    [Part("cx_control", data={"eot": bool(m[2]), "untap": True, "side": "theirs"}, obj=obj)])


@verb(r"gains? control of (~|it|this creature|this permanent|that creature|that permanent)", heads=("gain", "gains"),
      subjects=("player",))
def give_control(m, clause):
    if clause.duration:
        return None
    return [Part("cx_give_control", data={"what": "self" if m[1] in ("~", "this creature", "this permanent")
                                          else "prev"})]
