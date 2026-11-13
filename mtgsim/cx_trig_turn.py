"""Temporary triggers created by an effect (#399): "Whenever a creature attacks this turn, put a +1/+1 counter on
it", "Whenever you cast a creature spell this turn, draw a card", "When a creature dies this turn, ...".

The sentence's head without "this turn" must be one the trigger-event library reads (``cx_events.compile_head``)
and its effects must parse on their own, exactly as ``cx_events.split_head`` requires of a printed trigger. The
effect ``cx_turn_trigger`` (data: head, effects, once) records a watcher for the resolving player until the turn
ends; ``observe`` (called from ``Game.fire``) matches each fired event with the same ``cx_events._match`` a printed
"ev:" trigger uses, with the watcher's controller as "you", and queues the effects ("it" is the event's object, as
for a printed trigger). "When ..." (not "Whenever") triggers once.

Refused: heads naming "~", "it", "that creature" or "this way" (they would have to bind to an object chosen when the
spell resolved: cx_trig_watch covers "When that creature dies this turn"), and effects that refer to "~".
"""
from __future__ import annotations

import re

KINDS = {"cx_turn_trigger"}

_SENTENCE = re.compile(r"(?P<head>(?P<when>When(?:ever)?) (?P<event>.+?)) this turn, (?P<body>.+)", re.I)
_BACKREF = re.compile(r"(?:~|\bit\b|\bthat (?:creature|permanent|card|spell)\b|\bthis way\b|\bthose\b|\bthem\b)", re.I)


def parse(sentence: str):
    """[Effect] for one "Whenever <head> this turn, <effects>" sentence, or None."""
    from .cards import Effect
    from .cards.parse import _parse_effects
    from . import cx_events
    from . import cx_tokens as _cx_tokens
    m = _SENTENCE.fullmatch(sentence.strip().rstrip("."))
    if not m or _BACKREF.search(m["event"]) or "this turn" in m["event"].lower():
        return None
    head = f"{m['when'][0].upper()}{m['when'][1:].lower()} {m['event']}"
    got = cx_events.compile_head(head)
    if got is None:
        return None
    body = m["body"].replace(" ;; ", ". ")      # the later sentences of the same ability (SUBS below)
    if re.search(r"~", body):
        return None              # the spell isn't on the battlefield to be "~"
    with _cx_tokens.event_amount_ctx(got[0]):
        effects, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    if bad or not effects:
        return None
    return [Effect("cx_turn_trigger", data={"head": head, "effects": effects,
                                            "once": m["when"].lower() == "when"})]


def _build(m):
    from .cards import NO_MATCH
    out = parse(m[0])
    return NO_MATCH if out is None else out


# Sentences after "Whenever <event> this turn, A." belong to that trigger ("... create two tokens that are tapped
# and attacking. Sacrifice them at the beginning of the next end step."): keep them in one sentence, joined by " ;; ".
SUBS = [
    (re.compile(r"(\bWhen(?:ever)? [^.;]+? this turn, [^.]+)\.((?: [A-Z][^.]*\.)+)\s*$"),
     lambda m: _join(m)),
]


def _join(m):
    """The joined sentence when it reads as one temporary trigger, else the text unchanged (other templates own
    "When you next cast ... this turn, copy that spell. You may choose new targets for the copy.")."""
    joined = m[1] + "".join(" ;; " + x.strip().rstrip(".") for x in re.findall(r" [A-Z][^.]*\.", m[2]))
    lead = re.search(r"\bWhen(?:ever)? ", joined)
    return joined + "." if lead and parse(joined[lead.start():]) is not None else m[0]

EFFECT_PATTERNS = [
    (r"When(?:ever)? .+? this turn, .+", _build),
]


def resolve(game, p, eff, target, item):
    """Register the watcher for the rest of this turn."""
    from .engine.state import Permanent
    card = item.card if item is not None and item.card is not None else getattr(getattr(item, "source", None),
                                                                                   "card", None)
    if card is None:
        return
    host = Permanent(card, p)      # never on the battlefield: "you" for the head, the name for the log
    watchers = game.__dict__.setdefault("cx_turn_watchers", [])
    watchers.append({"turn": game.turn, "controller": p, "head": eff.data["head"], "effects": list(eff.data["effects"]),
                     "once": eff.data["once"], "host": host, "batch": {}})
    game.log(f"{eff.data['head'].lower()} this turn: watching", p)


def observe(game, p, event, source=None, context=None, subject=None):
    """Queue the effects of every live watcher this fired event matches (cx_events.observe's rules)."""
    watchers = game.__dict__.get("cx_turn_watchers")
    if not watchers:
        return
    from . import cx_events
    live = [w for w in watchers if w["turn"] == game.turn]
    if len(live) != len(watchers):
        watchers[:] = live
    if event not in cx_events._OBSERVED or not live:
        return
    if event == "perm_to_gy" and source is not None:
        return
    if event == "any_cast" and getattr(context, "controller", context) is not p:
        return
    from .residual_templates import trigger_suppressed
    if trigger_suppressed(game, event, source, context, subject):
        return
    for w in list(live):
        got = cx_events.compile_head(w["head"])
        if got is None or event not in got[0]:
            continue
        spec = got[1]
        ctx = cx_events._match(game, spec, event, w["host"], p, source, context, subject,
                               any(e.target in ("that_player", "that_controller") for e in w["effects"]))
        if ctx is False:
            continue
        if spec.get("batch"):           # "one or more ...": once per batch of simultaneous events
            stamp = (game.turn, game.step, id(getattr(game, "resolving_item", None)))
            if w["batch"].get("stamp") == stamp:
                continue
            w["batch"]["stamp"] = stamp
        if w["once"]:
            watchers.remove(w)
        effects = w["effects"]
        amount = getattr(game, "event_amount", None)
        if amount is not None and any(e.data.get("that_much") for e in effects):     # "loses that much life"
            import dataclasses
            effects = [dataclasses.replace(e, amount=amount) if e.data.get("that_much") else e for e in effects]
        game.queue_trigger(w["controller"], effects, None, w["host"].card.name, ctx)

