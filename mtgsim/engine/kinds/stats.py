"""Creature stats and state: pump, counters, keywords, tapping, combat restrictions."""
from __future__ import annotations

from ... import protection
from ..policy import default_choose_target, perm_value
from ..state import Permanent, Player, StackItem
from . import kind


@kind("proliferate")
def proliferate(game, p, eff, **_):
    for _ in range(eff.amount):
        game.proliferate(p)


@kind("equip")
def equip(game, p, eff, target, item, **_):
    equipment = item.source if item is not None else None
    if equipment is not None and equipment in equipment.controller.battlefield and \
            "Equipment" in equipment.card.subtypes and not equipment.is_creature and \
            isinstance(target, Permanent) and game.legal_target(p, eff, target) and target is not equipment:
        equipment.attached_to = target
        game.log(f"equips {equipment.card.name} to {target.card.name}", p)


@kind("attach_new_equipment")
def attach_new_equipment(game, p, target, **_):
    """"When you do, attach it to target creature you control": the Equipment token just created."""
    new = [x for x in p.battlefield if x.card.is_token and "Equipment" in x.card.subtypes and x.attached_to is None]
    if new and isinstance(target, Permanent) and target in p.battlefield and target.is_creature:
        new[-1].attached_to = target
        game.log(f"attaches {new[-1].card.name} to {target.card.name}", p)


@kind("gear_up")
def gear_up(game, p, eff, target, **_):
    """"Attach (any number of) target Equipment you control to target creature you control": all of them, or the
    best one not already on it."""
    if not isinstance(target, Permanent) or target not in p.battlefield or not target.is_creature:
        return
    gear = [x for x in p.battlefield if "Equipment" in x.card.subtypes and not x.is_creature and x.attached_to is not target]
    if not eff.data.get("all"):
        gear = sorted(gear, key=lambda x: sum(x.card.equip_bonus), reverse=True)[:1]
    for x in gear:
        x.attached_to = target
        game.log(f"attaches {x.card.name} to {target.card.name}", p)


@kind("hone")
def hone(game, p, **_):
    """Dwalin: a hone counter on each Equipment you control (+1/+0 each to the equipped creature)."""
    for x in p.battlefield:
        if "Equipment" in x.card.subtypes:
            x.counters["hone"] = x.counters.get("hone", 0) + 1


@kind("pump")
def pump(game, eff, target, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        target.pump_p += eff.amount
        target.pump_t += eff.amount2
        if eff.data.get("keyword"):
            target.temp_kw.add(eff.data["keyword"])


@kind("prevent_next")
def prevent_next(game, p, eff, target, **_):
    """A damage shield until end of turn; "you" (target none) shields the controller."""
    who = p if eff.target == "none" else target
    if isinstance(who, (Permanent, Player)):
        who.prevent_next += eff.amount


@kind("monstrosity")
def monstrosity(game, p, eff, item, **_):
    """If the source isn't monstrous, put N +1/+1 counters on it; it becomes monstrous."""
    src = item.source if item is not None else None
    if isinstance(src, Permanent) and src in p.battlefield and not getattr(src, "monstrous", False):
        src.counters["+1/+1"] = src.p1 + eff.amount
        src.monstrous = True
        game.fire(p, "monstrous", src)


@kind("self_damage")
def self_damage(game, target, **_):
    if isinstance(target, Permanent) and target.power > 0:
        game.deal_damage(target, target.power, by=target.controller, source=target)


@kind("bolster")
def bolster(game, p, eff, **_):
    """Put N +1/+1 counters on the creature you control with the least toughness."""
    if p.creatures:
        pick = min(p.creatures, key=lambda c: (c.toughness, -perm_value(c)))
        pick.counters["+1/+1"] = pick.p1 + eff.amount


@kind("support")
def support(game, p, eff, item, **_):
    """A +1/+1 counter on each of up to N other creatures (your best ones)."""
    src = item.source if item is not None else None
    for c in sorted((c for c in p.creatures if c is not src), key=perm_value, reverse=True)[:eff.amount]:
        c.counters["+1/+1"] = c.p1 + 1


@kind("fog")
def fog(game, p, eff, **_):
    """Prevent all combat damage this turn (or only that of creatures p's opponents control)."""
    game.fog = (game.turn, game.opponent(p) if eff.data.get("theirs") else None)


@kind("skip_untap")
def skip_untap(game, target, **_):
    if isinstance(target, Permanent):
        target.skip_untap = max(target.skip_untap, 1)


@kind("flanking")
def flanking(game, item, **_):
    """Each creature without flanking blocking the source gets -1/-1 until end of turn."""
    src = item.source if item is not None else None
    for blocker in game.blocks.get(src, ()):
        if not blocker.has("flanking"):
            blocker.pump_p -= 1
            blocker.pump_t -= 1


@kind("debuff")
def debuff(game, p, eff, opp, **_):
    victims = opp.creatures if eff.target == "opp_creatures" else p.creatures + opp.creatures
    for perm in victims:
        perm.pump_p -= eff.amount
        perm.pump_t -= eff.amount2


@kind("debuff_one")
def debuff_one(game, eff, target, **_):
    if isinstance(target, Permanent):
        target.pump_p -= eff.amount
        target.pump_t -= eff.amount2


@kind("p1_counters")
def p1_counters(game, p, eff, target, item, **_):
    if eff.target == 'my_creatures':
        src = item.source if item is not None else None
        n = len(p.hand) if eff.data.get("x") == "hand" else eff.amount
        only = eff.data.get("only", "")
        for c in p.creatures:
            if eff.data.get("other") and c is src:
                continue
            if only == "tapped" and not c.tapped:
                continue
            if only == "legendary" and not c.card.legendary:
                continue
            if only not in ("", "tapped", "legendary") and only not in c.card.subtypes:
                continue
            c.counters["+1/+1"] = c.p1 + n
    else:
        if isinstance(target, Permanent) and target in target.controller.battlefield:
            n = eff.amount
            if eff.data.get("x") == "entered":
                src = item.source if item is not None else None
                n = getattr(src, "entered_x", 0) or getattr(item, "x", 0)
            target.counters["+1/+1"] = target.p1 + n
            if eff.data.get("keyword"):
                target.perm_kw.add(eff.data["keyword"])


@kind("pump_all")
def pump_all(game, p, eff, item, **_):
    src = item.source if item is not None else None
    for c in p.creatures:
        if eff.data.get("other") and c is src:
            continue
        if eff.data.get("only") == "equipped_attacking" and not (c.equipment and c in game.attackers):
            continue
        c.pump_p += eff.amount
        c.pump_t += eff.amount2
        if eff.data.get("keyword"):
            c.temp_kw.add(eff.data["keyword"])


_KEYWORD_RANK = {k: i for i, k in enumerate(("flying", "double strike", "indestructible", "first strike", "trample",
                                              "menace", "deathtouch", "lifelink", "hexproof", "vigilance", "haste"))}


@kind("grant")
def grant(game, p, eff, target, item, **_):
    if eff.data.get("host") and item is not None and isinstance(item.source, Permanent):
        target = item.source.attached_to
    if isinstance(target, Permanent):
        keyword = eff.data["keyword"]
        if keyword == protection.CHOICE:
            keyword = protection.choose_color(game, p, target)
            game.log(f"{target.card.name} gains {keyword}", p)
        elif keyword.startswith("choice:"):        # "your choice of flying, vigilance, or lifelink": the best one it lacks
            options = keyword[7:].split("|")
            keyword = min(options, key=lambda k: (target.has(k), _KEYWORD_RANK.get(k, 20)))
            game.log(f"{target.card.name} gains {keyword}", p)
        if eff.data.get("perm"):
            target.counters[keyword] = target.counters.get(keyword, 0) + 1
        else:
            target.temp_kw.add(keyword)


@kind("add_counter")
def add_counter(game, p, eff, target, **_):
    if isinstance(target, Permanent):
        name = eff.data.get("counter", "+1/+1")
        n = eff.amount
        if eff.data.get("x") == "sacrificed":
            n = p.sacrificed_turn
            if n >= 3:
                target.temp_kw.add("lifelink")
        target.counters[name] = target.counters.get(name, 0) + n


@kind("increment")
def increment(game, item, **_):
    src = item.source if item is not None else None
    if isinstance(src, Permanent) and src in src.controller.battlefield and isinstance(item.context, StackItem):
        if item.context.mana_spent + item.context.x > min(src.power, src.toughness):
            src.counters["+1/+1"] = src.p1 + 1


@kind("cant_block_turn")
def cant_block_turn(game, target, **_):
    if isinstance(target, Permanent):
        target.temp_kw.add("cant_block_now")


@kind("force_block", "force_blocked")
def force_block(game, eff, target, k, **_):
    if isinstance(target, Permanent):
        target.temp_kw.add("must_block_now" if k == "force_block" else "must_be_blocked_now")
        if eff.data.get("attack"):
            target.temp_kw.add("must_attack_now")


@kind("shrink")
def shrink(game, eff, target, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        target.counters["-1/-1"] = target.m1 + eff.amount


@kind("shrink_all")
def shrink_all(game, p, eff, opp, **_):
    for v in p.creatures + opp.creatures:
        v.counters["-1/-1"] = v.m1 + eff.amount


@kind("grant_types")
def grant_types(game, p, eff, **_):
    for x in p.battlefield:
        if any(t in x.card.subtypes for t in eff.data["types"]):
            x.temp_kw.add(eff.data["keyword"])


@kind("cant_block_all")
def cant_block_all(game, p, eff, opp, **_):
    for c in p.creatures + opp.creatures:
        if not (eff.filter == "nonflying" and c.has("flying")):
            c.temp_kw.add("cant_block_now")


@kind("pump_attackers")
def pump_attackers(game, p, eff, **_):
    for a in game.attackers:
        if a.controller is p:
            a.pump_p += eff.amount
            a.pump_t += eff.amount2


@kind("untap_all")
def untap_all(game, p, eff, **_):
    for x in p.battlefield:
        if (x.is_creature if eff.data["what"] == "creatures" else x.card.is_land):
            x.tapped = False


@kind("untap_prev")
def untap_prev(game, target, **_):
    if isinstance(target, Permanent):
        target.tapped = False


@kind("untap_self")
def untap_self(game, item, **_):
    src = item.source if item is not None else None
    if src is not None and src in src.controller.battlefield:
        src.tapped = False


@kind("untap_other")
def untap_other(game, p, item, **_):
    tapped = [x for x in p.battlefield if x.tapped and x is not (item.source if item else None)]
    best = max(tapped, key=lambda x: (x.card.is_land or bool(x.card.produces), perm_value(x) if x.is_creature
                                     else x.card.cmc), default=None)
    if best is not None:
        best.tapped = False


@kind("tap")
def tap(game, p, eff, target, item=None, **_):
    if isinstance(target, Permanent):
        target.tapped = True
        src = item.source if item is not None else None
        if eff.data.get("silence") and isinstance(src, Permanent):
            target.silenced_by = src      # loses all abilities while the source stays out
        if eff.data.get("net"):
            target.net_locked = True
    for _ in range(eff.amount - 1):   # "tap up to two target creatures": the next best ones
        extra = default_choose_target(game, p, eff)
        if extra is not None:
            extra.tapped = True


@kind("unblockable")
def unblockable(game, target, **_):
    if isinstance(target, Permanent):
        target.temp_kw.add("unblockable")


@kind("stun")
def stun(game, eff, target, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        target.counters["stun"] = target.counters.get("stun", 0) + eff.amount


@kind("double_power")
def double_power(game, target, **_):
    if isinstance(target, Permanent) and target.power > 0:
        target.pump_p += target.power


@kind("double_counters")
def double_counters(game, p, eff, target, **_):
    if eff.target == 'my_creatures':
        for c in p.creatures:
            c.counters["+1/+1"] = c.p1 * 2
    else:
        if isinstance(target, Permanent) and target.p1:
            target.counters["+1/+1"] = target.p1 * 2


@kind("next_creature_counter")
def next_creature_counter(game, p, **_):
    p.next_creature_counters += 1


@kind("adversary")
def adversary(game, p, eff, item, **_):
    game.adversary(p, item, eff)


@kind("level_up")
def level_up(game, p, eff, item, **_):
    src = item.source if item is not None else None
    if isinstance(src, Permanent) and src in src.controller.battlefield:
        src.counters["level"] = eff.data["to"]
        game.log(f"{src.card.name} becomes level {eff.data['to']}", p)
        game.fire(p, "class_level", src, subject=eff.data["to"])
