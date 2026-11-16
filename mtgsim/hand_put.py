"""Qualified "put a <card> from your hand onto the battlefield" (#331): the Elvish Piper family, widened.

    {T}: You may put a creature card with mana value equal to the number of charge counters on ~ from your
        hand onto the battlefield.                                                         (Aether Vial)
    {3}, {T}: You may put a creature card of the chosen type from your hand onto the battlefield.  (Belbe's Portal)
    you may put a permanent card with mana value less than or equal to the number of lands you control from
        your hand onto the battlefield tapped.                                             (Anticausal Vestige)
    you may put a creature card from your hand onto the battlefield tapped and attacking. (Ilharg, the Raze-Boar)
    you may put an Aura card from your hand onto the battlefield attached to ~.            (Academy Researchers)
    If you do, you may put a creature card from your hand onto the battlefield blocking that creature. (Aetherplasm)

The effect is the existing ``hand_to_battlefield`` kind; its data gains

* ``spec``: a ``cx_condlib._filter`` card filter, plus ``chosen`` (the source's chosen creature type) and
  ``any_sub`` ("an Angel, Demon, or Dragon creature card");
* ``mvq``: (op, quantity) for a mana value compared with a ``cards._xq`` quantity, evaluated when the effect
  resolves (charge counters added in response count);
* ``entry``: "tapped", "attacking" (tapped and attacking the opponent), "attached" (an Aura attached to the
  source, which must be a legal host) or "blocking" (blocking the attacker a block trigger names: Aetherplasm).

Only the controller's own hand is covered: "each player may" / "that player may" need a decision by another
player and are left unmatched, as are quantities ``_xq`` doesn't know ("that damage": #313).
"""
from __future__ import annotations

import re

_ENTRY = {"tapped": "tapped", "tapped and attacking": "attacking", "tapped and attacking that opponent": "attacking",
          "attached to ~": "attached", "blocking that creature": "blocking"}
_MV_OPS = {"equal to": "==", "less than or equal to": "<=", "x or less": "<=", "x": "=="}


def _subtype_list(desc: str):
    """ "Angel, Demon, or Dragon creature" -> (["Angel", "Demon", "Dragon"], "creature")."""
    m = re.fullmatch(r"((?:[A-Z][\w'-]*, )+(?:or |and/or )[A-Z][\w'-]*|[A-Z][\w'-]* or [A-Z][\w'-]*) "
                     r"(creature|permanent)", desc)
    if not m:
        return None
    subs = [s for s in re.split(r", (?:or |and/or )?| or ", m[1]) if s]
    return subs, m[2]


def _spec(desc: str):
    from .cx_condlib import _filter
    listed = _subtype_list(desc)
    if listed:
        return {"types": [listed[1]], "any_sub": listed[0]}
    spec = _filter(desc, plural=False)
    if not spec:
        return None
    if spec.get("sub") and not spec.get("types") and spec["sub"] != ["Equipment"] and spec["sub"] != ["Aura"]:
        # "a Vampire card" is a creature or a tribal/kindred card: keep it as a permanent card only
        spec["types"] = ["permanent"]
    return spec


def _build(m):
    from .cards.model import Effect, NO_MATCH
    from .cards.clauses import _xq
    spec = _spec(m["desc"])
    if spec is None:
        return NO_MATCH
    if m["desc2"]:
        other = _spec(m["desc2"])
        if other is None or "any_sub" in spec or "any_sub" in other:
            return NO_MATCH
        spec = {"either": [spec, other]}
    if m["chosen"]:
        if spec.get("types") != ["creature"] or len(spec) != 1:
            return NO_MATCH
        spec["chosen"] = True
    data = {"spec": spec}
    if m["n"]:
        if "mv" in spec or "either" in spec:
            return NO_MATCH
        spec["mv"] = ["<=" if m["dir"] == "less" else ">=", int(m["n"])]
    if m["rel"]:
        # "with lesser power" (Shadowfax): compared with the source's own power / toughness
        stat = m["stat"].lower()
        data["statq"] = (stat, "<" if m["rel"].lower() == "lesser" else "<=", ("stat", "self", stat))
    op = (m["op"] or "").lower()
    if op:
        if op in ("x or less", "x"):
            q = m["where"]
        else:
            q = m["q"]
            if m["where"]:
                return NO_MATCH
        if not q and op == "x or less":
            quantity = ("paid_x",)       # the X paid for the spell or ability (Mind into Matter)
        else:
            quantity = _xq(q) if q else None
        if quantity is None or quantity[0] == "stat" and quantity[1] in ("prev", "referent"):
            return NO_MATCH          # "that damage", "that creature's power": dynamic referents (#313)
        data["mvq"] = (_MV_OPS[op], quantity)
    elif m["where"]:
        return NO_MATCH
    entry = (m["entry"] or "").strip().lower()
    if entry:
        data["entry"] = _ENTRY[entry]
        if data["entry"] == "attached" and spec.get("sub") != ["Aura"]:
            return NO_MATCH
        if data["entry"] in ("attacking", "blocking") and not all(
                "creature" in one.get("types", ()) or one.get("any_sub") for one in spec.get("either", [spec])):
            return NO_MATCH          # a noncreature permanent "attacking" (Summoner's Grimoire) is not modelled
    if any(one.get("sub") == ["Aura"] for one in spec.get("either", [spec])) and data.get("entry") != "attached":
        return NO_MATCH              # a bare Aura put from hand: the host choice is not modelled here
    if m["sac"]:
        data["sac_eot"] = True
    return Effect("hand_to_battlefield", data=data)


# "... onto the battlefield. Sacrifice it at the beginning of the next end step." (Planebound Accomplice): the
# "it" is the card this effect put, which an untargeted effect can't hand on as "prev"; fold it into the put.
def _own_where(m):
    """Bind ", where X is Q" to the put alone when X appears nowhere else in the sentence: the shared where-X rule
    (cards/parse.py) would scale every effect of the sentence ("Put two ingenuity counters on ~, then ...")."""
    head = m[1][:m[1].lower().rindex("with mana value x")]
    if re.search(r"\bX\b", head):
        return m[0]
    return f"{m[1]} HANDPUT_WHERE {m[2]}."


SUBS = [
    (re.compile(r"(from your hand onto the battlefield)\. Sacrifice it at the beginning of the next end step\.", re.I),
     r"\1 HANDPUT_SAC_EOT."),
    (re.compile(r"([^.]*\bwith mana value X or less from your hand onto the battlefield[^.,]*), where X is ([^.]+)\.",
                re.I), _own_where),
]

_MV = (r"(?: with mana value (?:(?P<n>\d+) or (?P<dir>less|greater|more)|(?P<op>equal to|less than or equal to|X or less|X)"
       r"(?: (?P<q>(?!from\b).+?))?)| with (?P<rel>lesser|equal or lesser) (?P<stat>power|toughness))?")
EFFECT_PATTERNS = [
    (r"(?:you may )?put (?:an?|one) (?P<desc>[\w ,'/-]+?) card(?: or an? (?P<desc2>[\w '/-]+?) card)?"
     r"(?P<chosen> of the chosen type)?" + _MV +
     r" from your hand onto the battlefield(?: (?P<entry>tapped and attacking(?: that opponent)?|tapped|attached to ~|blocking that creature))?"
     r"(?: HANDPUT_WHERE (?P<where>.+?))?(?P<sac> HANDPUT_SAC_EOT)?", _build),
]


# Counted puts and other players' puts (#331 slice 4):
#     Put any number of creature cards from your hand onto the battlefield.        (Ghalta, Myojin of Life's Web)
#     You may put up to two creature cards from your hand onto the battlefield.    (Tooth and Nail, Smuggler's Surprise)
#     you may put a creature card and/or a land card from your hand onto the battlefield.   (Michelangelo)
#     Each player may put an artifact, creature, enchantment, or land card from their hand onto the battlefield.
#     each other player / each opponent may put a creature card from their hand onto the battlefield.
# data: "who" (each / each_other / each_opp; absent = you), "count" (an int, or "any"), "each_of" (one card per
# listed filter). Every player chooses (active player first), then all the chosen cards enter together.
_CARD_TYPES = ("artifact", "creature", "enchantment", "land", "planeswalker", "battle")
_COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_WHO = {"each player": "each", "each other player": "each_other", "each opponent": "each_opp",
        # one other player named by the sentence: the previous target's controller (Divine Gambit, Fold into
        # Aether) or the trigger's player (Braids); "target opponent" is a targeted player
        "that player": "that", "that opponent": "that", "its controller": "that", "target opponent": "target"}


def _spec_or_list(desc: str):
    """_spec, plus card-type lists: "artifact, creature, enchantment, and/or land" -> {"any": [...]}."""
    m = re.fullmatch(r"((?:\w+, )+)(?:or|and/or) (\w+)", desc)
    if m:
        words = [w for w in m[1].split(", ") if w] + [m[2]]
        return {"any": words} if all(w in _CARD_TYPES for w in words) else None
    return _spec(desc)


def _build_many(m):
    from .cards.model import Effect, NO_MATCH
    who = _WHO.get((m["who"] or "").lower(), "")
    if who and m["whose"].lower() != "their" or not who and m["whose"].lower() != "your":
        return NO_MATCH
    data = {}
    if m["count"]:
        count = m["count"].lower()
        data["count"] = "any" if count == "any number of" else "x" if count == "up to x" else \
            _COUNTS[count.split()[-1]]
        spec = _spec_or_list(m["pdesc"])
    elif m["desc2"]:
        spec, other = _spec_or_list(m["desc"]), _spec_or_list(m["desc2"])
        if spec is None or other is None:
            return NO_MATCH
        data["each_of"] = [spec, other]
    else:
        if not who:
            return NO_MATCH            # a plain "you may put a ... card": the pattern above
        spec = _spec_or_list(m["desc"])
    if spec is None or any(one.get("any_sub") or one.get("sub") == ["Aura"] for one in data.get("each_of", [spec])):
        return NO_MATCH
    data["spec"] = spec
    if who:
        data["who"] = who
    if m["entry"]:
        data["entry"] = "tapped"
    if m["countered"]:
        if who != "that" or m["who"].lower() != "its controller":
            return NO_MATCH
        data["if_countered"] = True     # Fold into Aether: only if the counter worked
    if who == "that":
        return Effect("hand_to_battlefield", target="that_player", data=data)
    if who == "target":
        return Effect("hand_to_battlefield", target="player", filter="opp", data=data)
    return Effect("hand_to_battlefield", data=data)


EFFECT_PATTERNS.append(
    (r"(?P<countered>if that spell is countered this way, )?"
     r"(?:(?P<who>you|each player|each other player|each opponent|that player|that opponent|its controller|"
     r"target opponent) may )?put "
     r"(?:(?P<count>any number of|up to (?:one|two|three|four|five|six|seven|X)) (?P<pdesc>[\w ,'/-]+?) cards?"
     r"|(?:an?|one) (?P<desc>[\w ,'/-]+?) card(?: and/or an? (?P<desc2>[\w '/-]+?) card)?)"
     r" from (?P<whose>your|their) hand onto the battlefield(?P<entry> tapped)?", _build_many))


# ------------------------------------------------------------------ the engine side

def candidates(game, p, eff, item) -> list:
    """The cards in p's hand this effect may put onto the battlefield right now."""
    from .cx_condlib import _card_ok, _cmp
    from .engine.state import Permanent
    data = eff.data
    spec = dict(data["spec"])
    src = item.source if item is not None and isinstance(getattr(item, "source", None), Permanent) else None
    chosen = spec.pop("chosen", False)
    any_sub = spec.pop("any_sub", None)
    if chosen and not (src is not None and getattr(src, "chosen_type", "")):
        return []
    if "mvq" in data:
        op, q = data["mvq"]
        n = getattr(item, "x", 0) or 0 if q == ("paid_x",) else game.x_quantity(p, q, item, None)
        spec["mv"] = [op, n]
    elif "mv" in spec and data.get("xq"):
        # ", where X is Q" handled by the parser's shared where-X rule: it parsed "X or less" as "1 or less" and
        # tagged the effect with the quantity, so the bound is that many times Q
        op, n = spec["mv"]
        spec["mv"] = [op, n * game.x_quantity(p, data["xq"], item, None)]
    either = spec.pop("either", None)
    stat = None
    if "statq" in data:
        name, op, q = data["statq"]
        stat = (name, op, game.x_quantity(p, q, item, None))
    out = []
    for c in p.hand:
        if not c.is_permanent:
            continue
        if either:
            if not any(_card_ok(c, dict(one, **({"mv": spec["mv"]} if "mv" in spec else {}))) for one in either):
                continue
        elif not _card_ok(c, spec):
            continue
        if stat is not None:
            value = str(getattr(c, stat[0]) or "")
            if not c.is_creature or not value.isdigit() or not _cmp(int(value), stat[1], stat[2]):
                continue
        if data.get("entry") in ("attacking", "blocking") and not c.is_creature:
            continue
        if chosen and src.chosen_type not in c.subtypes:
            continue
        if any_sub and not any(s in c.subtypes for s in any_sub):
            continue
        if data.get("entry") == "attached" and not _host_ok(game, p, c, src):
            continue
        if c.aura and data.get("entry") != "attached":
            continue      # an Aura put without a host choice (303.4f isn't modelled here): not put
        out.append(c)
    return out


def _host_ok(game, p, card, host) -> bool:
    from . import auras
    return bool(card.aura) and host is not None and auras.can_attach(game, p, card, host, source=card, targeting=False)


def choose(game, me, cards, entry):
    """Default policy for ``choose_hand_put``: the card to put, or None to decline.

    Skips a legendary card whose name me already controls (the legend rule would cost one of them); an
    attacker is chosen by power, a blocker by toughness, anything else by mana value."""
    names = {x.card.name for x in me.battlefield if x.card.legendary}
    pool = [c for c in cards if not (c.legendary and c.name in names)]
    if not pool:
        return None
    def stat(c, name):
        value = str(getattr(c, name) or "0")
        return int(value) if value.isdigit() else 0
    if entry == "attacking":
        return max(pool, key=lambda c: (stat(c, "power"), c.cmc))
    if entry == "blocking":
        return max(pool, key=lambda c: (stat(c, "toughness"), stat(c, "power"), c.cmc))
    return max(pool, key=lambda c: c.cmc)


def _blocked_attacker(game, p, item):
    """ "blocking that creature": the attacker a "whenever ~ blocks a creature" trigger names (its context), while
    it is still attacking p in this combat; otherwise the creature just enters (CR 506.3)."""
    from .engine.state import Permanent
    attacker = getattr(item, "context", None)
    if not isinstance(attacker, Permanent) or game.step != "declare_blockers" or attacker not in game.attackers \
            or attacker.controller is p or attacker not in attacker.controller.battlefield:
        return None
    return attacker


def _optional(eff, item) -> bool:
    """Whether eff is the "you may put" right after its own "may" gate in item's effects."""
    effects = list(getattr(item, "effects", None) or ())
    i = next((n for n, e in enumerate(effects) if e is eff), None)
    return bool(i) and effects[i - 1].kind == "pay_gate" and effects[i - 1].data.get("gate") == ("may", "")


def _players(game, p, who, chooser=None):
    """The players who choose, active player first (APNAP)."""
    if who in ("that", "target"):
        return [chooser] if chooser is not None else []
    if not who:
        return [p]
    order = list(game.players)
    start = order.index(game.active) if game.active in order else 0
    order = order[start:] + order[:start]
    if who == "each":
        return order
    return [pl for pl in order if pl is not p]       # each_other / each_opp (two-player and free-for-all alike)


def choose_many(game, pl, eff, item) -> list:
    """The cards pl puts for a counted / and-or put: its hook picks one at a time, up to the limit."""
    from dataclasses import replace
    data = eff.data
    count = data.get("count", 1)
    if count == "x":                 # "{X}: put up to X ...": the X paid
        count = getattr(item, "x", 0) or 0
    elif isinstance(count, int) and data.get("xq"):      # "up to X ..., where X is <quantity>"
        who = getattr(item, "controller", None) or pl
        count *= game.x_quantity(who, data["xq"], item, None)
    limit = 99 if count == "any" else count
    groups = [(replace(eff, data=dict(data, spec=one)), 1) for one in data["each_of"]] if data.get("each_of") \
        else [(eff, limit)]
    out, names = [], {x.card.name for x in pl.battlefield if x.card.legendary}
    for e, n in groups:
        for _ in range(n):
            cards = [c for c in candidates(game, pl, e, item) if not any(c is x for x in out)
                     and not (c.legendary and c.name in names)]
            card = game.hook(pl, "choose_hand_put")(game, pl, cards, data.get("entry", "")) if cards else None
            if card is None or not any(card is c for c in cards):
                break
            out.append(card)
            if card.legendary:
                names.add(card.name)
    return out


def _chooser(eff, target, prev):
    """The one player of "that player / its controller / target opponent may put"."""
    from .engine.state import Permanent, Player, StackItem
    if eff.data.get("who") == "target":
        return target if isinstance(target, Player) else None
    if isinstance(prev, (Permanent, StackItem)):
        return prev.controller          # the controller of the object the previous effect acted on
    return target if isinstance(target, Player) else None      # the trigger's player (that_player)


def _put_many(game, p, eff, item, chooser=None):
    """Every chooser picks first, then all the picked cards enter together; returns p's first new permanent."""
    from .backlog_templates import entry_batch
    from .residual_templates import blocked_entry
    plan = [(pl, [c for c in choose_many(game, pl, eff, item) if c in pl.hand])
            for pl in _players(game, p, eff.data.get("who"), chooser)]
    tapped = eff.data.get("entry") == "tapped"
    mine = None
    previous = getattr(game, "_batch_entry_suppressed", False)       # as Game.enter_battlefield_many
    game._batch_entry_suppressed = previous or any(
        (c.advanced_rules.get("suppress_entry") or c.advanced_rules.get("suppress_entry_death"))
        and not blocked_entry(game, c) for _, cards in plan for c in cards)
    try:
        with entry_batch(game):          # one simultaneous entry for every player's cards (no SBA in between)
            for pl, cards in plan:
                for card in cards:
                    pl.hand.remove(card)
                    perm = game.enter_battlefield(pl, card, tapped=tapped)
                    game.log(f"puts {card.name} onto the battlefield" + (" (tapped)" if tapped else ""), pl)
                    if pl is p and mine is None:
                        mine = perm
    finally:
        game._batch_entry_suppressed = previous
    return mine


def resolve(game, p, eff, item, target=None, prev=None):
    if eff.data.get("if_countered") and (prev is None or any(prev is s for s in game.stack)):
        return None             # "if that spell is countered this way": it is still on the stack
    many = any(k in eff.data for k in ("who", "count", "each_of"))
    perm = _put_many(game, p, eff, item, _chooser(eff, target, prev)) if many else _put(game, p, eff, item)
    if item is not None and _optional(eff, item):
        item.gate_paid = perm is not None      # "If you do / If you don't, ..." ask whether a card was put
    return perm


def _put(game, p, eff, item):
    from .engine.state import Permanent
    cards = candidates(game, p, eff, item)
    entry = eff.data.get("entry", "")
    card = game.hook(p, "choose_hand_put")(game, p, cards, entry) if cards else None
    if card is None or card not in cards:
        return None
    src = item.source if item is not None and isinstance(getattr(item, "source", None), Permanent) else None
    p.hand.remove(card)
    if entry == "attached":
        game._aura_host = src
        try:
            perm = game.enter_battlefield(p, card)
        finally:
            game._aura_host = None
    elif entry == "attacking":
        in_combat = game.step in ("declare_attackers", "declare_blockers")
        # Put onto the battlefield attacking: it was never declared, so "whenever ~ attacks" doesn't trigger.
        # Outside combat it just enters tapped.
        perm = game.enter_battlefield(p, card, tapped_attacking=in_combat, tapped=not in_combat)
    elif entry == "blocking":
        perm = game.enter_battlefield(p, card)
        attacker = _blocked_attacker(game, p, item)
        if perm is not None and attacker is not None:
            # Put onto the battlefield blocking: it was never declared, so "whenever ~ blocks" doesn't trigger.
            # Evasion and block restrictions apply only to declared blocks.
            game.blocks.setdefault(attacker, []).append(perm)
            game.log(f"{card.name} blocks {attacker.card.name}", p)
    else:
        perm = game.enter_battlefield(p, card, tapped=entry == "tapped")
    game.log(f"puts {card.name} onto the battlefield" + (f" ({entry})" if entry else ""), p)
    if perm is not None and eff.data.get("sac_eot"):
        from .cards.model import Effect
        game.delayed_end_step.append((p, [Effect("sac_now")], src, perm))
    return perm


def value(game, me, eff, source) -> float:
    """AI worth of the put before it is activated: the mana value of the card it would choose (0: nothing)."""
    from types import SimpleNamespace
    from .engine.state import Permanent, StackItem
    src = source.source if isinstance(source, StackItem) else source
    item = SimpleNamespace(source=src if isinstance(src, Permanent) else None, card=getattr(src, "card", None),
                           context=None)
    if any(k in eff.data for k in ("who", "count", "each_of")):
        who = eff.data.get("who")
        mine = choose_many(game, me, eff, item) if who in (None, "each") else []
        # the opponents' hands are hidden: each one with cards in hand is assumed to put something worth 2
        others = [game.opponent(me)] if who in ("that", "target") else _players(game, me, who)
        theirs = 2.0 * sum(1 for pl in others if pl is not me and pl.hand) if who else 0.0
        return sum(float(c.cmc) + 1 for c in mine) - theirs
    cards = candidates(game, me, eff, item)
    card = game.hook(me, "choose_hand_put")(game, me, cards, eff.data.get("entry", "")) if cards else None
    return float(card.cmc) + 1 if card is not None else 0.0
