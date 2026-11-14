"""Exchange of control between two permanents (#334): "Exchange control of ~ and target nonland permanent.",
"Exchange control of target creature you control and target creature an opponent controls.", "Exchange control
of two target permanents that share a card type.", "... two other target creatures controlled by different
players.", "... target permanent an opponent controls that shares a card type with it."

An exchange is one operation on two objects (rule 701.12), laid out on the stack like a fight:

- ``cx_exchange_mark`` targets the first object and does nothing itself;
- ``cx_exchange`` targets the second object and swaps both controllers at once, reading the first object from
  the stack item (the mark's target, while it is still legal) or, with ``data["first"] == "self"``, the source.

It is never two gain-control effects: the handler (engine/kinds/cx_exchange.py) changes both controllers or
neither. Nothing happens if either object is gone or an illegal target, if one player controls both, or if the
pair no longer satisfies its relation.

Pair relations (``data["cx_pair"]`` on the second effect, checked while targets are chosen through
Game.passes_filter and again on resolution): ``share_card`` ("that share a card type", "that shares a card type
with it"), ``share_perm`` ("that share a permanent type"), ``share:<types>`` ("that shares one of those types
with it"), ``diff_ctrl`` ("controlled by different players"), ``power_le`` ("with power less than or equal to
that creature's power") and ``mv_le`` ("with equal or lesser mana value").

"You may exchange ..." goes through cards/parse.py's optional route (``data["optional"]``): the AI chooses no
targets unless the trade is favourable and declines on resolution if it no longer is.
"""
from __future__ import annotations

import contextlib
import re

KINDS = ("cx_exchange_mark", "cx_exchange")
CARD_TYPES = frozenset({"Artifact", "Battle", "Creature", "Enchantment", "Kindred", "Land", "Planeswalker"})
PERMANENT_TYPES = CARD_TYPES - {"Kindred"}

_SELF = r"~|this (?:creature|artifact|enchantment|permanent)"
_THEIRS = r"an opponent controls|you don't control"


def card_types(perm, only=CARD_TYPES) -> set:
    """perm's current card types (an animated land is also a creature)."""
    types = {t for t in perm.card.types if t in only}
    if perm.is_creature:
        types.add("Creature")
    return types


def pair_ok(first, second, rels) -> bool:
    """Whether first and second satisfy every relation in rels."""
    for rel in rels:
        if rel == "share_card" and not card_types(first) & card_types(second):
            return False
        if rel == "share_perm" and not card_types(first, PERMANENT_TYPES) & card_types(second, PERMANENT_TYPES):
            return False
        if rel.startswith("share:") and not card_types(first) & card_types(second) & {
                t.title() for t in rel[6:].split(",")}:
            return False
        if rel == "diff_ctrl" and first.controller is second.controller:
            return False
        if rel == "power_le" and not (first.is_creature and second.power <= first.power):
            return False
        if rel == "mv_le" and second.card.cmc > first.card.cmc:
            return False
    return True


# ---- parsing ----------------------------------------------------------------------------------------------

def _object(text: str):
    """(Subject, relations) for one "target ..." object phrase, or None."""
    from .cx_grammar import object_phrase
    rels = []
    t = text.strip()
    m = re.fullmatch(r"(.+?) that shares a card type with it", t, re.I)
    if m:
        t, rels = m[1], rels + ["share_card"]
    m = re.fullmatch(r"(.+?) that shares one of those types with it", t, re.I)
    if m:
        t, rels = m[1], rels + ["share:listed"]
    m = re.fullmatch(r"(target creature) with power less than or equal to that creature's power (" + _THEIRS + ")",
                     t, re.I)
    if m:
        t, rels = f"{m[1]} {m[2]}", rels + ["power_le"]
    m = re.fullmatch(r"(.+?) with equal or lesser mana value", t, re.I)
    if m:
        t, rels = m[1], rels + ["mv_le"]
    owner = None
    m = re.fullmatch(r"(target .+?) you neither own nor control", t, re.I)
    if m:
        t, owner = m[1], "opp"
    obj = object_phrase(t)
    if obj is None or obj.kind != "permanent" or obj.target in ("self", "prev", "host") or obj.copies != 1 \
            or obj.data.get("optional_target") or obj.data.get("distinct") or not t.lower().startswith("target "):
        return None
    if owner:
        sel = obj.data.get("selector")
        if sel is None or sel.get("controller") or sel.get("owner"):
            return None
        obj.data["selector"] = dict(sel, controller="opp", owner="opp")
    return obj, rels


def _listed_types(obj) -> list | None:
    """"one of those types": the types the first object's phrase lists ("target artifact or creature")."""
    sel = obj.data.get("selector") or {}
    types = sel.get("types_any") or [t for t in sel.get("types_all", []) if t != "permanent"]
    return list(types) or None


def _pair(first, second, rels, *, self_first=False):
    from .cards.model import Effect
    if self_first:
        return [Effect("cx_exchange", target=second.target, data=dict(second.data, first="self", cx_pair=rels))]
    common = {"group": "cx_exchange", "distinct": True}
    a = {k: v for k, v in first.data.items() if k not in ("distinct", "copies")}
    b = {k: v for k, v in second.data.items() if k not in ("distinct", "copies")}
    exchange = Effect("cx_exchange", target=second.target, data=dict(b, first="mark", cx_pair=rels, **common))
    mark = Effect("cx_exchange_mark", target=first.target,
                  data=dict(a, partner={"target": exchange.target, "data": dict(exchange.data)}, **common))
    return [mark, exchange]


def parse(s: str):
    """Effects for an "exchange control of ..." sentence, or None."""
    from .cx_grammar import object_phrase
    s = s.strip().rstrip(".")
    m = re.fullmatch(r"exchange control of two (other )?target (.+?)"
                     r"( that share a card type| that share a permanent type| controlled by different players)?", s, re.I)
    if m:
        obj = object_phrase(f"two {m[1] or ''}target {m[2]}")
        if obj is None or obj.kind != "permanent" or obj.copies != 2 or obj.data.get("optional_target"):
            return None
        rel = {" that share a card type": ["share_card"], " that share a permanent type": ["share_perm"],
               " controlled by different players": ["diff_ctrl"]}.get((m[3] or "").lower(), [])
        return _pair(obj, obj, rel)
    m = re.fullmatch(r"exchange control of (" + _SELF + r") and (target .+)", s, re.I)
    if m:
        got = _object(m[2])
        if got is None or any(r.startswith("share:") for r in got[1]):
            return None
        return _pair(None, got[0], got[1], self_first=True)
    m = re.fullmatch(r"exchange control of (target .+?) and (another )?(target .+)", s, re.I)
    if m:
        first, second = _object(m[1]), _object(m[3])
        if first is None or second is None or first[1]:
            return None
        rels = list(second[1])
        if "share:listed" in rels:
            listed = _listed_types(first[0])
            if not m[2] or listed is None:
                return None
            rels[rels.index("share:listed")] = "share:" + ",".join(listed)
        elif m[2]:
            return None
        return _pair(first[0], second[0], rels)
    return None


def _build(m):
    from .cards.model import NO_MATCH
    return parse(m[0]) or NO_MATCH


EFFECT_PATTERNS = [(r"exchange control of (?!.*\bspell\b).+", _build)]


# ---- targets and the first object ---------------------------------------------------------------------------

@contextlib.contextmanager
def _anchored(game, first):
    outer = getattr(game, "_exchange_anchor", None)
    game._exchange_anchor = first
    try:
        yield
    finally:
        game._exchange_anchor = outer


def _source(game):
    src = game.target_source
    return getattr(src, "source", src)


def anchor(game, eff):
    """The first object of the exchange whose second effect is eff, while its targets are chosen or checked."""
    from .engine.state import Permanent, StackItem
    over = getattr(game, "_exchange_anchor", None)
    if over is not None:
        return over
    if eff.data.get("first") == "self":
        src = _source(game)
        return src if isinstance(src, Permanent) else None
    item = game.target_source
    if isinstance(item, StackItem):
        idx = next((i for i, e in enumerate(item.effects) if e is eff), None)
        if idx and idx <= len(item.targets):
            return item.targets[idx - 1]
        return None
    chosen = getattr(game, "_choosing_targets", None)
    effects = getattr(game, "_choosing_effects", None) or ()
    idx = next((i for i, e in enumerate(effects) if e is eff), None)
    if chosen and idx:          # a whole target list being checked: the target of the effect before this one
        return chosen[idx - 1] if idx - 1 < len(chosen) else None
    return chosen[-1] if chosen else None


def pair_target_ok(game, eff, perm) -> bool:
    """Game.passes_filter: a second object must keep its relation to the first (unknown first: allowed here,
    the handler checks the pair again)."""
    first = anchor(game, eff)
    if first is None or not hasattr(first, "controller"):
        return True
    return pair_ok(first, perm, eff.data["cx_pair"])


# ---- AI -----------------------------------------------------------------------------------------------------

def worth(perm) -> float:
    from .engine.policy import perm_value
    from .engine.state import is_basic_land
    extra = (0.5 if is_basic_land(perm.card) else 1.5) if perm.card.is_land else 0.0
    return perm_value(perm) + extra


def swing(me, first, second) -> float:
    """What me gains (positive) or gives away when first and second change controllers."""
    if first is None or second is None or first is second or first.controller is second.controller:
        return 0.0
    total = 0.0
    for obj, new in ((first, second.controller), (second, first.controller)):
        if new is me:
            total += worth(obj)
        elif obj.controller is me:
            total -= worth(obj)
    return total


def _partner(eff):
    from .cards.model import Effect
    spec = eff.data["partner"]
    return Effect("cx_exchange", target=spec["target"], data=spec["data"])


def best_pair(game, me, eff):
    """(swing, first, second) of the best pair for a mark effect, or None when no pair is legal."""
    partner = _partner(eff)
    best = None
    for first in game.legal_targets(me, eff):
        with _anchored(game, first):
            seconds = [x for x in game.legal_targets(me, partner) if x is not first]
        for second in seconds:
            v = swing(me, first, second)
            if best is None or v > best[0]:
                best = (v, first, second)
    return best


def choose(game, me, eff):
    """policy.default_choose_target for the exchange kinds."""
    optional = eff.data.get("optional")
    if eff.kind == "cx_exchange_mark":
        best = best_pair(game, me, eff)
        if best is None or optional and best[0] <= 0:
            return None
        return best[1]
    first = anchor(game, eff)
    if first is None:
        return None
    pool = [x for x in game.legal_targets(me, eff) if x is not first]
    second = max(pool, key=lambda x: swing(me, first, x), default=None)
    if second is None or optional and swing(me, first, second) <= 0:
        return None
    return second


def mode_value(game, me, eff, tgt, chosen) -> float:
    """policy._mode_value for one exchange effect (chosen: the targets so far, tgt last)."""
    if eff.kind == "cx_exchange_mark":
        return 0.0
    first = (_source(game) if eff.data.get("first") == "self"
             else chosen[-2] if len(chosen) >= 2 else None)
    if not hasattr(first, "controller") or tgt is None:
        return -1.0
    return swing(me, first, tgt)
