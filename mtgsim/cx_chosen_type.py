"""The chosen creature type (#627): "<permanents> [that aren't] of the chosen type".

Where the choice lives:
- As the permanent enters ("As ~ enters, choose a creature type", Game.enter_battlefield): ``perm.chosen_type``.
- On resolution ("Choose a creature type. Creatures you control of the chosen type get +1/+0 ...", "Destroy all
  creatures of the creature type of your choice"): the sentence becomes the private "CHOOSECTYPE [HOSTILE]." (SUBS),
  read as the ``choose_ctype`` kind, which stores the pick on the resolving stack item (``item.chosen_type``).
The selector key ``chosen_type`` (permanent_templates.selector / matches: True, or "not" for "that aren't of the
chosen type") compares a permanent's subtypes with the source's choice, else the resolving item's. A card that reads
the key with no choice stored anywhere gets an unsupported note (``unbound``) rather than matching nothing. A choice
made on resolution can't restrict targets (they are chosen first), so a sentence with "target" is not rewritten.

Which type the AI names, from public information only (the battlefields, graveyards and exile; its own hand and
deck are its own): for text that helps those creatures, the type with the most of its own creatures minus the
opponent's on the battlefield (its own deck when the battlefield has none); for text that hurts them ("get -N/-N",
"don't untap", "destroy", "attack this turn if able", "your opponents control"), the reverse. "That aren't of the
chosen type" turns the sense around (Kindred Dominance names your own type). Ties go to the alphabetically first type,
so the pick is deterministic. The opponent's hand and library are never read.
"""
from __future__ import annotations

import re
from collections import Counter

_USES = re.compile(r"\bof the chosen (?:creature )?type\b", re.I)
_HOSTILE = re.compile(r"of the chosen (?:creature )?type(?: your opponents control)? (?:get -|don't untap|attack "
                      r"this turn if able)|of the chosen (?:creature )?type your opponents control|"
                      r"\bdestroy all [^.]*?(?<!aren't )of the chosen (?:creature )?type", re.I)
# a target restricted by the type ("X target creatures of the creature type of your choice"): chosen before the type
_TARGETED = re.compile(r"\btarget (?:[\w-]+ ){0,3}?(?:creatures?|permanents?|cards?)(?: you control)? of the "
                       r"(?:chosen|creature) (?:creature )?type", re.I)
_NOT = re.compile(r"that aren't of the chosen (?:creature )?type", re.I)


def hostile(text: str) -> bool:
    """Whether the chosen-type text hurts the creatures of that type (so the AI names the opponent's)."""
    return bool(_HOSTILE.search(text or "")) and not _NOT.search(text or "")


def _marker(sentence: str) -> str:
    return "CHOOSECTYPE HOSTILE. " if hostile(sentence) else "CHOOSECTYPE. "


def _your_choice(m):
    text = f"{m[1]} of the chosen type{m[2]}"
    if _TARGETED.search(text):
        return m[0]                     # targets are chosen before the type: not this rule's
    return _marker(text) + text[0].upper() + text[1:] + "."


SUBS = [
    # "Choose a creature type. <sentence using the chosen type>": the choice on resolution. Crippling Fear's "that aren't
    # of the chosen type get -N/-N" keeps its existing reading.
    (re.compile(r"choose a creature type\. (?=([^.]*\bof the chosen (?:creature )?type\b[^.]*)\.)"
                r"(?![^.]*aren't of the chosen type get -)", re.I),
     lambda m: _marker(m[1]) if not _TARGETED.search(m[1]) else m[0]),
    # "<group> of the creature type of your choice <verb>": the same choice inside one sentence
    (re.compile(r"(?:^|(?<=\. ))([^.]*?) of the creature type of your choice([^.]*)\.", re.I), _your_choice),
]


def _build(m):
    from .cards.model import Effect
    return Effect("choose_ctype", data={"hostile": bool(m[1])})


EFFECT_PATTERNS = [(r"choosectype( hostile)?", _build)]


def _walk(obj, test, depth=0) -> bool:
    if depth > 6 or obj is None:
        return False
    if test(obj):
        return True
    if isinstance(obj, dict):
        return any(_walk(v, test, depth + 1) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_walk(v, test, depth + 1) for v in obj)
    data = getattr(obj, "data", None)
    if isinstance(data, dict) and _walk(data, test, depth + 1):
        return True
    effects = getattr(obj, "effects", None)
    return _walk(effects, test, depth + 1) if effects is not None else False


def unbound(oracle: str, extra: dict, *parsed) -> list:
    """Unsupported notes for a card whose parsed text reads the chosen type with no choice stored anywhere."""
    if not _USES.search(oracle or "") or extra.get("choose_type"):
        return []
    uses = _walk(list(parsed), lambda o: isinstance(o, dict) and o.get("chosen_type") in (True, "not"))
    chooses = _walk(list(parsed), lambda o: getattr(o, "kind", None) == "choose_ctype")
    if not uses or chooses:
        return []
    return ["chosen creature type with no stored choice for 'of the chosen type'"]


def type_of(game, source) -> str:
    """The chosen type a selector reads: the source permanent's, else the resolving spell's or ability's. A spell's
    amounts ("equal to the number of permanents you control of the chosen type") are worked out before its effect
    handler runs (Game.resolve), so for a spell (no permanent source) the item its own choose_ctype just stored is
    read; every spell that reads the key chooses first (``unbound`` lists the others), so that record is its own."""
    typ = getattr(source, "chosen_type", "") or getattr(getattr(game, "resolving_item", None), "chosen_type", "")
    if typ or source is not None:
        return typ
    return getattr(getattr(game, "ctype_item", None), "chosen_type", "")


def _types(cards) -> Counter:
    out: Counter = Counter()
    for c in cards:
        if c.is_creature:
            out.update(set(c.subtypes))
    return out


def pick(game, p, harmful: bool) -> str:
    """The creature type p names, from public information (see the module doc)."""
    opp = game.opponent(p)
    mine = _types(x.card for x in p.battlefield)
    theirs = _types(x.card for x in opp.battlefield)
    score = Counter({t: theirs[t] - mine[t] if harmful else mine[t] - theirs[t] for t in set(mine) | set(theirs)})
    best = sorted((t for t in score if score[t] > 0), key=lambda t: (-score[t], t))
    if best:
        return best[0]
    if harmful:     # nothing of theirs in play: the public zones (graveyard, exile), else no type
        seen = _types(list(opp.graveyard) + list(opp.exile))
    else:
        seen = _types(list(p.hand) + list(p.deck))
    return min(seen, key=lambda t: (-seen[t], t)) if seen else ""


def pick_hostile(game, p) -> str:
    """The opponent's creature type a harmful "As ~ enters, choose a creature type" names (public information only)."""
    return pick(game, p, True)


def choose(game, p, item, harmful: bool) -> None:
    """The choose_ctype kind: store the pick on the resolving spell or ability."""
    if item is not None:
        item.chosen_type = pick(game, p, harmful)
        game.ctype_item = item
        game.log(f"chooses {item.chosen_type or 'no creature type'}", p)
