"""Referent damage (#313): "<creature> deals damage equal to its power to <recipient>".

    Target creature you control deals damage equal to its power to any target.               (Soul's Fire)
    Target creature you control deals damage equal to its power to another target creature.  (Hulk's Thunderclap)
    Up to two target creatures you control each deal damage equal to their power to another target creature.
    Target creature an opponent controls deals damage equal to its power to another target creature that player controls.
    Target creature you control deals damage equal to twice its power to target creature you don't control.
    Target creature deals damage equal to its power to itself.                                (Wisecrack)
    That creature deals damage equal to its power to its controller.                          (Backlash)
    Each creature deals damage to itself equal to its power.                                  (Solar Blaze)
    Each other Bird you control deals damage equal to its power to target creature an opponent controls.

"its" / "their" is the creature that deals the damage, read when the damage is dealt. The subject becomes one
``bite_src`` effect per source: a target ("target creature you control"), ~, "it" / "that creature" (the previous
object or the creature a trigger fired on) or the enchanted / equipped creature; each one that is still legal
when it resolves records its permanent on the stack item. The ``ref_bite`` effect that follows makes every recorded
source deal damage equal to its power (twice it, plus N) to the recipient: a target, "itself", "its controller",
untargeted players, or a group. A group subject ("each creature ...") becomes a ``cx_group`` whose members each
deal their own damage, or, with a single target as the recipient, a ``ref_bite`` whose sources are the group.

"another target ..." / "any other target" means another than the creatures dealing the damage, and "... that
player controls" one controlled by the source's controller: both are target restrictions (``rel_ok``, a hook in
``Game.passes_filter``) checked while targets are chosen and again on resolution. A source that is an illegal
target on resolution deals no damage (CR 608.2b). Sentences the existing damage verbs already read keep their
parse: this rider only answers when the rest of the grammar doesn't.
"""
from __future__ import annotations

import dataclasses
import re
from types import SimpleNamespace

from .cx_grammar import ai_value, object_phrase, rider, subject

_busy = []

_SENTENCE = (r"(?P<subj>.+?) (?:each )?deals? damage (?:to (?P<to1>.+?) )?equal to (?P<twice>twice )?(?:its|their) "
             r"power(?: plus (?P<plus>\d+))?(?: to (?P<to2>.+?))?")


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


@rider(_SENTENCE)
def bite(m, inner):
    if _busy:
        return None
    _busy.append(True)
    try:
        existing = inner(m[0])       # the damage verbs and other riders first: their parses stay as they are
    finally:
        _busy.pop()
    if existing:
        return existing
    if bool(m["to1"]) == bool(m["to2"]):
        return None
    return build(m["subj"], (m["to1"] or m["to2"]).strip(), 2 if m["twice"] else 1, int(m["plus"] or 0))


def _subjects(text: str):
    """The source Subjects: one, or "A and B each" (two targeted ones), or None."""
    low = text.strip().lower()
    if low in ("they", "they each", "those creatures", "each of those creatures"):
        return None                  # a group of earlier objects: not recorded here
    text = re.sub(r"\byour team controls\b", "you control", text)      # two-player games: your team is you
    one = subject(text)
    if one is not None:
        return [one]
    m = re.fullmatch(r"(.+?) and (.+?)(?: each)?", text.strip(), re.I)
    if m is None:
        return None
    pair = [subject(m[1]), subject(m[2])]
    if any(s is None or s.kind != "permanent" or s.target != "permanent" or s.copies != 1 for s in pair):
        return None
    return pair


def _aim(subj, to: str) -> str:
    """Whose creature the AI picks as a targeted source."""
    ctrl = (subj.data.get("selector") or {}).get("controller")
    if ctrl == "opp":
        return "theirs"
    if ctrl is None and to in ("self_each", "src_controller"):
        return "theirs"              # "Target creature deals damage equal to its power to itself": theirs
    return "mine"


def _recipient(text: str, subj_text: str):
    """(to, object Subject or None, extra data) for the recipient phrase, or None."""
    low = text.lower()
    if low == "itself":
        return "self_each", None, {}
    if low in ("its controller", "the creature's controller", "that creature's controller"):
        return "src_controller", None, {}
    if low == "that player" and re.search(r"\b(?:an opponent|you don't) controls?\b", subj_text, re.I):
        return "src_controller", None, {}
    rel = ""
    m = re.fullmatch(r"(.+) that player controls", text, re.I)
    if m:
        if not re.search(r"\ban opponent controls\b", subj_text, re.I):
            return None
        text, rel = m[1], "same_ctrl"
        low = text.lower()
    if low == "any other target":
        obj = object_phrase("any target")
        return "target", obj, {"bite_rel": "not_src" + ("_same_ctrl" if rel else "")}
    if low in ("~", "this creature"):
        return "source_perm", None, {}
    obj = object_phrase(text)
    if obj is None:
        return None
    if obj.kind == "player":
        if obj.who == "target":
            return "target", obj, {}
        if obj.who in ("you", "opponents", "each", "defending"):
            return "who", None, {"who": obj.who}
        return None
    if obj.kind == "group":
        if rel or (obj.data or {}).get("filter") or obj.target != "none":
            return None
        return "group", None, {"members": obj.group}
    if obj.kind != "permanent" or obj.target in ("self", "prev", "host") or obj.copies != 1:
        return None
    data = {}
    if obj.data.get("other"):
        obj = dataclasses.replace(obj, data={k: v for k, v in obj.data.items() if k != "other"})
        rel = "not_src_same_ctrl" if rel else "not_src"
    if rel:
        data["bite_rel"] = rel
    return "target", obj, data


def build(subj_text: str, to_text: str, mult: int = 1, plus: int = 0):
    """The Effects for one referent-damage sentence, or None."""
    subjects = _subjects(subj_text)
    rec = _recipient(to_text, subj_text)
    if subjects is None or rec is None:
        return None
    to, obj, extra = rec
    data = dict(extra, to=to, mult=mult, plus=plus, side="theirs")
    if len(subjects) == 1 and subjects[0].kind == "group":
        return _group(subjects[0], to, obj, data)
    out = []
    for subj in subjects:
        if subj.kind == "host":
            out.append(_effect("bite_src", target="host"))
        elif subj.kind == "permanent" and subj.target in ("self", "prev"):
            out.append(_effect("bite_src", target=subj.target))
        elif subj.kind == "permanent" and subj.target == "permanent":
            sdata = {k: v for k, v in subj.data.items() if k not in ("other", "filter")}
            if len(subjects) > 1 or subj.copies > 1:
                sdata.update(distinct=True, group="bite_src")
            sdata["aim"] = _aim(subj, to)
            first_optional = subj.data.get("optional_from", subj.copies)
            for i in range(subj.copies):
                out.append(_effect("bite_src", target="permanent", filter=subj.data.get("filter", ""),
                                   data=dict(sdata, **({"optional_target": True} if i >= first_optional else {}))))
        else:
            return None
    data["src"] = "marks"
    out.append(_bite(obj, data))
    return out


def _bite(obj, data):
    if obj is None:
        return _effect("ref_bite", data=data)
    odata = {k: v for k, v in obj.data.items() if k != "filter"}
    return _effect("ref_bite", target=obj.target, filter=obj.data.get("filter", ""), data=dict(odata, **data))


def _group(subj, to, obj, data):
    """A group subject: each member deals its own damage."""
    if subj.target != "none" or subj.data.get("filter"):
        return None                  # "each creature target player controls ...": not here
    if to == "target":               # every member hits the one target
        return [_bite(obj, dict(data, src="group", src_group=subj.group))]
    if to == "source_perm":
        return None
    inner = _effect("ref_bite", target="self", data=dict(data, src="member"))
    return [_effect("cx_group", data={"group": subj.group, "effects": [inner]})]


# ---------------------------------------------------------------- sources and target relations

def _source_perm(game):
    from .engine.state import Permanent, StackItem
    src = game.target_source
    src = src.source if isinstance(src, StackItem) else src
    return src if isinstance(src, Permanent) else None


def _lists(game, eff):
    """(effects, chosen targets, stack item or None) holding eff, while its targets are chosen or checked."""
    from .engine.state import StackItem
    effects = getattr(game, "_choosing_effects", None) or ()
    if any(e is eff for e in effects):
        return list(effects), list(getattr(game, "_choosing_targets", None) or ()), None
    item = game.target_source
    if isinstance(item, StackItem) and any(e is eff for e in item.effects):
        return item.effects, item.targets, item
    return None, None, None


def sources(game, eff, me=None):
    """The permanents that deal the damage of a ref_bite, as far as they are known now (targets being chosen or
    checked): the targets / referents of the bite_src effects just before it, or the group's members."""
    from .cx_grammar import group_members
    from .engine.state import Permanent, StackItem
    if eff.data.get("src") == "group":
        me = me or getattr(game.target_source, "controller", None)
        if me is None:
            return []
        return group_members(game, me, {"group": eff.data["src_group"]}, _source_perm(game))
    effects, chosen, item = _lists(game, eff)
    if effects is None:
        return []
    idx = next(i for i, e in enumerate(effects) if e is eff)
    out = []
    j = idx - 1
    while j >= 0 and effects[j].kind == "bite_src":
        mark = effects[j]
        if mark.target == "self":
            obj = _source_perm(game)
        elif mark.target == "host":
            own = _source_perm(game)
            obj = (own.aura_host or own.attached_to) if own is not None else None
        elif mark.target == "prev":
            from .engine.kinds.cx_grammar_bite import referent
            obj = chosen[j - 1] if j >= 1 and j - 1 < len(chosen) else None
            stack_item = item or (game.target_source if isinstance(game.target_source, StackItem) else None)
            if obj is None and stack_item is not None and isinstance(stack_item.context, Permanent):
                obj = stack_item.context
            obj = referent(obj, stack_item or SimpleNamespace(source=_source_perm(game)))
        else:
            obj = chosen[j] if j < len(chosen) else None
        if isinstance(obj, Permanent):
            out.append(obj)
        j -= 1
    return out


def rel_ok(game, eff, perm, by=None) -> bool:
    """Game.passes_filter: "another target ..." (not a source) and "... that player controls" (the source's
    controller's). Unknown sources: allowed (the resolution check reads them again)."""
    rel = eff.data["bite_rel"]
    srcs = sources(game, eff, by)
    if "not_src" in rel and any(s is perm for s in srcs):
        return False
    if "same_ctrl" in rel and srcs and perm.controller is not srcs[0].controller:
        return False
    return True


# ---------------------------------------------------------------- AI

def _power(src, eff):
    return max(0, src.power) * eff.data.get("mult", 1) + eff.data.get("plus", 0)


def _kills(perm, n) -> bool:
    if perm.is_planeswalker and not perm.is_creature:
        return perm.loyalty <= n
    return perm.is_creature and perm.toughness - perm.damage <= n and not perm.has("indestructible")


def _following_bite(game, eff):
    effects, _, _ = _lists(game, eff)
    if effects is None:
        return None
    idx = next(i for i, e in enumerate(effects) if e is eff)
    return next((e for e in effects[idx + 1:] if e.kind != "bite_src"), None)


def choose(game, me, eff):
    """Targets for bite_src (the creature that deals the damage) and ref_bite (what it hits)."""
    from .engine.policy import perm_value
    from .engine.state import Permanent
    opp = game.opponent(me)
    legal = game.legal_targets(me, eff)
    if eff.kind == "bite_src":
        bite_eff = _following_bite(game, eff)
        to = bite_eff.data.get("to") if bite_eff is not None else "target"
        aim = eff.data.get("aim", "mine")
        pool = [x for x in legal if isinstance(x, Permanent) and x.is_creature
                and (x.controller is me) == (aim == "mine")]
        if to == "self_each":       # it hurts itself: one of theirs that dies
            pool = [x for x in pool if _kills(x, _power(x, bite_eff))]
            return max(pool, key=perm_value, default=None)
        if to == "src_controller":   # it hurts its own controller: their biggest
            return max(pool, key=lambda x: (x.power, perm_value(x)), default=None) \
                if any(x.power > 0 for x in pool) else None
        if to == "group" and bite_eff is not None:
            def net(x):
                members = _members(game, me, bite_eff, x)
                n = _power(x, bite_eff)
                return sum((perm_value(v) + 1) * (1 if v.controller is opp else -1) for v in members if _kills(v, n))
            best = max(pool, key=net, default=None)
            return best if best is not None and net(best) > 0 else None
        pool = [x for x in pool if x.power > 0]
        return max(pool, key=lambda x: (x.power, perm_value(x)), default=None)
    total = sum(_power(s, eff) for s in sources(game, eff, me))
    if total <= 0 and eff.data.get("src") != "marks":
        return None
    if total <= 0:          # sources not chosen yet (planning): the biggest creature of mine stands in
        total = max((_power(c, eff) for c in me.creatures), default=0)
    theirs = [x for x in legal if isinstance(x, Permanent) and x.controller is opp]
    if opp in legal and total >= opp.life:
        return opp
    kill = [x for x in theirs if _kills(x, total)]
    if kill:
        return max(kill, key=perm_value)
    if opp in legal:
        return opp
    return None


def _members(game, me, eff, src):
    from .cx_grammar import group_members
    return group_members(game, me, {"group": eff.data["members"]}, src)


@ai_value("ref_bite")
def _member_value(game, me, eff, obj):
    """A group member dealing damage equal to its power to itself (or to its controller)."""
    from .ai import life_value, perm_value
    from .engine.state import Permanent
    if not isinstance(obj, Permanent) or not obj.is_creature:
        return 0.0
    mine = obj.controller is me
    sign = -1.0 if mine else 1.0
    n = _power(obj, eff)
    to = eff.data.get("to")
    if to == "self_each":
        return sign * (perm_value(obj) + 1) if _kills(obj, n) else sign * 0.3 * min(n, obj.toughness)
    if to == "src_controller":
        return sign * (life_value(obj.controller.life) - life_value(obj.controller.life - n))
    if to == "who" and eff.data.get("who") == "opponents":
        opp = game.opponent(obj.controller)
        return (1.0 if mine else -1.0) * (life_value(opp.life) - life_value(opp.life - n))
    return 0.0
