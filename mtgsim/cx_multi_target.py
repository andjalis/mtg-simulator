"""Counted target lists in any effect (#312, #391): "up to one target X", "up to two target Xs", "three target Xs".

    Destroy up to two target creatures.                     -> two optional, distinct "destroy" slots
    Attach up to one target Equipment you control to it.    -> one optional slot
    Exile up to three target lands you control, then return them to the battlefield tapped under their
    owner's control.                                         -> three optional chains (exile, return "it")

A sentence nothing else matched is rewritten with one singular target ("target creature", "it" for "them") and
parsed by the whole effect parser, so every verb a template or the grammar knows gets counted targets for free.
The one targeted Effect of that parse, with the Effects that act on it ("prev"), is the chain for one target:

- "up to one": the chain with ``optional_target`` (no target chosen: the chain does nothing, and the spell
  doesn't fizzle for it);
- "N" / "up to N": N copies of the chain, their targets distinct (``distinct`` within a group of their own),
  each optional for "up to".

- "any number of": one ``cx_multi`` Effect whose target slot holds a tuple of objects (engine kind "multi"):
  every member must be a legal target for the chain's first Effect (``probe``), each chosen once; on resolution
  the chain runs on each member that is still legal, and the spell fizzles only if every chosen member is gone.

Each target of a fixed count is then an ordinary slot: chosen by the AI's per-kind policy, checked on resolution, counted for
fizzling, wardable. Rejected: a sentence with another target, plural references the rewrite can't make
singular ("they", "each of them"), or a parse where other Effects don't act on the target.
"""
from __future__ import annotations

import dataclasses
import re

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_COUNTED = re.compile(r"\b(?:each of )?(up to )?(one|two|three|four|five|six|seven) (other |another )?target\b", re.I)
_PLURAL = re.compile(r"\b(creature|permanent|artifact|land|enchantment|planeswalker|player|opponent|card|spell|"
                     r"Equipment|Aura|Vehicle|token)s\b|\b([A-Z][a-z]+)s\b")
# Kinds whose lane decided an optional target needs rules of its own ("exchange control of ~ and up to one target
# creature": no exchange happens, #334).
_OWN_RULES = {"cx_exchange"}
_IRREGULAR = {"Elves": "Elf", "Dwarves": "Dwarf", "Wolves": "Wolf"}


def _singular_np(rest: str):
    """The text after "target": plural nouns of the noun phrase made singular, up to where it ends."""
    end = re.search(r"\b(?:you|an opponent|your opponents|target|that|from|to|on|onto|with|without|and gain|"
                    r"into|in|at|each|until|then|this)\b|[,.]", rest)
    np, tail = (rest[:end.start()], rest[end.start():]) if end else (rest, "")
    for plural, single in _IRREGULAR.items():
        np = re.sub(rf"\b{plural}\b", single, np)
    np = _PLURAL.sub(lambda m: m[1] or m[2], np)
    return np + tail


def _rewrite(s: str, n: int):
    """s with the counted target made a single target and its plural references singular, or None."""
    m = _COUNTED.search(s)
    head, rest = s[:m.start()], s[m.end():]
    other = m[3] or ""
    if n > 1:
        rest = _singular_np(rest)
        rest = re.sub(r"\btheir owners'", "its owner's", rest)
        rest = re.sub(r"\btheir owner's\b", "its owner's", rest)
        rest = re.sub(r"\bits owner's (hand|librar|graveyard)(s|ies)\b",
                      lambda m: "its owner's " + {"librar": "library"}.get(m[1], m[1]), rest)
        rest = re.sub(r"\bthem\b", "it", rest)
        rest = re.sub(r"\bthose (creature|permanent|land|artifact|card)s\b", r"that \1", rest)
        if re.search(r"\b(?:they|their|them|those|each|these)\b", rest, re.I):
            return None
    return head + other + "target" + rest


_ANY = re.compile(r"\bany number of (other |another )?target\b", re.I)
_AGREE = {"get": "gets", "gain": "gains", "have": "has", "become": "becomes", "lose": "loses", "deal": "deals",
          "mill": "mills", "discard": "discards", "draw": "draws", "sacrifice": "sacrifices", "create": "creates",
          "scry": "scries", "surveil": "surveils", "shuffle": "shuffles", "put": "puts", "return": "returns"}


_VERBS = "|".join(_AGREE)
_OUTSIDE_QUOTES = r'(?=[^"]*(?:"[^"]*"[^"]*)*$)'          # an even number of quotes follows


def _rewrite_any(s: str):
    m = _ANY.search(s)
    head = s[:m.start()]
    rest = _singular_np(s[m.end():])
    players = re.match(r"\s+(?:player|opponent)\b", rest) is not None
    # "... each get +1/+0 and gain ...", "Any number of target creatures become ...": the verbs agree with one target
    agreed = re.sub(rf"^((?:\s+\S+)*?)\s+each ({_VERBS})\b", lambda v: v[1] + " " + _AGREE[v[2]], rest, count=1)
    if agreed == rest and (not head or head.endswith(", ")):       # the list is the subject
        agreed = re.sub(rf"^((?:\s+(?!(?:{_VERBS})\b)\S+)*?)\s+({_VERBS})\b", lambda v: v[1] + " " + _AGREE[v[2]],
                        rest, count=1)
    rest = re.sub(rf"(\band|, then) ({_VERBS})\b{_OUTSIDE_QUOTES}", lambda v: f"{v[1]} {_AGREE[v[2]]}", agreed)
    if players:          # "each discard their hands": one player's own hand
        rest = re.sub(r"\btheir (hand|graveyard)s\b", r"their \1", rest)
        rest = re.sub(r"\btheir libraries\b", "their library", rest)
    return _plural_refs(head + (m[1] or "") + "target" + rest, players)


def _plural_refs(text: str, players: bool = False):
    head, quote, tail = text.partition('"')
    head = re.sub(r"\btheir owners'", "its owner's", head)
    head = re.sub(r"\btheir owner's\b", "its owner's", head)
    head = re.sub(r"\bits owner's (hand|librar|graveyard)(s|ies)\b",
                  lambda m: "its owner's " + {"librar": "library"}.get(m[1], m[1]), head)
    head = re.sub(r"\bthem\b", "it", head)
    plural = r"\b(?:they|them|those|each|these)\b" if players else r"\b(?:they|their|them|those|each|these)\b"
    if re.search(plural, head, re.I):
        return None
    return head + quote + tail


def _parse_one(text: str):
    """Parse the one-target sentence. "target artifact and/or enchantment" names one object, an artifact or an
    enchantment: when the words as written don't parse, read them as "artifact or enchantment"."""
    from .cards.parse import _parse_effects
    text = text[0].upper() + text[1:] + "."
    new, bad = _parse_effects(text)
    if (bad or not new) and " and/or " in text:
        new, bad = _parse_effects(text.replace(" and/or ", " or "))
    return new, bad


def legal_list(game, p, eff, tgt) -> bool:
    """A list target: each member a legal target for the chain's first Effect, none twice."""
    if tgt is None:
        return True
    if not isinstance(tgt, tuple) or len({id(x) for x in tgt}) != len(tgt):
        return False
    most = max_count(game, p, eff)
    if most is not None and len(tgt) > most:
        return False
    if not all(game.legal_target(p, eff.data["probe"], x) for x in tgt):
        return False
    if eff.kind == "gy_budget_return":
        from .graveyard_returns import budget_legal
        return budget_legal(eff, tgt)
    return True


def choose_list(game, me, eff) -> tuple:
    """The AI's choice for "any number of target ...": everything on the side its policy for one such target
    picks (its own creatures for a pump, the opponent's for removal), most valuable first."""
    from .engine.policy import default_choose_target, perm_value
    from .engine.state import Permanent
    probe = eff.data["probe"]
    pick = default_choose_target(game, me, probe)
    if pick is None:
        return ()
    side = pick.controller if isinstance(pick, Permanent) else pick
    pool = [x for x in game.legal_targets(me, probe)
            if (x.controller if isinstance(x, Permanent) else x) is side]
    pool = sorted(pool, key=lambda x: -perm_value(x) if isinstance(x, Permanent) else 0)
    most = max_count(game, me, eff)
    return tuple(pool if most is None else pool[:most])


def _lift_any(s: str, effects: list) -> bool:
    from .cards.model import Effect
    from .engine.state import TARGETED
    text = _rewrite_any(s)
    if text is None:
        return False
    new, bad = _parse_one(text)
    if bad or not new or new[0].target not in TARGETED or new[0].target == "multi" or new[0].kind in _OWN_RULES:
        return False
    if any(e.target != "prev" for e in new[1:]) or any(e.cond or e.data.get("distinct") or
                                                       e.data.get("optional_target") for e in new):
        return False
    effects.append(Effect("cx_multi", target="multi", data={"probe": new[0], "chain": list(new)}))
    return True


_UPTO_X = re.compile(r"\b(?i:up to) X ((?i:other |another ))?(?i:target)\b")
_WHERE_X = re.compile(r",? where X is (.+?)(?: as you (?:cast ~|activate this ability))?$")


def x_spec(phrase: str):
    """The X-quantity spec for ", where X is <phrase>", or None."""
    from .cards.clauses import _xq
    from .cx_grammar import _count_spec
    if re.search(r"\bnamed\b", phrase):
        return None          # "cards named ~ in all graveyards": the count spec would drop the name
    spec = _xq(phrase)
    if spec is None and phrase.lower().startswith("the number of "):
        spec = _count_spec(phrase[14:])
    return spec


def _lift_upto_x(s: str, effects: list) -> bool:
    """"Destroy up to X target lands, where X is the number of verse counters on ~": a list target of at most X
    objects, X counted when the targets are chosen (601.2c). X must mean nothing else in the sentence."""
    body = s.strip().rstrip(".")
    where = _WHERE_X.search(body)
    if where is None:
        return False
    spec = x_spec(where[1])
    body = body[:where.start()]
    if spec is None or len(re.findall(r"\bX\b", body)) != 1:
        return False
    new: list = []
    if not _lift_any(_UPTO_X.sub(lambda m: "any number of " + (m[1] or "") + "target", body), new):
        return False
    multi = new[0]
    effects.append(dataclasses.replace(multi, data=dict(multi.data, max_xq=spec)))
    return True


def max_count(game, p, eff):
    """The most objects an "up to X target" list may hold, or None for no limit. Counted while targets are chosen;
    on resolution (a stack item is the targeting source) the number chosen stands."""
    from .engine.state import Permanent, StackItem
    from .cards.model import CardDef
    spec = eff.data.get("max_xq")
    src = game.target_source
    if spec is None or isinstance(src, StackItem):
        return None
    item = StackItem(p, [], [], source=src if isinstance(src, Permanent) else None,
                     card=src if isinstance(src, CardDef) else None, name="up to X")
    return max(0, game.x_quantity(p, spec, item, None))


def lift(s: str, effects: list) -> bool:
    """Parse s, a sentence with one counted target ("up to two target creatures"), into effects. True if it did."""
    from .engine.state import TARGETED
    if chain_rider(s, effects):
        return True
    outside = re.sub(r'"[^"]*"', '""', s)          # a quoted ability's own targets are its own
    if len(re.findall(r"\btarget\b", outside, re.I)) != 1:
        return False
    if re.match(r"(?:you may )?choose\b", s, re.I):
        return False                          # "choose up to one target creature": a referent for later sentences
    if _ANY.search(outside):
        return not _COUNTED.search(outside) and _lift_any(s, effects)
    if _UPTO_X.search(outside):
        return _lift_upto_x(s, effects)
    found = list(_COUNTED.finditer(s))
    if len(found) != 1:
        return False
    m = found[0]
    n, upto = _NUM[m[2].lower()], bool(m[1])
    if n == 1 and not upto:
        return False                          # "one target creature" is just "target creature"
    text = _rewrite(s, n)
    if text is None:
        return False
    new, bad = _parse_one(text)
    if bad or not new:
        return False
    targeted = [i for i, e in enumerate(new) if e.target in TARGETED]
    if len(targeted) != 1 or targeted[0] != 0:
        return False
    # the chain on one target: the targeted Effect and Effects on "it"; for one target, untargeted Effects too
    # ("destroy up to one target artifact and you gain 2 life"), which several copies would repeat
    if any(e.target != "prev" and not (n == 1 and e.target == "none") for e in new[1:]):
        return False
    if new[0].kind in _OWN_RULES:
        return False
    if any(e.data.get("distinct") or e.data.get("optional_target") for e in new):
        return False                          # already a counted target of its own
    group = "cx_multi:" + text.lower()           # the same for every parse of this sentence
    for _ in range(n):
        first = dataclasses.replace(new[0], data=dict(new[0].data, **({"optional_target": True} if upto else {}),
                                                      **({"distinct": True, "group": group} if n > 1 else {})))
        effects.append(first)
        effects.extend(dataclasses.replace(e, data=dict(e.data)) for e in new[1:])
    return True



# ---------------------------------------------------------------- strive and riders on the chosen targets

_STRIVE = re.compile(r"(?:Strive — )?~ costs ((?:\{[^}]+\})+) more to cast for each target beyond the first\.")


def parse_line(line: str, st) -> bool:
    """"Strive — ~ costs {1}{W} more to cast for each target beyond the first." (face line)."""
    m = _STRIVE.fullmatch(line)
    if not m or "strive" in st.extra.get("advanced_rules", {}):
        return False
    from .cards.model import parse_mana_cost
    st.extra.setdefault("advanced_rules", {})["strive"] = parse_mana_cost(m[1])
    return True


def _count(effects, targets) -> int:
    from .engine.state import TARGETED
    return sum(len(t) if isinstance(t, tuple) else t is not None
               for e, t in zip(effects, targets) if e.target in TARGETED)


def strive_cost(game, p, card, effects, targets, cost):
    """The cost with strive's tax for each target beyond the first; a list target the caster can't pay for is cut
    to its most valuable members it can (choose_list sorts them). Returns (cost, targets)."""
    tax = card.advanced_rules.get("strive")
    if not tax:
        return cost, targets
    from . import costs as _costs

    def priced(n):
        out = dict(cost)
        for k, v in tax.items():
            out[k] = out.get(k, 0) + v * max(0, n - 1)
        return out
    targets = list(targets)
    while True:
        total = priced(_count(effects, targets))
        if _costs.spell_plan(game, p, card, total) is not None:
            return total, targets
        i = next((i for i in range(len(targets) - 1, -1, -1) if isinstance(targets[i], tuple) and len(targets[i]) > 1),
                 None)
        if i is None:
            return total, targets              # unaffordable: payment fails as usual
        targets[i] = targets[i][:-1]


_RIDER = re.compile(r"(untap|tap) (?:those creatures|them)|(?:they|those creatures) (gain|get) (.+)", re.I)


def chain_rider(s: str, effects: list) -> bool:
    """"Untap those creatures." / "They gain haste until end of turn." after an "any number of target" Effect: more
    of the chain each chosen target gets."""
    if not effects or effects[-1].kind != "cx_multi":
        return False
    m = _RIDER.fullmatch(s.strip().rstrip("."))
    if not m:
        return False
    from .cards.parse import _parse_effects
    text = f"{m[1].capitalize()} it." if m[1] else f"It {_AGREE[m[2].lower()]} {m[3]}."
    new, bad = _parse_effects(text)
    if bad or not new or any(e.target != "prev" or e.cond for e in new):
        return False
    multi = effects[-1]
    effects[-1] = dataclasses.replace(multi, data=dict(multi.data, chain=list(multi.data["chain"]) + new))
    return True


def no_regen_rider(s: str, effects: list) -> bool:
    """"They can't be regenerated." after a list target whose chain destroys: each destroyed member can't be."""
    if not effects or effects[-1].kind != "cx_multi" or not re.fullmatch(
            r"(?:they|those creatures|the creatures) can't be regenerated\.?", s.strip(), re.I):
        return False
    multi = effects[-1]
    chain = [dataclasses.replace(e, data=dict(e.data, no_regen=True)) if e.kind == "destroy" else e
             for e in multi.data["chain"]]
    if chain == multi.data["chain"]:
        return False
    probe = chain[0] if chain[0].kind == "destroy" else multi.data["probe"]
    effects[-1] = dataclasses.replace(multi, data=dict(multi.data, chain=chain, probe=probe))
    return True
