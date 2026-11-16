"""#646: Ward with costs other than mana, a fixed life payment or one discard (CR 702.21).

    Ward—Pay life equal to ~'s power.                                  {"life_power": True}
    Ward—Sacrifice a creature. / a legendary artifact or legendary creature. / a permanent with mana value 1 or
        greater.                                                       {"sacrifice": "<what>"}
    Ward—Get five poison counters.                                     {"poison": 5}
    Ward—Discard a card or pay {2}.                                    {"discard_or": 2}
    Ward—Collect evidence 4.                                           {"evidence": 4}

CR 702.21a: "Whenever this permanent becomes the target of a spell or ability an opponent controls, counter it unless
that player pays [cost]." The cost is ``advanced_rules["ward_cost"]``; the ward trigger (stack.py) is the usual
"counter unless" Effect carrying the spec and the warded permanent, and Game.counter asks ``pay`` here before it
counters. A cost that depends on the permanent (its power) is read as the trigger resolves, from the permanent or its
last known information.

The paying player's choice (the default AI): only when the targeting spell is worth it (the engine's ``pay_unless``
hook) and the cost is affordable (life above a margin, poison below 8 afterwards, its least valuable permanent).
"""
from __future__ import annotations

import re

_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def parse_line(line: str, st) -> bool:
    m = re.fullmatch(r"Ward—(.+)\.", line.strip())
    if not m:
        return False
    body, spec = m[1], None
    if re.fullmatch(r"Pay life equal to (?:~|this creature)'s power", body):
        spec = {"life_power": True}
    elif (k := re.fullmatch(r"Sacrifice an? (.+)", body)):
        from .permanent_templates import selector
        if selector(k[1]) is not None:
            spec = {"sacrifice": k[1]}
    elif (k := re.fullmatch(r"Get (one|two|three|four|five|six|\d+) poison counters?", body)):
        spec = {"poison": _N.get(k[1]) or int(k[1])}
    elif (k := re.fullmatch(r"Discard a card or pay \{(\d+)\}", body)):
        spec = {"discard_or": int(k[1])}
    elif (k := re.fullmatch(r"Collect evidence (\d+)", body)):
        spec = {"evidence": int(k[1])}
    if spec is None:
        return False
    st.extra.setdefault("advanced_rules", {})["ward_cost"] = spec
    return True


def pay(game, payer, spec, warded, target) -> bool:
    """Whether payer pays the ward cost for target (and pays it); False lets the ward counter it."""
    from .engine.policy import perm_value
    from .residual_templates import life_locked
    if not game.hook(payer, "pay_unless")(game, payer, 0, target):
        return False
    if spec.get("life_power"):
        n = max(0, getattr(warded, "power", 0) or 0)
        if n and (life_locked(payer) or payer.life <= n + 2):
            return False
        game.change_life(payer, -n, f"ward: pay {n} life")
        return True
    if spec.get("sacrifice"):
        pool = game.sacrifice_candidates(payer, None, spec["sacrifice"])
        if not pool:
            return False
        victim = min(pool, key=perm_value)
        game.log(f"sacrifices {victim.card.name} for ward", payer)
        game.sacrifice(victim)
        return True
    if spec.get("poison"):
        have = payer.counters.get("poison", 0)
        if have + spec["poison"] >= 8:
            return False
        payer.counters["poison"] = have + spec["poison"]
        game.log(f"gets {spec['poison']} poison counters for ward", payer)
        return True
    if spec.get("discard_or") is not None:
        cost = {"generic": spec["discard_or"]}
        if game.can_pay(payer, cost) and game.pay(payer, cost) is not None:
            game.log(f"pays {spec['discard_or']} for ward", payer)
            return True
        if payer.hand:
            card = payer.ai.choose_discard(game, payer)
            if card in payer.hand:
                game.discard_card(payer, card)
                game.log(f"discards {card.name} for ward", payer)
                return True
        return False
    if spec.get("evidence"):
        need = spec["evidence"]
        if sum(c.cmc for c in payer.graveyard) < need:
            return False
        total = 0
        for c in sorted(payer.graveyard, key=lambda c: -c.cmc):
            if total >= need:
                break
            game.move_card(c, payer.graveyard, payer.exile, reason="cost")
            total += c.cmc
        game.log(f"collects evidence {need} for ward", payer)
        return True
    return False


def ai_payable(game, by, spec, warded, card=None) -> bool:
    """HeuristicAI's targeting check (ai._ward_payable): would ``by`` be able and willing to pay this ward cost?"""
    if spec.get("life_power"):
        n = max(0, getattr(warded, "power", 0) or 0)
        return by.life > n + 3
    if spec.get("sacrifice"):
        return bool(game.sacrifice_candidates(by, None, spec["sacrifice"]))
    if spec.get("poison"):
        return by.counters.get("poison", 0) + spec["poison"] < 8
    if spec.get("discard_or") is not None:
        return len(by.hand) > (1 if card is not None and card in by.hand else 0) or \
            game.can_pay(by, {"generic": spec["discard_or"]})
    if spec.get("evidence"):
        return sum(c.cmc for c in by.graveyard) >= spec["evidence"]
    return False
