"""Graveyard self-return abilities, turn conditions and trigger timing."""
from __future__ import annotations

import dataclasses
import re


def is_return_ability(line):
    return re.search(r": Return (?:this card|~) from your graveyard to the battlefield", line) is not None


def parse_ability(line, approximations):
    from .cards import _parse_ability
    from .cards.patterns import _if_cond
    text = re.sub(r"^(?:Delirium|Descend \d+|Raid|Metalcraft) — ", "", line)
    conditions = []
    restrictions = {
        "there are four or more card types among cards in your graveyard": "delirium",
        "there are eight or more permanent cards in your graveyard": "gy8",
    }
    m = re.fullmatch(r"(.+\.) Activate only (.+)\.", text)
    if m and m[2] != "as a sorcery":
        rule = m[2]
        sorcery = rule.endswith(" and only as a sorcery")
        if sorcery:
            rule = rule[:-len(" and only as a sorcery")]
        if rule.startswith("during your upkeep"):
            conditions.append("your_upkeep")
            rule = rule[len("during your upkeep"):]
            if rule.startswith(" and only if "):
                rule = "if " + rule[len(" and only if "):]
        if rule:
            if not rule.startswith("if "):
                return None
            phrase = rule[3:]
            condition = restrictions.get(phrase) or _if_cond(phrase)
            if not condition:
                return None
            conditions.append(condition)
        text = m[1] + (" Activate only as a sorcery." if sorcery else "")
    condition = "&".join(conditions)
    text = text.replace("Return this card from your graveyard", "Return ~ from your graveyard")
    approx = []
    act = _parse_ability(text, approx)
    if act is None or act.once or act.once_game or act.modes or \
            set(act.extra_costs) - {"discard", "life", "sacrifice", "sac_n"} or \
            act.extra_costs.get("sacrifice", "land") != "land" or \
            any(e.target in ("self", "prev") for e in act.effects) or \
            not any(e.kind == "return_self_gy" for e in act.effects):
        return None
    act.condition, act.text = condition, line
    approximations += approx
    return act


def can_activate(game, p, card, idx):
    from . import modal
    from .engine import payable
    if card not in p.graveyard or not 0 <= idx < len(card.gy_activated):
        return False
    act = card.gy_activated[idx]
    if act.sorcery and not (p is game.active and game.step in ("main1", "main2") and not game.stack):
        return False
    if act.condition and not modal.upgrade_active(game, p, act.condition):
        return False
    if act.needs_max_speed and p.speed < 4:
        return False
    costs = act.extra_costs
    if costs.get("sacrifice") and len([x for x in p.battlefield if x.card.is_land]) < costs.get("sac_n", 1):
        return False
    if len(p.hand) < costs.get("discard", 0) or p.life < costs.get("life", 0):
        return False
    return payable(game.mana_sources(p, spell="ability"), act.cost)


def activate(game, p, card, idx):
    from .engine import StackItem
    if not can_activate(game, p, card, idx):
        return False
    card = p.graveyard.get(card)
    act = card.gy_activated[idx]
    if game.pay(p, act.cost) is None:
        return False
    if act.extra_costs.get("life"):
        game.change_life(p, -act.extra_costs["life"], f"{card.name}: graveyard ability cost")
    for _ in range(act.extra_costs.get("discard", 0)):
        game.discard_card(p, p.ai.choose_discard(game, p))
    for _ in range(act.extra_costs.get("sac_n", 1) if act.extra_costs.get("sacrifice") else 0):
        game.sacrifice(next(x for x in p.battlefield if x.card.is_land))
    item = StackItem(p, list(act.effects), game.auto_targets(p, act.effects), context=card,
                     name=f"{card.name} graveyard ability", kind="ability")
    game.stack.append(item)
    game.log(f"activates {item}", p)
    game.check_ward(item)
    game.settle()
    return True


def turn_history(game):
    """Only the bounded turn facts needed by graveyard return conditions."""
    history = getattr(game, "_graveyard_turn", None)
    if history is None or history["turn"] != game.turn:
        history = {"turn": game.turn, "casts": {}, "deaths": 0, "entries": 0, "non_skeleton_deaths": set()}
        game._graveyard_turn = history
    return history


def observe_event(game, p, event, source=None, context=None, subject=None):
    history = turn_history(game)
    if event == "any_cast" and context is p and subject is not None:
        casts = history["casts"].setdefault(p, {"instant_sorcery": 0, "creature": 0})
        casts["instant_sorcery"] += int(subject.is_instant or subject.is_sorcery)
        casts["creature"] += int(subject.is_creature)
    elif event == "dies" and source is not None:
        history["deaths"] += 1
        if "Skeleton" not in source.card.subtypes:
            history["non_skeleton_deaths"].add(p)
    elif event == "other_creature_enters" and subject is not None:
        history["entries"] += 1


def condition_active(game, p, condition):
    """Shared turn/battlefield conditions; None means another condition family owns it."""
    if "&" in condition:
        from . import modal
        return all(modal.upgrade_active(game, p, part) for part in condition.split("&"))
    if condition == "your_upkeep":
        return p is game.active and game.step == "upkeep"
    if condition == "attacked_turn":
        return p.attacked_with > 0
    if condition == "legendary_creature":
        return any(x.card.legendary for x in p.creatures)
    if condition == "artifacts3":
        return sum(x.card.is_artifact for x in p.battlefield) >= 3
    if condition == "control_swamp":
        return any("Swamp" in x.card.subtypes and x.card.is_land for x in p.battlefield)
    if condition.startswith("instants_sorceries>="):
        casts = turn_history(game)["casts"].get(p, {})
        return casts.get("instant_sorcery", 0) >= int(condition.split(">=")[1])
    if condition.startswith("creatures_died>="):
        return turn_history(game)["deaths"] >= int(condition.split(">=")[1])
    if condition == "non_skeleton_died":
        return p in turn_history(game)["non_skeleton_deaths"]
    if condition == "creature_entered_and_died":
        history = turn_history(game)
        return history["entries"] > 0 and history["deaths"] > 0
    return None


def intervening_active(game, p, effects, item):
    from .cards import Effect
    for effect in effects:
        condition = effect.data.get("intervening_if", "")
        if condition == "second_creature_spell":
            if not effect.data.get("second_creature_cast", False):
                return False
        elif condition and not game.check_cond(p, Effect("return_self_gy", cond=condition), item, None):
            return False
    return True


def trigger_effects(game, p, trig, card, event, context=None, subject=None):
    """Select graveyard listeners and check intervening-if before queueing any payment."""
    casting = trig.event == "cast_spell" and event == "any_cast" and context is p
    if trig.event != event and not casting:
        return None
    if trig.filter.startswith("attackers>=") and p.attacked_with < int(trig.filter.split(">=")[1]):
        return None
    if trig.filter.startswith("cmc<=") and (subject is None or subject.cmc > int(trig.filter[5:])):
        return None
    if casting and trig.filter.startswith("spell:"):
        what = trig.filter[6:]
        if not (what in subject.subtypes or what.capitalize() in subject.types):
            return None
    effects = trig.effects
    if any(e.data.get("intervening_if") == "second_creature_spell" for e in effects):
        second = casting and subject.is_creature and turn_history(game)["casts"].get(p, {}).get("creature") == 2
        effects = [dataclasses.replace(e, data=dict(e.data, second_creature_cast=second)) for e in effects]
    return effects
