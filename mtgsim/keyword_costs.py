"""#646: Echo and Buyback with costs that aren't mana.

    Echo—Discard a card.             (Deepcavern Imp, Rakdos Headliner)     echo_cost ("discard", 1, 1)
    Echo—Sacrifice two lands.        (Skizzik Surger)                       echo_cost ("sac", "land", 2)
    Buyback—Pay 4 life.              (Slaughter)                            AltCost("buyback", {}, life=4)

Echo (CR 702.30a): "At the beginning of your upkeep, if this came under your control since the beginning of your last
upkeep, sacrifice it unless you pay [cost]." The card keeps an empty mana echo (so creature_keywords queues the echo
trigger as for any echo card) and ``advanced_rules["echo_cost"]``; the trigger pays it with cumulative_costs.pay (the
same payments and default-AI rules, done ``n`` times) or sacrifices the permanent.

Buyback (CR 702.27a): an additional cost; if it was paid, the spell goes to its owner's hand as it resolves. "Pay N
life" is the variant's life (Game.cast pays alt.life); the existing buyback variant adds no mana.
"""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "two": 2, "three": 3}


def parse_line(line: str, st) -> bool:
    s = line.strip()
    m = re.fullmatch(r"Echo—(.+)\.", s)
    if m:
        body, cost = m[1], None
        if body == "Discard a card":
            cost = ("discard", 1, 1)
        elif (k := re.fullmatch(r"Sacrifice (a|an|two|three) (lands?|creatures?)", body)):
            n = _N[k[1]]
            if (n == 1) == (not k[2].endswith("s")):
                cost = ("sac", k[2].rstrip("s"), n)
        if cost is None:
            return False
        st.extra["echo"] = {"generic": 0}
        st.extra.setdefault("advanced_rules", {})["echo_cost"] = cost
        return True
    m = re.fullmatch(r"Buyback—Pay (\d+) life\.", s)
    if m:
        from .cards.model import AltCost
        st.alt_costs.append(AltCost("buyback", {"generic": 0}, life=int(m[1])))
        return True
    return False


def pay_echo(game, p, perm) -> bool:
    """Pay perm's non-mana echo (True), or decline (False: the caller sacrifices it)."""
    from .cumulative_costs import pay
    kind, data, n = perm.card.advanced_rules["echo_cost"]
    return pay(game, p, perm, kind, data, n)
