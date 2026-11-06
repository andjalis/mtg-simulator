"""Aura and equipment statics: "You control enchanted permanent." and "... and is goaded.", plus "You have shroud." and "You may cast sorcery spells as though they had flash."

* "You control enchanted permanent." (Confiscate, Lay Claim, Take Possession): the same ``aura_control`` rule the
  creature version uses; the engine's control machinery already works for any host.
* "Enchanted/Equipped creature gets +N/+M[, has KW,] and is goaded." (the Impetus Auras, Bloodthirsty Blade): goad is
  read as "attacks each combat if able", since the rider "attacks a player other than you if able" only matters in
  games with three or more players, which this simulator does not play. The line is rewritten and handed on."""
from __future__ import annotations

import re

_GOADED = re.compile(r"((?:Enchanted|Equipped) creature (?:gets [+-]\d+/[+-]\d+.*?)),? and is goaded\.")

# "Creatures you control get +1/+1 until end of turn. Untap them." (Rallying Roar): "them" is those creatures. Only that
# shape is rewritten; Great Oak Guardian and Leo's Guidance use "them" for other creatures.
_UNTAP_THEM = re.compile(r"((?:^|[.,] )[Cc]reatures you control [^.]*?)\. Untap them\.")


def parse_line(st, line: str):
    """Face-line handler: returns None once the line is handled, else the (possibly rewritten) line."""
    if line == "You have shroud.":                  # Ivory Mask, True Believer: nothing can target you, even you
        st.extra.setdefault("advanced_rules", {})["player_shroud"] = True
        return None
    if line.startswith("You may cast spells as though they had flash."):          # Vedalken Orrery, Leyline of Anticipation
        st.extra.setdefault("advanced_rules", {})["spells_flash"] = True
        return None
    if line.startswith("You may cast sorcery spells as though they had flash."):     # Gandalf, Hypersonic Dragon
        st.extra.setdefault("advanced_rules", {})["sorcery_flash"] = True
        return None
    if line == "You can't lose the game and your opponents can't win the game.":      # Platinum Angel
        st.extra.setdefault("advanced_rules", {})["cant_lose"] = True
        return None
    if line == "You control enchanted permanent.":
        st.extra.setdefault("advanced_rules", {})["aura_control"] = True
        return None
    if "Untap them." in line:        # "Creatures you control get +1/+1 until end of turn. Untap them."
        line = _UNTAP_THEM.sub(lambda m: f"{m[1]}. Untap all creatures you control.", line)
    m = _GOADED.fullmatch(line)
    if m:
        head = re.sub(r", has ", " and has ", m[1], count=1)
        return f"{head} and attacks each combat if able."
    return line


def cant_lose(game, player) -> bool:
    """True while a permanent says its controller can't lose the game (Platinum Angel)."""
    from .residual_templates import sources
    return any(x.controller is player for x in sources(game, "cant_lose"))
