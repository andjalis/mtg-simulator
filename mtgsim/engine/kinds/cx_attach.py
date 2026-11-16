"""Kinds for attaching an Aura or Equipment already on the battlefield (see mtgsim.cx_attach, #343)."""
from ...cx_attach import attach, gain, is_attachment, picked
from ...cx_delayed import _fresh
from ..state import Permanent
from . import kind


@kind("cx_attach_mark")
def attach_mark(game, p, target=None, item=None, **_):
    """The object of a two-target attach: the following cx_attach reads it from the stack item. It is also kept on
    the item, for a reflexive "When you do, attach target ... to target ..." whose targets are chosen one at a time
    on resolution (cx_trig_reflex)."""
    if item is not None:
        item.cx_attach_obj = target
    game.cx_attach_pending = target      # the host's target choice in the same resolution reads it (cx_attach.choose)


def _marked(game, p, eff, item):
    """The mark's target, while it is still a legal target."""
    if item is None:
        return None
    idx = next((i for i, e in enumerate(item.effects) if e is eff), None)
    if not idx or idx > len(item.targets) or item.effects[idx - 1].kind != "cx_attach_mark":
        obj = getattr(item, "cx_attach_obj", None)      # resolved by the mark just before (reflexive payoffs)
        return obj if isinstance(obj, Permanent) and obj in obj.controller.battlefield else None
    obj = item.targets[idx - 1]
    with game.targeting(item):
        return obj if obj is not None and game.legal_target(p, item.effects[idx - 1], obj) else None


def _referent(game, p, eff, item):
    """"it" / "that creature": the permanent the trigger is about, else the target of an earlier effect of the same
    spell or ability (while it is still a legal target)."""
    if item is None:
        return None
    fresh = [x for x in _fresh(game, item) if x.is_creature]
    if fresh:
        return fresh[-1]            # "Create a 1/1 Kor Warrior token. You may attach an Equipment you control to it."
    if item.kind == "trigger" and isinstance(item.context, Permanent):
        return item.context
    if item.kind == "trigger" and item.context is None and isinstance(item.source, Permanent):
        return item.source          # "Whenever ~ attacks, attach ... to it"
    idx = next((i for i, e in enumerate(item.effects) if e is eff), 0)
    for e, t in reversed(list(zip(item.effects[:idx], item.targets[:idx]))):
        if isinstance(t, Permanent):
            with game.targeting(item):
                return t if game.legal_target(p, e, t) else None
    return None


def _it(game, p, eff, item):
    """"attach it to ...": an Aura / Equipment that entered during this resolution ("create an Equipment token ...
    Attach it to ~"), else one an earlier effect targeted ("Gain control of target Equipment ... Attach it to ~"),
    else the attachment the trigger is about, else the source itself."""
    fresh = [x for x in _fresh(game, item) if is_attachment(x)]
    if fresh:
        return fresh[-1]
    idx = next((i for i, e in enumerate(item.effects) if e is eff), 0)
    for e, t in reversed(list(zip(item.effects[:idx], item.targets[:idx]))):
        if isinstance(t, Permanent):     # (the earlier effect itself may have changed who controls it)
            return t if is_attachment(t) and t in t.controller.battlefield else None
    for x in (getattr(item, "context", None), getattr(item, "source", None)):
        if isinstance(x, Permanent) and is_attachment(x):
            return x
    return None


@kind("cx_attach")
def attach_kind(game, p, eff, target, item=None, **_):
    host, spec = eff.data.get("host"), eff.data.get("obj")
    if host == "target":
        dest = target
    elif host == "self":
        dest = item.source if item is not None else None
    else:
        dest = _referent(game, p, eff, item)
    if spec is None:                     # a targeted object
        if host == "target":
            objs = [_marked(game, p, eff, item)]
            game.cx_attach_pending = None
        else:
            objs, dest = [target], dest
    elif spec == "self":
        objs = [item.source if item is not None else None]
    elif spec == "it":
        objs = [_it(game, p, eff, item)]
    else:                                # chosen on resolution
        objs = picked(game, p, spec, dest, optional=bool(eff.data.get("optional")))
    if not isinstance(dest, Permanent):
        return
    for obj in objs:
        if not isinstance(obj, Permanent):
            continue
        if eff.data.get("optional") and gain(game, p, obj, dest) <= 0:
            game.log(f"declines to attach {obj.card.name}", p)
            continue
        attach(game, p, obj, dest)
