"""Typed event delivery and a bounded replacement pipeline for supported rules."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CardSnapshot:
    physical_id: int
    generation: int
    name: str
    owner: str
    controller: str
    power: int | None
    toughness: int | None
    counters: tuple


def snapshot(permanent):
    card = permanent.front
    return CardSnapshot(card.physical_id, card.generation, permanent.card.name,
                        permanent.owner.name, permanent.controller.name,
                        permanent.power if permanent.is_creature else None,
                        permanent.toughness if permanent.is_creature else None,
                        tuple(sorted(permanent.counters.items())))


def card_snapshot(card, controller):
    return CardSnapshot(card.physical_id, card.generation, card.name, card.owner.name,
                        controller.name, None, None, ())


@dataclass(frozen=True)
class RulesEvent:
    kind: str
    player: object
    source: object = None
    context: object = None
    subject: object = None
    before: CardSnapshot | None = None
    destination: str = ""
    reason: str = ""
    replacements: tuple = ()
    source_zone: str = ""


class EventBus:
    def __init__(self, capture=False):
        self.listeners = []
        self.history = [] if capture else None

    def emit(self, event):
        if self.history is not None:
            self.history.append(event)
        for listener in tuple(self.listeners):
            listener(event)


@dataclass(frozen=True)
class MoveIntent:
    destination: str
    prevented: bool = False
    applied: tuple = ()


@dataclass(frozen=True)
class Replacement:
    id: str
    applies: object
    apply: object


def replace_event(intent, replacements, choose):
    """Recompute applicability after each replacement; apply each at most once."""
    while not intent.prevented:
        applicable = [r for r in replacements if r.id not in intent.applied and r.applies(intent)]
        if not applicable:
            break
        selected = choose(tuple(r.id for r in applicable), intent)
        replacement = next((r for r in applicable if r.id == selected), applicable[0])
        applied = intent.applied + (replacement.id,)
        intent = replace(replacement.apply(intent), applied=applied)
    return intent


def zone_destination(game, permanent, destination):
    """The supported battlefield-to-graveyard replacements; no printed-text guesses."""
    def to_exile(intent):
        return replace(intent, destination="exile")
    replacements = [
        Replacement("finality", lambda e: e.destination == "graveyard" and
                    bool(permanent.counters.get("finality", 0)), to_exile),
        Replacement("exile-if-dies-this-turn", lambda e: e.destination == "graveyard" and
                    permanent.exile_turn == game.turn, to_exile),
        Replacement("exile-damaged", lambda e: e.destination == "graveyard" and permanent.is_creature and
                    bool(permanent.damage or permanent.deathtouched) and
                    any(x.card.exile_damaged for x in game.opponent(permanent.controller).battlefield), to_exile),
    ]
    return replace_event(MoveIntent(destination), replacements,
        lambda choices, event: game.hook(permanent.controller, "choose_replacement")(
            game, permanent.controller, choices, event))


def regenerate(game, permanent):
    """Apply the supported destruction replacement, preserving its battlefield object."""
    permanent.regeneration_shields -= 1
    was_tapped = permanent.tapped
    permanent.tapped = True
    permanent.damage = 0
    permanent.deathtouched = False
    if permanent in game.attackers:
        game.attackers.remove(permanent)
    game.attack_targets.pop(permanent, None)
    game.blocks.pop(permanent, None)
    for blockers in game.blocks.values():
        blockers[:] = [b for b in blockers if b is not permanent]
    game.log(f"regenerates {permanent.card.name}", permanent.controller)
    if not was_tapped:
        game.fire(permanent.controller, "becomes_tapped", permanent)


def destruction(game, permanent, no_regen=False):
    replacements = [
        Replacement("regeneration", lambda e: not no_regen and not permanent.regeneration_blocked and
                    bool(permanent.regeneration_shields), lambda e: replace(e, prevented=True))]
    return replace_event(MoveIntent("graveyard"), replacements, lambda choices, event: choices[0])
