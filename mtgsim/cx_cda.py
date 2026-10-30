"""Characteristic-defining P/T counts: "~'s power and toughness are each equal to the number of creatures on the
battlefield" (Beast of Burden), "... creature cards in all graveyards" (Cruel Somnophage), "... other creatures you
control". The count is stored in ``pt_cda`` as ``cx:<scope>:<what>`` and evaluated by ``count``."""
from __future__ import annotations

import re

_LINE = re.compile(r"~'s power and toughness are each equal to the number of (other )?([\w -]+?) "
                   r"(you control|on the battlefield|in your graveyard|in all graveyards|your opponents control|"
                   r"in the hand of the opponent with the most cards in hand)\.")


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if m is None or m[3].startswith("in the hand"):
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
    if scope in ("my_gy", "all_gy"):
        return sum(fits(c, what) for pl in players if scope == "all_gy" or pl is me for c in pl.graveyard)
    return sum(1 for pl in players if scope == "all" or (pl is me) == (scope == "mine")
               for x in pl.battlefield if not (other and x is perm) and fits(x.card, what, x))
