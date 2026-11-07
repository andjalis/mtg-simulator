"""Cost modifiers, one grammar for a spell filter, a scope, a condition and an amount:

    Black creature spells you cast cost {1} less to cast.                  (Bontu's Monument)
    Green spells and blue spells you cast cost {1} less to cast.           (Sunscape Familiar)
    White spells you cast cost {W} more to cast.                           (Alabaster Leech)
    Artifact and enchantment spells your opponents cast cost {2} more to cast.
    Spells you cast from your graveyard cost {2} less to cast.
    During turns other than yours, spells you cast cost {1} less to cast.
    The first creature spell you cast each turn costs {2} less to cast.    (Conduit of Ruin)
    As long as ~ is tapped, creature spells you cast cost {1} less to cast.
    If you have 3 or less life, ~ costs {6} less to cast.                  (Avatar of Hope)
    ~ costs {1} less to cast for each creature your opponents control.
    ~ costs {X} less to cast, where X is the greatest power among creatures you control.

The filter is a ``cx_condlib`` card filter (alternatives joined by "and": "Goblin spells and Rogue spells"), the
condition a ``cx_condlib`` code, the count a ``where X is`` quantity (``cx_night_quantity``). Rules are stored in
``CardDef.advanced_rules``:

    cost_mod:  rules of a permanent, applied to the spells they describe while it is on the battlefield
    self_cost: rules of the card itself, applied while it is cast

``adjust`` is called from ``Game.cost_of`` with the older paths' generic increases and reductions too: every
increase first, then every reduction (rule 601.2f). A colored reduction
lowers that colored part, and what it can't lower comes off the generic part (rule 118.7d) unless the card says it
reduces only colored mana.
"""
from __future__ import annotations

import re

_LABEL = r"(?:[A-Z][\w' ]* — )?"
_AMOUNT = r"(?P<amt>(?:\{(?:\d+|[WUBRGCX])\})+)"
_LINE = re.compile(
    rf"{_LABEL}(?:(?P<pre>During your turn|During turns other than yours|If (?P<if>.+?)|As long as (?P<al>.+?)), )?"
    rf"(?P<subj>.+?) costs? {_AMOUNT} (?P<dir>less|more) to cast"
    r"(?P<tail>| during your turn| during turns other than yours| if .+| as long as .+| for each .+|, where X is .+)\."
    r"(?P<only> This effect reduces only the amount of colored mana you pay\.)?")
_WHO = (" you cast", "you"), (" your opponents cast", "opp")
_ZONES = (" from your graveyard", "graveyard"), (" from anywhere other than your hand", "not_hand")


def _amount(text: str):
    cost: dict = {}
    for sym in re.findall(r"\{(\w+)\}", text):
        key = "generic" if sym.isdigit() else sym
        cost[key] = cost.get(key, 0) + (int(sym) if sym.isdigit() else 1)
    return cost


def _alt(text: str):
    """One spell filter ("white creature", "creature with flying", "instant and sorcery"): a list of specs."""
    from .cx_condlib import _filter
    text = text.strip()
    if not text:
        return [{}]
    kw = None
    m = re.fullmatch(r"(.+?) with (flying|flash|trample|haste|deathtouch|lifelink|defender|reach|vigilance)", text)
    if m:
        text, kw = m[1], m[2]
    parts = [text]
    m = re.fullmatch(r"(\w+) (?:and|or) (\w+)", text)
    if m:
        parts = [m[1], m[2]]
    specs = []
    for part in parts:
        spec = _filter(part, plural=False)
        if spec is None or len(spec.get("sub", ())) > 1 or spec.get("other") or "tapped" in spec or "counter" in spec or "modified" in spec:
            return None
        if kw:
            spec = dict(spec, card_kw=kw)
        specs.append(spec)
    return specs


def _group(text: str):
    """(who, specs, zone, first) for a spell group subject, or None."""
    first = False
    m = re.fullmatch(r"The first (.+) each turn", text)
    if m:
        text, first = m[1], True
    text = re.sub(r"^(?:Each|All) ", "", text)
    who = "all"
    for word, key in _WHO:
        if word in text:
            head, _, rest = text.partition(word)
            text, who = head + rest, key
            break
    zone = None
    for word, key in _ZONES:
        if text.endswith(word):
            text, zone = text[:-len(word)], key
    m = re.fullmatch(r"(.*?) ?spells?( with .+)?", text, re.I)
    alts = []
    if m and " spell" not in m[1].lower():
        alts = [m[1] + (m[2] or "")]
    else:
        pieces = re.split(r" spells? (?:and|or) ", text)
        if len(pieces) < 2 or not re.search(r" spells?$", pieces[-1]):
            return None
        alts = pieces[:-1] + [re.sub(r" spells?$", "", pieces[-1])]
    specs = []
    for alt in alts:
        got = _alt(alt)
        if got is None:
            return None
        specs += got
    if first and (who != "you" or len(alts) != 1):
        return None
    return who, specs, zone, (alts[0].strip() if first else None)


_LOWER = {"white", "blue", "black", "red", "green", "creature", "artifact", "enchantment", "instant", "sorcery",
          "planeswalker", "noncreature", "nonartifact", "multicolored", "colorless", "legendary", "historic",
          "spells", "permanent", "nonland", "battle", "land"}


def _first_cond(text: str) -> str:
    from .cx_condlib import parse
    noun = text.lower() if text.split()[0].lower() in _LOWER else text
    art = "an" if noun[:1].lower() in "aeiou" else "a"
    return parse(f"you haven't cast {art} {noun} spell this turn")


def _sane(spec):
    """Drop a counters quantity whose counter name is really a longer phrase the count table misread."""
    if spec is not None and spec[0] == "counters" and not re.fullmatch(r"[+-]?\w+(?:/[+-]\d+)?", spec[1]):
        return None
    from .cx_night_quantity import _known_words
    if spec is not None and spec[0] == "gy" and not _known_words(spec[1]):
        return None         # "different mana value among instant and sorcery" isn't a card count
    return spec


def _count(text: str):
    from .cx_night_quantity import _quantity
    spec = _sane(_quantity("the number of " + text, plural=False))
    if spec is None:
        plural = re.sub(r"^(\w+?)(y)?\b", lambda m: m[1] + ("ies" if m[2] else "s"), text, count=1)
        spec = _sane(_quantity("the number of " + plural))
    return spec


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m or st.level_marks or st.extra.get("_lvl_blocks"):
        return False        # a Class level's ability applies only from that level on
    from .cx_condlib import as_static, parse
    amount = _amount(m["amt"])
    rule: dict = {"sign": -1 if m["dir"] == "less" else 1, "amount": amount, "cond": "", "turn": None, "per": None}
    if m["only"]:
        if m["dir"] != "less" or "generic" in amount:
            return False
        rule["colored_only"] = True
    conds = []
    pre = m["pre"] or ""
    tail = m["tail"]
    for text in (pre, tail.strip()):
        if text.lower() in ("during your turn", "during turns other than yours"):
            if rule["turn"]:
                return False
            rule["turn"] = "yours" if text.lower() == "during your turn" else "not_yours"
    if m["if"]:
        conds.append(parse(m["if"]))
    if m["al"]:
        conds.append(as_static(m["al"]))
    t = re.fullmatch(r" if (.+)", tail)
    if t:
        conds.append(parse(t[1]))
    t = re.fullmatch(r" as long as (.+)", tail)
    if t:
        conds.append(as_static(t[1]))
    t = re.fullmatch(r" for each (.+)", tail)
    if t:
        rule["per"] = _count(t[1])
        if rule["per"] is None or "X" in amount:
            return False
    t = re.fullmatch(r", where X is (.+)", tail)
    if t:
        rule["per"] = _sane(_quantity(t[1]))
        if rule["per"] is None or amount != {"X": 1}:
            return False
        rule["amount"] = {"generic": 1}
    elif "X" in amount:
        return False
    if any(not c for c in conds) or len(conds) > 1:
        return False
    rule["cond"] = conds[0] if conds else ""
    rules = st.extra.setdefault("advanced_rules", {})
    if m["subj"] == "~":
        if rule["per"] is not None and rule["per"][0] in ("stat", "counters"):
            return False        # the spell isn't a permanent yet
        rules["self_cost"] = rules.get("self_cost", ()) + (rule,)
        return True
    group = _group(m["subj"])
    if group is None:
        return False
    rule["who"], rule["specs"], rule["zone"], first = group
    if first:
        code = _first_cond(first)
        if not code or rule["cond"]:
            return False
        rule["cond"] = code
    if not st.types or "Instant" in st.types or "Sorcery" in st.types:
        return False        # a static of a permanent
    rules["cost_mod"] = rules.get("cost_mod", ()) + (rule,)
    return True


def _quantity(text: str):
    from .cx_night_quantity import _quantity as q
    return q(text)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class _Item:
    """Stands in for a stack item when a quantity or condition is read from a static's source."""
    def __init__(self, source, card=None):
        self.source, self.context, self.card = source, None, card
        self.targets, self.x = [], 0


def _spell_ok(card, spec) -> bool:
    from .cx_condlib import _card_ok
    if not spec:
        return True
    kw = spec.get("card_kw")
    if kw and kw not in card.keywords:
        return False
    return _card_ok(card, {k: v for k, v in spec.items() if k != "card_kw"})


def _zone_ok(game, p, card, zone) -> bool:
    if zone is None:
        return True
    where = game._zone(p, game._origin(card)[1])
    return where is p.graveyard if zone == "graveyard" else where is not p.hand


def _times(game, p, rule, source, card) -> int:
    """How many times the rule's amount applies: 0 when it doesn't."""
    turn = rule["turn"]
    if turn and (game.active is p) != (turn == "yours"):
        return 0
    item = _Item(source, card)
    if rule["cond"]:
        if source is not None:
            from .cx_condlib import holds_for
            ok = holds_for(source, rule["cond"])
        else:
            from .cx_condlib import _eval_any
            ok = _eval_any(game, p, rule["cond"], item, None)
        if not ok:
            return 0
    if rule["per"] is None:
        return 1
    return max(0, game.x_quantity(source.controller if source is not None else p, rule["per"], item, None))


def _applying(game, p, card):
    """(sign, amount, colored_only, times) for every cost rule that reaches this spell."""
    for rule in card.advanced_rules.get("self_cost", ()):
        n = _times(game, p, rule, None, card)
        if n:
            yield rule["sign"], rule["amount"], rule.get("colored_only", False), n
    from .residual_templates import sources
    for x in sources(game, "cost_mod"):
        if x.abilities_suppressed:
            continue
        for rule in x.card.advanced_rules["cost_mod"]:
            who = rule["who"]
            if who == "you" and x.controller is not p or who == "opp" and x.controller is p:
                continue
            if rule["specs"] and not any(_spell_ok(card, s) for s in rule["specs"]):
                continue
            if not _zone_ok(game, p, card, rule["zone"]):
                continue
            n = _times(game, p, rule, x, card)
            if n:
                yield rule["sign"], rule["amount"], rule.get("colored_only", False), n


def adjust(game, p, card, cost: dict, increase: int = 0, reduction: int = 0) -> dict:
    """The cost after every increase, then every reduction (601.2f). increase / reduction: generic amounts from
    Game.cost_of's older paths (taxes and "or pay {N}" costs; Affinity, "costs {1} less for each ...")."""
    mods = []
    if not card.is_land and (card.advanced_rules.get("self_cost") or _any_sources(game)):
        mods = list(_applying(game, p, card))
    cost = dict(cost)
    cost["generic"] = cost.get("generic", 0) + increase
    for sign, amount, _only, n in mods:
        if sign > 0:
            for key, k in amount.items():
                cost[key] = cost.get(key, 0) + k * n
    for sign, amount, only, n in mods:
        if sign > 0:
            continue
        for key, k in amount.items():
            k *= n
            if key != "generic":
                took = min(k, cost.get(key, 0))
                if took:
                    cost[key] -= took
                    if not cost[key]:
                        del cost[key]
                k = 0 if only else k - took
            cost["generic"] = max(0, cost.get("generic", 0) - k)
    cost["generic"] = max(0, cost["generic"] - reduction)
    return cost


def _any_sources(game) -> bool:
    from .residual_templates import sources
    return bool(sources(game, "cost_mod"))
