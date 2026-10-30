"""Milling and moving a filtered selection of the milled cards to another zone.

Optional selections use the same tutor policy as library searches. Unrecognised
card descriptions stay unsupported rather than silently broadening the selection.
"""
from __future__ import annotations

import dataclasses
import re

_COUNT = r"a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+"
_NUMBERS = dict(zip("one two three four five six seven eight nine ten".split(), range(1, 11)))
_TYPES = {"permanent", "creature", "land", "artifact", "enchantment", "planeswalker", "instant", "sorcery", "battle"}


def _number(word):
    return int(word) if word.isdigit() else _NUMBERS.get(word.lower(), 1)


def _mill(m):
    from .cards import Effect
    who = (m[1] or "").lower()
    target = {"target player": "player", "target opponent": "player", "that player": "that_player",
              "each opponent": "each_opponent", "each player": "each_player"}.get(who, "none")
    return Effect("mill", _number(m[2]), target=target, filter="opp" if who == "target opponent" else "")


def _types(what):
    # Each alternative is a card type or a capitalised subtype (Elf, Faerie).
    types = re.split(r",? (?:or|and/or) |, ", what)
    if any(t.lower() not in _TYPES and not re.fullmatch(r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?", t) for t in types):
        return None
    return [t.lower() if t.lower() in _TYPES else t for t in types]


def _pick(m):
    from .cards import Effect, NO_MATCH
    adventure = m["what"] is None
    types = [] if adventure else _types(m["what"])
    if types is None:
        return NO_MATCH
    dest = m["dest"].lower()
    return Effect("mill_pick", 0 if m["n"].lower() in ("all", "each") else _number(m["n"].split()[-1]),
                  data={"types": types, "adventure": adventure, "all": m["n"].lower() in ("all", "each"),
                        "dest": "hand" if "hand" in dest else "top" if "top" in dest else "battlefield",
                        "tapped": dest.endswith("tapped")})


_NON_TYPE = re.compile(r"non(creature|land|artifact|enchantment|planeswalker|instant|sorcery|permanent)$")
_CMC_RIDER = re.compile(r" with mana value (\d+) or (less|greater)$")


def _alt_specs(desc):
    """The alternative card descriptions of a rich mill_pick: [(positive, negative, cmc rider)], or None.

    Each alternative is a list of card-type/subtype words that must match, a list of "non<type>"
    words that must not, and an optional ("less"/"greater", n) mana-value rider. Unrecognised
    words stay unsupported rather than silently broadening the selection."""
    specs = []
    for alt in re.split(r" or (?=an? )", desc.strip()):
        m = _CMC_RIDER.search(alt)
        cmc = (m[2], int(m[1])) if m else None
        if m:
            alt = alt[:m.start()]
        if not re.search(r" ?cards?$", alt):
            return None
        body = re.sub(r" ?cards?$", "", alt)
        body = re.sub(r"^(?:an?) ", "", body).strip()
        pos, neg = [], []
        for word in body.split() if body else []:
            word = word.strip(",")
            non = _NON_TYPE.fullmatch(word.lower())
            if non:
                neg.append(non[1])
            elif word.lower() in _TYPES or re.fullmatch(r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?", word):
                pos.append(word.lower() if word.lower() in _TYPES else word)
            else:
                return None
        specs.append((pos, neg, cmc))
    return specs


def _pick_desc(m):
    from .cards import Effect, NO_MATCH
    specs = _alt_specs(m["desc"])
    if specs is None:
        return NO_MATCH
    dest = m["dest"].lower()
    return Effect("mill_pick", 0 if m["n"].lower() in ("all", "each") else _number(m["n"].split()[-1]),
                  data={"alts": specs, "all": m["n"].lower() in ("all", "each"),
                        "dest": "hand" if "hand" in dest else "top" if "top" in dest else "battlefield",
                        "tapped": dest.endswith("tapped")})


def _alt_matches(card, specs):
    """Whether a milled card fits one alternative of a rich mill_pick description."""
    from .engine import card_matches
    for pos, neg, cmc in specs:
        ok = all(card.is_permanent if t == "permanent" else card_matches(card, f"a {t} card") for t in pos)
        if ok:
            ok = not any(card_matches(card, f"a {t} card") for t in neg)
        if ok and cmc:
            ok = card.cmc <= cmc[1] if cmc[0] == "less" else card.cmc >= cmc[1]
        if ok:
            return True
    return False


EFFECT_PATTERNS = [
    (rf"(?:(you(?: may)?|target player|target opponent|that player|each opponent|each player) )?mills? ({_COUNT}) cards?",
     _mill),
    (rf"(?:you may )?(?:put|return) (?P<n>an?|up to (?:{_COUNT})|all|each) "
     r"(?:(?P<what>[\w ,/-]+?) cards?|cards? that (?:have|has) an Adventure) "
     r"(?:from among (?:the milled cards|the cards milled this way|them)|milled this way) "
     r"(?P<dest>into your hand|to your hand|onto the battlefield(?: tapped)?|on top of your library)", _pick),
    # Rich descriptions the simple type list can't express: "a Plains card or a creature card with
    # mana value 3 or less", "a noncreature, nonland card", "a card". Validated by _alt_specs.
    (rf"(?:you may )?(?:put|return) (?P<n>an?|up to (?:{_COUNT})|all|each) (?P<desc>.+?) "
     r"(?:from among (?:the milled cards|the cards milled this way|them)|milled this way) "
     r"(?P<dest>into your hand|to your hand|onto the battlefield(?: tapped)?|on top of your library)", _pick_desc),
]


def _condition(phrase):
    shared = re.fullmatch(rf"({_COUNT}) cards that share a card type (?:were|are) milled this way", phrase, re.I)
    if shared and _number(shared[1]) >= 2:
        return {"shared": _number(shared[1])}
    m = re.fullmatch(rf"(?:(?:an?|one or more|(?P<n>{_COUNT}) or more) (?P<what>[\w ,/-]+?) cards? "
                     r"(?:is|was|are|were) milled this way|you milled an? (?P<you>[\w ,/-]+?) card this way)",
                     phrase, re.I)
    if not m:
        return None
    types = _types(m["what"] or m["you"])
    return {"types": types, "minimum": _number(m["n"] or "one")} if types else None


def parse_conditional(text, prior=()):
    """Prefix and suffix milling conditions, only when the entire reward parses."""
    from .cards import Effect, _parse_effects
    m = re.fullmatch(r"if (.+? this way), (.+)", text, re.I)
    if m:
        phrase, body = m[1], m[2]
    else:
        m = re.fullmatch(r"(.+?) if (.+)", text, re.I)
        if not m:
            return None
        body, phrase = m[1], m[2]
    condition = _condition(phrase)
    if condition is None:
        return None
    repeat = re.fullmatch(r"(.+?) and repeat this process", body, re.I)
    if repeat:
        body = repeat[1]
    effects, bad = _parse_effects(body + ".")
    if bad or not effects:
        return None
    if repeat:
        # A bounded library process: mill, check, draw, then repeat that mill.
        # Other repeating chains remain unsupported rather than guessing a scope.
        if not condition.get("shared") or not prior or prior[-1].kind != "mill" or \
                prior[-1].target != "none" or prior[-1].amount <= 0 or prior[-1].cond or \
                prior[-1].data or any(e.kind != "draw" or e.amount <= 0 or e.target != "none" or
                                     e.cond or e.data for e in effects):
            return None
        return [Effect("mill_repeat", data={"milled_condition": condition, "mill": prior[-1], "rewards": effects})]
    return [dataclasses.replace(e, data=dict(e.data, milled_condition=condition)) for e in effects]


def cards_milled(p, item):
    # A spell/ability's reward must not see a previous resolution's mill.
    return getattr(item, "milled", {}).get(p, []) if item is not None else p.milled_last


def matches(card, types):
    from .engine import card_matches
    return any(card.is_permanent if t == "permanent" else card_matches(card, f"a {t} card") for t in types)


def condition_met(p, eff, item):
    condition = eff.data["milled_condition"]
    if condition.get("shared"):
        from .modal import _CARD_TYPES
        counts = {}
        for card in cards_milled(p, item):
            for kind in card.types & _CARD_TYPES:
                counts[kind] = counts.get(kind, 0) + 1
        return max(counts.values(), default=0) >= condition["shared"]
    return sum(matches(c, condition["types"]) for c in cards_milled(p, item)) >= condition["minimum"]


def resolve_repeat(game, p, eff, item):
    while condition_met(p, eff, item):
        for reward in eff.data["rewards"]:
            game.resolve(p, reward, None, item)
            if game.over:
                return
        game.resolve(p, eff.data["mill"], None, item)


def resolve_pick(game, p, eff, item=None):
    from .engine import choose_tutor
    from .returns import entry_counters
    types = eff.data.get("types", ["permanent"])
    alts = eff.data.get("alts")
    available = list(p.graveyard)
    cands = []
    for card in cards_milled(p, item):
        match = _alt_matches(card, alts) if alts is not None else \
            (card.adventure is not None if eff.data.get("adventure") else matches(card, types))
        if card in available and match:
            cands.append(card)
            available.remove(card)
    p.picked_last = None
    n = len(cands) if eff.data.get("all") else eff.amount if "types" in eff.data or "alts" in eff.data else 1
    for _ in range(min(n, len(cands))):
        card = choose_tutor(game, p, cands)
        cands.remove(card)
        p.graveyard.remove(card)
        dest = eff.data.get("dest", "hand")
        if dest == "hand":
            p.hand.append(card)
            p.picked_last = card
        elif dest == "top":
            p.library.append(card)
        else:
            game.enter_battlefield(p, card, tapped=eff.data.get("tapped", False), counters=entry_counters(eff, item))
        location = {"hand": "into hand", "top": "on top of the library", "battlefield": "onto the battlefield"}[dest]
        game.log(f"puts milled {card.name} {location}", p)
