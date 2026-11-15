"""Kinds for attaching an Aura or Equipment already on the battlefield (see mtgsim.cx_attach, #343)."""
from ...cx_attach import attach, gain
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


@kind("cx_attach")
def attach_kind(game, p, eff, target, item=None, **_):
    host = eff.data.get("host")
    if host == "target":
        obj = _marked(game, p, eff, item)
        dest = target
        game.cx_attach_pending = None
    else:
        obj = target
        dest = (item.source if item is not None else None) if host == "self" else _referent(game, p, eff, item)
    if not isinstance(obj, Permanent) or not isinstance(dest, Permanent):
        return
    if eff.data.get("optional") and gain(game, p, obj, dest) <= 0:
        game.log(f"declines to attach {obj.card.name}", p)
        return
    attach(game, p, obj, dest)
