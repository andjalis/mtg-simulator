"""Regeneration shields, damage prevention, upkeep payments and granted mana."""
from __future__ import annotations

import re

KINDS = {"regenerate", "prevent_damage", "fog", "no_prevention", "sac_unless", "grant_mana_turn", "no_regen_turn"}


def effect(kind, **kw):
    from .cards import Effect
    return Effect(kind, **kw)


def colors(text):
    return frozenset("WUBRG") if text.lower() == "one mana of any color" else frozenset(re.findall(r"[WUBRGC]", text))


EFFECT_PATTERNS = [
    (r"regenerate (~|target creature|target creature you control|target artifact|it|that creature)",
     lambda m: effect("regenerate", target={"~": "self", "it": "prev", "that creature": "prev",
                     "target creature": "creature", "target creature you control": "creature_mine",
                     "target artifact": "artifact"}[m[1].lower()])),
    (r"prevent the next (\d+) damage that would be dealt to (any target|target creature|~|you) this turn",
     lambda m: effect("prevent_damage", amount=int(m[1]), target={"any target": "any", "target creature": "creature",
                     "~": "self", "you": "none"}[m[2].lower()])),
    (r"prevent all (combat )?damage that would be dealt (?:to (~|target creature|target creature you control|you) )?this turn",
     lambda m: effect("prevent_damage" if m[2] else "fog", amount=-1,
                     target={None: "none", "~": "self", "target creature": "creature",
                             "target creature you control": "creature_mine", "you": "none"}[m[2].lower() if m[2] else None],
                     data={"combat": bool(m[1])})),
    (r"damage can't be prevented this turn", lambda m: effect("no_prevention")),
    (r"destroy target (nonbasic )?land( an opponent controls| you control)?",
     lambda m: effect("destroy", target="land", data={"nonbasic": bool(m[1]),
                     "controller": (m[2] or "").strip()})),
    (r"sacrifice ~ unless you pay ((?:\{[0-9WUBRGC]+\})+)",
     lambda m: _upkeep(m[1])),
    (r"(target creature|target land|~|it) gains? \"\{T\}: Add (one mana of any color|\{[WUBRGC]\})\.\"( until end of turn)?",
     lambda m: effect("grant_mana_turn", target={"target creature": "creature", "target land": "land",
                      "~": "self", "it": "prev"}[m[1].lower()], data={"colors": colors(m[2]), "permanent": not bool(m[3])})),
    (r"(?:it|that creature) can't be regenerated this turn", lambda m: effect("no_regen_turn", target="prev")),
]


def _upkeep(cost):
    from .cards import parse_mana_cost
    return effect("sac_unless", target="self", data={"cost": parse_mana_cost(cost)})


def parse_line(line, extra):
    """Static quoted mana grants on an Aura or on the permanent itself."""
    m = re.fullmatch(r'(Enchanted (?:creature|land|permanent)|Equipped creature|~) has "\{T\}: Add (one mana of any color|\{[WUBRGC]\})\."', line)
    if not m:
        return False
    scope = "self" if m[1] == "~" else "equipped" if m[1] == "Equipped creature" else "enchanted"
    if scope == "enchanted" and not extra.get("aura"):
        return False
    extra["grant_mana"] = extra.get("grant_mana", ()) + ((scope, colors(m[2])),)
    return True


def granted_mana(perm):
    out = frozenset()
    for player in (perm.controller, perm.controller.foe):
        if player is None:
            continue
        for src in player.battlefield:
            for scope, cols in src.card.grant_mana:
                if scope == "self" and src is perm or scope == "enchanted" and src.aura_host is perm or scope == "equipped" and src.attached_to is perm:
                    out |= cols
    game = getattr(perm, "_mana_game", None)
    if game is not None:
        for turn, cols in getattr(perm, "mana_grants", ()):
            if turn is None or turn == game.turn:
                out |= cols
    return out


def land_fits(eff, perm, by):
    from .engine import is_basic_land
    ctl = eff.data.get("controller")
    return (perm.card.is_land and (not eff.data.get("nonbasic") or not is_basic_land(perm.card))
            and (ctl != "an opponent controls" or perm.controller is not by)
            and (ctl != "you control" or perm.controller is by))


def resolve(game, p, eff, target, item):
    from .engine import Permanent
    k = eff.kind
    present = isinstance(target, Permanent) and target in target.controller.battlefield
    if k == "regenerate" and present:
        if getattr(target, "regen_turn", -1) != game.turn:
            target.regen_shields = 0
        target.regen_turn = game.turn
        target.regen_shields = getattr(target, "regen_shields", 0) + 1
    elif k == "no_regen_turn" and present:
        target.no_regen_turn = game.turn
    elif k in ("prevent_damage", "fog"):
        if eff.target == "none":
            target = None if k == "fog" else p
        shields = getattr(game, "damage_shields", [])
        shields.append([game.turn, target, eff.amount, eff.data.get("combat", False)])
        game.damage_shields = shields
    elif k == "no_prevention":
        game.no_prevention_turn = game.turn
    elif k == "sac_unless" and present:
        payer = p
        cost = eff.data["cost"]
        if game.can_pay(payer, cost, spell="ability") and game.hook(payer, "pay_optional")(game, payer, cost, "upkeep"):
            game.pay(payer, cost, spell="ability")
        elif target.controller is p:
            game.sacrifice(target)
    elif k == "grant_mana_turn" and present:
        target._mana_game = game
        target.mana_grants = getattr(target, "mana_grants", []) + [(None if eff.data.get("permanent") else game.turn, eff.data["colors"])]


def regenerate(game, perm):
    """Replace one destruction, including lethal damage. Sacrifice never calls this."""
    if (getattr(perm, "regen_turn", -1) != game.turn or not getattr(perm, "regen_shields", 0)
            or getattr(perm, "no_regen_turn", -1) == game.turn):
        return False
    perm.regen_shields -= 1
    perm.tapped = True
    perm.damage = 0
    perm.deathtouched = False
    if perm in game.attackers:
        game.attackers.remove(perm)
    # Keep a blocked attacker's entry even when its last blocker leaves combat.
    game.blocks.pop(perm, None)
    for blockers in game.blocks.values():
        if perm in blockers:
            blockers.remove(perm)
    game.log(f"regenerates {perm.card.name}", perm.controller)
    return True


def prevent(game, target, amount, combat=False):
    if getattr(game, "no_prevention_turn", -1) == game.turn:
        return amount
    for shield in getattr(game, "damage_shields", ()):
        turn, obj, left, combat_only = shield
        if turn != game.turn or (obj is not None and obj is not target) or combat_only and not combat:
            continue
        used = amount if left == -1 else min(amount, left)
        amount -= used
        if left != -1:
            shield[2] -= used
        if amount == 0:
            break
    return amount


def choose(game, me, eff):
    from .engine import Permanent, perm_value
    mine = [x for x in game.legal_targets(me, eff) if isinstance(x, Permanent) and x.controller is me]
    return max(mine, key=perm_value, default=me if eff.target == "any" else None)


def worth(game, me, perm, effects):
    """Minimal policy: protect threatened objects; never loop a free shield activation."""
    from .engine import Permanent
    for eff in effects:
        if eff.kind not in ("regenerate", "prevent_damage", "fog"):
            continue
        if eff.kind == "fog":
            if game.step != "declare_blockers" or game.active is me or not game.attackers:
                return False
            continue
        tgt = perm if eff.target == "self" else me if eff.target == "none" else choose(game, me, eff)
        if eff.kind == "regenerate" and (not isinstance(tgt, Permanent) or
                getattr(tgt, "regen_turn", -1) == game.turn and getattr(tgt, "regen_shields", 0)):
            return False
        if eff.kind == "prevent_damage" and any(s[0] == game.turn and s[1] is tgt and s[2] for s in getattr(game, "damage_shields", ())):
            return False
        threatened = any(t is tgt and e.kind in ("damage", "destroy") and not e.data.get("no_regen")
                         for stack in game.stack for e, t in zip(stack.effects, stack.targets))
        combat = game.step == "declare_blockers" and (tgt in game.attackers or
                    any(tgt in bs for bs in game.blocks.values()))
        if not threatened and not combat:
            return False
    return True


def respond(game, me):
    """Fallback priority actions so the new shields can actually be used by existing AIs."""
    from .engine import Permanent
    if game.stack and game.stack[-1].controller is me:
        return None
    for perm in me.battlefield:
        for i, act in enumerate(perm.card.activated):
            if act.kind == "ability" and any(e.kind in ("regenerate", "prevent_damage", "fog") for e in act.effects):
                if game.can_activate(me, perm, i) and worth(game, me, perm, act.effects):
                    return ("activate", perm, f"ability:{i}")
    for card in game.spell_options(me):
        if not card.instant_speed or not game.can_cast_now(me, card):
            continue
        protection = [e for e in card.spell_effects if e.kind in ("regenerate", "prevent_damage", "fog")]
        if not protection:
            continue
        if game.stack:
            for e, tgt in zip(game.stack[-1].effects, game.stack[-1].targets):
                if e.kind not in ("damage", "destroy") or getattr(tgt, "controller", tgt) is not me:
                    continue
                for shield in protection:
                    if shield.kind == "regenerate" and (e.kind != "destroy" and e.kind != "damage" or e.data.get("no_regen")):
                        continue
                    if shield.kind == "prevent_damage" and e.kind != "damage":
                        continue
                    if shield.kind == "fog" or tgt not in game.legal_targets(me, shield):
                        continue
                    targets = game.auto_targets(me, card.spell_effects)
                    targets[card.spell_effects.index(shield)] = tgt
                    return card, targets
        elif game.step == "declare_blockers" and game.active is not me and game.attackers:
            if any(e.kind == "fog" for e in protection):
                return card, game.auto_targets(me, card.spell_effects)
    return None


def approximations(text):
    """Don't promote old, loose removal templates to full support by adding their rider."""
    if "can't be regenerated" not in text.lower():
        return []
    out = []
    for m in re.finditer(r'destroy target ((?:[\w-]+,? )+)creature', text, re.I):
        restriction = m[1].strip().lower()
        if restriction not in ('tapped', 'untapped', 'attacking or blocking', 'nonartifact'):
            out.append(f"destroy restriction not enforced: {restriction}")
    return out
