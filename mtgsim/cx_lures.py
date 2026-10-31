"""Blocking requirements and limits ("lures"):

    All creatures able to block target creature this turn do so.        (grant lure_now)
    All creatures able to block enchanted creature do so.               (aura / equipment static: lure)
    {1}: Target creature blocks ~ this turn if able.                    you may have target creature block it this turn if able.
    {R}: Target creature can't block ~ this turn.
    Monocolored creatures can't block this turn.                         Creatures your opponents control can't block this turn.
    ~ blocks each combat if able.    ~ attacks or blocks each combat if able.    All creatures block each combat if able.
    Creatures can't block.           Enchanted creature can't block.
    Each creature you control can block an additional creature each combat.     ~ can block an additional creature this turn.
    Enchanted creature can block any number of creatures.
    Each creature you control with power 4 or greater can't be blocked by more than one creature.

Statics become keywords: ``lure``, ``must_block_now``, ``cant_block_now``, ``extra_block``, ``block_any`` and
``max_one_blocker`` (on the card, through ``static_keyword_grants`` or as ``advanced_rules["host_kws"]`` on an Aura
or Equipment, read by ``cx_statics.grants``). Pairings ("blocks ~", "can't block ~") are kept on the game for the turn
and read by ``Game.force_blocks`` and ``can_block``."""
from __future__ import annotations

import re

_SIDE_THEIRS = {"side": "theirs"}


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _who(word: str) -> str:
    word = word.lower()
    if word in ("~", "this creature"):
        return "self"
    if word in ("it", "that creature"):
        return "prev"
    return "creature"


def _lure(m):
    who = _who(m["w"])
    return _effect("grant", target=who, data={"keyword": "lure_now", "side": "mine"})


def _filtered(kind, m, data=None):
    data = dict(data or {}, side="theirs")
    if m["f"]:
        data["selector"] = {"types_all": ["artifact", "creature"]}
    return _effect(kind, target="creature", data=data)


def _mass(m):
    from .permanent_templates import selector
    from .cards.model import NO_MATCH
    text = m["f"]
    if text.lower().startswith(("target ", "~", "it ", "that ", "those ", "other ", "up to ")):
        return NO_MATCH
    spec = selector(text, plural=True)
    if spec is None or "creature" not in spec.get("types_all", ()):
        return NO_MATCH
    return _effect("cx_mass_cant_block", data={"selector": spec})


def _extra(m):
    return _effect("grant", target=_who(m["w"]), data={"keyword": "block_any" if m["any"] else "extra_block",
                                                       "side": "mine"})


EFFECT_PATTERNS = [
    (r"all creatures able to block (?P<w>target creature|it|~|that creature) this turn do so", _lure),
    (r"(?:target|another target) (?P<f>artifact )?creature blocks ~ this (?:turn|combat) if able",
     lambda m: _filtered("cx_must_block", m)),
    (r"(?:you may )?have target (?P<f>)creature block (?:it|~) this turn if able",
     lambda m: _filtered("cx_must_block", m)),
    (r"target (?P<f>artifact )?creature can't block ~ this turn", lambda m: _filtered("cx_cant_block_src", m)),
    (r"(?P<f>[\w ,'-]+?) can't block this turn", _mass),
    (r"(?P<w>~|it|target creature) can block (?:(?P<any>any number of creatures)|an additional creature) this turn",
     _extra),
]


# ---------------------------------------------------------------------------
# Static lines
# ---------------------------------------------------------------------------

_HOST = r"(?P<h>Enchanted|Equipped) creature"
_STATIC_SELF = {
    "~ blocks each combat if able.": ("must_block_now",),
    "~ attacks or blocks each combat if able.": ("must_block_now", "attacks_or_blocks"),
    "~ can block any number of creatures.": ("block_any",),
    "~ can block an additional creature each combat.": ("extra_block",),
    "~ can't be blocked by more than one creature.": ("max_one_blocker",),
}
_GROUP = [
    (re.compile(r"All creatures block each combat if able\."), "creatures", ("must_block_now",)),
    (re.compile(r"Creatures can't block\."), "creatures", ("cant_block_now",)),
    (re.compile(r"(?:Each )?(?P<s>.+?) can block an additional creature each combat\."), None, ("extra_block",)),
    (re.compile(r"(?:Each )?(?P<s>.+?) can't be blocked by more than one creature\."), None, ("max_one_blocker",)),
]
_HOST_LINES = [
    (re.compile(r"All creatures able to block (?P<h>enchanted|equipped) creature do so\."), ("lure",)),
    (re.compile(rf"{_HOST} can't block\."), ("cant_block_now",)),
    (re.compile(rf"{_HOST} can block an additional creature each combat\."), ("extra_block",)),
    (re.compile(rf"{_HOST} can block any number of creatures\."), ("block_any",)),
    (re.compile(rf"{_HOST} can't be blocked by more than one creature\."), ("max_one_blocker",)),
]


def parse_line(line: str, st) -> bool:
    extra = st.extra
    kws = _STATIC_SELF.get(line)
    if kws:
        if "attacks_or_blocks" in kws:
            extra["must_attack"] = True
            kws = ("must_block_now",)
        st.keywords.update(kws)
        return True
    for rx, kws in _HOST_LINES:
        m = rx.fullmatch(line)
        if m:
            host = m["h"].lower()
            if (host == "enchanted") != bool(extra.get("aura")) or \
                    host == "equipped" and "Equipment" not in extra.get("_subtypes", ()):
                return False
            rules = extra.setdefault("advanced_rules", {})
            rules["host_kws"] = rules.get("host_kws", ()) + kws
            return True
    from .permanent_templates import selector
    for rx, subject, kws in _GROUP:
        m = rx.fullmatch(line)
        if not m:
            continue
        text = subject or m["s"]
        if text.startswith(("~", "Enchanted", "Equipped")):
            return False
        spec = selector(text, plural=not text.endswith("creature"))
        if spec is None or "keyword" in spec:
            return False
        extra["static_keyword_grants"] = extra.get("static_keyword_grants", ()) + ((spec, kws),)
        return True
    return False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def extra_blocks(blocker) -> int:
    """How many more attackers than one this creature can block."""
    if blocker.has("block_any"):
        return 99
    return blocker.card.extra_blocks + (1 if blocker.has("extra_block") else 0)


def is_lure(attacker) -> bool:
    return bool(attacker.card.lure) or attacker.has("lure") or attacker.has("lure_now")


def max_blockers(attacker) -> int:
    limit = attacker.card.max_blockers
    if attacker.has("max_one_blocker"):
        return 1 if not limit else min(limit, 1)
    return limit


def _pairs(game, name):
    pairs = getattr(game, name, None)
    if not pairs:
        return []
    live = [x for x in pairs if x[0] == game.turn]
    if len(live) != len(pairs):
        setattr(game, name, live)
    return live


def add_pair(game, name, blocker, attacker):
    if not hasattr(game, name):
        setattr(game, name, [])
    getattr(game, name).append((game.turn, blocker, attacker))


def pair_blocked(blocker, attacker) -> bool:
    """"Target creature can't block ~ this turn"."""
    game = getattr(blocker.controller, "_game", None)
    return game is not None and any(b is blocker and a is attacker for _t, b, a in _pairs(game, "_cx_cant_block"))


def forced_pairs(game):
    """(blocker, attacker) pairs from "target creature blocks ~ this turn if able"."""
    return [(b, a) for _t, b, a in _pairs(game, "_cx_must_block")]
