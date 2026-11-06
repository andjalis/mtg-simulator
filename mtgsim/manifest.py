"""Manifest: the top card of a library enters the battlefield face down as a 2/2 creature.

The face-down foundation already in the engine (the morph/disguise cast path and
``turns.turn_face_up``) stores the real card on ``permanent.hidden`` and turns a face-down
creature face up by paying an alt cost carried by that hidden card. Manifest reuses it
exactly: the manifested card enters as a hand-built "Face-down creature" CardDef (so no
enters-the-battlefield ability of the real card fires, CR 701.4a) whose physical front is
the library card, and ``hidden`` gets a clone of the real card carrying a "morph" alt
cost for its own mana cost — the existing main-phase ``turn_face_up`` then unmorphs
creature cards automatically once the mana is spare. Noncreature cards stay face down
(the rules allow no other way to turn them up).

Manifest dread (Duskmourn) looks at the top two cards, manifests one (a creature if there
is one) and mills the other.

The bare "Manifest dread." wording parses to the foundation kind
(engine/kinds/permanents.py, from cards/patterns.py); the variants that single effect
can't express ride this module's manifest_dread_more kind instead — "manifest dread
twice", "manifest dread, then attach this Equipment" and Valgavoth's Onslaught's
"manifest dread X times, then put X +1/+1 counters on each of those creatures".

Batch 4 adds the Paranormal Analyst's listener ("Whenever you manifest dread, put a
card you put into your graveyard this way into your hand"): this module's dread
resolution records the milled cards on the game and fires a manifest_dread event the
trigger reads back. The foundation kind (bare "Manifest dread.") does not fire it yet —
see the cross-area note — so until that lands the listener only hears the
manifest_dread_more dreads. Stay Hidden, Stay Silent's "Shuffle enchanted creature into
its owner's library, then manifest dread" is a shuffle_enchanted effect (the aura's
host leaves for a random spot of its owner's library) followed by the foundation dread.

Recorded simplifications: manifest dread always manifests a creature over a noncreature;
Fierce Invocation's "+1/+1 counters on it" is applied by the manifest effect itself; the
from-hand and graveyard-pile manifests (Kozilek, Ghastly Conscription, The Good Time
Sleuth) and the becomes-an-Aura templates (Cloudform, Rageform) are not built;
the recovered card is the most valuable one milled by the dread (a card, as written);
Disturbing Mirth's "When you sacrifice this enchantment" is not built (the sacrifice
trigger dispatch has no self-only convention), and neither is Turn Inside Out's
"When it dies this turn" delayed trigger (no floating one-turn trigger foundation).
"""
from __future__ import annotations

import dataclasses




def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


EFFECT_PATTERNS = [
    (r"manifest the top card of your library, then put two \+1/\+1 counters on it",
     lambda m: _e("manifest", 1, data={"counters": ("+1/+1", 2)})),
    (r"manifest the top card of your library", lambda m: _e("manifest", 1)),
    (r"manifest a number of cards from the top of your library equal to the number of counters on (?:~|it)",
     lambda m: _e("manifest", data={"counters_of_source": True})),
    (r"manifest dread twice", lambda m: _e("manifest_dread_more", 2)),
    (r"manifest dread, then attach this equipment to that creature",
     lambda m: _e("manifest_dread_more", 1, data={"attach": True})),
    (r"manifest dread X times, then put X \+1/\+1 counters on each of those creatures",
     lambda m: _e("manifest_dread_more", 1, data={"times": "x", "counters": ("+1/+1", "x")})),
    (r"manifest one of those cards, then put the other on the top or bottom of your library",
     lambda m: _e("manifest", 1)),
    # Stay Hidden, Stay Silent: the aura's host leaves for a random spot of its owner's
    # library, then the foundation's bare dread resolves.
    (r"shuffle enchanted creature into its owner's library, then manifest dread",
     lambda m: [_e("shuffle_enchanted"), _e("manifest_dread")]),
    # Paranormal Analyst: read back a card the dread just milled.
    (r"put a card you put into your graveyard this way into your hand",
     lambda m: _e("manifest_recover")),
]

TRIGGERS = [
    (r"Whenever you cast an instant or sorcery spell from your hand, (.+)", ("cast_instant_sorcery",)),
    (r"Whenever you manifest dread, (.+)", ("manifest_dread",)),
]


def _face_down_def():
    from .cards import CardDef
    return CardDef(name="Face-down creature", mana_cost={"generic": 0}, cmc=0,
                   types=frozenset({"Creature"}), power=2, toughness=2)


def manifest_one(game, p, card=None):
    """Put card (by default the top card of p's library) onto the battlefield face down."""
    if card is None:
        if not p.library:
            return None
        card = p.library.pop()
    from .cards import AltCost
    real = getattr(card, "definition", card)
    hidden = real
    if real.is_creature:                    # a creature card can be turned face up for its cost
        hidden = dataclasses.replace(real, alt_costs=list(real.alt_costs) + [AltCost("morph", real.mana_cost)])
    perm = game.enter_battlefield(p, _face_down_def(), physical_card=card)
    if perm is None:
        return None
    perm.hidden = hidden
    perm.card = _face_down_def()
    game.log(f"manifests {real.name} face down", p)
    return perm


def manifest(game, p, eff, item):
    made = []
    n = eff.amount or 1
    if eff.data.get("counters_of_source"):
        src = item.source if item is not None else None
        n = sum(src.counters.values()) if src is not None else 0
    for _ in range(max(0, n)):
        perm = manifest_one(game, p)
        if perm is not None:
            made.append(perm)
    kind, n2 = eff.data.get("counters", (None, 0))
    if kind and made:
        for perm in made:
            perm.counters[kind] = perm.p1 + n2
    return made


def manifest_dread(game, p, eff, item):
    n = eff.amount or 1
    if eff.data.get("times") == "x":       # "manifest dread X times"
        n = getattr(item, "x", 0) if item is not None else 0
    made = []
    for _ in range(max(0, n)):
        if not p.library:
            break
        look = [p.library.pop() for _ in range(min(2, len(p.library)))]
        pick = next((c for c in look if c.is_creature), look[0])
        look.remove(pick)
        perm = manifest_one(game, p, pick)
        made.append(perm)
        milled = []
        for other in look:
            p.graveyard.append(other)
            milled.append(other)
            game.log(f"mills {other.name}", p)
        if milled:
            game.__dict__["_manifest_dread_milled"] = milled
            game.fire(p, "manifest_dread", context=tuple(milled))   # Paranormal Analyst's listener
        if perm is not None and eff.data.get("attach") and item is not None and item.source is not None \
                and "Equipment" in item.source.card.types:
            item.source.attached_to = perm
            game.log(f"attaches {item.source.card.name} to the manifested creature", p)
    kind, n2 = eff.data.get("counters", (None, 0))
    if kind and made:
        if n2 == "x":
            n2 = getattr(item, "x", 0) if item is not None else 0
        for perm in made:
            if perm is not None:
                perm.counters[kind] = perm.p1 + n2
    return made


def shuffle_enchanted(game, p, eff, item):
    """Stay Hidden, Stay Silent: the aura's host leaves for a random spot of its owner's library."""
    from .engine.state import Permanent
    src = item.source if item is not None else None
    host = getattr(src, "aura_host", None)
    if not isinstance(host, Permanent) or host not in host.controller.battlefield:
        return
    owner = host.owner
    if game.leave_battlefield(host, "graveyard") and not host.front.is_token \
            and host.front in owner.graveyard:
        owner.graveyard.remove(host.front)
        owner.library.insert(game.rng.randrange(len(owner.library) + 1), host.front)
        game.log(f"shuffles {host.card.name} into its owner's library", p)


def manifest_recover(game, p, eff, item):
    """Paranormal Analyst: a card the last dread milled goes back to the hand."""
    milled = getattr(item, "context", None) if item is not None else None
    if not isinstance(milled, (tuple, list)):
        milled = game.__dict__.get("_manifest_dread_milled", ())
    milled = [c for c in milled if c in p.graveyard]
    if not milled:
        return
    best = max(milled, key=lambda c: (c.cmc, getattr(c, "power", 0) or 0))
    p.graveyard.remove(best)
    p.hand.append(best)
    game.log(f"recovers {best.name} from the dread", p)
