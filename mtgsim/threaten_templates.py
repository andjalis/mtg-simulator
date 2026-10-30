"""Mass threaten: "Gain control of all creatures [an opponent / target opponent controls] until
end of turn. Untap them. They gain haste until end of turn." (Mob Rule, Broadcast Takeover,
Call for Aid, Dihada, Mutinous Massacre, Rowan), the Reins of Power / Twist Allegiance swaps,
and the "for each opponent, gain control of up to one target creature that player controls"
threatens, which in the two-player engine are the plain single-target threaten.

The multi-sentence wordings are rewritten by SUBS to a MASSGAIN sentinel sentence; the
``mass_threaten`` kind lives in engine/kinds/permanents.py.
"""
from __future__ import annotations

import re


def _e(kind, **kw):
    from .cards import Effect
    return Effect(kind, 1, **kw)


# <what> <scope> <power_min> <power_max>; "0" means no bound.
_SENTINEL = r"MASSGAIN {0} {1} {2} {3}."

SUBS = [
    # "Gain control of all creatures / artifacts your opponents control / nonland permanents
    # until end of turn. Untap them. They gain haste until end of turn."
    (re.compile(r"(?:then )?gain control of all (?P<what>creatures|artifacts(?: your opponents control)?|"
                r"nonland permanents) until end of turn\.[.\s]*untap (?:them|those creatures)\.[.\s]*"
                r"(?:they|those creatures) gain haste until end of turn", re.I),
     lambda m: _SENTINEL.format(m["what"].split(" your ")[0], "all", 0, 0)),
    # Mob Rule: "… all creatures with power N or greater / less …"
    (re.compile(r"gain control of all creatures with power (?P<n>\d+) or (?P<dir>greater|less) until end of "
                r"turn\.[.\s]*untap those creatures\.[.\s]*(?:they|those creatures) gain haste until end of "
                r"turn", re.I),
     lambda m: _SENTINEL.format("creatures", "all", m["n"] if m["dir"] == "greater" else 0,
                                m["n"] if m["dir"] == "less" else 0)),
    # Call for Aid: "… all creatures target opponent controls until end of turn. Untap those
    # creatures. Those creatures gain haste until end of turn."
    (re.compile(r"gain control of all creatures (?P<who>target opponent|target player) controls until end "
                r"of turn\.[.\s]*untap those creatures\.[.\s]*(?:they|those creatures) gain haste until end "
                r"of turn", re.I),
     lambda m: _SENTINEL.format("creatures", "target", 0, 0)),
    # Twist Allegiance / Reins of Power: each side gains control of the other's creatures.
    (re.compile(r"(?:untap all creatures you control and all creatures target opponent controls\.[.\s]*)?"
                r"you and (?P<who>target|that) opponent each gain control of all creatures the other "
                r"controls until end of turn\.(?:[.\s]*untap those creatures\.)?[.\s]*those creatures gain "
                r"haste until end of turn", re.I),
     lambda m: _SENTINEL.format("creatures", "swap", 0, 0)),
    # Molten Primordial and friends: one creature per opponent, which the two-player engine
    # plays as the single-target threaten (with its untap and haste riders).
    (re.compile(r"for each opponent, gain control of up to one target creature that player controls "
                r"until end of turn\.[.\s]*untap those creatures\.[.\s]*they gain haste until end of turn",
                re.I),
     lambda m: "gain control of target creature an opponent controls until end of turn. "
               "Untap it. It gains haste until end of turn."),
]

EFFECT_PATTERNS = [
    (r"(?:then )?MASSGAIN (?P<what>creatures|artifacts|nonland permanents) (?P<scope>all|target|swap) "
     r"(?P<pmin>\d+) (?P<pmax>\d+)", lambda m: _massgain(m)),
    # Emrakul, the World Anew: control stays past the turn, without untap or haste.
    (r"gain control of all creatures (?P<who>target player|target opponent) controls",
     lambda m: _e("mass_threaten", target="player", data={"until_eot": False, "untap": False,
                                                          "haste": False})),
]

_TYPES = {"creatures": "creature", "artifacts": "artifact", "nonland permanents": "nonland"}


def _massgain(m):
    data = {"type": _TYPES[m["what"]]}
    if int(m["pmin"]):
        data["power_min"] = int(m["pmin"])
    if int(m["pmax"]):
        data["power_max"] = int(m["pmax"])
    if m["scope"] == "target":
        return _e("mass_threaten", target="player", data=data)
    if m["scope"] == "swap":
        return _e("mass_threaten", target="player", data=dict(data, swap=True))
    return _e("mass_threaten", data=data)
