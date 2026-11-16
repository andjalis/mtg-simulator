"""Delayed actions "at the beginning of the next end step" (and, #344, of other steps):

    Exile it at the beginning of the next end step.                    (a token, a reanimated creature, the target)
    At the beginning of the next end step, sacrifice it.               Its controller sacrifices it at ...
    Sacrifice them / the tokens / those tokens / the Devil tokens at the beginning of the next end step.
    Destroy ~ at the beginning of the next end step.                   Destroy that creature at ...
    Return it to its owner's hand at the beginning of the next end step.   Return that creature to your hand ...
    Return it to the battlefield tapped under its owner's control at the beginning of the next end step.
    At the beginning of the next end step, return that card to the battlefield ... with a +1/+1 counter on it.
    Discard three cards at the beginning of the next end step.         (any whole sentence the parser reads)

The rider turns the sentence into ``cx_delay``, which, as the ability resolves, picks the objects and puts a
``cx_delayed_do`` on ``game.delayed_end_step`` with them as context. "It" is the ability's last target, or else the
newest permanent that entered while the ability resolved (a token, a reanimated or put-onto-the-battlefield card);
"them" and "the tokens" are all the permanents that entered while it resolved. A returned card is the exiled card
of the target (or of ~); it comes back only if it is still in exile.

Other timings (#344) keep the same actions but wait in ``game.cx_delayed_at`` until their step really begins
(``at_step``, called from the turn structure):

    at the beginning of the next turn's upkeep / the next upkeep    the next upkeep of any player
    at the beginning of your next upkeep                            the controller's next upkeep
    at the beginning of their / that player's next upkeep           that player's (fixed as the ability resolves)
    at the beginning of your next end step                          the next end step of the controller's turn
    at the beginning of your / the next main phase this turn        this turn's next main phase, if one is left
    at the beginning of the next cleanup step                       the next cleanup step

"At the beginning of your next upkeep, pay {C}. If you don't, you lose the game." (the Pacts) is a delayed
``cx_pact``: the controller pays if it can, else loses."""
from __future__ import annotations

import dataclasses
import re

_WHEN = (r"at the beginning of (?:the next end step|your next end step|the next turn's upkeep|the next upkeep|"
         r"your next upkeep|(?:their|that player's) next upkeep|(?:your|the) next main phase this turn|"
         r"the next cleanup step)")
_TIMING = [("the next end step", "end"), ("your next end step", "end_you"), ("the next turn's upkeep", "upkeep"),
           ("the next upkeep", "upkeep"), ("your next upkeep", "upkeep_you"), ("their next upkeep", "upkeep_that"),
           ("that player's next upkeep", "upkeep_that"), ("next main phase this turn", "main"),
           ("the next cleanup step", "cleanup")]


def _timing(s: str) -> str:
    low = s.lower()
    return next(t for words, t in _TIMING if "beginning of " + words in low or
                words.startswith("next main") and words in low)
_ONE = (r"it|~|this creature|that creature|that token|the token|that card|the creature|that artifact|the artifact|"
        r"that permanent|that vehicle|that dragon|the exiled card")
_MANY = r"them|the tokens|those tokens|the [a-z]+ tokens"
_SUBJ = rf"(?P<s>{_ONE}|{_MANY})"
_ACTIONS = [
    (re.compile(rf"(?P<op>exile|sacrifice|destroy) {_SUBJ}", re.I), None),
    (re.compile(r"its controller (?P<op>sacrifices) (?P<s>it|that creature)", re.I), None),
    (re.compile(rf"return {_SUBJ} to (?:its owner's|your|their owner's|their owners') hand", re.I), "hand"),
    (re.compile(r"return (?P<s>it|~|that card|the exiled card) to the battlefield(?P<tapped> tapped)?"
                r"(?: under (?:its owner's|your) control)?(?: tapped)?(?P<counter> with a \+1/\+1 counter on it)?",
                re.I), "battlefield"),
]


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _who(subject: str) -> str:
    subject = subject.lower()
    if subject in ("~", "this creature"):
        return "self"
    if re.fullmatch(_MANY, subject):
        return "fresh"
    return "prev"


def action(text: str):
    """The cx_delay effect for one action sentence (without the timing words), or None."""
    text = text.strip().rstrip(".")
    for rx, op in _ACTIONS:
        m = rx.fullmatch(text)
        if not m:
            continue
        data = {"op": op or m["op"].lower().rstrip("s"), "who": _who(m["s"])}
        if op == "battlefield":
            data["tapped"] = bool(m["tapped"])
            data["counter"] = bool(m["counter"])
            if data["who"] == "fresh":
                return None
        return _effect("cx_delay", data=data)
    return None


_HASTE = re.compile(r"(?:it|the creature|the artifact|that [a-z]+) gains haste(?: until end of turn)?", re.I)


_BUSY = False


def parse_rider(sentence: str, effects: list) -> bool:
    """"<action> at the beginning of the next end step" or "At the beginning of the next end step, <action>".

    Also "That creature gains haste." after an untargeted put-onto-the-battlefield effect (Sneak Attack): the newest
    permanent that entered while the ability resolved gains haste."""
    global _BUSY
    s = sentence.strip().rstrip(".")
    if not _BUSY and _pact_rider(s, effects):
        return True
    if _BUSY or not (_HASTE.fullmatch(s) or re.search(_WHEN, s, re.I)):
        return False
    from .cards.parse import _parse_effects
    _BUSY = True
    try:
        new, bad = _parse_effects(s + ".")        # a wording the parser already reads keeps its parse
    finally:
        _BUSY = False
    if new and not bad:
        return False
    if _HASTE.fullmatch(s) and effects and effects[-1].target == "none" and effects[-1].kind not in ("token",
                                                                                                     "copy_token"):
        effects.append(_effect("cx_fresh_grant", data={"keyword": "haste"}))
        return True
    m = re.fullmatch(rf"(?P<a>.+?) {_WHEN}", s, re.I) or re.fullmatch(rf"{_WHEN}, (?P<a>.+)", s, re.I)
    if not m:
        return False
    at = _timing(s)
    if at == "upkeep_that":
        return False        # the player is not read yet
    body = m["a"]
    eff = action(body)
    player = None
    pm = re.fullmatch(r"(its controller|that player) (.+)", body, re.I)
    if eff is None and pm:
        # "Its controller may draw up to two cards at the beginning of the next turn's upkeep" (Arcane Denial): the
        # player is fixed as this resolves (the countered spell's controller) and acts as "you" in the body
        player = "controller" if pm[1].lower() == "its controller" else "that_player"
        body = "you " + _base_verb(pm[2])
        if body is None:
            return False
    if eff is None:
        if re.search(r"\b(?:it|them|that|those|this way)\b", body, re.I):
            return False
        new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
        if bad or not new or any(e.target not in ("none", "self", "you", "") for e in new):
            return False
        eff = _effect("cx_delay", data={"op": "effects", "who": "none", "effects": new})
        if player:
            eff = dataclasses.replace(eff, data=dict(eff.data, player=player))
        conds = {e.cond for e in new}
        if len(conds) == 1 and next(iter(conds)) and re.match(r"if ", body, re.I):
            # "If <C>, <action> at the beginning of the next end step": C is checked as this resolves, not at the end step
            eff = dataclasses.replace(eff, cond=next(iter(conds)),
                                      data=dict(eff.data, effects=[dataclasses.replace(e, cond="") for e in new]))
    if effects and effects[-1].kind == "token" and eff.data["op"] in ("exile", "sacrifice") and \
            eff.data["who"] != "self" and at == "end":
        return False                  # the token line's own "end" rider (cards/parse.py)
    if at != "end":
        eff = dataclasses.replace(eff, data=dict(eff.data, at=at))
    effects.append(eff)
    return True


def _base_verb(text: str):
    """"may draw up to two cards" / "draws a card" -> the form after "you"."""
    m = re.match(r"(may )?(\w+)(.*)", text)
    verb = m[2]
    if not m[1]:
        if not verb.endswith("s"):
            return None
        verb = verb[:-2] if verb.endswith(("ches", "shes", "sses")) else verb[:-1]
    return (m[1] or "") + verb + m[3]


_PACT = re.compile(r"at the beginning of your next upkeep, pay (?P<c>(?:\{[0-9WUBRG]\})+)", re.I)


def _pact_rider(s: str, effects: list) -> bool:
    """"At the beginning of your next upkeep, pay {2}{B}." + "If you don't, you lose the game." (two sentences)."""
    m = _PACT.fullmatch(s)
    if m:
        from .cards.model import parse_mana_cost
        effects.append(_effect("cx_delay", data={"op": "effects", "who": "none", "at": "upkeep_you", "pact_open": True,
                                                 "effects": [_effect("cx_pact", data={"cost": parse_mana_cost(m["c"])})]}))
        return True
    if re.fullmatch(r"if you don't, you lose the game", s, re.I) and effects and \
            effects[-1].kind == "cx_delay" and effects[-1].data.get("pact_open"):
        data = {k: v for k, v in effects[-1].data.items() if k != "pact_open"}
        effects[-1] = dataclasses.replace(effects[-1], data=data)
        return True
    return False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _fresh(game, item):
    from .engine.state import Permanent
    start = getattr(item, "cx_start", None)
    if start is None:
        return []
    found = [x for pl in game.players for x in pl.battlefield
             if isinstance(x, Permanent) and (getattr(x, "rules_timestamp", 0) or 0) > start]
    return sorted(found, key=lambda x: x.rules_timestamp)


def schedule(game, p, eff, prev, item):
    from .engine.state import Permanent
    data = eff.data
    op, who = data["op"], data["who"]
    source = item.source if item is not None else None
    if op == "effects":
        if data.get("player"):
            who = _player(game, data["player"], prev, item)
            if who is None:
                return
            p = who                     # it acts as "you" in the delayed effects
        _store(game, p, data, list(data["effects"]), source, None)
        return
    if op == "battlefield":
        perm = prev if isinstance(prev, Permanent) else source if who != "fresh" else None
        if who == "self":
            perm = source
        if not isinstance(perm, Permanent) or perm in perm.controller.battlefield:
            return
        objs = [perm.front]
    elif who == "self":
        objs = [source] if isinstance(source, Permanent) else []
    elif who == "fresh":
        objs = _fresh(game, item)
    else:
        fresh = _fresh(game, item)
        objs = [prev] if isinstance(prev, Permanent) else fresh[-1:]
    if not objs:
        return
    _store(game, p, data, [_effect("cx_delayed_do", data=dict(data))], source, tuple(objs))


def _player(game, how, prev, item):
    """The player a delayed "its controller / that player ..." names, fixed as the ability resolves."""
    from .engine.state import Permanent, Player, StackItem
    if isinstance(prev, (StackItem, Permanent)):
        return prev.controller if how == "controller" else None
    if isinstance(prev, Player):
        return prev
    ctx = getattr(item, "context", None)
    return ctx if isinstance(ctx, Player) and how == "that_player" else None


def _store(game, p, data, effects, source, context):
    at = data.get("at", "end")
    if at == "end":
        game.delayed_end_step.append((p, effects, source, context))
        return
    if not hasattr(game, "cx_delayed_at"):
        game.cx_delayed_at = []
    game.cx_delayed_at.append({"at": at, "controller": p, "effects": effects, "source": source, "context": context,
                               "turn": game.turn, "step": game.step})


_STEP = {"upkeep": ("upkeep", "upkeep_you"), "end": ("end_you",), "main2": ("main",), "cleanup": ("cleanup",)}


def at_step(game, step: str, active) -> None:
    """The turn structure reached ``step`` of ``active``'s turn: queue the delayed triggers waiting for it."""
    waiting = getattr(game, "cx_delayed_at", None)
    if not waiting:
        return
    keep = []
    for d in waiting:
        at = d["at"]
        due = at in _STEP.get(step, ()) and (not at.endswith("_you") or active is d["controller"])
        if at == "main" and d["turn"] != game.turn:
            continue                    # "this turn": no main phase was left
        if at == "main" and d["step"] in ("main2", "end_step", "cleanup"):
            continue
        if due:
            game.queue_trigger(d["controller"], d["effects"], d["source"], "delayed trigger", context=d["context"])
        else:
            keep.append(d)
    game.cx_delayed_at = keep


def pact(game, p, eff, item):
    """Pay the Pact's cost if possible (the AI always does), else lose the game."""
    cost = dict(eff.data["cost"])
    if game.can_pay(p, cost) and game.pay(p, cost) is not None:
        game.log("pays the Pact", p)
        return
    if not p.lost:
        game.log("can't pay the Pact and loses the game", p)
        game.audit("loss", seat=game.players.index(p), cause="didn't pay a Pact")
        p.lost = True


def _return(game, p, card, data):
    owner = getattr(card, "owner", None) or p
    if card not in owner.exile:
        return
    owner.exile.remove(card)
    perm = game.enter_battlefield(owner, card, tapped=data.get("tapped", False),
                                  counters={"+1/+1": 1} if data.get("counter") else None)
    if perm is not None:
        game.log(f"{card.name} returns to the battlefield", owner)


def act(game, p, eff, item):
    from .engine.state import Permanent
    data = eff.data
    objs = item.context if item is not None and isinstance(item.context, tuple) else ()
    op = data["op"]
    for obj in objs:
        if op == "battlefield":
            _return(game, p, obj, data)
            continue
        if not isinstance(obj, Permanent) or obj not in obj.controller.battlefield:
            continue
        if op == "exile":
            game.leave_battlefield(obj, "exile")
        elif op == "sacrifice":
            game.sacrifice(obj)
        elif op == "destroy":
            game.destroy(obj)
        elif op == "hand":
            game.leave_battlefield(obj, "hand")


def fresh_grant(game, p, eff, prev, item):
    from .engine.state import Permanent
    perm = prev if isinstance(prev, Permanent) else (_fresh(game, item)[-1:] or [None])[0]
    if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
        game.resolve(p, _effect("grant", data={"keyword": eff.data["keyword"]}), perm, item)


def pact_affordable(me, card) -> bool:
    """AI policy: cast a Pact only when the mana sources it controls could pay its upkeep cost (they untap first);
    otherwise the delayed trigger loses the game."""
    costs = [d.data["cost"] for e in getattr(card, "spell_effects", ()) if e.kind == "cx_delay"
             for d in e.data.get("effects", ()) if d.kind == "cx_pact"]
    if not costs:
        return True
    sources = [x for x in me.battlefield if x.card.produces and not x.card.is_token]
    for cost in costs:
        if len(sources) < sum(cost.values()):
            return False
        if any(sum(1 for x in sources if col in x.card.produces) < n for col, n in cost.items() if col != "generic"):
            return False
    return True


_FLASH = ("You may cast ~ as though it had flash. If you cast it any time a sorcery couldn't have been cast, the "
          "controller of the permanent it becomes sacrifices it at the beginning of the next cleanup step.")


def flash_line(line: str, st) -> bool:
    """The flash Auras (Lightning Reflexes, Armor of Thorns): flash, and if cast when a sorcery couldn't have been,
    a delayed "sacrifice it at the beginning of the next cleanup step" made as it resolves (``flash_resolved``)."""
    if line != _FLASH:
        return False
    st.keywords.add("flash")
    st.extra.setdefault("advanced_rules", {})["flash_cleanup"] = True
    return True


def flash_resolved(game, perm, item) -> None:
    """A permanent spell resolved: schedule the flash Aura's cleanup sacrifice when it was cast at instant timing."""
    if perm is None or not perm.card.advanced_rules.get("flash_cleanup") or getattr(item, "sorcery_timing", True):
        return
    _store(game, perm.controller, {"at": "cleanup"},
           [_effect("cx_delayed_do", data={"op": "sacrifice", "who": "fresh"})], perm, (perm,))
