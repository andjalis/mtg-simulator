"""Physical card identities alongside compatible, name-equal card definitions.

Rules code uses physical IDs and frozen ZoneRefs. CardDef equality remains a
definition lookup convenience; it must not select between physical copies.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import itertools

from .cards import CardDef

_IDS = itertools.count(1)


class CardInstance(CardDef):
    def __init__(self, definition=None, **values):
        # dataclasses.replace remains available for creating new definitions/copies.
        if definition is None:
            definition = CardDef(**values)
        super().__init__(**{f.name: getattr(definition, f.name) for f in fields(CardDef)})
        self.definition = getattr(definition, "definition", definition)
        self.physical_id = next(_IDS)
        self.generation = 0
        self.owner = None
        self.zone = None
        self.last_zone = ""
        self.pending_move = None

    def __eq__(self, other):
        if isinstance(other, CardInstance):
            return self.physical_id == other.physical_id
        return CardDef.__eq__(self, other)

    __hash__ = CardDef.__hash__  # preserve hash compatibility with definition lookups


def instance(card, owner=None):
    card = card if isinstance(card, CardInstance) else CardInstance(card)
    if card.owner is None:
        card.owner = owner
    return card


@dataclass(frozen=True)
class ZoneRef:
    physical_id: int
    generation: int

    def find(self, zone):
        return next((c for c in zone if isinstance(c, CardInstance) and
                     c.physical_id == self.physical_id and c.generation == self.generation), None)


class CardZone(list):
    """Identity-aware card storage; raw definitions can still be used for lookup.

    A tracked instance never falls back to another same-name card. A definition
    lookup selects the first matching definition for legacy callers.
    """
    track_departures = False

    def __init__(self, cards=(), *, owner=None, name=""):
        super().__init__()
        self.owner, self.name = owner, name
        self.left = []
        self.versions = {}
        self.initializing = True
        self.extend(cards)
        self.initializing = False

    def index(self, card, start=0, stop=None):
        stop = len(self) if stop is None else stop
        for i in range(*slice(start, stop).indices(len(self))):
            other = list.__getitem__(self, i)
            if (other is card or isinstance(card, CardInstance) and other.physical_id == card.physical_id
                    or not isinstance(card, CardInstance) and other == card):
                return i
        raise ValueError("card is not in this zone")

    def __contains__(self, card):
        try:
            self.index(card)
            return True
        except ValueError:
            return False

    def get(self, card):
        return self[self.index(card)]

    def _arrive(self, card):
        card = instance(card, self.owner)
        if isinstance(card.zone, CardZone) and card in card.zone:
            raise ValueError("remove the physical card from its source zone before insertion")
        if card.pending_move is None and card.zone is not None:
            if getattr(card.zone, "physical_card", None) is not card:
                raise ValueError("remove the physical card from the battlefield before insertion")
            from .rules_events import card_snapshot
            controller = getattr(card.zone, "controller", self.owner)
            card.pending_move = (card_snapshot(card, controller), "stack", controller, None, ())
        card.generation += 1
        card.zone = self
        self.versions[card.physical_id] = card.generation
        return card

    def append(self, card):
        card = self._arrive(card)
        super().append(card)
        self._added(card)

    def insert(self, index, card):
        card = self._arrive(card)
        super().insert(index, card)
        self._added(card)

    def _added(self, card):
        game = getattr(self.owner, "_game", None)
        if game is not None and not self.initializing:
            game.zone_arrived(card, self)

    def _depart(self, card):
        if getattr(self.owner, "_game", None) is not None:
            from .rules_events import card_snapshot
            card.pending_move = (card_snapshot(card, self.owner), self.name, self.owner, None, ())
        card.generation += 1
        card.last_zone = self.name
        card.zone = None
        self.versions[card.physical_id] = card.generation
        if self.track_departures:
            self.left.append(card)

    def extend(self, cards):
        for card in list(cards):
            self.append(card)

    def __iadd__(self, cards):
        self.extend(cards)
        return self

    def __delitem__(self, key):
        removed = self[key] if isinstance(key, slice) else [self[key]]
        super().__delitem__(key)
        for card in removed:
            self._depart(card)

    def __setitem__(self, key, value):
        incoming = list(value) if isinstance(key, slice) else [value]
        prepared = [instance(c, self.owner) for c in incoming]
        before = list(self)
        after = list(self)
        after[key] = prepared if isinstance(key, slice) else prepared[0]
        if len({c.physical_id for c in after}) != len(after):
            raise ValueError("a physical card cannot occur twice in one zone")
        for card in prepared:
            if isinstance(card.zone, CardZone) and card.zone is not self and card in card.zone:
                raise ValueError("remove the physical card from its source zone before insertion")
        for card in before:
            if not any(card is c for c in after):
                self._depart(card)
        for card in prepared:
            if not any(card is c for c in before):
                self._arrive(card)
        list.__setitem__(self, slice(None), after)
        for card in prepared:
            if not any(card is c for c in before):
                self._added(card)

    def __imul__(self, count):
        if count <= 0:
            self.clear()
        elif count != 1:
            raise ValueError("create copies from card definitions, not physical instances")
        return self

    def remove(self, card):
        del self[self.index(card)]

    def pop(self, index=-1):
        card = self[index]
        del self[index]
        return card

    def clear(self):
        del self[:]

    def version(self, card):
        if isinstance(card, CardInstance):
            return self.versions.get(card.physical_id, 0)
        return 0

    def reference(self, card):
        card = self.get(card)
        return ZoneRef(card.physical_id, card.generation)

    def shuffle(self, rng):
        cards = list(self)
        rng.shuffle(cards)
        self.reorder(cards)

    def reorder(self, cards):
        cards = list(cards)
        if sorted(c.physical_id for c in cards) != sorted(c.physical_id for c in self):
            raise ValueError("reordering must preserve every physical card exactly once")
        list.__setitem__(self, slice(None), cards)


class Graveyard(CardZone):
    track_departures = True

    def __init__(self, *args, **kwargs):
        self.descents = 0
        super().__init__(*args, **kwargs)

    def append(self, card):
        previous = self.descents
        if card.is_permanent and not card.is_token:
            self.descents += 1
        try:
            super().append(card)
        except Exception:
            self.descents = previous
            raise
