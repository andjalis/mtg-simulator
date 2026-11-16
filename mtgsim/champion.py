"""#646: Champion (CR 702.72).

    Champion a creature / Champion an Elf / Champion a Treefolk or Warrior

CR 702.72a: "When this permanent enters, sacrifice it unless you exile another [object] you control" and "When this
permanent leaves the battlefield, return the exiled card to the battlefield under its owner's control." The two
abilities are linked (CR 702.72b, 607.2k): the enters trigger is an ``champion`` Effect; the exile is
Game.exile_until_leaves (the same link O-Ring uses), so the card comes back under its owner's control when the
champion leaves, a championed token is gone for good, and a card that already left exile stays where it is.

The controller chooses (the default AI: a nontoken permanent that gains from entering again, else the least
valuable one). With nothing to champion, or with only permanents worth more than keeping the champion, the
champion is sacrificed. HeuristicAI doesn't cast a champion with nothing to champion (``ai_value``).
"""
from __future__ import annotations

import re


def _selector(noun: str):
    from .permanent_templates import _SUBTYPE_TYPES, subject
    names = re.split(r" or ", noun)
    if len(names) == 2 and all(re.fullmatch(r"[A-Z][a-z]+", n) and _SUBTYPE_TYPES.get(n.lower()) == ["creature"]
                               for n in names):
        return {"controller": "mine", "any_subtypes": [n.lower() for n in names], "types_any": ["permanent"],
                "other": True}
    if len(names) != 1:
        return None
    subj = subject("another target " + noun + " you control")
    if subj is None or subj[0] != "permanent" or subj[1]["selector"].get("controller") != "mine":
        return None
    return subj[1]["selector"]


def parse_line(line: str, st) -> bool:
    m = re.fullmatch(r"Champion an? ((?:[A-Z][a-z]+|creature)(?: or [A-Z][a-z]+)?)", line.strip())
    if not m:
        return False
    sel = _selector(m[1])
    if sel is None:
        return False
    from .cards import Effect, Trigger
    st.triggers.append(Trigger("etb", [Effect("champion", data={"selector": sel, "desc": m[1]})]))
    return True


def candidates(game, p, src, sel):
    from .permanent_templates import matches
    return [x for x in p.battlefield if x is not src and matches(game, x, sel, p, src)]


def _gains(pool):
    """Nontoken permanents that get their enters abilities again when they come back."""
    return [x for x in pool if not x.card.is_token and
            (x.card.etb_effects or any(t.event == "etb" for t in x.card.triggers))]


def _choice(pool):
    from .ai import perm_value
    gains = _gains(pool)
    return max(gains, key=perm_value) if gains else min(pool, key=perm_value)


def resolve(game, p, eff, item):
    from .ai import perm_value
    src = item.source if item is not None else None
    if src is None or src not in src.controller.battlefield:
        return              # it already left: nothing to sacrifice, and exiling now would never come back
    pool = candidates(game, p, src, eff.data["selector"])
    pick = _choice(pool) if pool else None
    if pick is not None and (pick in _gains(pool) or perm_value(pick) <= perm_value(src)):
        game.exile_until_leaves(src, [pick])
        game.log(f"champions {pick.card.name} with {src.card.name}", p)
        return
    game.log(f"sacrifices {src.card.name} (nothing championed)", p)
    game.sacrifice(src)


def ai_value(game, me, eff, card) -> float:
    """HeuristicAI's enters value of a champion (ai._etb_value, where below zero means "don't cast it"): negative
    when nothing can be championed (it would be sacrificed at once) or when the only choice is worth more than the
    champion, else 0 (the championed permanent comes back when the champion leaves)."""
    from .ai import card_value, perm_value
    pool = candidates(game, me, None, eff.data["selector"])
    if not pool:
        return -card_value(card) - 10.0
    pick = _choice(pool)
    return 0.0 if pick in _gains(pool) or perm_value(pick) <= card_value(card) else -1.0
