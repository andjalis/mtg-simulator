"""Back-references to a group (#628): the next sentence acts on the permanents a group effect just acted on.

    Put a +1/+1 counter on each creature you control. Those creatures gain vigilance until end of turn.
    Untap all creatures you control. They gain flying and double strike until end of turn.
    Creatures target player controls get +3/+3 until end of turn. Untap them.
    It deals 1 damage to each creature with flying your opponents control. Tap those creatures.
    Tap all creatures your opponents control, then put a stun counter on each of those creatures.

"They" / "those creatures" / "them" / "each of them" / "each of those creatures" is read in the singular ("It gains
vigilance until end of turn", "Untap it", "Put a stun counter on it") and every resulting effect must act on "it".

- After a ``cx_group`` / ``permanent_group`` the new effects join the group's inner effects: the same members,
  fixed when the group resolves (CR 611.2c).
- After a fixed group kind (``p1_counters`` on your creatures, ``untap_all``, ``pump_all``, ``debuff``, damage to
  each member of a ``group_remove``) the sentence becomes a ``permanent_group`` over the same selector, resolved
  right after it. Nothing between the two effects can change who matches (state-based actions wait until the
  whole spell or ability has resolved), except a first effect that taps or untaps when the selector reads tapped
  state: that is refused. The group's members are fixed before its own inner effects run, so "put a counter on
  each tapped creature you control, then untap them" keeps the tapped ones.

Anything that moves the group to another zone (destroy, exile, return) is refused: "they" would then be cards in
another zone, which this module does not follow.
"""
from __future__ import annotations

import dataclasses
import re

_REF = r"(?:those creatures|those permanents|they|them|each of them|each of those creatures|each of those permanents)"
_SUBJ = re.compile(r"(?:those creatures|those permanents|they|each of those creatures) (.+)", re.I)
_PUT = re.compile(rf"(put .+?) on {_REF}", re.I)
_TAP = re.compile(rf"(untap|tap) {_REF}", re.I)
_PLURAL_WORD = re.compile(r"\b(?:they|them|their|those|each)\b", re.I)
_AGREE = {"gain": "gains", "get": "gets", "have": "has", "lose": "loses", "can't": "can't", "attack": "attacks",
          "don't": "doesn't", "block": "blocks"}
# Kinds that move the member out of play, or end the effect on it: "they" afterwards is not on the battlefield.
_MOVES = {"destroy", "exile", "bounce", "sacrifice", "tuck", "return_hand", "exile_until", "flicker"}
_TAPPING = {"tap", "untap_prev", "untap_all", "stun"}
_STATE_WORDS = ("tapped", "untapped")


def singular(s: str):
    """The sentence about "them" as one about "it", or None."""
    t = s.strip().rstrip(".")
    m = _SUBJ.fullmatch(t)
    if m:
        verb, _, rest = m[1].partition(" ")
        low = verb.lower()
        if low not in _AGREE:
            return None
        rest = re.sub(r"\btheir controllers' next untap steps\b", "its controller's next untap step", rest, flags=re.I)
        return None if _PLURAL_WORD.search(rest) else f"It {_AGREE[low]} {rest}."
    m = _PUT.fullmatch(t)
    if m and not _PLURAL_WORD.search(m[1]):
        return f"{m[1]} on it."
    m = _TAP.fullmatch(t)
    if m:
        return f"{m[1].capitalize()} it."
    return None


def _inner(text: str):
    """Inner effects of a group for the singular sentence: every effect acts on "it", unconditionally."""
    from .cards.parse import _parse_effects
    new, bad = _parse_effects(text)
    if bad or not new or any(e.target != "prev" or e.cond or e.kind in _MOVES for e in new):
        return None
    return [dataclasses.replace(e, target="self") for e in new]


def _selector(eff):
    """The battlefield selector a fixed group effect acted on, or None."""
    k, d = eff.kind, eff.data
    if k == "p1_counters" and eff.target == "my_creatures" and not d.get("x"):
        sel = {"controller": "mine", "types_all": ["creature"]}
        only = d.get("only", "")
        if only in ("tapped", "legendary"):
            sel["traits"] = [only]
        elif only:
            sel["subtypes"] = [only.lower()]
    elif k == "untap_all" and d.get("what") == "creatures":
        sel = {"controller": "mine", "types_all": ["creature"]}
    elif k == "pump_all" and not d.get("only"):
        sel = {"controller": "mine", "types_all": ["creature"]}
    elif k == "debuff" and eff.target == "opp_creatures":
        sel = {"controller": "opp", "types_all": ["creature"]}
    elif k == "group_remove" and d.get("op") == "damage" and isinstance(d.get("selector"), dict):
        return dict(d["selector"])
    else:
        return None
    if d.get("other"):
        sel["other"] = True
    return sel


def _taps(eff) -> bool:
    inner = eff.data.get("effects") or ([eff.data["effect"]] if eff.data.get("effect") else [])
    return eff.kind in _TAPPING or eff.data.get("untap") or any(e.kind in _TAPPING for e in inner)


def _reads_tapped(sel) -> bool:
    return any(t in _STATE_WORDS for t in (sel or {}).get("traits", []))


def apply(s: str, effects: list) -> bool:
    """Append "they ..." after a group effect to effects. True if the sentence was consumed."""
    if not effects:
        return False
    text = singular(s)
    if text is None:
        return False
    last = effects[-1]
    if last.cond:
        return False
    inner = _inner(text)
    if inner is None:
        return False
    if last.kind in ("cx_group", "permanent_group"):
        old = list(last.data.get("effects") or [last.data["effect"]])
        if any(e.kind in _MOVES for e in old):
            return False
        data = {k: v for k, v in last.data.items() if k != "effect"}
        effects[-1] = dataclasses.replace(last, data=dict(data, effects=old + inner))
        return True
    sel = _selector(last)
    if sel is None or _reads_tapped(sel) and _taps(last):
        return False
    from .cards.model import Effect
    effects.append(Effect("permanent_group", data={"selector": sel, "effects": inner}))
    return True


_COMPOUND = re.compile(rf"(.+?)(?:,? then|,? and) ((?:put .+? on|untap|tap) {_REF}|(?:they|those creatures) .+)", re.I)


def parse(s: str, effects: list, starts=()) -> bool:
    """The _parse_effects hook: a back-reference sentence, or "A, then <back-reference>" in one sentence. starts holds
    where each sentence's effects begin: when the sentence before this one produced nothing (it was not understood),
    "them" may name what that sentence chose ("choose up to that many creatures tapped this way. Put a stun counter
    on each of them."), so the sentence is refused."""
    if len(starts) >= 2 and starts[-2] == starts[-1]:
        return False
    if apply(s, effects):
        return True
    m = _COMPOUND.fullmatch(s.strip().rstrip("."))
    if m is None:
        return False
    from .cards.parse import _parse_effects
    new, bad = _parse_effects(m[1][0].upper() + m[1][1:] + ".")
    if bad or not new or not apply(m[2], new):
        return False
    effects += new
    return True


def cond_rider(cond: str, body: str, effects: list) -> bool:
    """"If C, those creatures [also] gain vigilance until end of turn." after a group or counted targets: the rider
    under condition C. After a group it is always a separate ``permanent_group`` (a group's inner effects are not
    checked against conditions, so the rider can't join one); after counted targets the chain_rider copies carry C."""
    if not effects or effects[-1].cond:
        return False
    body = re.sub(r"^(those creatures|they|each of them|each of those creatures) also ", r"\1 ", body.strip(), flags=re.I)
    text = singular(body)
    if text is None:
        return False
    last = effects[-1]
    if last.kind == "permanent_group" and "selector" in last.data:
        sel = dict(last.data["selector"])
        if any(e.kind in _MOVES for e in last.data.get("effects") or [last.data.get("effect")] if e is not None):
            return False
    else:
        sel = _selector(last)
    if sel is not None:
        inner = _inner(text)
        if inner is None or _reads_tapped(sel) and _taps(last):
            return False
        from .cards.model import Effect
        effects.append(Effect("permanent_group", cond=cond, data={"selector": sel, "effects": inner}))
        return True
    if last.kind == "cx_group":
        return False            # a group of a target player's permanents: a second group would need that target
    from .cx_multi_target import chain_rider
    tmp = list(effects)
    if not chain_rider(body[0].upper() + body[1:].rstrip(".") + ".", tmp):
        return False
    if last.kind == "cx_multi":         # the rider joined the list target's chain: its new links carry C
        multi, n = tmp[-1], len(last.data["chain"])
        chain = list(multi.data["chain"][:n]) + [dataclasses.replace(e, cond=cond) for e in multi.data["chain"][n:]]
        effects[-1] = dataclasses.replace(multi, data=dict(multi.data, chain=chain))
        return True
    old = {id(e) for e in effects}
    # the rider's copies (on "it"); a split "tap up to two" entry's new tap copies stay unconditional
    effects[:] = [e if id(e) in old or e.target != "prev" else dataclasses.replace(e, cond=cond) for e in tmp]
    return True


_LINE_RIDER = re.compile(r"(?:[A-Z][\w' ]+ — )?if (?P<cond>.+?), (?P<body>(?:those creatures|they|each of them|each of "
                         r"those creatures) .+)", re.I)


def spell_line_rider(line: str, spell: list) -> bool:
    """An instant's or sorcery's own line "[Ability word —] If C, those creatures ..." after the line that chose or
    named them (Kytheon's Tactics, Icy Blast): the conditional rider on the spell's effects so far."""
    m = _LINE_RIDER.fullmatch(line.strip())
    if m is None or not spell or "." in m["body"].rstrip("."):
        return False
    from .cards.clauses import _if_cond
    cond = _if_cond(m["cond"])
    return bool(cond) and cond_rider(cond, m["body"], spell)
