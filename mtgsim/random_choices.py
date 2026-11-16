"""Random choices (#634 RANDOM): random numbers, targets chosen at random, and more "at random" wordings.

    Create an X/X black Zombie creature token, where X is a number from 2 to 6 chosen at random. (Murgish Cemetery)
    {T}: This creature deals 2 damage to any target chosen at random.                         (Goblin Test Pilot)
    When this creature enters, it fights target creature an opponent controls chosen at random. (Scab-Clan Giant)
    At the beginning of your upkeep, reveal a card from your hand at random.               (Goblin Secret Agent)
    Look at a card at random in target player's hand.                                          (Urza's Bauble)
    Exile a card at random from your graveyard.

Every random outcome comes from the game's seeded generator (``game.rng``), so a game replays the same way.

- "a number from A to B chosen at random" is a quantity for the shared ", where X is ..." reader:
  ``("cxq", "random", A, B)``, drawn once when the effect resolves (``cx_grammar_quantity.value``).
- "<a targeted effect> chosen at random": the effect parses as written and is marked ``random_target``; its target
  is then drawn uniformly from its legal targets when targets are chosen (``Game.auto_targets``), whatever the AI
  would have picked. Only a targeted body is read: "a creature an opponent controls chosen at random" (not
  targeted, so hexproof doesn't stop it) is left alone.
- Revealing or looking at a random card is information only: the existing ``reveal_random`` kind picks the card
  (so "that card" can refer to it) and nothing else changes.
"""
from __future__ import annotations

import re

_TARGETED_RANDOM = re.compile(r"(.*?\btarget\b.*?) chosen at random(.*)", re.I)


def _random_target(m):
    from .cards.model import NO_MATCH
    from .cards.parse import _parse_effects
    from .engine.state import TARGETED
    body = m[1] + m[2]
    if re.search(r"\bwhere X is\b|\bnumber from\b", body, re.I):
        return NO_MATCH
    effects, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    targeted = [e for e in effects if e.target in TARGETED and e.target not in ("self", "prev", "multi")]
    if bad or len(targeted) != 1:
        return NO_MATCH
    for e in targeted:
        e.data["random_target"] = True
    return effects


def _reveal(target):
    def make(m):
        from .cards import Effect
        return Effect("reveal_random", target=target, data={"side": "theirs"} if target != "none" else {})
    return make


def _exile_random(m):
    from .cards import Effect
    return Effect("cx_players", data={"who": "you", "effects": [Effect(
        "cx_card_choose", 1, data={"to": "exile", "cx_card": {"types": []}, "up_to": False, "random": True})]})


EFFECT_PATTERNS = [
    (r"(?:you )?reveal a card (?:from your hand at random|at random from your hand)", _reveal("none")),
    (r"that player reveals a card at random from their hand", _reveal("that_player")),
    (r"look at a card at random in target player's hand", _reveal("player")),
    (r"exile a card at random from your graveyard", _exile_random),
    (_TARGETED_RANDOM.pattern, _random_target),
]

SUBS = [
    # "Target opponent loses 2 life, then reveals a card at random from their hand." (Hired Torturer)
    (re.compile(r", then reveals a card at random from their hand\.", re.I),
     ". That player reveals a card at random from their hand."),
]


def quantity(low: str):
    """("cxq", "random", A, B) for "a number from A to B chosen at random", else None."""
    m = re.fullmatch(r"a number from (\d+) to (\d+) chosen at random", low)
    if m and int(m[1]) <= int(m[2]):
        return ("cxq", "random", int(m[1]), int(m[2]))
    return None


def value(game, spec) -> int:
    return game.rng.randint(spec[2], spec[3])


def pick_target(game, p, eff):
    """A random legal target for an effect "chosen at random", or None when there is none."""
    legal = list(game.legal_targets(p, eff))
    return game.rng.choice(legal) if legal else None


def reroll(game, p, effects, targets) -> list:
    """An explicit target list with each "chosen at random" slot drawn again (the caster doesn't choose it)."""
    targets = list(targets)
    for i, e in enumerate(effects):
        if i < len(targets) and e.data.get("random_target"):
            targets[i] = pick_target(game, p, e)
    return targets


def side_balance(game, me, effects) -> float:
    """For effects with a target "chosen at random": (legal targets on the opponent's side - on mine) / all of them,
    the share of the time a random pick lands where we want it, net. 1.0 when nothing is random."""
    from .engine.state import Permanent
    balance = 1.0
    for e in effects:
        if not e.data.get("random_target"):
            continue
        legal = list(game.legal_targets(me, e))
        if not legal:
            return 0.0
        mine = sum(1 for t in legal if (t.controller if isinstance(t, Permanent) else t) is me)
        balance = min(balance, (len(legal) - 2 * mine) / len(legal))
    return balance
