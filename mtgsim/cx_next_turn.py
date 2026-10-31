"""Durations that end at the controller's next turn, and "player or planeswalker" damage targets.

"Until your next turn": the sentence is parsed as its "until end of turn" (or "this turn") reading and its
effects are flagged ``until_next_turn``. On resolution, ``lasting`` moves what those effects did for the turn
(pump, keywords, scoped continuous effects, player flags) into effects that end when the controller's next turn
begins (``advanced_templates.begin_turn``).

"Target player or planeswalker" / "target opponent or planeswalker": parsed as the player wording, with damage
effects flagged ``or_pw`` so a planeswalker is a legal target too (``engine.targets.legal_targets``)."""
from __future__ import annotations

import contextlib
import dataclasses
import re

_PREFIX = re.compile(r"until your next turn, (.+)", re.I)
_INNER = re.compile(r"\buntil your next turn\b", re.I)
_PW = [(re.compile(r"\b(?:up to one )?target (player|opponent) or planeswalker\b", re.I), r"target \1"),
       (re.compile(r"\bthat player or that planeswalker's controller\b", re.I), "that player")]


_CHECKING = []     # sentences being read without rewriting


def _candidates(s):
    m = _PREFIX.fullmatch(s)
    if m:
        body = m[1]
        return [body + " until end of turn", body + " this turn"]
    if _INNER.search(s):
        return [_INNER.sub("until end of turn", s), _INNER.sub("this turn", s)]
    return []


def rewrite(s):
    """(sentence, kind) to parse in place of s, or (s, None). kind is 'next_turn' or 'or_pw'."""
    from .cards.parse import _parse_effects
    if _CHECKING:
        return s, None
    if _INNER.search(s) or any(rx.search(s) for rx, _ in _PW):
        _CHECKING.append(s)
        try:
            new, bad = _parse_effects(s[0].upper() + s[1:] + ".")
        finally:
            _CHECKING.pop()
        if new and not bad:         # an existing template reads the whole sentence
            return s, ("or_pw" if any(rx.search(s) for rx, _ in _PW) else None)
    out = re.sub(r"\btarget creature defending player controls\b", "target creature an opponent controls", s, flags=re.I)
    pw = False
    for rx, rep in _PW:
        out, n = rx.subn(rep, out)
        pw = pw or bool(n)
    options = _candidates(out)
    if options:
        for option in options:
            new, bad = _parse_effects(option[0].upper() + option[1:] + ".")
            if new and not bad:
                return option, "next_turn"
        return options[0], "next_turn"
    return (out, "or_pw") if pw else (s, None)


def _upgrade(eff):
    if eff.kind == "damage" and eff.target == "player":
        return dataclasses.replace(eff, data=dict(eff.data, or_pw=True))
    inner = eff.data.get("effect")
    if inner is not None and hasattr(inner, "kind"):
        new = _upgrade(inner)
        if new is not inner:
            return dataclasses.replace(eff, data=dict(eff.data, effect=new))
    return eff


def mark(effects, pending):
    """Flag the effects one rewritten sentence produced. pending is (first index, kind) or None."""
    if pending is None:
        return
    first, kind = pending
    for i in range(first, len(effects)):
        e = effects[i]
        if kind == "next_turn":
            effects[i] = dataclasses.replace(e, data=dict(e.data, until_next_turn=True))
        effects[i] = _upgrade(effects[i])


def _waiting(game):
    if not hasattr(game, "next_turn_modifiers"):
        game.next_turn_modifiers = []
    return game.next_turn_modifiers


@contextlib.contextmanager
def lasting(game, p):
    """Resolve an "until your next turn" effect: its end-of-turn results last until p's next turn."""
    from .engine.state import Permanent
    perms = [x for pl in game.players for x in pl.battlefield]
    before = {id(x): (x.pump_p, x.pump_t, set(x.temp_kw)) for x in perms}
    effects = {e.id for e in game.continuous_effects}
    yield
    waiting = _waiting(game)
    for e in list(game.continuous_effects):
        if e.id not in effects and e.until_eot:
            kept = dataclasses.replace(e, until_eot=False)
            game.continuous_effects[game.continuous_effects.index(e)] = kept
            waiting.append((p, kept))
    granted = {(id(e.target), e.keyword) for e in game.continuous_effects
               if e.operation == "grant" and e.id not in effects}
    for x in [x for pl in game.players for x in pl.battlefield]:
        if not isinstance(x, Permanent) or id(x) not in before:
            continue
        bp, bt, kws = before[id(x)]
        dp, dt = x.pump_p - bp, x.pump_t - bt
        if dp or dt:
            x.pump_p, x.pump_t = bp, bt
            waiting.append((p, game.add_continuous_effect(x, "modify", power=dp, toughness=dt)))
        for kw in x.temp_kw - kws:
            x.temp_kw.discard(kw)
            if (id(x), kw) not in granted:
                waiting.append((p, game.add_continuous_effect(x, "grant", keyword=kw)))


class _Flag:
    """A player flag such as hexproof or "creatures can't attack you": this turn, or until the controller's next turn."""
    def __init__(self, game, controller, player, flag, amount, data, next_turn):
        self.controller, self.player, self.flag, self.amount, self.data = controller, player, flag, amount, data
        self.turn, self.next_turn = game.turn, next_turn


def add_flag(game, controller, player, eff):
    entry = _Flag(game, controller, player, eff.data["flag"], eff.amount, eff.data, bool(eff.data.get("until_next_turn")))
    if not hasattr(game, "cx_player_flags"):
        game.cx_player_flags = []
    game.cx_player_flags = [f for f in game.cx_player_flags if _live(game, f)] + [entry]
    if entry.next_turn:
        _waiting(game).append((controller, entry))


def _live(game, f):
    if f.next_turn:
        return any(e is f for _, e in getattr(game, "next_turn_modifiers", ()))
    return f.turn == game.turn


def flags(game, player, flag):
    return [f for f in getattr(game, "cx_player_flags", ()) if f.player is player and f.flag == flag and _live(game, f)]


def player_flag(game, player, flag):
    return game is not None and bool(flags(game, player, flag))


def attack_flag_tax(game, defender):
    if player_flag(game, defender, "no_attack"):
        return 10 ** 6
    return sum(f.amount for f in flags(game, defender, "attack_tax"))


def flag_tax(game, player, card):
    total = 0
    for f in getattr(game, "cx_player_flags", ()):
        if f.flag == "tax" and f.controller is not player and _live(game, f) and \
                (f.data.get("filter") != "noncreature" or not card.is_creature):
            total += f.amount
    return total


# Patterns for the "this turn" readings that until-your-next-turn sentences are rewritten to.
_UNTIL = r"(?: until end of turn| this turn)"
_KW_LOCK = {"attack": "cant_attack_now", "block": "cant_block_now", "activate": "cant_activate_now"}


def _build(kind, subj, **kw):
    from .cards.model import NO_MATCH
    from .permanent_templates import build
    eff = build(kind, subj, **kw)
    return eff if eff is not None else NO_MATCH


def _lock(m):
    from .cards.model import NO_MATCH
    words = ["attack", "block"] if m["what"] == "attack or block" else [m["what"]]
    if m["act"]:
        words.append("activate")
    eff = _build("cx_temp_kw", m["subj"], data={"keywords": frozenset(_KW_LOCK[w] for w in words)})
    return eff if eff is NO_MATCH or eff.kind != "permanent_group" or m["subj"].lower().startswith(("creatures ", "each ", "all ")) \
        else NO_MATCH


def _debuff_and(m):
    from .cards.model import NO_MATCH
    from .permanent_templates import keywords
    p, t = int(m["p"]), int(m["t"])
    first = _build("debuff_one" if p <= 0 and t <= 0 else "pump", m["subj"],
                   amount=-p if p <= 0 and t <= 0 else p, amount2=-t if p <= 0 and t <= 0 else t)
    if first is NO_MATCH or first.kind == "permanent_group":
        return NO_MATCH
    then = "it" if first.target == "permanent" else m["subj"]
    if m["lose"]:
        kws = keywords(m["lose"])
        if not kws:
            return NO_MATCH
        return [first] + [_build("cx_lose_kw", then, data={"keyword": k}) for k in kws]
    return [first, _build("cx_temp_kw", then, data={"keywords": frozenset({"cant_activate_now"})})]


def _group_gain(m):
    from .cards.model import NO_MATCH
    from .permanent_templates import keywords, selector
    kws = keywords(m["kws"])
    subj = m["subj"]
    if subj.lower().startswith("tokens "):
        subj = "token creatures" + subj[6:]       # "tokens you control": token permanents, creatures in practice
    spec = selector(subj, plural=True)
    if not kws or spec is None or "controller" not in spec:
        return NO_MATCH
    from .cards.model import Effect
    return Effect("permanent_group", data={"selector": spec, "effects": [
        Effect("grant", target="self", data={"keyword": k}) for k in kws]})


def _base(m):
    eff = _build("cx_set_base", m["subj"], amount=int(m["p"]), amount2=int(m["t"]))
    from .cards.model import NO_MATCH
    return NO_MATCH if eff is NO_MATCH or eff.kind == "permanent_group" else eff


def _base_player(m):
    from .cards.model import Effect
    return Effect("cx_set_base", int(m["p"]), int(m["t"]), target="player", data={"group": True})


def _flag(flag, who="you", amount=0, **data):
    def build(m):
        from .cards.model import Effect
        n = int(m["n"]) if "n" in m.re.groupindex else amount
        return Effect("cx_player_flag", n, data=dict(data, flag=flag, who=who))
    return build


def _both(*builders):
    def build(m):
        return [b(m) for b in builders]
    return build


def _e_x():
    from .cards.model import Effect
    return Effect("damage", target="player", data={"x": True})


def _player_and_creatures(m):
    """"~ deals 4 damage to target player or planeswalker and each creature that player or that planeswalker's
    controller controls": the second effect hits the creatures of the first target (or of its controller)."""
    from .cards.model import Effect
    x = m["n"].lower() == "x"
    n = 0 if x else int(m["n"])
    splash = int(m["m"].split()[0]) if m["m"] else n
    data = {"x": True} if x else {}
    return [Effect("damage", n, target="player", data=dict(data)),
            Effect("cx_controller_creatures_damage", splash, target="prev", data=dict(data) if not m["m"] else {})]


_SUBJ = r"(?P<subj>(?:up to one )?target [^,]+?|it|that creature|(?:each )?creatures? [^,]*?)"
EFFECT_PATTERNS = [
    (rf"{_SUBJ} can't (?P<what>attack or block|attack|block)(?P<act>,? and (?:its|their) activated abilities can't be activated)?"
     rf"{_UNTIL}", _lock),
    (rf"{_SUBJ} gets (?P<p>[+-]\d+)/(?P<t>[+-]\d+) and (?:loses (?P<lose>[a-z ,]+)|its activated abilities can't be activated)"
     rf"{_UNTIL}", _debuff_and),
    (rf"(?P<subj>(?:non-)?[a-z]+(?: creatures)? (?:you control|your opponents control)) gains? (?P<kws>[a-z ,]+){_UNTIL}", _group_gain),
    (rf"{_SUBJ} (?:has|have) base power and toughness (?P<p>\d+)/(?P<t>\d+){_UNTIL}", _base),
    (rf"creatures target player controls have base power and toughness (?P<p>\d+)/(?P<t>\d+){_UNTIL}", _base_player),
    (rf"{_SUBJ} attacks?(?: a player)? each combat if able(?: and attacks? a player other than you if able)?{_UNTIL}",
     lambda m: _build("cx_temp_kw", m["subj"], data={"keywords": frozenset({"must_attack_now"})})),
    (r"(?:~|it|he|she) deals (?P<n>\d+|x) damage to target (?:player|opponent) and (?P<m>\d+ damage to )?each creature that player controls",
     _player_and_creatures),
    (r"(?:~|it|he|she) deals x damage to target (?:player|opponent)",
     lambda m: _e_x()),
    (rf"you may cast sorcery spells as though they had flash{_UNTIL}", _flag("sorcery_flash")),
    (rf"you gain hexproof{_UNTIL}", _flag("hexproof")),
    (rf"you gain protection from everything{_UNTIL}", _flag("protection")),
    (rf"your life total can't change{_UNTIL}", _flag("life_lock")),
    (rf"your life total can't change and you gain protection from everything{_UNTIL}",
     _both(_flag("life_lock"), _flag("protection"))),
    (rf"prevent all damage that would be dealt to you{_UNTIL}", _flag("prevent_damage")),
    (rf"creatures can't attack you{_UNTIL}", _flag("no_attack")),
    (rf"creatures can't attack you(?: or planeswalkers you control)? unless their controller pays \{{(?P<n>\d+)\}} "
     rf"for each of those creatures{_UNTIL}", _flag("attack_tax")),
    (rf"you have no maximum hand size{_UNTIL}", _flag("no_max_hand")),
    (rf"you can't cast spells{_UNTIL}", _flag("no_cast")),
    (rf"(?:spells your opponents cast cost|(?P<nc>noncreature) spells your opponents cast cost) \{{(?P<n>\d+)\}} more to cast{_UNTIL}",
     lambda m: _flag("tax", filter="noncreature" if m["nc"] else "")(m)),
]
