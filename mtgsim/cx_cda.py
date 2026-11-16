"""Characteristic-defining P/T counts: "~'s power and toughness are each equal to the number of creatures on the
battlefield" (Beast of Burden), "... creature cards in all graveyards" (Cruel Somnophage), "... other creatures you
control". The count is stored in ``pt_cda`` as ``cx:<scope>:<what>`` and evaluated by ``count``."""
from __future__ import annotations

import re

_LINE = re.compile(r"~'s power and toughness are each equal to the number of (other )?([\w -]+?) "
                   r"(you control|on the battlefield|in your graveyard|in all graveyards|your opponents control|"
                   r"in the hand of the opponent with the most cards in hand)\.")


_ANY = re.compile(r"(?:[A-Z][\w' -]* — )?~'s (power|toughness|power and toughness are each) (?:is )?equal to (.+?)\.")


def _any_quantity(line: str, st) -> bool:
    """Any quantity ``cards._xq`` reads ("the greatest mana value among creatures you control", "the number of
    cards in your hand", "1 plus the number of lands you control"): ``advanced_rules["cda_q"]`` = (spec, power
    scale, toughness scale), evaluated for the permanent as its P/T is read (Permanent._pt_bonus)."""
    m = _ANY.fullmatch(line)
    if m is None or re.search(r"\b(?:it|its|that|this|those|their)\b", m[2], re.I):
        return False
    from .cards.clauses import _xq
    spec = _xq(m[2])
    if spec is None:
        return False
    scale = {"power": (1, 0), "toughness": (0, 1)}.get(m[1], (1, 1))
    st.extra.setdefault("advanced_rules", {})["cda_q"] = (spec, scale)
    return True


def late_line(line: str, st) -> bool:
    """After every face-line reader: a CDA line nobody read, with any _xq quantity (cards/parse.py hook)."""
    return _any_quantity(line, st)


def quantity_bonus(perm) -> tuple:
    """(power, toughness) from a ``cda_q`` quantity (0, 0 without one)."""
    q = perm.card.advanced_rules.get("cda_q")
    game = getattr(perm.controller, "_game", None)
    if not q or game is None:
        return 0, 0
    from types import SimpleNamespace
    spec, (sp, st) = q
    n = max(0, game.x_quantity(perm.controller, spec, SimpleNamespace(source=perm, card=perm.card, context=None,
                                                                      x=0), None))
    return sp * n, st * n


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if m is None or m[3].startswith("in the hand"):
        return False
    # The lazy noun match can swallow a second clause ("Elves you control plus the number of Elf cards"): those go
    # to the general quantity reader (late_line) instead of a garbled count that evaluates to 0 (#784).
    if re.search(r"\b(?:plus|minus|number|control|controls|battlefield|graveyards?|among)\b", m[2]) and \
            "watermark" not in m[2]:       # watermarks (Knight of the Widget): left as they are here, see #790
        return False
    what = re.sub(r"\bcards?\b", "", m[2]).strip().replace(" and ", " or ")
    what = " ".join(w[:-1] if w.endswith("s") and not w.endswith("ss") and w != "or" else w for w in what.split())
    if not what or " plus " in what or "chosen" in what:
        return False
    scope = {"you control": "mine", "on the battlefield": "all", "in your graveyard": "my_gy",
             "in all graveyards": "all_gy", "your opponents control": "opp"}[m[3]]
    st.extra["pt_cda"] = f"cx:{scope}:{'other ' if m[1] else ''}{what}"
    return True


def count(perm, spec: str) -> int:
    from .copies import fits
    _, scope, what = spec.split(":", 2)
    other = what.startswith("other ")
    what = what[6:] if other else what
    game = getattr(perm.controller, "_game", None)
    me = perm.controller
    players = game.players if game is not None else [me]
    named = what.startswith("differently named ")      # "the number of differently named lands you control"
    what = what[len("differently named "):] if named else what
    if scope in ("my_gy", "all_gy"):
        cards = [c for pl in players if scope == "all_gy" or pl is me for c in pl.graveyard if fits(c, what)]
    else:
        cards = [x.card for pl in players if scope == "all" or (pl is me) == (scope == "mine")
                 for x in pl.battlefield if not (other and x is perm) and fits(x.card, what, x)]
    return len({c.name for c in cards}) if named else len(cards)
