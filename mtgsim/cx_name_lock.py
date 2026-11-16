"""Name locks (#627): the card name a permanent chooses as it enters (Meddling Mage, Nevermore, Disruptor Flute), and
"Spells with the chosen name cost {N} more to cast" (Disruptor Flute).

The name comes from public information only: the opponent's cards on the battlefield, in their graveyard and in exile
(spells they have cast, permanents they have played), each copy weighted by how threatening it is (mana value + 1, a
creature also by its power). Their hand, library and decklist are never read. Nothing public yet: no name (the lock
waits idle), which is deterministic. Ties go to the alphabetically first name.
"""
from __future__ import annotations

import re
from collections import Counter

_TAX = re.compile(r"Spells with the chosen name cost \{(\d+)\} more to cast\.")


def lock_name(game, p, nonland: bool = True) -> str:
    """The nonland card name p locks, from the opponent's public cards."""
    opp = game.opponent(p)
    weights: Counter = Counter()
    cards = list(opp.graveyard) + list(opp.exile) + [x.card for x in opp.battlefield if not x.card.is_token]
    for c in cards:
        if nonland and c.is_land:
            continue
        weights[c.name] += 1 + (c.cmc or 0) + (max(0, c.power or 0) if c.is_creature else 0)
    return min(weights, key=lambda n: (-weights[n], n)) if weights else ""


def parse_line(line: str, st) -> bool:
    """"Spells with the chosen name cost {N} more to cast." on a card that chooses a name as it enters."""
    m = _TAX.fullmatch(line.strip())
    if m is None or not any(t.event == "etb" and any(e.kind == "choose_name" for e in t.effects)
                            for t in getattr(st, "triggers", ())):
        return False
    st.extra.setdefault("advanced_rules", {})["named_tax"] = int(m[1])
    return True


def named_tax(game, card) -> int:
    """Generic mana a spell named like a lock's chosen name costs more (Game.cost_of)."""
    name = getattr(card, "name", "")
    return sum(x.card.advanced_rules.get("named_tax", 0) for pl in game.players for x in pl.battlefield
               if name and x.chosen_name == name and not x.abilities_suppressed) if name else 0
