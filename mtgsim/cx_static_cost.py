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


# "for each <phrase>" counts the general quantity readers don't have (#341): exact phrases only, evaluated by
# _costq from the static's controller's point of view.
_COSTQ = {
    "1 life you gained this turn": ("life_gained",),
    "spell your opponents have cast this turn": ("opp_spells",),
    "creature you control with a +1/+1 counter on it": ("with_counter", "creature", "+1/+1"),
    "permanent you control with oil counters on it": ("with_counter", "permanent", "oil"),
    "artifact you control and each artifact card in your hand": ("artifacts_and_hand",),
    "counter among players and permanents": ("all_counters",),
    "creature card you own in exile and in your graveyard": ("creature_cards_exile_gy",),
    "different mana value among instant and sorcery cards in your graveyard": ("distinct_mv_gy",),
    "opponent who was dealt damage this turn": ("opps_damaged",),
}


def _costq(game, p, spec) -> int:
    kind = spec[0]
    if kind == "life_gained":
        return p.life_gained_turn
    if kind == "opp_spells":
        counts = getattr(game, "spells_cast", {})
        return sum(n for k, n in counts.items() if k != "turn" and k != p.name) if counts.get("turn") == game.turn else 0
    if kind == "with_counter":
        return sum(1 for x in p.battlefield if x.counters.get(spec[2], 0) > 0 and
                   (spec[1] == "permanent" or x.is_creature))
    if kind == "artifacts_and_hand":
        return sum(x.card.is_artifact for x in p.battlefield) + sum(c.is_artifact for c in p.hand)
    if kind == "all_counters":
        return sum(max(0, n) for pl in game.players for x in pl.battlefield for n in x.counters.values()) + \
            sum(max(0, n) for pl in game.players for n in getattr(pl, "counters", {}).values())
    if kind == "creature_cards_exile_gy":
        return sum(c.is_creature for c in list(p.exile) + list(p.graveyard) if getattr(c, "owner", p) in (p, None))
    if kind == "distinct_mv_gy":
        return len({c.cmc for c in p.graveyard if c.is_instant or c.is_sorcery})
    if kind == "opps_damaged":
        return sum(getattr(o, "last_damage_turn", None) == game.turn for o in game.players if o is not p)
    return 0


def _count(text: str):
    if text in _COSTQ:
        return ("costq",) + _COSTQ[text]
    from .cx_night_quantity import _quantity
    spec = _sane(_quantity("the number of " + text, plural=False))
    if spec is None:
        plural = re.sub(r"^(\w+?)(y)?\b", lambda m: m[1] + ("ies" if m[2] else "s"), text, count=1)
        spec = _sane(_quantity("the number of " + plural))
    return spec


def parse_line(line: str, st) -> bool:
    two = re.fullmatch(r"~ costs (\{\d+\}) less to cast if (.+?)(?: and|\. It also costs) (\{\d+\}) less to cast "
                       r"if (.+)\.", line)
    if two:     # "~ costs {1} less to cast if you control an artifact and {1} less to cast if you control an enchantment"
        import copy
        saved = copy.deepcopy(st.extra)
        if parse_line(f"~ costs {two[1]} less to cast if {two[2]}.", st) and \
                parse_line(f"~ costs {two[3]} less to cast if {two[4]}.", st):
            return True
        st.extra.clear()
        st.extra.update(saved)
        return False
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
    target = None
    t = re.fullmatch(r" if it targets (.+)", tail)
    if t:                               # "~ costs {2} less to cast if it targets a black permanent" (#341)
        target = target_spec(t[1])
        if target is None:
            return False
        tail = ""
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
    if m["subj"] == "~" and target is not None:
        if rule["turn"] or rule["per"] is not None or conds:
            return False
        rule["target"] = target
        rules["target_cost"] = rules.get("target_cost", ()) + (rule,)
        return True
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


def target_spec(text: str):
    """What "if it targets <text>" asks of a target: ("spell", card filter) for "a blue spell", ("card", card filter)
    for "a creature card with mana value 3 or less" (a graveyard card), ("permanent", noun spec) otherwise; or None."""
    from .cx_condlib import _filter
    m = re.fullmatch(r"an? (.+)", text.strip())
    if not m:
        return None
    words = m[1]
    spell = re.fullmatch(r"(.+?) spell", words)
    if spell:
        f = _filter(spell[1], plural=False)
        return None if f is None else ("spell", f)
    card = re.fullmatch(r"(.+? card(?: with .+)?)", words)
    if card and " card" in words:
        f = _filter(words, plural=False)
        return None if f is None else ("card", f)
    damaged = words.endswith(" that was dealt damage this turn")      # the engine's "damaged" filter: marked damage
    if damaged:
        words = words[:-len(" that was dealt damage this turn")]
    from .cx_grammar import _noun
    noun = _noun(words, plural=False)
    if noun is None:
        return None
    spec = dict(noun.get("selector", noun))
    if damaged:
        spec["damaged"] = True
    return ("permanent", spec)


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
    if rule["per"][0] == "costq":
        return max(0, _costq(game, source.controller if source is not None else p, rule["per"][1:]))
    return max(0, game.x_quantity(source.controller if source is not None else p, rule["per"], item, None))


def _applying(game, p, card):
    """(sign, amount, colored_only, times) for every cost rule that reaches this spell."""
    for rule in _temp_rules(game, p, card):         # "the next Dragon spell you cast costs {2} less"
        yield -1, rule["amount"], False, 1
        if rule["once"]:
            break
    for rule in card.advanced_rules.get("target_cost", ()):
        if _targets_fit(game, p, card, rule["target"]):
            yield rule["sign"], rule["amount"], rule.get("colored_only", False), 1
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
    if not card.is_land and (card.advanced_rules.get("self_cost") or card.advanced_rules.get("target_cost")
                             or _any_sources(game) or getattr(game, "temp_cost_rules", None)):
        mods = list(_applying(game, p, card))
    cost = dict(cost)
    cost["generic"] = cost.get("generic", 0) + increase
    unused = 0          # generic reduction beyond the generic part: it lowers the {X} part instead (601.2f, #512)
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
            unused += max(0, k - cost.get("generic", 0))
            cost["generic"] = max(0, cost.get("generic", 0) - k)
    unused += max(0, reduction - cost["generic"])
    cost["generic"] = max(0, cost["generic"] - reduction)
    game.x_reduction = unused if "X" in card.mana_cost else 0      # read by Game.cast's X loop
    return cost


def _any_sources(game) -> bool:
    from .residual_templates import sources
    return bool(sources(game, "cost_mod"))


# ---------------------------------------------------------------------------
# "~ costs {N} less to cast if it targets ..." (#341): read from the chosen targets
# ---------------------------------------------------------------------------

def _flat(targets):
    for t in targets or ():
        if isinstance(t, (tuple, list)):
            yield from _flat(t)
        elif t is not None:
            yield t


def fits(game, p, obj, spec) -> bool:
    """Whether obj (a permanent, a spell on the stack or a graveyard card) is what the rule's target spec says."""
    from .engine.state import Permanent, StackItem
    from .cx_condlib import _card_ok
    kind, f = spec
    if kind == "permanent":
        if not isinstance(obj, Permanent) or f.get("damaged") and not obj.damage > 0:
            return False
        from .permanent_templates import matches
        return matches(game, obj, {k: v for k, v in f.items() if k != "damaged"}, p, None)
    if kind == "spell":
        return isinstance(obj, StackItem) and obj.card is not None and _card_ok(obj.card, f)
    return not isinstance(obj, (Permanent, StackItem)) and hasattr(obj, "types") and _card_ok(obj, f)


def _targeted(card):
    from .engine.state import TARGETED
    return [e for e in card.spell_effects if e.target in TARGETED]


def _candidates(game, p, card):
    """Every legal target of the card's targeted effects (a castability check, before targets are chosen)."""
    with game.targeting(card):
        for e in _targeted(card):
            yield from game.legal_targets(p, e)


def _targets_fit(game, p, card, spec) -> bool:
    """While the spell is cast (Game.cast sets game._cost_targets): whether one of its chosen targets fits (601.2f
    follows 601.2c). Before that (can it be cast?): whether some legal target would."""
    chosen = getattr(game, "_cost_targets", None)
    objs = _flat(chosen) if chosen is not None else _candidates(game, p, card)
    return any(fits(game, p, o, spec) for o in objs)


def _side(game, obj):
    owner = getattr(obj, "controller", None)
    if owner is not None:
        return owner
    return next((pl for pl in game.players if any(c is obj for c in pl.graveyard)), None)


def target_cost(game, p, card, effects, targets):
    """(cost, targets) for Game.cast: the cost with the chosen targets. When the discount is what makes the spell
    affordable and a chosen target doesn't qualify, that target is replaced by the most valuable qualifying legal
    one on the same side (the caster wants the discount); otherwise the targets stay and payment decides."""
    from . import costs as _costs
    from .engine.state import Permanent, TARGETED

    def priced(tgts):
        game._cost_targets = tgts
        try:
            return game.cost_of(p, card, assist=False)
        finally:
            game._cost_targets = None
    cost = priced(targets)
    if _costs.spell_plan(game, p, card, cost) is not None:
        return cost, targets
    from .engine.policy import perm_value
    for spec in [r["target"] for r in card.advanced_rules.get("target_cost", ())]:
        for i, e in enumerate(effects):
            t = targets[i]
            if e.target not in TARGETED or t is None or isinstance(t, (tuple, list)) or fits(game, p, t, spec):
                continue
            with game.targeting(card):
                options = [o for o in game.legal_targets(p, e) if fits(game, p, o, spec) and
                           _side(game, o) is _side(game, t)]
            if not options:
                continue
            best = max(options, key=lambda o: perm_value(o) if isinstance(o, Permanent) else getattr(
                getattr(o, "card", o), "cmc", 0))
            trial = list(targets)
            trial[i] = best
            new = priced(trial)
            if _costs.spell_plan(game, p, card, new) is not None:
                return new, trial
    return cost, targets


# ---------------------------------------------------------------------------
# One-shot discounts for a group of spells (#341 slice 2)
#
#     The next Dragon spell you cast costs {2} less to cast.               (once, until used)
#     The next noncreature spell you cast this turn costs {1} less to cast. (once, this turn)
#     Artifact spells you cast this turn cost {1} less to cast.            (every one, this turn)
#
# The kind cx_temp_cost adds a rule to game.temp_cost_rules; _applying reads it like a permanent's cost_mod; a
# "next" rule is spent by the first matching spell its player casts (spell_cast, from Game.cast).
# ---------------------------------------------------------------------------

def _temp_effect(m, once: bool):
    from .cards.model import Effect
    from .cards.model import NO_MATCH     # refuse: the sentence stays unsupported (None would drop it)
    words = m["g"].strip()
    that = re.fullmatch(r"spells you cast this turn that are (\w+) and/or (\w+)", "spells you cast this turn " + words) \
        if words.startswith("that are ") else None
    group = _group(f"{that[1]} spells and {that[2]} spells you cast" if that else
                   words + (" spell you cast" if once else " spells you cast"))
    amount = _amount(m["amt"])
    if group is None or group[0] != "you" or group[2] is not None or group[3] is not None:
        return NO_MATCH
    data = {"specs": group[1], "amount": amount, "once": once, "this_turn": bool(m["turn"]) or not once}
    if "X" in amount:
        where = m["x"] if "x" in m.re.groupindex else None
        if amount != {"X": 1}:
            return NO_MATCH
        if where:           # ", where X is <Q> [as this ability resolves]": fixed on resolution
            q = _sane(_quantity(re.sub(r" as this ability resolves$", "", where)))
            if q is None:
                return NO_MATCH
            data["xq"] = q
        else:
            data["x_paid"] = True          # "The next Dragon creature spell you cast costs {X} less" (Draconic Debut)
    return Effect("cx_temp_cost", data=data)


EFFECT_PATTERNS = [
    (r"the next (?P<g>[\w ,-]+?) spell you cast(?P<turn> this turn)? costs (?P<amt>(?:\{(?:\d+|[WUBRGX])\})+) less "
     r"to cast(?:, where X is (?P<x>.+))?", lambda m: _temp_effect(m, True)),
    (r"(?P<g>[\w ,-]+?) spells you cast(?P<turn> this turn) cost (?P<amt>(?:\{(?:\d+|[WUBRGX])\})+) less to cast"
     r"(?:, where X is (?P<x>.+))?", lambda m: _temp_effect(m, False)),
    (r"spells you cast(?P<turn> this turn) (?P<g>that are \w+ and/or \w+) cost (?P<amt>\{X\}) less to cast, where X is "
     r"(?P<x>.+)", lambda m: _temp_effect(m, False)),
]
SUBS: list = []


def _temp_rules(game, p, card):
    for r in getattr(game, "temp_cost_rules", ()):
        if r["player"] is p and (r["turn"] is None or r["turn"] == game.turn) and \
                (not r["specs"] or any(_spell_ok(card, s) for s in r["specs"])):
            yield r


def spell_cast(game, p, card) -> None:
    """A spell was cast: spend the "next ... spell" discounts it used, drop the ones whose turn is over."""
    rules = getattr(game, "temp_cost_rules", None)
    if not rules:
        return
    used = next((r for r in _temp_rules(game, p, card) if r["once"]), None) if not card.is_land else None
    game.temp_cost_rules = [r for r in rules if r is not used and (r["turn"] is None or r["turn"] == game.turn)]
