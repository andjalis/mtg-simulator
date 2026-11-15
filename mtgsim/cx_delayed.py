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

Other timings (#344, #539) keep the same actions but wait in ``game.cx_delayed_at`` until their step really begins
(``at_step``, called from the turn structure):

    at the beginning of the next turn's upkeep / the next upkeep    the next upkeep of any player
    at the beginning of your next upkeep                            the controller's next upkeep
    at the beginning of their / that player's next upkeep           that player's (fixed as the ability resolves)
    at the beginning of their / that player's next draw step       that player's next draw step (fixed the same way)
    at the beginning of the next draw step                          the next draw step of any player
    at the beginning of the next combat (phase) (this turn)        the next combat phase, this turn if written
    at the beginning of (that player's) next declare attackers step  that step of that player's turn
    at the beginning of your next end step                          the next end step of the controller's turn
    at the beginning of your / the next main phase this turn        this turn's next main phase, if one is left
    at the beginning of the next cleanup step                       the next cleanup step

A timing with a fixed player ("their next upkeep", "their next draw step", "that player's next declare attackers
step") records that player as the ability resolves and waits for that player's step, not the active one's.

"At the beginning of your next upkeep, pay {C}. If you don't, you lose the game." (the Pacts) is a delayed
``cx_pact``: the controller pays if it can, else loses."""
from __future__ import annotations

import dataclasses
import re

_WHEN = (r"at the beginning of (?:the next end step|your next end step|the next turn's upkeep|the next upkeep|"
         r"your next upkeep|(?:their|that player's) next upkeep|(?:your|the) next main phase this turn|"
         r"the next cleanup step|the next draw step|(?:their|that player's) next draw step|"
         r"the next combat(?: phase)?(?: this turn)?|"
         r"(?:the next|(?:their|that player's) next) declare attackers step)")
# The first entry whose words follow "beginning of " in the sentence wins, so the longer "this turn" / "phase"
# / "_that" wordings must come before their shorter prefixes.
_TIMING = [("the next combat phase this turn", "combat_turn"), ("the next combat this turn", "combat_turn"),
           ("the next combat phase", "combat"), ("the next combat", "combat"),
           ("their next draw step", "draw_that"), ("that player's next draw step", "draw_that"),
           ("the next draw step", "draw"),
           ("that player's next declare attackers step", "attackers_that"),
           ("their next declare attackers step", "attackers_that"), ("the next declare attackers step", "attackers"),
           ("the next end step", "end"), ("your next end step", "end_you"), ("the next turn's upkeep", "upkeep"),
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
]
_BF_RETURN = re.compile(rf"return (?P<s>{_ONE}|{_MANY}) to the battlefield(?P<rest>.*)", re.I)
_BF_FRAGS = [("under its owner's control", {"control": "owner"}),
             ("under your control", {"control": "you"}),
             ("under that player's control", {"control": "that"}),
             ("tapped and attacking", {"tapped": True, "attacking": True}),
             ("tapped", {"tapped": True}), ("and attacking", {"attacking": True})]


def _bf_rest(rest: str):
    """The fragments after "return ... to the battlefield": control, tapped/attacking, a +1/+1 counter, in any
    order ("under its owner's control tapped and attacking"), or None."""
    rest = rest.strip()
    counter = False
    m = re.search(r"\s*with a \+1/\+1 counter on it$", rest, re.I)
    if m:
        counter, rest = True, rest[:m.start()].strip()
    out = {"tapped": False, "attacking": False, "control": None, "counter": counter}
    while rest:
        for frag, data in _BF_FRAGS:
            if rest.lower().startswith(frag):
                out.update(data)
                rest = rest[len(frag):].strip()
                break
        else:
            return None
    return out


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
    m = _BF_RETURN.fullmatch(text)
    if m:
        rest = _bf_rest(m["rest"])
        if rest is None or rest["attacking"] and _who(m["s"]) == "fresh":
            return None
        return _effect("cx_delay", data={"op": "battlefield", "who": _who(m["s"]), **rest})
    for rx, op in _ACTIONS:
        m = rx.fullmatch(text)
        if not m:
            continue
        data = {"op": op or m["op"].lower().rstrip("s"), "who": _who(m["s"])}
        return _effect("cx_delay", data=data)
    return None


_HASTE = re.compile(r"(?:it|the creature|the artifact|that [a-z]+) gains haste(?: until end of turn)?", re.I)
_CANT_BLOCK_COMBAT = re.compile(r"(?:it|that creature|that permanent) can't be blocked that combat", re.I)

# A body may name the fixed player ("that player loses 2 life") or the token's colours ("that are red, green,
# and white"); other anaphors still refuse the sentence. "this way" is allowed at the non-end-step timings:
# its count is baked into the delayed effect as the ability resolves (schedule).
_ANAPHOR = re.compile(r"\b(?:it|them|those|this way)\b|\bthat\b(?!\s+(?:player|are)\b)", re.I)
_ANAPHOR_NO_TW = re.compile(r"\b(?:it|them|those)\b|\bthat\b(?!\s+(?:player|are)\b)", re.I)
# "the next combat (phase) this turn": targets of the delayed trigger are chosen as it goes on the stack
_TARGETED_AT = ("draw", "draw_that", "combat", "combat_turn", "attackers", "attackers_that")


_BUSY = False


def parse_rider(sentence: str, effects: list) -> bool:
    """"<action> at the beginning of the next end step" or "At the beginning of the next end step, <action>".

    Also "at the beginning of ..." riders of other steps (#539): "... at the beginning of their next draw step
    unless they pay {2} before that step", "... at the beginning of the next combat this turn, ...",
    "... at the beginning of that player's next declare attackers step", and a trailing ", where X is ...".
    Also "That creature gains haste." after an untargeted put-onto-the-battlefield effect (Sneak Attack): the newest
    permanent that entered while the ability resolved gains haste."""
    global _BUSY
    s = sentence.strip().rstrip(".")
    if not _BUSY and _pact_rider(s, effects):
        return True
    if _CANT_BLOCK_COMBAT.fullmatch(s) and effects and effects[-1].kind == "cx_delay" \
            and effects[-1].data.get("op") == "battlefield" and effects[-1].data.get("attacking"):
        effects[-1] = dataclasses.replace(effects[-1], data=dict(effects[-1].data, cant_block_combat=True))
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
    m = re.fullmatch(rf"(?P<a>.+?) {_WHEN}(?: unless (?P<u>.+?) before that (?:draw )?step)?"
                     rf"(?:, where (?P<wx>x) is (?P<q>.+?))?", s, re.I) or \
        re.fullmatch(rf"{_WHEN}, (?P<a>.+?)(?: unless (?P<u>.+?) before that (?:draw )?step)?"
                     rf"(?:, where (?P<wx>x) is (?P<q>.+?))?", s, re.I)
    if not m:
        return False
    at = _timing(s)
    gd = m.groupdict()
    body = gd["a"]
    if gd.get("u"):
        body += f" unless {gd['u']}"
    if gd.get("q"):
        q = re.sub(r"\s+at that time$", "", gd["q"], flags=re.I)
        body += f", where X is {q}"
    eff = action(body)
    if eff is None:
        if re.fullmatch(r"gain control of (?:that creature|that permanent|it) until end of turn", body, re.I):
            # "At the beginning of the next combat this turn, gain control of that creature until end of turn"
            # (The Wrath of Khan): "that creature" is the target the ability just resolved on
            new = [_effect("cx_control", target="prev", data={"eot": True, "side": "theirs"})]
        else:
            if (at in ("end", "end_you") and _ANAPHOR or _ANAPHOR_NO_TW).search(body):
                return False
            body = re.sub(r"\bthe player gets another\b", "that player gets a", body, flags=re.I)
            new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
            allowed = ("none", "self", "you", "")
            if at.endswith("_that"):
                allowed += ("that_player", "prev")
            if at in _TARGETED_AT:
                from .engine.state import TARGETED
                allowed += TARGETED
            if bad or not new or any(e.target not in allowed for e in new):
                return False
        eff = _effect("cx_delay", data={"op": "effects", "who": "none", "effects": new})
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
    from .engine.state import Permanent, Player
    data = eff.data
    op, who = data["op"], data["who"]
    source = item.source if item is not None else None
    # "their / that player's next ...": the player is fixed as this resolves — the targeted player, else the
    # trigger's context player ("whenever ~ deals combat damage to a player, that player ..."), else the owner
    # of a targeted card ("... cards from a player's graveyard ... that player draws a card ...")
    fixed = prev if isinstance(prev, Player) else (item.context if item is not None and isinstance(item.context, Player)
                                                  else None)
    if fixed is None and item is not None:
        for t in getattr(item, "targets", ()) or ():
            if isinstance(t, Player):
                fixed = t
                break
            owner = getattr(t, "owner", None)
            if isinstance(owner, Player):
                fixed = owner
                break
    if op == "effects":
        inner = list(data["effects"])
        names_player = any(e.target == "that_player" or e.data.get("who") == "that_player" for e in inner)
        if names_player and fixed is None:
            return                  # no player to fix "that player" on: leave the trigger unscheduled
        tw = getattr(item, "this_way", None) if item is not None else None
        if tw is not None:
            # "for each creature returned to your hand this way": the count was recorded as this resolved;
            # bake it in, so the delayed trigger does not read a fresh (empty) "this way"
            baked = []
            for e in inner:
                xq = e.data.get("xq")
                if isinstance(xq, tuple) and xq and xq[0] == "this_way" and tw[0] == xq[1] and xq[2] in tw[1]:
                    e = dataclasses.replace(e, amount=e.amount * tw[2],
                                           data={k: v for k, v in e.data.items() if k != "xq"})
                baked.append(e)
            inner = baked
        ctx = fixed if names_player else (prev if any(e.target == "prev" for e in inner) else None)
        _store(game, p, data, inner, source, ctx, fixed)
        return
    if op == "battlefield":
        perm = prev if isinstance(prev, Permanent) else source if who != "fresh" else None
        if who == "self":
            perm = source
        if not isinstance(perm, Permanent) or perm in perm.controller.battlefield:
            return
        objs = [perm.front]
        if fixed is None and at_endswith_that(data) and getattr(perm.front, "owner", None) is not None:
            fixed = perm.front.owner       # "return it ... under its owner's control at the beginning of their ..."
    elif who == "self":
        objs = [source] if isinstance(source, Permanent) else []
    elif who == "fresh":
        objs = _fresh(game, item)
    else:
        fresh = _fresh(game, item)
        objs = [prev] if isinstance(prev, Permanent) else fresh[-1:]
    if not objs:
        return
    _store(game, p, data, [_effect("cx_delayed_do", data=dict(data))], source, tuple(objs), fixed)


def at_endswith_that(data) -> bool:
    return str(data.get("at", "")).endswith("_that")


def _store(game, p, data, effects, source, context, player=None):
    at = data.get("at", "end")
    if at == "end":
        game.delayed_end_step.append((p, effects, source, context))
        return
    if not hasattr(game, "cx_delayed_at"):
        game.cx_delayed_at = []
    game.cx_delayed_at.append({"at": at, "controller": p, "effects": effects, "source": source, "context": context,
                               "player": player, "turn": game.turn, "step": game.step})


_STEP = {"upkeep": ("upkeep", "upkeep_you", "upkeep_that"), "draw": ("draw", "draw_that"), "end": ("end_you",),
         "main2": ("main",), "cleanup": ("cleanup",), "combat": ("combat", "combat_turn"),
         "declare_attackers": ("attackers", "attackers_that")}
_COMBAT_STEPS = ("declare_attackers", "declare_blockers", "first_strike_damage", "combat_damage", "end_combat")


def at_step(game, step: str, active) -> None:
    """The turn structure reached ``step`` of ``active``'s turn: queue the delayed triggers waiting for it."""
    waiting = getattr(game, "cx_delayed_at", None)
    if not waiting:
        return
    keep = []
    for d in waiting:
        at = d["at"]
        due = at in _STEP.get(step, ()) and (not at.endswith("_you") or active is d["controller"]) \
            and (not at.endswith("_that") or d.get("player") is None or active is d["player"])
        if at == "main" and d["turn"] != game.turn:
            continue                    # "this turn": no main phase was left
        if at == "main" and d["step"] in ("main2", "end_step", "cleanup"):
            continue
        if at == "combat_turn" and (d["turn"] != game.turn or d["step"] in _COMBAT_STEPS):
            continue                    # "the next combat this turn": this turn's combat already began
        if due:
            effects = [dataclasses.replace(e, data=dict(e.data, player=d.get("player")))
                       if e.kind == "cx_delayed_do" else e for e in d["effects"]]
            game.queue_trigger(d["controller"], effects, d["source"], "delayed trigger", context=d["context"])
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
    from .engine.state import Player
    owner = getattr(card, "owner", None) or p
    if card not in owner.exile:
        return
    ctrl = owner
    if data.get("control") == "you":
        ctrl = p
    elif data.get("control") == "that" and isinstance(data.get("player"), Player):
        ctrl = data["player"]      # "under that player's control" (Plague Reaver)
    owner.exile.remove(card)
    attacking = bool(data.get("attacking")) and ctrl is game.active \
        and game.step in ("declare_attackers", "declare_blockers")
    perm = game.enter_battlefield(ctrl, card, tapped=data.get("tapped", False) or attacking,
                                  tapped_attacking=attacking,
                                  counters={"+1/+1": 1} if data.get("counter") else None)
    if perm is not None:
        game.log(f"{card.name} returns to the battlefield", ctrl)
        if data.get("cant_block_combat"):
            perm.temp_kw.add("unblockable")     # "It can't be blocked that combat" (cleared in cleanup)


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
