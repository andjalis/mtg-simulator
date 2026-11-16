"""Piles (#634 PILES): one player separates objects into two piles, another chooses one.

    Look at the top five cards of your library and separate them into a face-down pile and a face-up pile. An
    opponent chooses one of those piles. Put that pile into your hand and the other into your graveyard.
                                                                    (Curator of Destinies, Riddles in the Dark)
    Target opponent looks at the top four cards of your library and separates them into a face-down pile and a
    face-up pile. Put one pile into your hand and the other into your graveyard.  (Fortune's Favor, Atris)
    Separate all creatures target player controls into two piles. Destroy all creatures in the pile of that
    player's choice. They can't be regenerated.                                                   (Do or Die)
    −6: Separate all permanents target player controls into two piles. That player sacrifices all permanents in the
    pile of their choice.                                                                (Liliana of the Veil)
    Each opponent separates the creatures they control into two piles. For each opponent, you choose one of their
    piles. Each opponent sacrifices the creatures in their chosen pile.                       (Make an Example)
    Separate all creature cards in your graveyard into two piles. Exile the pile of an opponent's choice and
    return the other to the battlefield.                                                     (Death or Glory)

Each wording is folded (SUBS) into one ``piles`` effect. Play is the minimax both players would play from what they
can see: the chooser takes the pile best for them, so the separator splits to make that pick as bad as possible for
the chooser (exact over every split of up to 14 objects, greedy beyond). Values are the AI's card / permanent values.
A face-down pile is hidden from the chooser: they judge it at a flat value per card (``FACE_DOWN``), never by its
cards; the separator, who saw them, plays against that rule. Nothing here is random.
"""
from __future__ import annotations

import re

FACE_DOWN = 2.5         # what a chooser who can't see a face-down card counts it as

_N = r"(\w+)"
SUBS = [
    (re.compile(r"\blook at the top " + _N + r" cards of your library and separate them into a face-down pile and a "
                r"face-up pile\. an opponent chooses one of (?:those|the) piles\. put that pile into your hand and "
                r"the other into your graveyard\.?", re.I), lambda m: f"PILES libyou {_count(m[1])}."),
    (re.compile(r"\btarget opponent looks at the top " + _N + r" cards of your library and separates them into a "
                r"face-down pile and a face-up pile\. put one pile into your hand and the other into your "
                r"graveyard\.?", re.I), lambda m: f"PILES libopp {_count(m[1])}."),
    (re.compile(r"\bseparate all creatures target player controls into two piles\. destroy all creatures in the pile "
                r"of that player's choice\. they can't be regenerated\.?", re.I), lambda m: "PILES destroy 0."),
    (re.compile(r"\bseparate all permanents target player controls into two piles\. that player sacrifices all "
                r"permanents in the pile of their choice\.?", re.I), lambda m: "PILES sacperm 0."),
    (re.compile(r"\beach opponent separates the creatures they control into two piles\. for each opponent, you choose "
                r"one of their piles\. each opponent sacrifices the creatures in their chosen pile\.?"
                r"(?: \(piles can be empty\.\))?", re.I), lambda m: "PILES example 0."),
    (re.compile(r"\bseparate all creature cards in your graveyard into two piles\. exile the pile of an opponent's "
                r"choice and return the other to the battlefield\.?", re.I), lambda m: "PILES glory 0."),
]


def _count(word: str) -> int:
    from .cards import _num
    try:
        return int(_num(word.lower()))
    except (TypeError, ValueError):
        return 0


def _effect(m):
    from .cards import Effect
    from .cards.model import NO_MATCH
    family, n = m[1].lower(), int(m[2])
    if family in ("libyou", "libopp") and not n:
        return NO_MATCH
    target, filt = {"destroy": ("player", ""), "sacperm": ("player", ""), "libopp": ("player", "opp")}.get(
        family, ("none", ""))
    return Effect("piles", n, target=target, filter=filt, data={"family": family})


EFFECT_PATTERNS = [(r"PILES (libyou|libopp|destroy|sacperm|example|glory) (\d+)", _effect)]


# ------------------------------------------------------------------ the engine side

def _splits(items):
    """Every split of items into (pile A, pile B), or a greedy balanced one when there are too many."""
    n = len(items)
    if n <= 14:
        for mask in range(1 << n):
            yield ([x for i, x in enumerate(items) if mask >> i & 1], [x for i, x in enumerate(items) if not mask >> i & 1])
        return
    yield None          # the caller balances greedily


def _balanced(items, value):
    a, b, va, vb = [], [], 0.0, 0.0
    for x in sorted(items, key=value, reverse=True):
        if va <= vb:
            a.append(x); va += value(x)
        else:
            b.append(x); vb += value(x)
    return a, b


def best_split(items, value, chooser_pick, separator_score):
    """The split the separator makes: maximize separator_score(chosen, other) where the chooser picks
    chooser_pick(a, b) -> the chosen pile."""
    best = None
    for split in _splits(items):
        if split is None:
            split = _balanced(items, value)
        a, b = split
        chosen = chooser_pick(a, b)
        other = b if chosen is a else a
        score = separator_score(chosen, other)
        if best is None or score > best[0]:
            best = (score, a, b, chosen, other)
    return best[3], best[4]


def seen(down, up):
    """What a chooser sees of a (face-down pile, face-up pile) split: FACE_DOWN per hidden card, the open cards'
    values. The hidden cards themselves never enter it."""
    from .ai import card_value
    return FACE_DOWN * len(down), sum(card_value(c) for c in up)


def resolve(game, p, eff, target, item):
    from .ai import card_value
    from .engine.policy import perm_value
    fam = eff.data["family"]
    opp = game.opponent(p)
    if fam in ("libyou", "libopp"):
        cards = list(reversed(p.library[-min(eff.amount, len(p.library)):]))
        if not cards:
            return
        total = lambda pile: sum(card_value(c) for c in pile)          # noqa: E731
        if fam == "libyou":     # I separate; an opponent picks the pile I get: the one that looks worse for me
            pick = lambda down, up: down if seen(down, up)[0] < seen(down, up)[1] else up          # noqa: E731
            chosen, other = best_split(cards, card_value, pick, lambda ch, ot: total(ch))
        else:                   # the opponent separates; I pick the pile that looks better, they make it bad
            pick = lambda down, up: down if seen(down, up)[0] > seen(down, up)[1] else up          # noqa: E731
            chosen, other = best_split(cards, card_value, pick, lambda ch, ot: -total(ch))
        for c in chosen:
            game.move_card(c, p.library, p.hand, reason="piles")
        for c in other:
            game.move_card(c, p.library, p.graveyard, reason="piles")
        game.log(f"piles: {len(chosen)} card(s) to hand, {len(other)} to the graveyard", p)
        return
    if fam in ("destroy", "sacperm", "example"):
        victim = target if fam != "example" else opp
        if victim is None or victim not in game.players:
            return
        objs = list(victim.creatures if fam != "sacperm" else victim.battlefield)
        if fam == "example":    # they separate, I choose which pile they sacrifice: they keep the bigger "smaller" pile
            pick = lambda a, b: a if sum(map(perm_value, a)) >= sum(map(perm_value, b)) else b      # noqa: E731
            chosen, _ = best_split(objs, perm_value, pick, lambda ch, ot: -sum(map(perm_value, ch)))
        else:                   # I separate, the victim chooses the pile they lose: the cheaper one
            pick = lambda a, b: a if sum(map(perm_value, a)) <= sum(map(perm_value, b)) else b      # noqa: E731
            sep_sign = 1 if victim is not p else -1
            chosen, _ = best_split(objs, perm_value, pick, lambda ch, ot: sep_sign * sum(map(perm_value, ch)))
        game.log(f"piles: {victim.name} loses {[x.card.name for x in chosen]}", p)
        for x in chosen:
            if x in victim.battlefield:
                game.destroy(x, no_regen=True) if fam == "destroy" else game.sacrifice(x)
        return
    if fam == "glory":          # I separate my graveyard's creature cards; an opponent exiles the pile they fear more
        cards = [c for c in p.graveyard if c.is_creature]
        if not cards:
            return
        total = lambda pile: sum(card_value(c) for c in pile)      # noqa: E731
        pick = lambda a, b: a if total(a) >= total(b) else b     # noqa: E731
        exiled, returned = best_split(cards, card_value, pick, lambda ch, ot: total(ot))
        for c in exiled:
            game.move_card(c, p.graveyard, p.exile, reason="piles")
        for c in returned:
            p.graveyard.remove(c)
            game.enter_battlefield(p, c)
        game.log(f"piles: exiles {[c.name for c in exiled]}, returns {[c.name for c in returned]}", p)


def value(game, me, eff, target) -> float:
    """The AI's value for a piles effect it controls, from the split both players would make now."""
    from .ai import card_value
    from .engine.policy import perm_value
    fam = eff.data["family"]
    opp = game.opponent(me)
    if fam in ("libyou", "libopp"):
        n = min(eff.amount, len(me.library))
        return 1.5 * (n // 2 if fam == "libopp" else (n + 1) // 2)      # cards that reach the hand, about
    if fam in ("destroy", "sacperm", "example"):
        objs = list(opp.creatures if fam != "sacperm" else opp.battlefield)
        if not objs:
            return 0.0
        if fam == "example":
            pick = lambda a, b: a if sum(map(perm_value, a)) >= sum(map(perm_value, b)) else b      # noqa: E731
            chosen, _ = best_split(objs, perm_value, pick, lambda ch, ot: -sum(map(perm_value, ch)))
        else:
            pick = lambda a, b: a if sum(map(perm_value, a)) <= sum(map(perm_value, b)) else b      # noqa: E731
            chosen, _ = best_split(objs, perm_value, pick, lambda ch, ot: sum(map(perm_value, ch)))
        return sum(map(perm_value, chosen))
    if fam == "glory":
        cards = [c for c in me.graveyard if c.is_creature]
        total = lambda pile: sum(card_value(c) for c in pile)      # noqa: E731
        pick = lambda a, b: a if total(a) >= total(b) else b     # noqa: E731
        _, returned = best_split(cards, card_value, pick, lambda ch, ot: total(ot)) if cards else ([], [])
        return total(returned)
    return 0.0
