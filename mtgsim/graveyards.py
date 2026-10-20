"""Target selection and resolution for matched graveyard return effects.

A multi-target effect stores a tuple of GraveyardTargets in its target slot. An
empty tuple records choosing zero targets; it must not be filled in later.
"""
import dataclasses
import re

from . import copies


def uses_x(effect):
    return effect.target == "graveyard_card" and (effect.data.get("x_n")
           or bool(effect.data.get("cmc") and effect.data["cmc"][0] == "x"))


def with_x(effects, x):
    return [dataclasses.replace(e, data={**e.data, "bound_x": x}) if uses_x(e) else e for e in effects]


def planned_x(game, player, card, cost, reserved=()):
    """Choose an affordable X before targets; this spell pays base and X together."""
    from .engine import payable
    if "X" not in card.mana_cost:
        return 0
    sources = [s for s in game.mana_sources(player, spell=card) if s not in reserved]
    if not payable(sources, cost):
        return 0
    x = 0
    while x < 20 and payable(sources, {**cost, "generic": cost.get("generic", 0) + x + 1}):
        x += 1
    required = [e for e in card.spell_effects + [e for mode in card.modes for e in mode]
                if e.target == "graveyard_card" and e.data.get("x_n") and not e.data.get("upto")]
    while x and any(not can_choose(game, player, e, getattr(card, "graveyard_target", None))
                    for e in with_x(required, x)):
        x -= 1
    return x


def description_fits(card, description):
    # copies.fits deliberately treats these words loosely for battlefield copies.
    # Graveyard target restrictions must enforce them, including within alternatives.
    for alternative in re.split(r",? or |, ", description):
        words = alternative.lower().split()
        if "permanent" in words and not card.is_permanent:
            continue
        if "nonlegendary" in words and card.legendary:
            continue
        if "legendary" in words and not card.legendary:
            continue
        if copies.fits(card, re.sub(r"\blegendary\s+", "", alternative, flags=re.I)):
            return True
    return False


def count(effect):
    return effect.data.get("bound_x", 0) if effect.data.get("x_n") else max(1, effect.amount)


def fits(player, effect, target):
    """Recheck the zone owner, exact entry, description and mana value."""
    from .engine import GraveyardTarget, _gy_desc
    if not isinstance(target, GraveyardTarget) or target.index() is None:
        return False
    data, card = effect.data, target.card
    zone = data.get("zone", "mine")
    if zone == "mine" and target.controller is not player:
        return False
    if zone == "opp" and target.controller is player:
        return False
    what = data.get("what", {"regrow": "creature", "reanimate_one": "creature",
                             "regrow_perm": "permanent", "regrow_any": "card"}.get(effect.kind, "card"))
    if what != "card" and not description_fits(card, _gy_desc(what)):
        return False
    if (effect.kind == "reanimate_one" or data.get("dest") == "bf") and not card.is_permanent:
        return False
    if data.get("cmc"):
        limit, comparison = data["cmc"]
        limit = data.get("bound_x", 0) if limit == "x" else limit
        if (card.cmc > limit) if comparison == "less" else (card.cmc < limit):
            return False
    return True


def candidates(game, player, effect):
    from .engine import GraveyardTarget
    return [target for owner in game.players
            for card, entry in zip(owner.graveyard, owner.graveyard.entries)
            if fits(player, effect, target := GraveyardTarget(owner, card, entry))]


def capacity(effect, choices):
    """How many of these candidates one legal selection can hold ("single graveyard", "different names")."""
    if effect.data.get("single"):
        groups = {}
        for t in choices:
            groups.setdefault(id(t.controller), []).append(t)
        pools = list(groups.values())
    else:
        pools = [list(choices)]
    return max((len({t.card.name for t in pool}) if effect.data.get("distinct") else len(pool)
                for pool in pools), default=0)


def can_choose(game, player, effect, exclude=None):
    minimum = 0 if effect.data.get("upto") else count(effect)
    return capacity(effect, [t for t in candidates(game, player, effect) if t != exclude]) >= minimum


def entries(target):
    return target if isinstance(target, tuple) else (target,)


def legal(player, effect, target):
    if target == ():
        return bool(effect.data.get("upto")) or count(effect) == 0
    return any(fits(player, effect, entry) for entry in entries(target))


def valid_selection(effect, picked):
    """Whether these entries respect "from a single graveyard" and "with different names"."""
    if effect.data.get("single") and len({id(t.controller) for t in picked}) > 1:
        return False
    return not effect.data.get("distinct") or len({t.card.name for t in picked}) == len(picked)


KINDS = frozenset({"gy_exile", "gy_hate"})     # exile effects resolved here rather than in Game.resolve


def hates(effect):
    return effect.kind in KINDS


def choose(game, player, effect, exclude=None):
    choices = [t for t in candidates(game, player, effect) if t != exclude]
    if hates(effect):
        # Hate removes the opponent's best card; never spend an optional exile on your own graveyard.
        theirs = [t for t in choices if t.controller is not player]
        choices = theirs or ([] if effect.data.get("upto") else choices)
        choices.sort(key=lambda t: (t.card.is_creature, t.card.cmc), reverse=True)
    else:
        choices.sort(key=lambda t: t.card.cmc, reverse=True)
    picked = []
    for t in choices:
        if len(picked) < count(effect) and valid_selection(effect, picked + [t]):
            picked.append(t)
    if effect.data.get("single") and len(picked) < count(effect):
        # the greedy pick may straddle graveyards; fall back to the largest single one
        pools = {}
        for t in choices:
            pools.setdefault(id(t.controller), []).append(t)
        picked = max(([t for t in pool if valid_selection(effect, [t])][:count(effect)] for pool in pools.values()),
                     key=len, default=[])
    if count(effect) == 1 and picked:
        return picked[0]
    return tuple(picked)


def bind(game, player, effect, target, exclude=None):
    """Validate every announced choice before payment, rather than just one survivor."""
    from .cards import CardDef
    from .engine import GraveyardTarget
    choices = [t for t in candidates(game, player, effect) if t != exclude]
    if target is None:
        target = game.auto_targets(player, [effect])[0]
        if exclude is not None and any(t == exclude for t in entries(target)):
            target = choose(game, player, effect, exclude)
    selected = []
    for entry in entries(target):
        if isinstance(entry, CardDef):
            entry = next((t for t in choices if t.card is entry and t not in selected), None)
        if not isinstance(entry, GraveyardTarget) or entry not in choices or entry in selected:
            return None
        selected.append(entry)
    maximum = count(effect)
    minimum = 0 if effect.data.get("upto") else maximum
    if not minimum <= len(selected) <= maximum or not valid_selection(effect, selected):
        return None
    return selected[0] if maximum == 1 and selected else tuple(selected)


def resolve_hate(game, player, effect, selected):
    """Exile the still-legal chosen entries; Diregraf Scavenger-style gy_hate also drains for a creature card."""
    for entry in selected:
        entry.controller.graveyard.pop(entry.index())
    for entry in selected:
        entry.controller.exile.append(entry.card)
        game.log(f"exiles {entry.card.name} from {entry.controller}'s graveyard", player)
    if effect.kind == "gy_hate" and any(e.card.is_creature for e in selected):
        for opponent in game.players:
            if opponent is not player:
                game.change_life(opponent, -effect.amount, "gy_hate")
        game.change_life(player, effect.amount, "gy_hate")


def resolve(game, player, effect, target):
    selected = []
    for t in entries(target):
        # a chosen entry that left or changed is skipped, never replaced by another card
        if fits(player, effect, t) and not (effect.data.get("distinct")
                                            and any(t.card.name == s.card.name for s in selected)):
            selected.append(t)
    if hates(effect):
        return resolve_hate(game, player, effect, selected)
    # Remove the entire batch before ETB triggers, including repeated CardDefs.
    for entry in selected:
        entry.controller.graveyard.pop(entry.index())
    battlefield = effect.kind == "reanimate_one" or effect.data.get("dest") == "bf"
    returned = []
    for entry in selected:
        if battlefield:
            permanent = game.enter_battlefield(player, entry.card)
            permanent.owner = entry.controller
            if effect.data.get("tapped"):
                permanent.tapped = True
            returned.append(permanent)
            game.log(f"returns {entry.card.name} to the battlefield", player)
        else:
            player.hand.append(entry.card)
            game.log(f"returns {entry.card.name} to hand", player)
    return returned[0] if len(returned) == 1 else None
