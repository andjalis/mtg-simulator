"""Combat declaration taxes, scoped to their actual defender and source condition.

Costs are combined for a declaration. Unaffordable proposals shed their last
creature, then recheck companion restrictions before trying again. Failed
payments roll back so a rejected declaration never spends mana or life.
"""
from __future__ import annotations

import itertools
import re

_PRICE = r"(?:\{(?:\d+|[WUBRGC](?:/P)?)\})+"
_ATTACK = r"attack (?:you(?: or planeswalkers you control)?|planeswalkers you control)"
_EACH = (r"for each of those creatures|for each creature they control that's attacking you|"
         r"for each creature they control that's attacking a planeswalker you control")
_STATIC = re.compile(rf"(?:As long as (.+?), )?[Cc]reatures can't ({_ATTACK}|block) "
                     rf"unless their controller pays ({_PRICE}) ({_EACH})\.")


def _cost(text):
    out = {}
    for pip in re.findall(r"\{([^}]+)\}", text):
        key, n = ("generic", int(pip)) if pip.isdigit() else (pip, 1)
        out[key] = out.get(key, 0) + n
    return out


def parse_line(line, st):
    variable = re.fullmatch(rf"[Cc]reatures can't ({_ATTACK}) unless their controller pays \{{X\}} "
                            rf"(?:{_EACH}), where X is the number of (enchantments you control|basic land types among lands you control)\.", line)
    counters = re.fullmatch(rf"Each creature with one or more counters on it can't ({_ATTACK}) unless its controller pays "
                            r"\{X\}, where X is the number of counters on that creature\.", line)
    if variable or counters:
        m = variable or counters
        scope = "both" if "you or" in m[1] else "planeswalker" if "attack planeswalkers" in m[1] else "player"
        quantity = "creature_counters" if counters else "enchantments" if variable[2].startswith("enchantments") else "domain"
        rules = st.extra.setdefault("advanced_rules", {})
        entry = ("attack", scope, {"generic": (quantity,)}, "")
        rules["cx_combat_taxes"] = rules.get("cx_combat_taxes", ()) + (entry,)
        return True
    m = _STATIC.fullmatch(line)
    if not m:
        return False
    from .cx_condlib import as_static
    cond = as_static(m[1]) if m[1] else ""
    if m[1] and not cond:
        return False
    what = "block" if m[2] == "block" else "attack"
    scope = "both" if "you or" in m[2] else "planeswalker" if "attack planeswalkers" in m[2] else "player"
    rules = st.extra.setdefault("advanced_rules", {})
    cost = _cost(m[3])
    if not cond and what == "attack" and scope in ("player", "both") and set(cost) == {"generic"}:
        rules["attack_tax"] = cost["generic"]
        if scope == "both":
            rules["attack_tax_planeswalkers"] = True
        return True
    entry = (what, scope, cost, cond)
    rules["cx_combat_taxes"] = rules.get("cx_combat_taxes", ()) + (entry,)
    return True


def _war_tax(m):
    from .cards import Effect
    return Effect("combat_tax", data={"x": True})


EFFECT_PATTERNS = [
    (r"this turn, creatures can't attack unless their controller pays \{x\} for each attacking creature they control",
     _war_tax),
]
SUBS = []


def add_temporary(game, amount):
    taxes = getattr(game, "combat_taxes", ())
    game.combat_taxes = [(turn, n) for turn, n in taxes if turn == game.turn] + [(game.turn, amount)]


def _add(total, cost):
    for pip, n in cost.items():
        total[pip] = total.get(pip, 0) + n


def _static_costs(game, creature, action, target=None):
    from .cx_condlib import holds_for
    from .engine.state import Player
    out = {}
    defender = target if isinstance(target, Player) else getattr(target, "controller", None)
    for p in game.players:
        for source in p.battlefield:
            if source.abilities_suppressed:
                continue
            for what, scope, cost, cond in source.card.advanced_rules.get("cx_combat_taxes", ()):
                if what != action or cond and not holds_for(source, cond):
                    continue
                if action == "attack":
                    if source.controller is not defender:
                        continue
                    if scope == "player" and target is not defender or scope == "planeswalker" and target is defender:
                        continue
                for pip, n in cost.items():
                    if isinstance(n, tuple):
                        if n[0] == "creature_counters":
                            n = sum(max(0, v) for v in creature.counters.values()) if creature is not None else 0
                        elif n[0] == "enchantments":
                            n = sum("Enchantment" in c.card.types for c in source.controller.battlefield)
                        elif n[0] == "domain":
                            n = game.x_quantity(source.controller, ("domain",), None, None)
                    _add(out, {pip: n})
    return out


def attack_cost(game, creature, target):
    from .cx_next_turn import flags, player_flag
    from .engine.state import Player
    defender = target if isinstance(target, Player) else target.controller
    if target is defender and player_flag(game, defender, "no_attack"):
        return None
    out = _static_costs(game, creature, "attack", target)
    # Preserve older parser outputs, including synthetic fixtures.
    for source in defender.battlefield:
        if not source.abilities_suppressed and (target is defender or source.card.advanced_rules.get("attack_tax_planeswalkers")):
            _add(out, {"generic": source.card.advanced_rules.get("attack_tax", 0)})
    for flag in flags(game, defender, "attack_tax"):
        if target is defender or flag.data.get("planeswalkers"):
            _add(out, {"generic": flag.amount})
    _add(out, {"generic": sum(n for turn, n in getattr(game, "combat_taxes", ()) if turn == game.turn)})
    return out


def _pay(game, player, total, creatures):
    if total is None:
        return False
    if not any(total.values()):
        return True
    from .actions import Transaction
    from .residual_templates import life_locked
    phyrexian = [(pip[0], n) for pip, n in total.items() if pip.endswith("/P")]
    mana = {pip: n for pip, n in total.items() if not pip.endswith("/P")}
    # Prefer mana to life; try all mixtures so generic costs don't strand a white pip.
    for life_pips in itertools.product(*(range(n + 1) for _, n in phyrexian)):
        life = 2 * sum(life_pips)
        if life and (life_locked(player) or player.life < life):
            continue
        cost = dict(mana)
        for (color, n), paid_life in zip(phyrexian, life_pips):
            _add(cost, {color: n - paid_life})
        with Transaction(game) as tx:
            if game.pay(player, cost, spell="combat", exclude_many=creatures) is None:
                continue
            if life and (life_locked(player) or player.life < life):
                continue
            if life:
                game.change_life(player, -life, "combat tax: paid life")
            tx.commit = True
            return True
    return False


def pay_attackers(game, player, attackers, targets):
    from .cx_static_combat import declaration_group
    group = declaration_group(attackers, "attack")
    while group:
        costs = [attack_cost(game, c, targets[c]) for c in group]
        total = {}
        for cost in costs:
            if cost is not None:
                _add(total, cost)
        if all(cost is not None for cost in costs) and _pay(game, player, total, group):
            return group
        group = declaration_group(group[:-1], "attack")
    return []


def pay_blockers(game, player, blocks):
    from .batch1_templates import drop_solo_blocks
    blocks = drop_solo_blocks(blocks)
    while blocks:
        creatures = list(dict.fromkeys(b for bl in blocks.values() for b in bl))
        total = {}
        for c in creatures:
            _add(total, _static_costs(game, c, "block"))
        if _pay(game, player, total, creatures):
            return blocks
        drop = creatures[-1]
        blocks = drop_solo_blocks({a: [b for b in bl if b is not drop] for a, bl in blocks.items()})
    return {}
