"""Spell additional costs: "As an additional cost to cast ~, <cost>." (#342)

A cost is one or more alternatives ("sacrifice a creature, discard a card, or pay 4 life"); an alternative
is one or more parts joined by "and" ("discard a card and sacrifice a creature"). Parts:

    sacrifice a blue permanent / two creatures / a Goblin / a creature with power 4 or greater
    sacrifice all permanents you control          discard your hand
    discard two cards / a land card / a red or green card
    pay 4 life          pay {3}{B}
    exile a creature you control                  exile two cards from your graveyard
    return a land you control to its owner's hand
    tap four untapped creatures you control / two untapped artifacts, creatures, and/or lands you control
    put a -1/-1 counter on a creature you control
    reveal a Pirate card from your hand
    behold an Elf and exile it (an Elf you control or an Elf card in hand; it returns to its owner's hand when
        the permanent the spell became leaves: "When ~ leaves the battlefield, return the exiled card ...")

The parse is stored as ``advanced_rules["spell_add_cost"]``: a tuple of alternatives, each a tuple of
``(kind, n, spec)`` parts (``spec`` is a cx_condlib filter, or the mana dict for kind "mana"). Anything
else (X counts, "any number of", "that dealt damage this turn", newer keyword costs) rejects the whole line,
which stays ignored.

Engine contract (rule 601.2b/f-h): the alternative is chosen as the spell is cast, its mana is part of the
total cost, and every part is paid in full before the spell is on the stack; Game.cast is transactional, so a
failed payment leaves nothing changed. Countering the spell refunds nothing. Copies of the spell aren't cast
and pay nothing. The AI takes the first payable alternative without mana (in printed order), else the first
with mana, and pays with its least valuable objects, avoiding the spell's own targets when it can. Paying life
needs more life than the amount (the AI never pays itself to 0), as the engine's other life costs do.
"""
from __future__ import annotations

import re

from .cards.model import parse_mana_cost

_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "X": "x", "any number of": "any"}
_Q = r"(a|an|one|two|three|four|five|six|seven|X|any number of)"
# kinds whose count may be X (chosen as the spell is cast) or "any number of"
_COUNTED = {"discard": "xa", "discard_random": "x", "life": "x", "sac": "xa", "bounce": "xa", "tap": "xa",
            "exile_gy": "xa", "exile_hand": "a", "rm_p1": "a"}
_VERB = r"(?:sacrifice|discard|pay|exile|return|tap|put|reveal|blight|forage|waterbend)\b"
_TYPES = {"artifacts": "artifact", "creatures": "creature", "lands": "land", "enchantments": "enchantment",
          "planeswalkers": "planeswalker"}
KEY = "spell_add_cost"


def _filter(desc: str, plural: bool):
    from .cx_condlib import _filter as cond_filter
    m = re.fullmatch(r"(\w+), (\w+),? and/or (\w+)", desc)
    if m:     # "artifacts, creatures, and/or lands"
        words = [_TYPES.get(w) for w in m.groups()]
        return None if None in words else {"any": words}
    return cond_filter(desc, plural=plural)


def _part(text: str):
    """One cost part as (kind, n, spec), or None."""
    m = re.fullmatch(r"sacrifice all (.+?) you control", text)
    if m:
        spec = _filter(m[1], True)
        return None if spec is None else ("sac_all", 0, spec)
    if text == "discard your hand":
        return ("discard_hand", 0, {})
    m = re.fullmatch(r"behold an? ([A-Z][\w'-]+) and exile it", text)
    if m:     # choose a <Sub> you control or a <Sub> card in your hand, and exile it
        return ("behold_exile", 1, {"sub": [m[1]]})
    m = re.fullmatch(r"pay (\d+|X) life", text)
    if m:
        return ("life", "x" if m[1] == "X" else int(m[1]), {})
    part = _keyword_part(text)
    if part is not None:
        return part
    m = re.fullmatch(r"pay ((?:\{[0-9WUBRGC]\})+)", text)
    if m:
        return ("mana", 0, parse_mana_cost(m[1]))
    m = re.fullmatch(rf"discard {_Q} cards?( at random)?", text)
    if m:
        return ("discard_random" if m[2] else "discard", _NUM[m[1]], {})
    if text == "remove any number of +1/+1 counters from among creatures you control":
        return ("rm_p1", "any", {})
    m = re.fullmatch(rf"exile {_Q} (.+? cards?) from your hand", text)
    if m:
        spec = _filter(re.sub(r" cards$", " card", m[2]), False)
        return None if spec is None or "card" not in spec.get("types", ()) else ("exile_hand", _NUM[m[1]], spec)
    m = re.fullmatch(rf"exile {_Q} (?:(.+?) )?cards? from your graveyard", text)
    if m:
        spec = _filter(m[2] + " card", False) if m[2] else {}
        return None if spec is None else ("exile_gy", _NUM[m[1]], spec)
    patterns = (("discard", rf"discard {_Q} (.+? cards?)"),
                ("reveal", r"reveal (a|an) (.+? card) from your hand"),
                ("bounce", rf"return {_Q} (.+?) you control to (?:its|their) owners?'s? hands?"),
                ("tap", rf"tap {_Q} untapped (.+?) you control"),
                ("m1_counter", r"put (a|an|one) -1/-1 counter on (?:a|an|one) (.+?) you control"),
                ("exile_bf", rf"exile {_Q} (.+?) you control"),
                ("sac", rf"sacrifice {_Q} (.+)"))
    for kind, rx in patterns:
        m = re.fullmatch(rx, text)
        if not m:
            continue
        n = _NUM[m[1]]
        desc = re.sub(r" cards$", " card", m[2])
        spec = _filter(desc, not isinstance(n, int) or n > 1)
        if spec is None or (kind in ("discard", "reveal") and "card" not in spec.get("types", ())):
            return None
        if kind == "m1_counter" and "creature" not in spec.get("types", ()):
            return None
        return (kind, n, spec)
    return None


def _keyword_part(text: str):
    """#513: "blight N" (N -1/-1 counters on one creature you control), "forage" (exile three cards from your
    graveyard or sacrifice a Food), "sacrifice half the lands you control, rounded up"."""
    m = re.fullmatch(r"blight (\d+)", text)
    if m:
        return ("blight", int(m[1]), {})
    if text == "forage":
        return ("forage", 1, {})
    m = re.fullmatch(r"waterbend \{(\d+)\}", text)
    if m:     # pay {N}; each untapped artifact or creature you control tapped for it pays {1}
        return ("waterbend", int(m[1]), {})
    if text == "sacrifice half the lands you control, rounded up":
        return ("sac_half", 0, {"types": ["land"]})
    return None


def _pick_keyword(game, p, kind, n, used, avoid, card=None):
    """Picks for the #513 parts, or None when they can't be paid."""
    from .engine.policy import perm_value
    if kind == "blight":     # one creature takes all N: a token or cheap one that survives it, else the cheapest
        pool = [x for x in p.creatures if id(x) not in used]
        if not pool:
            return None
        pool = _cheap(pool)
        pool.sort(key=lambda x: (any(x is t for t in avoid), x.toughness <= n))
        return (pool[0],)
    if kind == "forage":
        cards = sorted(p.graveyard, key=lambda c: (not c.is_land, c.cmc))
        foods = [x for x in p.battlefield if x.card.token_kind == "food" and id(x) not in used]
        if len(cards) >= 3:
            return tuple(cards[:3])
        return (foods[0],) if foods else None
    if kind == "sac_half":
        lands = _cheap([x for x in p.battlefield if x.card.is_land and id(x) not in used])
        return tuple(lands[:(len(lands) + 1) // 2])
    if kind == "waterbend":  # helpers that make no mana for the spell; the ones that can't attack now first
        sources = _mana_sources(game, p, card)
        pool = [x for x in p.battlefield if not x.tapped and id(x) not in used and id(x) not in sources
                and (x.is_creature or x.card.is_artifact)]
        pool.sort(key=lambda x: (any(x is t for t in avoid), x.is_creature and x.can_attack(), perm_value(x)))
        return tuple(pool[:n])
    return None


def _kills_worth(picked) -> bool:
    """A "blight N" that would kill a creature worth keeping: the AI pays the mana alternative instead (#513)."""
    from .engine.policy import perm_value
    return any(kind == "blight" and picks[0].toughness <= n and perm_value(picks[0]) >= 2
               for kind, n, _, picks in picked)


def parse_cost(text: str):
    """The alternatives of "<cost>" (no trailing period), or None when a part isn't modelled."""
    alts = []
    for alt in re.split(rf",? or (?={_VERB})|, (?={_VERB})", text):
        parts = tuple(_part(p) for p in re.split(rf",? and (?={_VERB})(?!exile it$)", alt))
        if not parts or None in parts or sum(k == "mana" for k, _, _ in parts) > 1:
            return None
        alts.append(parts)
    counted = [(k, n) for alt in alts for k, n, _ in alt if not isinstance(n, int)]
    if counted and (len(counted) > 1 or len(alts) > 1 or
                    any({"x": "x", "any": "a"}[n] not in _COUNTED.get(k, "") for k, n in counted)):
        return None          # one X / "any number of" part, in a cost without alternatives
    return tuple(alts)


_COLOR = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
DEFILER = "defiler"


def parse_line(line: str, extra: dict, mana_cost=None) -> bool:
    d = re.fullmatch(r"As an additional cost to cast (white|blue|black|red|green) permanent spells, you may pay 2 life\. "
                     r"Those spells cost \{([WUBRG])\} less to cast if you paid life this way\. This effect reduces "
                     r"only the amount of \1 mana you pay\.", line)
    if d and _COLOR[d[1]] == d[2]:       # the Defilers: a static on the permanent for its controller's spells
        extra.setdefault("advanced_rules", {})[DEFILER] = d[2]
        return True
    line = re.sub(r"^[A-Z][\w' ]* — ", "", line)          # an ability word ("Frenzied Metabolism — ")
    o = re.fullmatch(r"As an additional cost to cast (?:~|this spell), you may ([^.]+)\. (?:~|This spell) costs "
                     r"\{(\d+)\} less to cast for each [^.]+ this way\.", line)
    if o:      # optional "any number of", each unit paying {N} of the generic cost (Torgaar, the Marches)
        part = _part(o[1])
        if part is None or part[1] != "any" or "X" in (mana_cost or {}):
            return False     # with {X}: the engine pays X after the reduction, so it couldn't lower X (the Marches)
        extra.setdefault("advanced_rules", {})[KEY] = (((part[0], "any", dict(part[2], reduce=int(o[2]))),),)
        return True
    m = re.fullmatch(r"As an additional cost to cast (?:~|this spell), (.+)\.", line)
    if not m:
        return False
    alts = parse_cost(m[1])
    if alts is None:
        return False
    extra.setdefault("advanced_rules", {})[KEY] = alts
    return True


# --------------------------------------------------------------------------- engine


def alternatives(card):
    if getattr(card, "spell_copy", False) or getattr(card, "is_ability", False):
        return ()
    rules = getattr(card, "advanced_rules", None) or {}
    return rules.get(KEY, ())


def _cheap(things):
    from .engine.policy import perm_value
    from .engine.state import Permanent
    return sorted(things, key=lambda x: (not x.card.is_token, perm_value(x)) if isinstance(x, Permanent)
                  else (not x.is_land, x.cmc))


def _candidates(game, p, card, kind, spec):
    from .cx_condlib import _card_ok
    base = game._origin(card)[0]
    if kind in ("sac", "sac_all", "exile_bf", "bounce"):
        return [x for x in p.battlefield if _card_ok(x.card, spec, x)]
    if kind == "tap":
        return [x for x in p.battlefield if not x.tapped and _card_ok(x.card, spec, x)]
    if kind == "m1_counter":
        return [x for x in p.battlefield if x.is_creature and _card_ok(x.card, spec, x)]
    if kind == "rm_p1":            # one unit per +1/+1 counter
        return [x for x in p.battlefield if x.is_creature for _ in range(x.counters.get("+1/+1", 0))]
    if kind in ("discard", "reveal", "exile_hand"):        # never the spell's own physical card
        own = p.hand.get(base) if base in p.hand else None
        return [c for c in p.hand if c is not own and c is not card and c is not base and
                (not spec or _card_ok(c, spec))]
    if kind == "exile_gy":
        return [c for c in p.graveyard if not spec or _card_ok(c, spec)]
    if kind == "behold_exile":       # cards in hand first (the cheapest), then permanents
        own = p.hand.get(base) if base in p.hand else None
        hand = sorted((c for c in p.hand if c is not own and c is not card and c is not base and _beholds(c, spec)),
                      key=lambda c: c.cmc)
        return hand + _cheap([x for x in p.battlefield if _beholds(x.card, spec)])
    return []


def _beholds(card, spec) -> bool:
    return spec["sub"][0] in card.subtypes or bool(getattr(card, "changeling", False))


def _mana_sources(game, p, card):
    return {id(s) for s in game.mana_sources(p, spell=card)}


def _pick(game, p, card, alt, avoid=()):
    """[(kind, n, spec, picks)] for one alternative, or None when it can't be paid. Objects are distinct
    across parts; the spell's targets (avoid) are used only when nothing else will do."""
    from .residual_templates import life_locked
    used, out = set(), []
    sources = None
    for kind, n, spec in alt:
        if not isinstance(n, int):          # X / "any number of": chosen now (601.2b)
            pool = [] if kind in ("life", "discard_random") else \
                [x for x in _candidates(game, p, card, kind, spec) if id(x) not in used]
            pool = pool if kind == "rm_p1" else _cheap(pool)
            if kind == "discard_random":
                pool = list(_candidates(game, p, card, "discard", spec))
            if n == "any":              # "any number of": never the spell's own targets
                pool = [x for x in pool if not any(x is t for t in avoid)]
            else:
                pool.sort(key=lambda x: any(x is t for t in avoid))       # stable: targets last
            k = choose_count(game, p, card, kind, spec, pool, n)
            picks = tuple(pool[:k]) if kind not in ("life", "discard_random") else ()
            if kind != "rm_p1":
                used.update(id(x) for x in picks)
            out.append((kind, k, dict(spec, counted=n), picks))
            continue
        if kind == "life":
            if life_locked(p) or p.life < n:        # CR 119.4: may pay the last life (#467)
                return None
            out.append((kind, n, spec, ()))
            continue
        if kind in ("mana", "discard_hand"):
            out.append((kind, n, spec, ()))
            continue
        if kind in ("blight", "forage", "sac_half", "waterbend"):
            picks = _pick_keyword(game, p, kind, n, used, avoid, card)
            if picks is None:
                return None
            used.update(id(x) for x in picks)
            out.append((kind, n, spec, picks))
            continue
        pool = [x for x in _candidates(game, p, card, kind, spec) if id(x) not in used]
        if kind == "sac_all":
            out.append((kind, n, spec, tuple(pool)))
            used.update(id(x) for x in pool)
            continue
        if len(pool) < n:
            return None
        pool = pool if kind == "behold_exile" else _cheap(pool)
        if kind == "tap":       # keep mana sources for the mana: tap the others first
            sources = _mana_sources(game, p, card) if sources is None else sources
            pool.sort(key=lambda x: id(x) in sources)
        pool.sort(key=lambda x: any(x is t for t in avoid))       # stable: targets last
        picks = tuple(pool[:n])
        if kind != "reveal":
            used.update(id(x) for x in picks)
        out.append((kind, n, spec, picks))
    return out


def _unit_cheap(x) -> bool:
    """For "any number of": a permanent the AI gives up freely (a token or a small creature)."""
    from .engine.policy import perm_value
    return x.card.is_token or (x.is_creature and perm_value(x) <= 1.0)


def sized(card, x: int):
    """card with its X effects at x and without its additional cost (for valuing one choice of X)."""
    import dataclasses
    effects = [dataclasses.replace(e, amount=x, amount2=x if e.data.get("x2") else e.amount2,
                                   data={**e.data, "x": False, "x_n": False})
               if (e.data or {}).get("x") or (e.data or {}).get("x_n") else e
               for e in card.spell_effects]
    rules = {k: v for k, v in (card.advanced_rules or {}).items() if k != KEY}
    return dataclasses.replace(card, spell_effects=effects, advanced_rules=rules)


def choose_count(game, p, card, kind, spec, pool, mode) -> int:
    """How many: p's ``choose_cost_count`` hook if it has one; else for "any number of" every cheap unit, and for
    X the value-maximising X: the AI's own plan for the spell sized at X, less what paying X gives up."""
    hook = getattr(p.ai, "choose_cost_count", None)
    if hook is not None:
        return max(0, min(int(hook(game, p, card, kind, pool, mode)), len(pool) if pool else p.life - 1))
    limit = min(10, p.life - 1 if kind == "life" else len(pool))
    if kind == "life" and _life_locked(p):
        limit = 0
    if mode == "any" and spec.get("reduce"):
        # pay only as many units as the mana needs (cheapest first): "costs {N} less for each ... this way"
        need = sum(v for k, v in card.mana_cost.items() if k != "X") - len(game.mana_sources(p, spell=card))
        return min(limit, -(-need // spec["reduce"])) if need > 0 else 0
    if mode == "any":
        return sum(1 for x in pool[:limit] if _unit_cheap(x))
    plan = getattr(p.ai, "plan_spell", None)
    if plan is None or card.is_permanent or limit < 1:
        return 0
    best, best_k = 0.0, 0
    for k in range(1, limit + 1):
        try:
            got = plan(game, p, sized(card, k))
        except Exception:        # an evaluation the AI can't make: don't pay
            got = None
        if not got:
            continue
        net = got[0] - _value(p, [(kind, k, spec, tuple(pool[:k]))])
        if net > best + 1e-9:
            best, best_k = net, k
    return best_k


def _life_locked(p) -> bool:
    from .residual_templates import life_locked
    return bool(life_locked(p))


def has_x_cost(card) -> bool:
    return any(n == "x" for alt in alternatives(card) for _, n, _ in alt)


def cost_x(game, p, card):
    """The X this cast's additional cost will pay (for the AI's sizing), or None without an X part."""
    if not has_x_cost(card):
        return None
    chosen = choose(game, p, card)
    return next((k for kind, k, spec, _ in chosen[1] if spec.get("counted") == "x"), 0) if chosen else None


def _order(alts):
    """Alternatives without mana first (printed order), then those with mana."""
    return sorted(range(len(alts)), key=lambda i: any(k == "mana" for k, _, _ in alts[i]))


def choose(game, p, card, avoid=()):
    """(alternative index, picked parts) the cast will pay, or None when no alternative can be paid: the
    cheapest payable alternative without mana (by _value), else the first payable one with mana."""
    alts = alternatives(card)
    best = None
    for i in _order(alts):
        picked = _pick(game, p, card, alts[i], avoid)
        if picked is None:
            continue
        if any(k == "mana" for k, _, _ in alts[i]):
            return (i, picked) if best is None or _kills_worth(best[1]) else best
        if best is None or _value(p, picked) < _value(p, best[1]):
            best = (i, picked)
    return best


def payable(game, p, card) -> bool:
    return not alternatives(card) or choose(game, p, card) is not None


def extra_mana(game, p, card) -> dict:
    """The mana part of the alternative the cast will use ({} when none)."""
    if not alternatives(card):
        return {}
    chosen = choose(game, p, card)
    if chosen is None:
        return {}
    mana = next((dict(spec) for kind, _, spec, _ in chosen[1] if kind == "mana"), {})
    for kind, n, _, picks in chosen[1]:
        if kind == "waterbend" and n > len(picks):        # what the tapped helpers don't cover is paid as mana
            mana["generic"] = mana.get("generic", 0) + n - len(picks)
    return mana


def reduction(game, p, card) -> int:
    """Generic mana paid by the cost's units ("costs {2} less to cast for each creature sacrificed this way")."""
    if not alternatives(card):
        return 0
    chosen = choose(game, p, card)
    return sum(spec.get("reduce", 0) * k for _, k, spec, _ in chosen[1]) if chosen else 0


def add_mana(game, p, card, cost: dict) -> dict:
    mana = extra_mana(game, p, card)
    if not mana:
        return cost
    out = dict(cost)
    for k, v in mana.items():
        out[k] = out.get(k, 0) + v
    return out


def reserved(game, p, card, chosen=None) -> list:
    """Permanents the mana payment must not use: the ones tapped for the cost, and those the cost removes
    that would be consumed by their own mana ability (a Treasure)."""
    from .costs import consumed_for_mana
    chosen = chosen if chosen is not None else (choose(game, p, card) if alternatives(card) else None)
    if chosen is None:
        return []
    out = []
    for kind, _, _, picks in chosen[1]:
        if kind in ("tap", "waterbend"):
            out += list(picks)
        elif kind in ("sac", "sac_all", "exile_bf", "bounce"):
            out += [x for x in picks if consumed_for_mana(x)]
    return out


def for_cast(game, p, card, targets):
    """The choice a cast pays: same alternative as the cost was computed with, picks avoiding the targets."""
    if not alternatives(card):
        return None
    first = choose(game, p, card)
    if first is None:
        return None
    picked = _pick(game, p, card, alternatives(card)[first[0]], avoid=[t for t in targets if t is not None])
    return (first[0], picked if picked is not None else first[1])


def pay(game, p, card, chosen) -> tuple | None:
    """Pay the non-mana parts (the mana is already paid); returns the sacrificed creature's
    (power, toughness, mana value) for "the sacrificed creature" riders, or None. False on failure."""
    from .engine.state import Permanent
    sac_stats = None
    game._add_cost_exiled = []      # (card, owner) exiled until the permanent this spell becomes leaves
    game._add_cost_x, game._add_cost_this_way = None, None
    for kind, n, spec, picks in chosen[1]:
        if kind == "behold_exile":
            x = picks[0]
            if isinstance(x, Permanent):
                if x not in p.battlefield:
                    return False
                owner, front = x.owner, x.front
                game.log(f"beholds and exiles {x.card.name} for {card.name}", p)
                game.leave_battlefield(x, "exile")
                if not front.is_token:
                    game._add_cost_exiled.append((front, owner))
            else:
                if x not in p.hand:
                    return False
                game.log(f"beholds and exiles {x.name} from hand for {card.name}", p)
                game._add_cost_exiled.append((game.move_card(x, p.hand, p.exile, reason="cost"), p))
            continue
        if kind in ("sac", "sac_all", "exile_bf", "bounce", "tap", "m1_counter") and \
                any(not isinstance(x, Permanent) or x not in p.battlefield for x in picks):
            return False
        if kind in ("discard", "reveal") and any(c not in p.hand for c in picks):
            return False
        if kind == "exile_gy" and any(c not in p.graveyard for c in picks):
            return False
        if spec.get("counted") == "x":
            game._add_cost_x = n
        if spec.get("counted") == "any" and kind == "sac" and n:
            nouns = {t.lower() for x in picks for t in x.card.types} | {"permanent"}
            game._add_cost_this_way = ("sacrificed", frozenset(nouns), n)
        if kind == "life":
            if n:
                game.change_life(p, -n, f"{card.name}: additional cost")
        elif kind == "discard_random":
            for _ in range(n):
                if not p.hand:
                    return False
                c = game.rng.choice(list(p.hand))
                game.discard_card(p, c)
                game.log(f"discards {c.name} at random for {card.name}", p)
        elif kind in ("sac", "sac_all"):
            for x in picks:
                if sac_stats is None and x.is_creature:
                    sac_stats = (x.power, x.toughness, x.card.cmc)
                game.log(f"sacrifices {x.card.name} for {card.name}", p)
                game.sacrifice(x)
        elif kind == "exile_bf":
            for x in picks:
                game.log(f"exiles {x.card.name} for {card.name}", p)
                game.leave_battlefield(x, "exile")
        elif kind == "bounce":
            for x in picks:
                game.log(f"returns {x.card.name} to hand for {card.name}", p)
                game.leave_battlefield(x, "hand")
        elif kind == "tap":
            for x in picks:
                x.tapped = True
                game.fire(p, "becomes_tapped", x)
            game.log(f"taps {[x.card.name for x in picks]} for {card.name}", p)
        elif kind == "blight":
            x = picks[0]
            if x not in p.battlefield:
                return False
            x.counters["-1/-1"] = x.counters.get("-1/-1", 0) + n
            game.log(f"blights {n} on {x.card.name} for {card.name}", p)
        elif kind == "forage":
            if isinstance(picks[0], Permanent):
                if picks[0] not in p.battlefield:
                    return False
                game.log(f"forages: sacrifices {picks[0].card.name} for {card.name}", p)
                game.sacrifice(picks[0])
            else:
                if any(c not in p.graveyard for c in picks):
                    return False
                for c in picks:
                    game.move_card(c, p.graveyard, p.exile, reason="cost")
                game.log(f"forages: exiles {[c.name for c in picks]} for {card.name}", p)
        elif kind == "waterbend":
            if any(x not in p.battlefield or x.tapped for x in picks):
                return False
            for x in picks:
                x.tapped = True
                game.fire(p, "becomes_tapped", x)
            if picks:
                game.log(f"waterbends: taps {[x.card.name for x in picks]} for {card.name}", p)
        elif kind == "sac_half":
            if any(x not in p.battlefield for x in picks):
                return False
            for x in picks:
                game.log(f"sacrifices {x.card.name} for {card.name}", p)
                game.sacrifice(x)
        elif kind == "m1_counter":
            for x in picks:
                x.counters["-1/-1"] = x.counters.get("-1/-1", 0) + 1
                game.log(f"puts a -1/-1 counter on {x.card.name} for {card.name}", p)
        elif kind == "discard":
            pool = list(picks)
            plain = not {k: v for k, v in spec.items() if k != "counted"}
            for _ in range(n):
                choice = p.ai.choose_discard(game, p) if plain else None
                c = choice if any(choice is x for x in _candidates(game, p, card, kind, spec)) else pool[0]
                if c in pool:
                    pool.remove(c)
                if c not in p.hand:
                    return False
                game.discard_card(p, c)
                game.log(f"discards {c.name} for {card.name}", p)
        elif kind == "discard_hand":
            for c in list(p.hand):
                game.discard_card(p, c)
            game.log(f"discards their hand for {card.name}", p)
        elif kind == "exile_gy":
            for c in picks:
                game.move_card(c, p.graveyard, p.exile, reason="cost")
            game.log(f"exiles {[c.name for c in picks]} from their graveyard for {card.name}", p)
        elif kind == "reveal":
            game.log(f"reveals {picks[0].name} for {card.name}", p)
        elif kind == "exile_hand":
            for c in picks:
                if c not in p.hand:
                    return False
                game.move_card(c, p.hand, p.exile, reason="cost")
            if picks:
                game.log(f"exiles {[c.name for c in picks]} from hand for {card.name}", p)
        elif kind == "rm_p1":
            for x in picks:
                if x not in p.battlefield or x.counters.get("+1/+1", 0) < 1:
                    return False
                x.counters["+1/+1"] -= 1
            if picks:
                game.log(f"removes {len(picks)} +1/+1 counters for {card.name}", p)
    return sac_stats


def defiler_discount(game, p, card, cost: dict) -> dict:
    """The Defilers (601.2b/f): for each one p controls whose colour the permanent spell has, p may pay 2 life to
    pay one {C} less (colored only). The AI pays only when the spell isn't payable otherwise and stays above 5
    life. The decision is kept on game._defiler_life for Game.cast, which pays the life."""
    game._defiler_life = (card, 0)
    if not card.is_permanent or card.is_land or getattr(card, "spell_copy", False) or getattr(card, "is_ability", False):
        return cost
    colors = [x.card.advanced_rules.get(DEFILER) for x in p.battlefield
              if not x.abilities_suppressed and (x.card.advanced_rules or {}).get(DEFILER)]
    colors = [c for c in colors if c in card.colors]
    if not colors or _life_locked(p):
        return cost
    from .engine.mana import payable as mana_payable
    sources = game.mana_sources(p, spell=card)
    out, life = dict(cost), 0
    for c in colors:
        if mana_payable(sources, out) or not out.get(c) or p.life - life - 2 <= 5:
            break
        out[c] -= 1
        life += 2
    game._defiler_life = (card, life)
    return out


def to_item(game, item, chosen):
    """After the cast: what the paid cost hands to the spell (the X, "sacrificed this way", beheld cards)."""
    item.behold_exiled = list(getattr(game, "_add_cost_exiled", ())) if chosen is not None else []
    if chosen is None:
        return
    if getattr(game, "_add_cost_x", None) is not None:
        item.x = game._add_cost_x
    if getattr(game, "_add_cost_this_way", None) is not None:
        item.this_way = game._add_cost_this_way


def ai_cost(game, p, card) -> float:
    """What the AI gives up paying the cost (for the cast decision): permanents, cards and life."""
    chosen = choose(game, p, card) if alternatives(card) else None
    return 0.0 if chosen is None else _value(p, chosen[1])


def _value(p, picked) -> float:
    from .engine.policy import perm_value
    value = 0.0
    for kind, n, _, picks in picked:
        if kind in ("sac", "sac_all", "exile_bf"):
            value += sum(perm_value(x) if x.is_creature else 0.5 * x.card.cmc + 0.5 for x in picks)
        elif kind == "behold_exile":       # it comes back when the permanent leaves: a loan, not a loss
            value += sum(0.5 * perm_value(x) if hasattr(x, "card") else 0.5 for x in picks)
        elif kind == "bounce":
            value += sum(0.3 * x.card.cmc for x in picks)
        elif kind == "m1_counter":
            value += 0.5 * len(picks)
        elif kind == "discard":
            value += sum(0.4 if c.is_land else 1.0 for c in picks)
        elif kind == "discard_hand":
            value += 0.8 * max(0, len(p.hand) - 1)
        elif kind == "life":
            # a life curve near 0 (#502), and the AI never pays itself to 0 (#467)
            value += 0.25 * n + max(0, 8 - max(0, p.life - n)) + (100 if n >= p.life else 0) if n else 0.0
        elif kind == "tap":
            value += 0.2 * n
        elif kind == "exile_hand":
            value += 1.0 * len(picks)
        elif kind == "rm_p1":
            value += 0.6 * len(picks)
        elif kind == "blight":
            x = picks[0]
            value += perm_value(x) if x.toughness <= n else 0.5 * n
        elif kind == "forage":
            value += 0.8 if hasattr(picks[0], "card") else 0.3 * len(picks)
        elif kind == "sac_half":
            value += 1.5 * len(picks)
        elif kind == "waterbend":       # a creature that could attack is worth a little; the rest is free
            value += 0.3 * sum(x.is_creature and x.can_attack() for x in picks)
    return value
