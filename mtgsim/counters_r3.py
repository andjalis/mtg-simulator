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
* "when you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter" (Kumano
  Faces Kakkazan chapter II): the existing ``next_creature_counter`` effect.
* "Other creatures you control enter with an additional +1/+1 counter on them for each opponent who lost life this
  turn" (Gev): ``CardDef.others_enter_counters``, applied by ``enter_bonus`` as a creature enters.
* "put X +1/+1 counters on target attacking creature, where X is the number of permanents you've sacrificed this turn.
  If X is three or more, that creature gains lifelink" (Obsessive Pursuit): the old "three or greater" template
  already existed; "three or more" is the same sentence.
* "exile up to one target creature card from a graveyard. If a card is put into exile this way, look at the top
  three cards of your library, then put one of those cards into your hand and the rest into your graveyard"
  (Corpse Appraiser): ``appraise``. The graveyard card is chosen on resolution (the engine has no graveyard
  targets), the best creature card, opposing graveyard first.
* "Choose one of them. Until end of turn, you may play that card." after exiling the top cards (Fireglass Mentor):
  ``may_play_exiled`` with ``one``: only the most valuable exiled card can be played.
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
    (r"when you next cast a creature spell this turn, that creature enters with an additional \+1/\+1 counter on it",
     lambda m: _next_counter()),
    (r"OBSESSIVE", lambda m: _obsessive()),
    (r"APPRAISE (\w+)", lambda m: _appraise(m)),
    (r"PLAYONE", lambda m: _play_one()),
]


def _opp_counter(m):
    from .cards import Effect, _num
    return Effect("p1_counters", _num(m[1]), target="creature", filter="opp")


def _next_counter():
    from .cards import Effect
    return Effect("next_creature_counter")


def _obsessive():
    from .cards import Effect
    return Effect("add_counter", 0, target="creature_mine", filter="attacking_blocking",
                  data={"counter": "+1/+1", "x": "sacrificed"})


def _appraise(m):
    from .cards import Effect, _num
    return Effect("appraise", _num(m[1]))


def _play_one():
    from .cards import Effect
    return Effect("may_play_exiled", 0, data={"one": True})


def _tap_self():
    from .cards import Effect
    return Effect("tap", 1, target="self")


# "tap it" means the elf itself only right after its own indestructible grant.
SUBS = [
    (re.compile(r"put x \+1/\+1 counters on target attacking creature, where x is the number of permanents you've "
                r"sacrificed this turn\. if x is three or more, that creature gains lifelink until end of turn\.", re.I),
     lambda m: "OBSESSIVE."),
    (re.compile(r"exile up to one target creature card from a graveyard\. if a card is put into exile this way, look at "
                r"the top (\w+) cards of your library, then put one of those cards into your hand and the rest into your "
                r"graveyard\.", re.I), lambda m: f"APPRAISE {m[1]}."),
    (re.compile(r"choose one of them\. until end of turn, you may play that card\.", re.I), lambda m: "PLAYONE."),
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


def enter_bonus(game, p, perm) -> int:
    """+1/+1 counters perm gets entering under p: Gev gives one per opponent who lost life this turn."""
    if not any(x.card.others_enter_counters == "opp_lost_life" for x in p.battlefield):
        return 0
    lost = sum(opp.lost_life_turn for opp in game.players if opp is not p)
    return lost * sum(x.card.others_enter_counters == "opp_lost_life" for x in p.battlefield)


def appraise(game, p, eff):
    """Exile the best creature card from a graveyard (an opponent's first), then keep the best of the top cards."""
    pool = [(c, pl) for pl in sorted(game.players, key=lambda pl: pl is p) for c in pl.graveyard if c.is_creature]
    if not pool:
        return
    card, owner = max(pool, key=lambda t: (t[1] is not p, t[0].cmc))
    game.move_card(card, owner.graveyard, owner.exile, reason="exile")
    game.log(f"exiles {card.name} from {owner}'s graveyard", p)
    from .ai import card_value
    top = [p.library.pop() for _ in range(min(eff.amount, len(p.library)))]
    if not top:
        return
    keep = max(top, key=card_value)
    p.hand.append(keep)
    for c in top:
        if c is not keep:
            p.graveyard.append(c)
    game.log(f"keeps {keep.name} and puts {len(top) - 1} card(s) into the graveyard", p)
