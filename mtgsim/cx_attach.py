"""Attach an Aura or Equipment that is already on the battlefield to another object (#343, rule 701.3).

    Attach target Aura you control to target creature.                       (Aura Finesse)
    {T}: Attach target Equipment you control to target creature you control.  (Brass Squire)
    Attach up to one target Equipment you control to that creature.           (Sokka and Suki)
    Attach target Equipment you control to ~.                                (Kazuul's Toll Collector)

The sentence names two roles, kept apart: the **object** that moves (an Aura or Equipment) and the **host** that
receives it. Each role is either a target or a fixed reference (the source "~", or "it" / "that creature": the
object the previous effect or the trigger acted on).

- Both targeted: ``cx_attach_mark`` targets the object and does nothing itself; ``cx_attach`` targets the host
  and reads the object from the stack item (the mark's target, while it is still a legal target). The two-target
  layout is the same as an exchange of control (cx_exchange).
- Object targeted, host fixed: one ``cx_attach`` whose target is the object, ``data["host"]`` "self" or "prev".

Resolution (``attach``) moves the object or does nothing: the object must still be on the battlefield and an Aura
or Equipment, and the host must be something it can legally be attached to: an Aura by its enchant restriction and
protection (not hexproof or shroud: attaching doesn't target), Equipment only to a creature without protection
from it, never to itself, and an Equipment that is a creature can't be attached. An illegal destination leaves the
object where it was (701.3b), and attaching to its current host does nothing (701.3c). A move gets a new
attachment timestamp; ownership and control don't change. It is not an equip activation: no equip cost, no equip
restriction ("Equip Knight") applies.

The AI moves an attachment where it helps most: a friendly Aura or Equipment onto its best creature, a hostile
Aura onto the opponent's best creature. "You may" and "up to one" moves are skipped unless they gain something.
"""
from __future__ import annotations

import re

KINDS = ("cx_attach_mark", "cx_attach")

_FIXED = {"~": "self", "this creature": "self", "this permanent": "self", "it": "prev", "that creature": "prev",
          "him": "self", "her": "self"}
_OBJ_TYPES = {"aura", "equipment"}


# ---- the rules side ---------------------------------------------------------------------------------------

def is_attachment(perm) -> bool:
    return bool(perm.card.aura) or "Equipment" in perm.card.subtypes


def current_host(perm):
    return perm.aura_host if perm.card.aura else perm.attached_to


def can_host(game, obj, host) -> bool:
    """Whether obj (an Aura or Equipment on the battlefield) can legally be attached to host."""
    from .engine.state import Permanent, protected_from
    from . import auras
    if not isinstance(host, Permanent) or host is obj or host not in host.controller.battlefield:
        return False
    if obj.card.aura:
        if obj.card.aura == "player":
            return False
        return auras.can_attach(game, obj.controller, obj.card, host, source=obj, targeting=False)
    if "Equipment" not in obj.card.subtypes or (obj.is_creature and not obj.card.reconfigure):
        return False
    return host.is_creature and not protected_from(host, obj)


def attach(game, p, obj, host) -> bool:
    """Attach obj to host (rule 701.3), or do nothing. True if it moved."""
    from .engine.state import Permanent
    from . import auras
    if not isinstance(obj, Permanent) or obj not in obj.controller.battlefield or not is_attachment(obj):
        return False
    if current_host(obj) is host or not can_host(game, obj, host):
        game.log(f"{obj.card.name} stays where it is", p)
        return False
    if obj.card.aura:
        auras.detach(obj)
        auras.attach(game, obj, host)
    else:
        obj.attached_to = host
        obj.attachment_timestamp = game.next_effect_timestamp()
        game.log(f"attaches {obj.card.name} to {host.card.name}", p)
    return True


# ---- parsing ----------------------------------------------------------------------------------------------

def _object(text: str):
    """The Subject for a targeted object phrase that can only be an Aura or Equipment, or None."""
    from .cx_grammar import object_phrase
    obj = object_phrase(text)
    if obj is None or obj.kind != "permanent" or obj.target != "permanent" or obj.copies != 1:
        return None
    sel = obj.data.get("selector") or {}
    subs = {s.lower() for s in sel.get("subtypes", ())}
    if not subs or not subs <= _OBJ_TYPES or sel.get("types_any", ["permanent"]) != ["permanent"] or sel.get("types_all"):
        return None
    return obj


def _host(text: str):
    """("fixed", "self"/"prev") or ("target", Subject) for the host phrase, or None."""
    from .cx_grammar import object_phrase
    low = text.lower().strip()
    if low in _FIXED:
        return "fixed", _FIXED[low]
    if not re.match(r"(?:up to one )?target ", low):
        return None
    obj = object_phrase(text)
    if obj is None or obj.kind != "permanent" or obj.target != "permanent" or obj.copies != 1:
        return None
    sel = obj.data.get("selector") or {}
    if sel.get("types_all") != ["creature"] and not (sel.get("subtypes") and sel.get("types_any") == ["permanent"]):
        return None              # Equipment and most Auras go on creatures: a creature host only, for now
    return "target", obj


_SELF_OBJ = {"~": "self", "this equipment": "self", "this aura": "self", "this enchantment": "self", "it": "it"}
_PICK = re.compile(r"(an?|any number of|all) (aura|equipment)s?(?: and (?:aura|equipment)s?)?"
                   r"(?: (you control|on the battlefield))?", re.I)


def _pick(text: str):
    """An untargeted object chosen on resolution: {"pick": "one"/"any"/"all", "subs": [...], "ctl": "mine"/""}."""
    m = _PICK.fullmatch(text.strip())
    if not m or (m[1].lower() != "all" and not m[3]) or (m[1].lower() == "all" and not m[3]):
        return None                 # "an Equipment" alone: whose? (stays unsupported)
    subs = sorted({w.capitalize() if w.lower() == "aura" else "Equipment"
                   for w in re.findall(r"aura|equipment", text, re.I)})
    return {"pick": {"an": "one", "a": "one", "any number of": "any", "all": "all"}[m[1].lower()],
            "subs": subs, "ctl": "mine" if (m[3] or "").lower() == "you control" else ""}


def parse(s: str):
    """Effects for an "attach <object> to <host>" sentence, or None."""
    from .cards.model import Effect
    m = re.fullmatch(r"attach (up to one .+?|.+?) to (.+?)\.?", s.strip(), re.I)    # not the "to" of "up to one"
    if not m:
        return None
    host = _host(m[2])
    if host is None:
        return None
    if re.match(r"(?:up to one )?target ", m[1], re.I):
        obj = _object(m[1])
        if obj is None:
            return None
        a = dict(obj.data)
        if host[0] == "fixed":
            return [Effect("cx_attach", target=obj.target, data=dict(a, host=host[1]))]
        b = dict(host[1].data)
        if a.get("optional_target") and b.get("optional_target"):
            return None
        common = {"group": "cx_attach", "distinct": True}
        move = Effect("cx_attach", target=host[1].target, data=dict(b, host="target", **common))
        mark = Effect("cx_attach_mark", target=obj.target,
                      data=dict(a, partner={"target": move.target, "data": dict(move.data)}, **common))
        return [mark, move]
    # the object isn't targeted: the attachment itself, or Auras / Equipment chosen on resolution
    obj = _SELF_OBJ.get(m[1].lower()) or _pick(m[1])
    if obj is None or (obj == host[1] if host[0] == "fixed" else False) or (obj == "it" and host == ("fixed", "prev")):
        return None
    if host[0] == "fixed":
        return [Effect("cx_attach", target="none", data={"host": host[1], "obj": obj})]
    return [Effect("cx_attach", target=host[1].target, data=dict(host[1].data, host="target", obj=obj))]


def _build(m):
    from .cards.model import NO_MATCH
    return parse(m[0]) or NO_MATCH


EFFECT_PATTERNS = [(r"attach (?:up to one )?target (?:aura|equipment)\b.+", _build),
                   (r"attach (?:~|it|this (?:equipment|aura|enchantment)) to (?!target creature you control$).+", _build),
                   (r"attach (?:an?|any number of|all) (?:aura|equipment)s?\b.+", _build)]


def pool(game, p, spec, host) -> list:
    """The Auras / Equipment an untargeted "attach an / any number of / all ..." can choose from."""
    subs = set(spec["subs"])
    return [x for pl in game.players for x in pl.battlefield
            if x is not host and (not spec["ctl"] or x.controller is p)
            and (("Aura" in subs and x.card.aura) or ("Equipment" in subs and "Equipment" in x.card.subtypes))]


def picked(game, p, spec, host, *, optional=False) -> list:
    """The objects an untargeted attach moves: all of them, the ones that gain something ("any number of"), or the
    one that gains most ("an Equipment you control"; a "may" one only if it gains)."""
    cands = pool(game, p, spec, host)
    if spec["pick"] == "all":
        return cands
    if spec["pick"] == "any":
        return [x for x in cands if gain(game, p, x, host) > 0]
    best = max(cands, key=lambda x: gain(game, p, x, host), default=None)
    return [best] if best is not None and (not optional or gain(game, p, best, host) > 0) else []


# ---- the AI -----------------------------------------------------------------------------------------------

def benefit(me, obj, host) -> float:
    """What obj being on host is worth to me."""
    from .engine.policy import perm_value
    if host is None:
        return 0.0
    sign = 1.0 if host.controller is me else -1.0
    if obj.card.aura and obj.card.aura_hostile:
        sign = -sign
    return sign * (1.0 + 0.1 * perm_value(host))


def gain(game, me, obj, host) -> float:
    """What moving obj onto host gains me (negative: it hurts, or the move can't happen)."""
    if obj is None or host is None or not can_host(game, obj, host) or current_host(obj) is host:
        return -1.0
    return benefit(me, obj, host) - benefit(me, obj, current_host(obj))


def _partner(eff):
    from .cards.model import Effect
    spec = eff.data["partner"]
    return Effect("cx_attach", target=spec["target"], data=spec["data"])


def _fixed_host(game, eff):
    from .cx_exchange import _source
    from .engine.state import Permanent
    if eff.data.get("host") == "self":
        src = _source(game)
        return src if isinstance(src, Permanent) else None
    ctx = getattr(game, "trigger_context", None)
    if isinstance(ctx, Permanent):
        return ctx                   # "that creature": what the trigger is about
    item = game.target_source
    ctx = getattr(item, "context", None)
    if isinstance(ctx, Permanent):
        return ctx
    src = _source(game)              # "Whenever ~ attacks, attach ... to it"
    return src if isinstance(src, Permanent) else None


def choose_many(game, me, eff):
    """"Attach any number of target Equipment to it": every legal object that does more good on the host."""
    probe = eff.data["probe"]
    host = _fixed_host(game, probe)
    pool = [x for x in game.legal_targets(me, probe) if gain(game, me, x, host) > 0]
    return tuple(pool)


def choose(game, me, eff):
    """policy.default_choose_target for the attach kinds."""
    from .cx_exchange import _anchored, anchor
    optional = eff.data.get("optional") or eff.data.get("optional_target")
    if eff.kind == "cx_attach_mark":
        partner = _partner(eff)
        best = None
        for obj in game.legal_targets(me, eff):
            with _anchored(game, obj):
                hosts = [x for x in game.legal_targets(me, partner) if x is not obj]
            for host in hosts:
                v = gain(game, me, obj, host)
                if best is None or v > best[0]:
                    best = (v, obj)
        if best is None or (optional or partner.data.get("optional_target")) and best[0] <= 0:
            return None
        return best[1]
    if eff.data.get("host") == "target" and eff.data.get("obj") is not None:
        pool_ = [x for x in game.legal_targets(me, eff)]
        if not pool_:
            return None
        host = max(pool_, key=lambda x: host_value(game, me, eff, x))
        return None if optional and host_value(game, me, eff, host) <= 0 else host
    if eff.data.get("host") == "target":
        obj = anchor(game, eff) or getattr(game, "cx_attach_pending", None)    # reflexive: chosen one at a time
        pool = [x for x in game.legal_targets(me, eff) if x is not obj]
        if obj is None or not pool:
            return None
        host = max(pool, key=lambda x: gain(game, me, obj, x))
        return None if optional and gain(game, me, obj, host) <= 0 else host
    host = _fixed_host(game, eff)
    pool = list(game.legal_targets(me, eff))
    if not pool:
        return None
    obj = max(pool, key=lambda x: gain(game, me, x, host))
    return None if optional and gain(game, me, obj, host) <= 0 else obj


def _own(game):
    """The attachment an "attach ~ / it to target ..." moves, while its host is chosen."""
    from .cx_exchange import _source
    from .engine.state import Permanent
    for x in (getattr(game, "trigger_context", None), _source(game)):
        if isinstance(x, Permanent) and is_attachment(x):
            return x
    return None


def host_value(game, me, eff, host) -> float:
    """What a host target is worth for an attach whose object isn't targeted."""
    spec = eff.data["obj"]
    if spec in ("self", "it"):
        return gain(game, me, _own(game), host)
    gains = [gain(game, me, x, host) for x in pool(game, me, spec, host)]
    if spec["pick"] == "all":
        return sum(gains)
    return sum(g for g in gains if g > 0) if spec["pick"] == "any" else max(gains, default=-1.0)


def mode_value(game, me, eff, tgt, chosen) -> float:
    """policy._mode_value for one attach effect (chosen: the targets so far, tgt last)."""
    if eff.kind == "cx_attach_mark":
        return 0.0
    if eff.data.get("host") == "target" and eff.data.get("obj") is not None:
        return host_value(game, me, eff, tgt) if tgt is not None else -1.0
    if eff.data.get("host") == "target":
        obj = chosen[-2] if len(chosen) >= 2 else None
        return gain(game, me, obj, tgt) if hasattr(obj, "controller") and tgt is not None else -1.0
    host = _fixed_host(game, eff)
    return gain(game, me, tgt, host) if tgt is not None and host is not None else 0.0
