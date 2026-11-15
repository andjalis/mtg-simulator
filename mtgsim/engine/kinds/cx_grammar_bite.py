"""Kinds for referent damage, "<creature> deals damage equal to its power to <recipient>" (mtgsim.cx_grammar_bite)."""
from ..state import Permanent, Player
from . import kind


def referent(obj, item):
    """The creature "it" / "that creature" names: the previous object or the creature a trigger fired on; with
    none, the ability's own source ("Sacrifice ~: It deals damage equal to its power"). "It" deals damage equal to
    its power, so it is a creature: an Aura's own enters trigger means the enchanted creature (Bind the Monster)."""
    own = getattr(item, "source", None)
    if isinstance(obj, Permanent) and obj.is_creature:
        return obj
    if obj is None or obj is own:
        if isinstance(own, Permanent) and not own.is_creature:
            host = own.aura_host or own.attached_to
            return host if isinstance(host, Permanent) else None
        return own if isinstance(own, Permanent) else None
    return None


@kind("bite_src")
def bite_src(game, eff, item, target, **_):
    """One creature that will deal the damage: recorded on the stack item (a source that is an illegal target by
    now never gets here, so it deals no damage)."""
    if eff.target == "prev":
        target = referent(target, item)
    if item is not None and isinstance(target, Permanent):
        sources = getattr(item, "bite_sources", None)
        if sources is None:
            item.bite_sources = sources = []
        sources.append(target)


@kind("ref_bite")
def ref_bite(game, p, eff, target, item, prev=None, cause=None, **_):
    """Each source deals damage equal to its power (times ``mult``, plus ``plus``) to the recipient, all read
    before any damage is dealt."""
    from ...cx_grammar import group_members, players
    data = eff.data
    src_kind = data.get("src")
    if src_kind == "member":                 # inside a cx_group: the member is the source
        srcs = [target] if isinstance(target, Permanent) else []
    elif src_kind == "group":
        srcs = group_members(game, p, {"group": data["src_group"]}, item.source if item is not None else None)
    else:
        srcs = list(getattr(item, "bite_sources", None) or ()) if item is not None else []
        if item is not None:
            item.bite_sources = []          # the next sentence records its own sources
    hits = []
    for src in srcs:
        n = max(0, src.power) * data.get("mult", 1) + data.get("plus", 0)
        to = data.get("to")
        if to == "self_each":
            victims = [src]
        elif to == "src_controller":
            victims = [src.controller]
        elif to == "source_perm":
            own = item.source if item is not None else None
            victims = [own] if isinstance(own, Permanent) else []
        elif to == "who":
            victims = players(game, p, data["who"], item, prev, target)
        elif to == "group":
            victims = group_members(game, p, {"group": data["members"]}, src)
        else:
            victims = [target]
        hits += [(src, v, n) for v in victims]
    for src, victim, n in hits:
        if isinstance(victim, Player) or isinstance(victim, Permanent) and victim in victim.controller.battlefield:
            game.deal_damage(victim, n, by=src.controller, cause=cause or "noncombat damage", source=src)
