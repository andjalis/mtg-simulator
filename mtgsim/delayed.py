"""Narrow, object-bound next-end-step templates and a shared delayed-trigger queue.

Only complete exile/return pairs and haste/sacrifice/exile/destroy continuations
bound directly to token creation are accepted. Unrecognized conditions and unbound
pronouns remain unsupported.
"""
from __future__ import annotations

import dataclasses
import re


# Fold the pair before the ordinary sentence parser can mistake exile for destroy.
_BLINK = re.compile(
    r"exile (?P<desc>(?:up to one )?(?:other |another )?target "
    r"(?:creature or artifact|artifact or creature|nontoken creature|creature|nonland permanent)"
    r"(?: you control)?(?: without flying)?)\. "
    r"return (?:it|that card) to the battlefield under its owner's control"
    r"(?P<counter> with a flying counter on it)? at the beginning of the next end step\.", re.I)
SUBS = [(_BLINK, lambda m: f"DELAYEDBLINK {m['desc']}"
         f"{' FLYINGCOUNTER' if m['counter'] else ''}.")]


def blink(m):
    from .cards import Effect
    desc = m[1].lower()
    return Effect("blink_delayed", target="nonland_perm", data={
        "what": "artifact or creature" if "artifact" in desc else
                "nonland permanent" if "nonland" in desc else "creature",
        "mine": "you control" in desc, "other": "other " in desc or "another " in desc,
        "upto": "up to one" in desc,
        "nontoken": "nontoken" in desc, "no_flying": "without flying" in desc,
        "flying_counter": bool(m[2]),
    })


EFFECT_PATTERNS = [(r"DELAYEDBLINK (.+?)( FLYINGCOUNTER)?", blink)]


def continuation(effects, sentence):
    """Bind a known continuation to the immediately preceding token creation.

Require an uninterrupted, unconditional creation/continuation chain. Never infer a
referent across an unsupported sentence or an unrelated intervening effect.
"""
    if not effects or effects[-1].kind not in ("token", "copy_perm") or effects[-1].cond:
        return False
    creator = effects[-1]
    m = re.fullmatch(r"(?:it|that token|the token|they|those tokens) gains? haste(?: until end of turn)?", sentence, re.I)
    if m:
        creator.data = dict(creator.data, created_haste=True)
        return True
    m = re.fullmatch(r"(sacrifice|exile|destroy) (?:it|them|that token|the token|those tokens|the tokens) "
                     r"at the beginning of "
                     r"(the|your) next end step", sentence, re.I)
    if m:
        action = (m[1].lower(), "mine" if m[2].lower() == "your" else "any")
        creator.data = dict(creator.data, delayed_actions=[*creator.data.get("delayed_actions", ()), action])
        return True
    return False


@dataclasses.dataclass
class Scheduled:
    controller: object
    effect: object
    context: object
    source: object
    name: str
    after_event: int
    scope: str = "any"


def schedule(game, controller, effect, context, source=None, name="delayed effect", scope="any"):
    game.delayed.append(Scheduled(controller, effect, context, source, name, game.end_step_event, scope))


def end_step(game, active):
    # Advance the event BEFORE queueing anything: effects created by end-step
    # triggers or responses cannot see the event that has already begun.
    game.end_step_event += 1
    pending, game.delayed = game.delayed, []
    for entry in pending:
        if entry.after_event < game.end_step_event and (entry.scope == "any" or entry.controller is active):
            game.queue_trigger(entry.controller, [entry.effect], entry.source, entry.name,
                               context=entry.context, targets=[None])
        else:
            game.delayed.append(entry)


_BOUND = ("delayed_sacrifice", "delayed_exile", "delayed_destroy")


def prune(game, perm):
    """Drop pending sacrifice/exile/destroy entries bound to ``perm``, which has left the battlefield.

A new object never inherits them, so they could only resolve as no-ops. Order of the other
entries and the one-time semantics of the rest are untouched.
"""
    if game.delayed:
        game.delayed[:] = [e for e in game.delayed if not (e.effect.kind in _BOUND and e.context is perm)]


def sacrifice_later(game, controller, perm, source=None, scope="any"):
    action_later(game, controller, perm, "sacrifice", source, scope)


def action_later(game, controller, perm, action, source=None, scope="any"):
    from .cards import Effect
    schedule(game, controller, Effect(f"delayed_{action}"), perm, source,
             f"{perm.card.name} delayed {action}", scope)


def created(game, controller, perm, data, source=None):
    """Apply continuations to each exact object made by a token/copy effect."""
    if data.get("created_haste"):
        perm.temp_kw.add("haste")
    for action, scope in data.get("delayed_actions", ()):
        action_later(game, controller, perm, action, source, scope)
    # Copy templates fold the legacy sacrifice wording into the creation clause.
    if data.get("mods", {}).get("sac_end"):
        sacrifice_later(game, controller, perm, source)


def resolve(game, p, eff, target, item):
    from .cards import Effect
    if eff.kind == "blink_delayed":
        if target is None or target not in target.controller.battlefield:
            return
        owner = target.owner
        # CardDef instances are shared by deck copies. Give this zone object a
        # distinct identity; ExileZone also detects a leave-and-reenter cycle.
        card = dataclasses.replace(target.front)
        token = target.front.is_token
        if game.leave_battlefield(target, "exile") and not token:
            zone = owner.exile
            # leave_battlefield appends this physical card last. Earlier copies
            # may share the same CardDef instance, so do not search by equality.
            zone[-1] = card
            context = (owner, card, zone.version(card))
            schedule(game, p, Effect("delayed_return", data=eff.data), context,
                     item.source if item else None, f"{card.name} delayed return")
    elif eff.kind == "delayed_return":
        owner, card, version = item.context
        zone = owner.exile
        if zone.version(card) != version or not any(c is card for c in zone):
            return
        zone.remove(card)
        perm = game.enter_battlefield(owner, card)
        if eff.data.get("flying_counter"):
            perm.counters["flying"] = 1
            perm.perm_kw.add("flying")
    elif eff.kind in ("delayed_sacrifice", "delayed_exile", "delayed_destroy"):
        perm = item.context
        if perm not in perm.controller.battlefield:
            return
        # Sacrifice requires control by the delayed ability's controller; exile
        # and destroy still act on a stolen object. None of these effects target.
        if eff.kind == "delayed_sacrifice" and perm.controller is p:
            game.sacrifice(perm)
        elif eff.kind == "delayed_destroy":
            game.destroy(perm)
        elif eff.kind == "delayed_exile":
            if game.leave_battlefield(perm, "exile"):
                game.log(f"{perm.card.name} is exiled", p)
