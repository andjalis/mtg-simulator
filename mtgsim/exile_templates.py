"""Exile family templates: self-exile payoffs, hand-exile O-rings, temporary reanimation.

Joined at the end of ``cards/__init__.py``. MAYEXILESELF rewrites "you may exile it. If
you do, <payoff>" inside a dies trigger; EXILEHAND/HANDEXILE cover the "reveal their hand,
choose a card, exile it" cluster (the until-~-leaves variant reuses the HANDEXILE sentinel
that cards/patterns.py already turns into a hand_exile effect); REANIMTEMP covers "return
a creature card from your graveyard ... gains haste ... exile it at the next end step".
"""
from __future__ import annotations

import re


EFFECT_PATTERNS = [
    (r"MAYEXILESELF (.+)", lambda m: _exile_self(m)),
    (r"PROCESSEXILE (.+)", lambda m: _process(m)),
    (r"EXILEHAND (.+)", lambda m: _e("exile_hand_perm", target="player", filter=m[1])),
    # Redundant with the engine's exiled_cards / exiled_to_hand return-on-leaves: the
    # exile effect that took the card in the first place puts it back when ~ leaves.
    (r"return(?:s)? the exiled cards? to (?:its|their) (?:owner's|owners') hands?",
     lambda m: _e("exiled_returned")),
    (r"REANIMTEMP (.+)", lambda m: _reanim(m)),
    (r"REANIMTOP", lambda m: _e("reanimate_temp", data={"top": True})),
]

SUBS = [
    (re.compile(r"(you may exile (?:it|this card)\. (?:if|when) you do, )(.+)", re.I), lambda m: _may_exile_sub(m)),
    # "you may put a card an opponent owns from exile into that player's graveyard. If you
    # do, <payoff>" (the Process cards: Wasteland Strangler, Ulamog's Reclaimer, ...)
    (re.compile(r"(you may put a card an opponent owns from exile into that player's graveyard\. "
                r"(?:if|when) you do, )(.+)", re.I), lambda m: _may_exile_sub(m, "PROCESSEXILE")),
    # "... reveals their hand and you choose a <filter> card from it. Exile that card. When ~
    # leaves the battlefield, return the exiled card to its owner's hand." (Mesmeric Fiend)
    (re.compile(r"(?:target|that) (?:opponent|player) reveals their hand and you choose "
                r"an? (nonland|noncreature, nonland|nonartifact, nonland|instant or sorcery) card from it\. "
                r"exile that card\.?", re.I),
     lambda m: f"HANDEXILE {m[1].lower()}."),
    # The same reveal-and-choose, but the exile is permanent (Night Terrors and friends).
    (re.compile(r"(?:target|that) (?:opponent|player) reveals their hand(?:\.| and) you choose "
                r"an? (nonland|noncreature, nonland|nonartifact, nonland|instant or sorcery) card from it\. "
                r"exile that card\.?", re.I),
     lambda m: f"EXILEHAND {m[1].lower()}."),
    # "Return target creature card from your graveyard to the battlefield. It gains haste.
    # Exile it at the beginning of the next end step." (Goryo's Vengeance, Dawn of the Dead)
    (re.compile(r"(?:you may )?return (?:the top |target |a |an? )?((?:legendary )?creature(?: or planeswalker)? card"
                r"(?: with mana value x)?) (?:of|from) your graveyard to the battlefield\. "
                r"(?:that creature|it) gains haste(?: until end of turn)?\. exile (?:it|them) at the "
                r"beginning of the next end step\.?", re.I),
     lambda m: _reanim_sub(m)),
]


def _may_exile_sub(m, sentinel="MAYEXILESELF"):
    """Rewrite into the sentinel only when the payoff parses; leave the original wording
    (so it stays a readable ignored line) when it does not."""
    from .cards import _parse_effects
    effects, bad = _parse_effects(m[2])
    if not effects or bad:
        return m[0]
    return f"{sentinel} {m[2]}"


def _process(m):
    """Wrap the payoff in a process_payoff effect: move an exiled card of the opponent's
    to their graveyard, then run the payoff."""
    from .cards import NO_MATCH, Effect, _parse_effects
    body = m[1].strip()
    effects, bad = _parse_effects(body[0].upper() + body[1:])
    if not effects or bad:
        return NO_MATCH
    return Effect("process_payoff", data={"effects": effects})


def _reanim_sub(m):
    top = m[0].lower().startswith(("return the top", "you may return the top"))
    return "REANIMTOP." if top else f"REANIMTEMP {m[1].lower()}."


def _reanim(m):
    from .cards import Effect
    desc = m[1]
    data = {"desc": desc}
    if desc.startswith("legendary"):
        data = {"desc": desc[len("legendary "):], "legendary": True}
    if desc.endswith("with mana value x"):
        data["desc"] = desc[:desc.index(" with mana value x")]
        data["x"] = True
    return Effect("reanimate_temp", data=data)


def _exile_self(m):
    """Wrap the payoff in an exile_self_payoff effect: exile the dead source card from its
    owner's graveyard, then run the payoff."""
    from .cards import NO_MATCH, Effect, _parse_effects
    body = m[1].strip()
    effects, bad = _parse_effects(body[0].upper() + body[1:])
    if not effects or bad:
        return NO_MATCH
    return Effect("exile_self_payoff", data={"effects": effects})


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)
