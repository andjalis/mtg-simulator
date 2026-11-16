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


_OWN = re.compile(rf"(?:[A-Z][\w' ]* — )?(~|Enchanted creature) can't (attack|block|attack or block) unless "
                  rf"(you pay|its controller pays) ({_PRICE})( for each \+1/\+1 counter on it| for each card in your hand)?\.")


def _own_cost(line, st):
    """"~ can't attack or block unless you pay {2}." / "Enchanted creature can't attack unless its controller pays
    {3}." (#325): a price the creature's controller pays when declaring it, recorded as
    ``advanced_rules["cx_own_combat_cost"]`` (or ``"cx_own_combat_cost@host"`` on an Aura): ((what, cost), ...)."""
    m = _OWN.fullmatch(line)
    if not m or (m[1] == "~") != (m[3] == "you pay") or m[1] == "~" and "Creature" not in st.types \
            or m[1] != "~" and not st.extra.get("aura") or m[1] == "~" and m[5] and "your hand" in m[5]:
        return False
    cost = _cost(m[4])
    if m[5]:
        if set(cost) != {"generic"}:
            return False
        cost = {"generic": ("p1_counters", cost["generic"]) if "counter" in m[5] else ("source_hand", cost["generic"])}
    what = {"attack": "attack", "block": "block"}.get(m[2], "both")
    key = "cx_own_combat_cost" + ("" if m[1] == "~" else "@host")
    rules = st.extra.setdefault("advanced_rules", {})
    rules[key] = rules.get(key, ()) + ((what, cost),)
    if m[1] != "~":
        st.extra["gate_hostile"] = True         # a pacifism-like Aura: auras.finish puts it on their creature
    return True


_ACT_LABEL = r"(?:[A-Z][\w' ]* — )?"
_ACT = re.compile(rf"{_ACT_LABEL}~ can't (attack|block|attack or block) unless you (sacrifice|return|tap) "
                  r"(an? (?:untapped )?[\w -]+?)( you control)?( to its owner's hand)?"
                  r"( not declared as an attacking or blocking creature this combat)?\.")
_GROUP_ACT = re.compile(r"(White|Blue|Black|Red|Green) creatures can't attack unless their controller sacrifices a "
                        r"land of their choice for each (white|blue|black|red|green) creature they control that's "
                        r"attacking\.")


def _own_action(line, st):
    """Non-mana prices to declare a creature (#325 slice 2), recorded as ``advanced_rules["cx_own_combat_action"]``
    ((what, (kind, spec)), ...) with kind "sacrifice", "bounce" or "tap" and spec a cx_condlib filter:

        ~ can't attack unless you sacrifice a land.                                          (Exalted Dragon)
        ~ can't attack unless you return an enchantment you control to its owner's hand.     (Floodtide Serpent)
        ~ can't attack or block unless you tap an untapped creature you control not declared as an attacking or
        blocking creature this combat.                                                      (Hollow Warrior)
    and the group form "Green creatures can't attack unless their controller sacrifices a land of their choice for
    each green creature they control that's attacking." (``"cx_combat_action@group"``: (color, what, action))."""
    from .cx_condlib import _filter
    g = _GROUP_ACT.fullmatch(line)
    if g:
        if g[1].lower() != g[2]:
            return False
        rules = st.extra.setdefault("advanced_rules", {})
        color = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}[g[2]]
        rules["cx_combat_action@group"] = rules.get("cx_combat_action@group", ()) + (
            (color, "attack", ("sacrifice", {"types": ["land"]})),)
        return True
    m = _ACT.fullmatch(line)
    if not m or "Creature" not in st.types:
        return False
    verb, noun, yours, hand, undeclared = m[2], m[3], m[4], m[5], m[6]
    if (verb == "return") != bool(hand) or (verb == "tap") != bool(undeclared and yours and "untapped" in noun) \
            or verb == "tap" and m[1] != "attack or block" or verb == "sacrifice" and (yours or hand):
        return False
    spec = _filter(re.sub(r"^an? (?:untapped )?", "", noun), plural=False)
    if spec is None:
        return False
    kind = {"sacrifice": "sacrifice", "return": "bounce", "tap": "tap"}[verb]
    what = {"attack": "attack", "block": "block"}.get(m[1], "both")
    rules = st.extra.setdefault("advanced_rules", {})
    rules["cx_own_combat_action"] = rules.get("cx_own_combat_action", ()) + ((what, (kind, spec)),)
    return True


def parse_line(line, st):
    if _own_cost(line, st) or _own_action(line, st):
        return True
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
    if creature is not None:
        _add(out, own_cost(creature, action))
    return out


def own_cost(creature, action) -> dict:
    """The price creature's own static or its Aura's asks to declare it as an attacker / blocker (#325)."""
    out = {}
    rows = [] if creature.abilities_suppressed else \
        [(creature, r) for r in creature.card.advanced_rules.get("cx_own_combat_cost", ())]
    rows += [(a, r) for a in creature.auras if not a.abilities_suppressed
             for r in a.card.advanced_rules.get("cx_own_combat_cost@host", ())]
    for source, (what, cost) in rows:
        if what not in (action, "both"):
            continue
        for pip, n in cost.items():
            if isinstance(n, tuple):
                n = n[1] * (creature.counters.get("+1/+1", 0) if n[0] == "p1_counters"
                            else len(source.controller.hand))
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
        chosen = _choose_actions(game, player, group, "attack")
        if all(cost is not None for cost in costs) and chosen is not None and _pay(game, player, total, group):
            _do_actions(game, player, chosen)
            return group
        group = declaration_group(group[:-1], "attack")
    return []


def own_actions(game, creature, action) -> list:
    """The non-mana prices (kind, spec) to declare creature as an attacker / blocker."""
    out = []
    if not creature.abilities_suppressed:
        out += [a for what, a in creature.card.advanced_rules.get("cx_own_combat_action", ())
                if what in (action, "both")]
    for p in game.players:
        for source in p.battlefield:
            if source.abilities_suppressed or not source.card.advanced_rules:
                continue
            for color, what, a in source.card.advanced_rules.get("cx_combat_action@group", ()):
                if what == action and color in creature.card.colors and creature.is_creature:
                    out.append(a)
    return out


def _choose_actions(game, player, group, action):
    """[(kind, permanent)] paying every declared creature's non-mana price with distinct permanents (the least
    valuable ones; never one of the declared creatures), or None when they can't all be paid."""
    from .cx_condlib import _card_ok
    from .engine.policy import perm_value
    used, out = set(), []
    for c in group:
        for kind, spec in own_actions(game, c, action):
            pool = [x for x in player.battlefield if id(x) not in used and x not in group and _card_ok(x.card, spec, x)
                    and (kind != "tap" or not x.tapped and x.is_creature)]
            if not pool:
                return None
            pick = min(pool, key=lambda x: (perm_value(x), not x.tapped))
            used.add(id(pick))
            out.append((kind, pick))
    return out


def _do_actions(game, player, chosen):
    for kind, perm in chosen:
        if perm not in player.battlefield:
            continue
        if kind == "sacrifice":
            game.sacrifice(perm)
        elif kind == "bounce":
            game.leave_battlefield(perm, "hand")
        else:
            perm.tapped = True
        game.log(f"pays a declaration cost: {kind} {perm.card.name}", player)


def pay_blockers(game, player, blocks):
    from .batch1_templates import drop_solo_blocks
    blocks = drop_solo_blocks(blocks)
    while blocks:
        creatures = list(dict.fromkeys(b for bl in blocks.values() for b in bl))
        total = {}
        for c in creatures:
            _add(total, _static_costs(game, c, "block"))
        chosen = _choose_actions(game, player, creatures, "block")
        if chosen is not None and _pay(game, player, total, creatures):
            _do_actions(game, player, chosen)
            return blocks
        drop = creatures[-1]
        blocks = drop_solo_blocks({a: [b for b in bl if b is not drop] for a, bl in blocks.items()})
    return {}
