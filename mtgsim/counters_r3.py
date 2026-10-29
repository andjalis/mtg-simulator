"""O4 round 3: small counter and ability templates.

* "put a +1/+1 counter on target creature an opponent controls" (Sunset Saboteur): a ``p1_counters`` effect with
  the ``opp`` filter. The AI puts it on the opposing creature that is worth least.
* "that many" after "Whenever you discard one or more cards" (Marauding Mako, Scrounging Skyray): the discard
  trigger fires once per card discarded, so each firing is "one" (see ``that_many``), which totals the same.
  Other "that many" antecedents (damage, life, counters) are not matched and stay unsupported.
* "Activate only if an opponent lost life this turn" (Hired Claw): ``Activated.condition = "opp_lost_life"``, checked
  by ``Game.can_activate`` against the per-turn ``Player.lost_life_turn``; "and only once each turn" sets ``once``.
* "Exile target creature you control, then return that card to the battlefield under its owner's control [with
  N +1/+1 counters on it]" (Daydream): a ``blink`` effect. The card comes back as a new object, so its enters
  triggers fire and it loses its counters and damage. Tokens cease to exist.
* "~ gains indestructible until end of turn. Tap it." (Iron-Shield Elf): "tap it" is only read as "tap ~" right
  after that grant, so "Tap it." elsewhere (where "it" may be another permanent) stays unsupported.
* "Whenever ~ attacks while you control a creature with power N or greater" (Nighthowl Pursuer): the attack trigger
  with the existing ``power_ge`` intervening-if.
"""
from __future__ import annotations

import re

_NUM = r"(a|an|one|two|three|four)"


def _blink(m):
    from .cards import Effect, _num  # at match time: this module loads before cards
    n = _num(m[2]) if m[2] else 0
    return Effect("blink", target="creature_mine", data={"counters": n} if n else {})


def that_many(events, rest: str) -> str:
    """Rewrite "that many" for triggers whose antecedent is one card at a time (discard)."""
    if events == ("you_discard",):
        return re.sub(r"\bthat many\b", "one", rest)
    return rest


EFFECT_PATTERNS = [
    (rf"put {_NUM} \+1/\+1 counters? on target creature an opponent controls",
     lambda m: _opp_counter(m)),
    (r"exile target creature you control, then return (?:that card|it) to the battlefield under (its owner's|your) "
     r"control(?: with (a|one|two|three) \+1/\+1 counters? on it)?", _blink),
    (r"tap ~", lambda m: _tap_self()),
]


def _opp_counter(m):
    from .cards import Effect, _num
    return Effect("p1_counters", _num(m[1]), target="creature", filter="opp")


def _tap_self():
    from .cards import Effect
    return Effect("tap", 1, target="self")


# "tap it" means the elf itself only right after its own indestructible grant.
SUBS = [
    (re.compile(r"(~ gains indestructible until end of turn)\. tap it\.", re.I), lambda m: f"{m[1]}. Tap ~."),
]


def blink(game, p, target, eff):
    """Exile target and return it at once; counters from the effect go on the new object."""
    from .engine import Permanent
    if not (isinstance(target, Permanent) and target in target.controller.battlefield):
        return
    owner, card, token = target.owner, target.front, target.front.is_token
    name = target.card.name
    if not game.leave_battlefield(target, "exile") or token:
        return
    if card in owner.exile:
        owner.exile.remove(card)
    n = eff.data.get("counters", 0)
    game.enter_battlefield(owner, card, counters={"+1/+1": n} if n else None)
    game.log(f"{name} is exiled and returns", p)


def blink_target(game, me, legal):
    """The creature that gains most from a blink: enters-the-battlefield triggers, few counters to lose."""
    def key(x):
        etb = len(x.card.etb_effects) + sum(t.event == "etb" for t in x.card.triggers)
        return (etb > 0, -sum(x.counters.values()) - x.damage, etb, -x.tapped)
    return max(legal, key=key, default=None)
