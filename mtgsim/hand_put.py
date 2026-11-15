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

Multi-puts ("put up to two creature cards ...", "put any number of land cards ... tapped", #523) are the same
effect with ``data["many"]`` and the count in ``amount`` ("any number" is 99, the gy_move convention); a
", where X is ..." on the sentence scales ``amount`` through the shared where-X rule, so "put up to X land
cards ..., where X is ..." needs no special casing.

Only the controller's own hand is covered: "each player may" / "that player may" need a decision by another
player and are left unmatched, as are quantities ``_xq`` doesn't know ("that damage": #313).
"""
from __future__ import annotations

import re

_ENTRY = {"tapped": "tapped", "tapped and attacking": "attacking", "tapped and attacking that opponent": "attacking",
          "attached to ~": "attached", "attached to it": "attached", "blocking that creature": "blocking"}
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


def _common(m):
    """The shared data of a put: spec, mana value bound, entry modifier. NO_MATCH when unsupported."""
    from .cards.model import NO_MATCH
    from .cards.clauses import _xq
    gd = m.groupdict()
    spec = _spec(m["desc"])
    if spec is None:
        return NO_MATCH
    if gd.get("desc2"):
        other = _spec(gd["desc2"])
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
        if not q and op in ("x or less", "x"):
            quantity = ("paid_x",)       # the X paid for the spell or ability (Mind into Matter, {X}{U}: Metathran Aerostat)
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
        if entry == "attached to it":
            data["attach_it"] = True        # the host is the trigger's referent, not the source (Holy Avenger)
        if data["entry"] == "attached" and spec.get("sub") != ["Aura"]:
            return NO_MATCH
        if data["entry"] in ("attacking", "blocking") and not all(
                "creature" in one.get("types", ()) or one.get("any_sub") for one in spec.get("either", [spec])):
            return NO_MATCH          # a noncreature permanent "attacking" (Summoner's Grimoire) is not modelled
    if any(one.get("sub") == ["Aura"] for one in spec.get("either", [spec])) and data.get("entry") != "attached":
        return NO_MATCH              # a bare Aura put from hand: the host choice is not modelled here
    if m["sac"]:
        data["sac_eot"] = True
    return data


def _build(m):
    from .cards.model import Effect, NO_MATCH
    data = _common(m)
    if data is NO_MATCH:
        return NO_MATCH
    return Effect("hand_to_battlefield", data=data)


def _build_many(m):
    """"Put up to N / any number of <desc> cards from your hand onto the battlefield" (#523): the count rides
    in the effect's amount, so the shared where-X rule scales "up to X" by its quantity at resolution."""
    from .cards.model import Effect, NO_MATCH, _num
    data = _common(m)
    if data is NO_MATCH:
        return NO_MATCH
    gd = m.groupdict()
    if gd.get("many_any"):
        n = 99                    # "any number of": every candidate the policy chooses to put
    else:
        try:
            n = _num(gd["many_n"])
        except (KeyError, ValueError):
            return NO_MATCH       # "up to X" with no ", where X is ...": no constant count
    data["many"] = True
    return Effect("hand_to_battlefield", amount=n, data=data)


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
_ENTRY_RX = r"(?: (?P<entry>tapped and attacking(?: that opponent)?|tapped|attached to (?:~|it)|blocking that creature))?"
_WHERE_RX = r"(?: HANDPUT_WHERE (?P<where>.+?))?(?P<sac> HANDPUT_SAC_EOT)?"
EFFECT_PATTERNS = [
    (r"(?:you may )?put (?:up to (?P<many_n>\w+)|(?P<many_any>any number of)) (?P<desc>[\w ,'/-]+?) cards?"
     r"(?P<chosen> of the chosen type)?" + _MV + r" from your hand onto the battlefield" + _ENTRY_RX + _WHERE_RX,
     _build_many),
    (r"(?:you may )?put (?:an?|one) (?P<desc>[\w ,'/-]+?) card(?: or an? (?P<desc2>[\w '/-]+?) card)?"
     r"(?P<chosen> of the chosen type)?" + _MV +
     r" from your hand onto the battlefield" + _ENTRY_RX + _WHERE_RX, _build),
]


# ------------------------------------------------------------------ the engine side

def candidates(game, p, eff, item) -> list:
    """The cards in p's hand this effect may put onto the battlefield right now."""
    from .cx_condlib import _card_ok, _cmp
    data = eff.data
    spec = dict(data["spec"])
    src = _source_perm(game, item)
    host = _host_perm(game, item, data.get("attach_it"))
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
        if data.get("entry") == "attached" and not _host_ok(game, p, c, host):
            continue
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


def choose_many(game, me, cards, entry, n) -> list:
    """Default policy for a multi-put: up to n cards, each picked through the single-choice hook."""
    picked, remaining = [], list(cards)
    while remaining and len(picked) < n:
        card = game.hook(me, "choose_hand_put")(game, me, remaining, entry)
        if card is None or card not in remaining:
            break
        picked.append(card)
        remaining.remove(card)
    return picked


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


def resolve(game, p, eff, item):
    perms = _put(game, p, eff, item)
    if item is not None and _optional(eff, item):
        item.gate_paid = bool(perms)      # "If you do / If you don't, ..." ask whether a card was put
    if eff.data.get("many"):
        return perms or None
    return perms[0] if perms else None


def _put(game, p, eff, item):
    cards = candidates(game, p, eff, item)
    entry = eff.data.get("entry", "")
    if not cards:
        return []
    limit = eff.amount if eff.data.get("many") else 1    # amount already scaled by a where-X quantity
    return [perm for card in choose_many(game, p, cards, entry, limit)
            if (perm := _enter_one(game, p, eff, item, card, entry)) is not None]


def _host_perm(game, item, attach_it):
    """The Aura's host: "attached to it" names the trigger's referent (the equipped creature, the returned
    card), "attached to ~" the source itself."""
    from .engine.state import Permanent
    if attach_it:
        from .referent import permanent as _ref
        who = _ref(item, None, game)
        if isinstance(who, Permanent):
            return who
    return _source_perm(game, item)


def _source_perm(game, item):
    """The permanent this effect's source is: the ability/trigger's own permanent, or — for a graveyard
    ability ("Return this card from your graveyard ... attached to it", Evershrike) — the permanent the
    card became when it returned."""
    from .engine.state import Permanent
    if item is None:
        return None
    src = getattr(item, "source", None)
    if isinstance(src, Permanent):
        return src
    ctx = getattr(item, "context", None)
    from .cards.model import CardDef
    if isinstance(ctx, CardDef):
        for pl in game.players:
            for perm in pl.battlefield:
                if perm.card is ctx:
                    return perm
    return None


def _enter_one(game, p, eff, item, card, entry):
    src = _source_perm(game, item)
    p.hand.remove(card)
    if entry == "attached":
        game._aura_host = _host_perm(game, item, eff.data.get("attach_it"))
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
    """AI worth of the put before it is activated: the mana value of the card(s) it would choose (0: nothing)."""
    from types import SimpleNamespace
    from .engine.state import Permanent, StackItem
    src = source.source if isinstance(source, StackItem) else source
    item = SimpleNamespace(source=src if isinstance(src, Permanent) else None, card=getattr(src, "card", None),
                           context=getattr(src, "card", None) if isinstance(src, Permanent) else None)
    cards = candidates(game, me, eff, item)
    entry = eff.data.get("entry", "")
    if eff.data.get("many"):
        limit = eff.amount or 99
        if eff.data.get("xq"):
            limit *= game.x_quantity(me, eff.data["xq"], item, None)
        picked = choose_many(game, me, cards, entry, limit)
        return sum(c.cmc for c in picked) + len(picked) if picked else 0.0
    card = game.hook(me, "choose_hand_put")(game, me, cards, entry) if cards else None
    return float(card.cmc) + 1 if card is not None else 0.0
