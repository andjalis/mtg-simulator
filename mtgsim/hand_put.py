"""Qualified "put a <card> from your hand onto the battlefield" (#331): the Elvish Piper family, widened.

    {T}: You may put a creature card with mana value equal to the number of charge counters on ~ from your
        hand onto the battlefield.                                                         (Aether Vial)
    {3}, {T}: You may put a creature card of the chosen type from your hand onto the battlefield.  (Belbe's Portal)
    you may put a permanent card with mana value less than or equal to the number of lands you control from
        your hand onto the battlefield tapped.                                             (Anticausal Vestige)
    you may put a creature card from your hand onto the battlefield tapped and attacking. (Ilharg, the Raze-Boar)
    you may put an Aura card from your hand onto the battlefield attached to ~.            (Academy Researchers)

The effect is the existing ``hand_to_battlefield`` kind; its data gains

* ``spec``: a ``cx_condlib._filter`` card filter, plus ``chosen`` (the source's chosen creature type) and
  ``any_sub`` ("an Angel, Demon, or Dragon creature card");
* ``mvq``: (op, quantity) for a mana value compared with a ``cards._xq`` quantity, evaluated when the effect
  resolves (charge counters added in response count);
* ``entry``: "tapped", "attacking" (tapped and attacking the opponent) or "attached" (an Aura attached to the
  source, which must be a legal host).

Only the controller's own hand is covered: "each player may" / "that player may" need a decision by another
player and are left unmatched, as are quantities ``_xq`` doesn't know ("that damage": #313).
"""
from __future__ import annotations

import re

_ENTRY = {"tapped": "tapped", "tapped and attacking": "attacking", "tapped and attacking that opponent": "attacking",
          "attached to ~": "attached"}
_MV_OPS = {"equal to": "==", "less than or equal to": "<=", "x or less": "<=", "x": "=="}


def _subtype_list(desc: str):
    """ "Angel, Demon, or Dragon creature" -> (["Angel", "Demon", "Dragon"], "creature")."""
    m = re.fullmatch(r"((?:[A-Z][\w'-]*, )+(?:or |and/or )[A-Z][\w'-]*|[A-Z][\w'-]* or [A-Z][\w'-]*) "
                     r"(creature|permanent)", desc)
    if not m:
        return None
    subs = [s for s in re.split(r", (?:or |and/or )?| or ", m[1]) if s]
    return subs, m[2]


def _spec(desc: str):
    from .cx_condlib import _filter
    listed = _subtype_list(desc)
    if listed:
        return {"types": [listed[1]], "any_sub": listed[0]}
    spec = _filter(desc, plural=False)
    if not spec:
        return None
    if spec.get("sub") and not spec.get("types") and spec["sub"] != ["Equipment"] and spec["sub"] != ["Aura"]:
        # "a Vampire card" is a creature or a tribal/kindred card: keep it as a permanent card only
        spec["types"] = ["permanent"]
    return spec


def _build(m):
    from .cards.model import Effect, NO_MATCH
    from .cards.clauses import _xq
    spec = _spec(m["desc"])
    if spec is None:
        return NO_MATCH
    if m["chosen"]:
        if spec.get("types") != ["creature"] or len(spec) != 1:
            return NO_MATCH
        spec["chosen"] = True
    data = {"spec": spec}
    op = (m["op"] or "").lower()
    if op:
        if op in ("x or less", "x"):
            q = m["where"]
        else:
            q = m["q"]
            if m["where"]:
                return NO_MATCH
        quantity = _xq(q) if q else None
        if quantity is None or quantity[0] == "stat" and quantity[1] in ("prev", "referent"):
            return NO_MATCH          # "that damage", "that creature's power": dynamic referents (#313)
        data["mvq"] = (_MV_OPS[op], quantity)
    elif m["where"]:
        return NO_MATCH
    entry = (m["entry"] or "").strip().lower()
    if entry:
        data["entry"] = _ENTRY[entry]
        if data["entry"] == "attached" and spec.get("sub") != ["Aura"]:
            return NO_MATCH
        if data["entry"] == "attacking" and "creature" not in spec.get("types", ()) and not spec.get("any_sub"):
            return NO_MATCH          # a noncreature permanent "attacking" (Summoner's Grimoire) is not modelled
    if spec.get("sub") == ["Aura"] and data.get("entry") != "attached":
        return NO_MATCH              # a bare Aura put from hand: the host choice is not modelled here
    if m["sac"]:
        data["sac_eot"] = True
    return Effect("hand_to_battlefield", data=data)


# "... onto the battlefield. Sacrifice it at the beginning of the next end step." (Planebound Accomplice): the
# "it" is the card this effect put, which an untargeted effect can't hand on as "prev"; fold it into the put.
SUBS = [
    (re.compile(r"(from your hand onto the battlefield)\. Sacrifice it at the beginning of the next end step\.", re.I),
     r"\1 HANDPUT_SAC_EOT."),
]

_MV = r"(?: with mana value (?P<op>equal to|less than or equal to|X or less|X)(?: (?P<q>(?!from\b).+?))?)?"
EFFECT_PATTERNS = [
    (r"(?:you may )?put (?:an?|one) (?P<desc>[\w ,'/-]+?) card(?P<chosen> of the chosen type)?" + _MV +
     r" from your hand onto the battlefield(?: (?P<entry>tapped and attacking(?: that opponent)?|tapped|attached to ~))?"
     r"(?:, where X is (?P<where>.+?))?(?P<sac> HANDPUT_SAC_EOT)?", _build),
]


# ------------------------------------------------------------------ the engine side

def candidates(game, p, eff, item) -> list:
    """The cards in p's hand this effect may put onto the battlefield right now."""
    from .cx_condlib import _card_ok
    from .engine.state import Permanent
    data = eff.data
    spec = dict(data["spec"])
    src = item.source if item is not None and isinstance(getattr(item, "source", None), Permanent) else None
    chosen = spec.pop("chosen", False)
    any_sub = spec.pop("any_sub", None)
    if chosen and not (src is not None and getattr(src, "chosen_type", "")):
        return []
    if "mvq" in data:
        op, q = data["mvq"]
        spec["mv"] = [op, game.x_quantity(p, q, item, None)]
    out = []
    for c in p.hand:
        if not c.is_permanent or not _card_ok(c, spec):
            continue
        if chosen and src.chosen_type not in c.subtypes:
            continue
        if any_sub and not any(s in c.subtypes for s in any_sub):
            continue
        if data.get("entry") == "attached" and not _host_ok(game, p, c, src):
            continue
        out.append(c)
    return out


def _host_ok(game, p, card, host) -> bool:
    from . import auras
    return bool(card.aura) and host is not None and auras.can_attach(game, p, card, host, source=card, targeting=False)


def choose(game, me, cards, entry):
    """Default policy for ``choose_hand_put``: the card to put, or None to decline.

    Skips a legendary card whose name me already controls (the legend rule would cost one of them); an
    attacker is chosen by power, anything else by mana value."""
    names = {x.card.name for x in me.battlefield if x.card.legendary}
    pool = [c for c in cards if not (c.legendary and c.name in names)]
    if not pool:
        return None
    if entry == "attacking":
        return max(pool, key=lambda c: (int(c.power or 0) if str(c.power or "0").isdigit() else 0, c.cmc))
    return max(pool, key=lambda c: c.cmc)


def resolve(game, p, eff, item):
    from .engine.state import Permanent
    cards = candidates(game, p, eff, item)
    entry = eff.data.get("entry", "")
    card = game.hook(p, "choose_hand_put")(game, p, cards, entry) if cards else None
    if card is None or card not in cards:
        return None
    src = item.source if item is not None and isinstance(getattr(item, "source", None), Permanent) else None
    p.hand.remove(card)
    if entry == "attached":
        game._aura_host = src
        try:
            perm = game.enter_battlefield(p, card)
        finally:
            game._aura_host = None
    elif entry == "attacking":
        in_combat = game.step in ("declare_attackers", "declare_blockers")
        # Put onto the battlefield attacking: it was never declared, so "whenever ~ attacks" doesn't trigger.
        # Outside combat it just enters tapped.
        perm = game.enter_battlefield(p, card, tapped_attacking=in_combat, tapped=not in_combat)
    else:
        perm = game.enter_battlefield(p, card, tapped=entry == "tapped")
    game.log(f"puts {card.name} onto the battlefield" + (f" ({entry})" if entry else ""), p)
    if perm is not None and eff.data.get("sac_eot"):
        from .cards.model import Effect
        game.delayed_end_step.append((p, [Effect("sac_now")], src, perm))
    return perm


def value(game, me, eff, source) -> float:
    """AI worth of the put before it is activated: the mana value of the card it would choose (0: nothing)."""
    from types import SimpleNamespace
    from .engine.state import Permanent, StackItem
    src = source.source if isinstance(source, StackItem) else source
    item = SimpleNamespace(source=src if isinstance(src, Permanent) else None, card=getattr(src, "card", None),
                           context=None)
    cards = candidates(game, me, eff, item)
    card = game.hook(me, "choose_hand_put")(game, me, cards, eff.data.get("entry", "")) if cards else None
    return float(card.cmc) + 1 if card is not None else 0.0
