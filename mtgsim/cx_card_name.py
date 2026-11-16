"""Naming a card, then checking a hidden card against the name (#627):

    {3}, {T}: Choose a card name, then reveal a card at random from your hand. If that card has the chosen name,
    ~ deals 2 damage to any target.                                                    (Cursed Scroll, Magus of the Scroll)
    Choose a nonland card name, then reveal the top card of your library. If that card has the chosen name, you draw
    three cards.                                                                       (Mise)
    Choose a card name, then target opponent mills a card. If a card with the chosen name was milled this way, you
    draw a card.                                                                       (Foreshadow, Lammastide Weave)

The sentences become private ones ("NAMEGUESS hand.", "NAMEGUESS top nonland.", "NAMEMILL target opponent." then
"NAMEHIT <reward>."). ``name_guess`` names the card, then reveals / mills and sets ``item.gate_paid`` when it matches;
the reward is the ordinary effect with the existing ``paid`` condition (so the AI sees and aims "deals 2 damage to any
target" as it does any damage ability).

The name comes only from information the player has (never the actual hidden card):
- your hand: the card you hold the most copies of;
- your library: the most common nonland card left in your decklist after the cards you have seen (hand,
  battlefield, graveyard, exile);
- an opponent's library: the most common card among their public cards (battlefield, graveyard, exile).
Ties go to the alphabetically first name, so every pick is deterministic.
"""
from __future__ import annotations

import re
from collections import Counter

_REWARD = r"if (?:that card has the chosen name|a card with the chosen name was milled this way), ([^.]+)\."
SUBS = [
    (re.compile(r"choose a card name, then reveal a card at random from your hand\. " + _REWARD, re.I),
     lambda m: f"NAMEGUESS hand. NAMEHIT {m[1]}."),
    (re.compile(r"choose a (nonland )?card name, then reveal the top card of your library\. " + _REWARD, re.I),
     lambda m: f"NAMEGUESS top{' nonland' if m[1] else ''}. NAMEHIT {m[2]}."),
    (re.compile(r"choose a card name, then (target opponent|target player) mills a card\. " + _REWARD, re.I),
     # a reward about the milled card itself ("you gain life equal to its mana value") is not read: "its" would
     # name the targeted player there
     lambda m: m[0] if re.search(r"\bits\b", m[2], re.I) else f"NAMEMILL {m[1]}. NAMEHIT {m[2]}."),
]


def _guess(m):
    from .cards.model import Effect
    return Effect("name_guess", data={"where": m[1].lower(), "nonland": bool(m[2])})


def _mill(m):
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    new, bad = _parse_effects(f"{m[1][0].upper()}{m[1][1:]} mills a card.")
    if bad or len(new) != 1 or new[0].kind != "mill":
        return NO_MATCH
    import dataclasses
    return dataclasses.replace(new[0], kind="name_guess", data=dict(new[0].data, where="mill", nonland=False))


def _hit(m):
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    import dataclasses
    new, bad = _parse_effects(m[1][0].upper() + m[1][1:] + ".")
    if bad or not new or any(e.cond for e in new):
        return NO_MATCH
    return [dataclasses.replace(e, cond="paid") for e in new]


EFFECT_PATTERNS = [
    (r"nameguess (hand|top)( nonland)?", _guess),
    (r"namemill (target opponent|target player)", _mill),
    (r"namehit (.+)", _hit),
]


def _best(counts: Counter) -> str:
    return min(counts, key=lambda n: (-counts[n], n)) if counts else ""


def name_for(game, p, where: str, nonland: bool, who=None) -> str:
    """The name p chooses, from what p is allowed to know (see the module doc)."""
    if where == "hand":
        return _best(Counter(c.name for c in p.hand))
    if where == "top":
        left = Counter(c.name for c in p.deck if not (nonland and c.is_land))
        seen = Counter(c.name for c in list(p.hand) + list(p.graveyard) + list(p.exile))
        seen.update(x.card.name for x in p.battlefield)
        return _best(Counter({n: k for n, k in (left - seen).items() if k > 0}))
    who = who or game.opponent(p)
    public = Counter(c.name for c in list(who.graveyard) + list(who.exile))
    public.update(x.card.name for x in who.battlefield if not x.card.is_token)
    return _best(public)


def resolve(game, p, eff, target, item):
    """The name_guess kind."""
    from .engine.state import Player
    where = eff.data["where"]
    if item is not None:
        item.gate_paid = False
    who = target if isinstance(target, Player) else None
    name = name_for(game, p, where, eff.data.get("nonland", False), who)
    game.log(f"names {name or 'nothing'}", p)
    if where == "hand":
        card = game.rng.choice(list(p.hand)) if p.hand else None
    elif where == "top":
        card = p.library[-1] if p.library else None
    else:
        if who is None:
            return
        from .engine.kinds import HANDLERS
        import dataclasses
        HANDLERS["mill"](game, p=p, eff=dataclasses.replace(eff, kind="mill", amount=1), target=who, item=item,
                         opp=game.opponent(p))
        card = who.milled_last[0] if getattr(who, "milled_last", None) else None
    if card is not None:
        game.log(f"reveals {card.name}", p)
    if item is not None and card is not None and name and card.name == name:
        item.gate_paid = True
