"""Aura and equipment statics: "You control enchanted permanent." and "... and is goaded.", plus "You have shroud."

* "You control enchanted permanent." (Confiscate, Lay Claim, Take Possession): the same ``aura_control`` rule the
  creature version uses; the engine's control machinery already works for any host.
* "Enchanted/Equipped creature gets +N/+M[, has KW,] and is goaded." (the Impetus Auras, Bloodthirsty Blade): goad is
  read as "attacks each combat if able", since the rider "attacks a player other than you if able" only matters in
  games with three or more players, which this simulator does not play. The line is rewritten and handed on."""
from __future__ import annotations

import re

_GOADED = re.compile(r"((?:Enchanted|Equipped) creature (?:gets [+-]\d+/[+-]\d+.*?)),? and is goaded\.")


def parse_line(st, line: str):
    """Face-line handler: returns None once the line is handled, else the (possibly rewritten) line."""
    if line == "You have shroud.":                  # Ivory Mask, True Believer: nothing can target you, even you
        st.extra.setdefault("advanced_rules", {})["player_shroud"] = True
        return None
    if line == "You control enchanted permanent.":
        st.extra.setdefault("advanced_rules", {})["aura_control"] = True
        return None
    m = _GOADED.fullmatch(line)
    if m:
        head = re.sub(r", has ", " and has ", m[1], count=1)
        return f"{head} and attacks each combat if able."
    return line
