"""Storage lands: lands that bank storage counters and later spend them as mana.

    {T}: Put a storage counter on ~.            {1}, {T}: Put a storage counter on ~.
    {T}, Remove any number of storage counters from ~: Add {W} for each storage counter removed this way.
    {1}, Remove X storage counters from ~: Add X mana in any combination of {W} and/or {U}.
    You may choose not to untap ~ during your untap step.
    At the beginning of your upkeep, if ~ is tapped, put a storage counter on it.

``parse_line`` records the parts in ``CardDef.storage``. A storage land with counters offers one mana of its
colors per counter (see ``stored_sources``) in place of its own mana: spending any of it taps the land, which
pays the {T} or, for the {1} kind, the {1} through its own {C}. Choices: a land that stayed untapped through the
opponent's turn banks a counter as their turn ends (it untaps right after, so this is free), and a land that may
stay tapped is untapped only when its stored mana lets its controller cast something they couldn't otherwise.
Crucible of the Spirit Dragon's mana pays only for Dragon spells (not abilities). Not parsed: City of Shadows.
"""
from __future__ import annotations

import dataclasses
import re

_COUNTER = "storage"
_HOLD = "You may choose not to untap ~ during your untap step."
_UPKEEP = "At the beginning of your upkeep, if ~ is tapped, put a storage counter on it."
_STORED: dict = {}


def parse_line(line: str, st) -> bool:
    from .cards.model import parse_mana_cost
    if "Land" not in st.types:                # "You may choose not to untap ~" on Amber Prison is not storage
        return False
    storage = st.extra.setdefault("storage", {})
    try:
        return _parse(line, storage, parse_mana_cost)
    finally:
        if not storage:
            del st.extra["storage"]


def _parse(line, storage, parse_mana_cost) -> bool:
    m = re.fullmatch(r"((?:\{\d+\}, )?)\{T\}: Put a storage counter on ~\.", line)
    if m:
        storage["bank"] = parse_mana_cost(m[1].rstrip(", ")) if m[1] else {}
        storage["bank_text"] = line
        return True
    m = re.fullmatch(r"\{T\}, Remove any number of storage counters from ~: Add \{([WUBRGC])\} for each storage counter "
                     r"removed this way\.", line)
    if m:
        storage["colors"] = frozenset({m[1]})
        return True
    m = re.fullmatch(r"\{1\}, Remove X storage counters from ~: Add X mana in any combination of \{([WUBRG])\} and/or "
                     r"\{([WUBRG])\}\.", line)
    if m:
        storage["colors"] = frozenset({m[1], m[2]})
        return True
    m = re.fullmatch(r"\{T\}, Remove X storage counters from ~: Add X mana in any combination of colors\. Spend this "
                     r"mana only to cast ([A-Z]\w+) spells or activate abilities of \1s\.", line)
    if m:                                     # Crucible of the Spirit Dragon: only for Dragon spells
        storage.update(colors=frozenset("WUBRG"), restriction=f"subtype:{m[1]}")
        return True
    if line == _HOLD:
        storage["hold"] = True
        return True
    if line == _UPKEEP:
        storage["upkeep"] = True
        return True
    return False


def finish(extra: dict, unsupported: list) -> None:
    """Holding a land tapped or banking counters means nothing without a way to spend them (Ice Floe)."""
    storage = extra.get("storage")
    if storage and not storage.get("colors"):
        unsupported += [_HOLD] if storage.get("hold") else []
        unsupported += [_UPKEEP] if storage.get("upkeep") else []
        unsupported += [storage["bank_text"]] if "bank_text" in storage else []
        del extra["storage"]


def _stored_mana(colors: frozenset):
    from .engine.state import FIREBEND_MANA
    if colors not in _STORED:
        _STORED[colors] = dataclasses.replace(FIREBEND_MANA, name="stored mana", produces=colors)
    return _STORED[colors]


def stored_sources(p, exclude=None, allowed=lambda restriction: True) -> list:
    """One mana per storage counter on p's untapped storage lands (each carries ``stored_in``). ``allowed`` says
    whether mana with a spending restriction ("subtype:Dragon") may pay for what is being paid for."""
    from .engine.state import Permanent
    out = []
    for perm in p.battlefield:
        colors = perm.card.storage.get("colors") if perm.card.storage else None
        restriction = perm.card.storage.get("restriction") if colors else None
        if restriction and not allowed(restriction):
            continue
        if colors and not perm.tapped and perm is not exclude and perm.counters.get(_COUNTER, 0) > 0:
            for _ in range(perm.counters[_COUNTER]):
                mana = Permanent(_stored_mana(colors), p)
                mana.stored_in, mana.produces_now = perm, colors
                out.append(mana)
    return out


def spend(source) -> None:
    """Pay with one stored mana: remove its counter and tap its land."""
    land = source.stored_in
    land.counters[_COUNTER] = max(0, land.counters.get(_COUNTER, 0) - 1)
    land.tapped = True


def before_untap(game, p) -> None:
    """Bank a counter on each storage land that stayed untapped through the opponent's turn."""
    for perm in list(p.battlefield):
        bank = perm.card.storage.get("bank") if perm.card.storage else None
        if bank is None or perm.tapped:
            continue
        if bank and game.pay(p, bank, exclude=perm) is None:
            continue
        perm.tapped = True
        perm.counters[_COUNTER] = perm.counters.get(_COUNTER, 0) + 1
        game.log(f"puts a storage counter on {perm.card.name} ({perm.counters[_COUNTER]})", p)


def keeps_tapped(game, p, perm) -> bool:
    """"You may choose not to untap ~": stay tapped (and bank) unless the stored mana makes a spell castable."""
    if not (perm.card.storage and perm.card.storage.get("hold")):
        return False
    stored = perm.counters.get(_COUNTER, 0)
    others = sum(1 for x in p.battlefield if x is not perm and x.card.is_land and (x.card.produces or x.card.storage))
    costs = [c.cmc for c in p.hand if not c.is_land]
    return not any(others < cmc <= others + stored for cmc in costs)


def upkeep(game, p) -> None:
    for perm in p.battlefield:
        if perm.card.storage and perm.card.storage.get("upkeep") and perm.tapped:
            perm.counters[_COUNTER] = perm.counters.get(_COUNTER, 0) + 1
            game.log(f"puts a storage counter on {perm.card.name} ({perm.counters[_COUNTER]})", p)
