"""Event results "this way" (#642): what the previous effect of the same resolution actually did.

    Exile target card from a graveyard. If a creature card is exiled this way, you gain 2 life.   (Deathgorge Scavenger)
    Destroy target artifact or land. If an artifact is destroyed this way, create a Treasure token. (Smashing Success)
    Mill four cards. You gain 1 life for each creature card milled this way.                       (Gorging Vulture)
    Target player mills four cards. You draw a card for each creature card put into their graveyard this way.
    ~ deals 3 damage to target creature. If a Werewolf is dealt damage this way, destroy it.      (Silver Bolt)

**The journal.** A listener on the rules-event bus (``zone_change``) records every card that moves while an effect
resolves, on the resolving item: ``(card, from zone, to zone, owner, controller)``; ``Game.deal_damage`` adds what
was dealt damage. ``start(game, item, eff)`` (called as ``Game.resolve`` begins an effect) keeps one journal for the
effects since the last one that read it (one instruction can be several engine effects), so:

* a condition on an effect ("If a creature card is exiled this way, ...") is checked before that effect resolves and
  reads ``item.tw_journal``: the previous effect's results;
* an effect that reads "this way" (by its condition or its counted amount) doesn't start a new journal, so every
  effect of "If ..., A and B" and a quantity read while the effect resolves see the same results.

**Verbs** are told apart by the move: exiled (to exile), milled (library to graveyard), discarded (hand to
graveyard), put into a graveyard (to graveyard), destroyed (battlefield to graveyard during an effect whose kind
destroys), dealt damage (the damage journal). Card filters are cx_condlib's (``_filter`` / ``_card_ok``).
Refused: anything the journal can't answer (sacrifices paid as costs, "returned", "revealed", "looked at", per-player
splits such as "creatures they controlled that were destroyed this way").
"""
from __future__ import annotations

import json
import re

_DESTROY_KINDS = ("destroy", "wrath")       # effect kinds whose battlefield-to-graveyard moves are destructions
_SAC_KINDS = ("sac", "edict")               # ... and sacrifices ("sac_own", "edict_each", a player's "sacrifices")
_VERBS = {"exiled": "exiled", "milled": "milled", "discarded": "discarded", "destroyed": "destroyed",
          "put into your graveyard": "gy_yours", "put into their graveyard": "gy", "put into a graveyard": "gy",
          "put into graveyards": "gy", "put into that player's graveyard": "gy", "sacrificed": "sacrificed",
          "sacrifice": "sacrificed"}
_VERB_RX = r"(exiled|milled|discarded|destroyed|sacrificed|put into (?:your|their|a|that player's) graveyards?|" \
    r"put into graveyards)"


# ----------------------------------------------------------------------------------------------- the journal

def _listener(game):
    def on_event(event):
        item = getattr(game, "resolving_item", None)
        if item is None or event.kind != "zone_change" or event.destination in ("stack", "battlefield"):
            return
        journal = getattr(item, "tw_journal", None)
        if journal is None:
            return
        card = event.subject
        if card is None and event.source is not None and hasattr(event.source, "card"):
            card = event.source.card            # a token leaving the battlefield
        if card is None:
            return
        before = event.before
        journal.append({"card": card, "from": event.source_zone or "", "to": event.destination,
                        "owner": getattr(card, "owner", None), "controller": getattr(before, "controller", None),
                        "kind": getattr(item, "tw_kind", "")})
    return on_event


def _ensure(game):
    if not game.__dict__.get("_this_way_listener"):
        game.__dict__["_this_way_listener"] = True
        game.rule_events.listeners.append(_listener(game))


def _reads(eff) -> bool:
    """Whether eff reads "this way" (its condition or its counted amount): it then keeps the journal it reads."""
    xq = eff.data.get("xq") if isinstance(eff.data, dict) else None
    return '"this_way"' in (eff.cond or "") or (isinstance(xq, tuple) and len(xq) > 1 and xq[:2] == ("cxq", "tw")) \
        or bool(isinstance(eff.data, dict) and eff.data.get("tw_keep"))


def start(game, item, eff):
    """Game.resolve: a new effect of item begins. The journal gathers the effects since the last one that read it:
    one instruction can be several engine effects ("destroy all artifacts and enchantments", "discard two cards,
    then draw two cards"), and "this way" names all of them. An effect that reads "this way" keeps the journal ("If a
    creature card is exiled this way, you gain 2 life and draw a card": both read the exile); the first effect after
    a reader starts a new one."""
    if item is None:
        return
    _ensure(game)
    if _reads(eff) and getattr(item, "tw_journal", None) is not None:
        item.tw_read = True
        return
    if getattr(item, "tw_journal", None) is None or getattr(item, "tw_read", False):
        item.tw_journal = []
        item.tw_read = False
    kinds = [eff.kind] + [e.kind for e in eff.data.get("effects", ()) if hasattr(e, "kind")] \
        if isinstance(eff.data, dict) else [eff.kind]
    if eff.kind == "group_remove":
        kinds = ["destroy" if eff.data.get("op") == "destroy" else eff.kind]
    item.tw_kind = "|".join(kinds)      # a wrapper (cx_players) names its inner kinds: "each player sacrifices"
    if getattr(item, "cost_sacrificed", None) and not getattr(item, "tw_cost_done", False):
        # the permanents sacrificed to pay for an activated ability: "If a Saproling was sacrificed this way"
        item.tw_cost_done = True
        item.tw_journal += [{"card": c, "from": "battlefield", "to": "graveyard", "owner": getattr(c, "owner", None),
                             "controller": None, "kind": "sac_cost"} for c in item.cost_sacrificed]


def note_damage(game, target, amount):
    """Game.deal_damage: a permanent or player was dealt damage by the resolving effect."""
    item = getattr(game, "resolving_item", None)
    journal = getattr(item, "tw_journal", None) if item is not None else None
    if journal is not None and amount > 0:
        journal.append({"damaged": target, "amount": amount})


def _entries(journal, verb, owner_name=None):
    out = []
    for e in journal:
        if "damaged" in e:
            continue
        frm, to = e["from"], e["to"]
        kinds = e["kind"].split("|")
        ok = {"exiled": to == "exile", "milled": frm == "library" and to == "graveyard",
              "discarded": frm == "hand" and to == "graveyard", "gy": to == "graveyard",
              "gy_yours": to == "graveyard", "hand": to == "hand",
              "destroyed": frm == "battlefield" and to == "graveyard" and any(k.startswith(_DESTROY_KINDS)
                                                                              for k in kinds),
              "sacrificed": frm == "battlefield" and to == "graveyard" and any(k.startswith(_SAC_KINDS) or
                                                                               "_sac" in k for k in kinds)}[verb]
        if ok and (verb not in ("gy_yours",) or getattr(e["owner"], "name", None) == owner_name):
            out.append(e)
    return out


def _known_words(words: str) -> bool:
    """Capitalised words must be real subtypes: the shared filter reads any capitalised word as one."""
    from .permanent_templates import _SUBTYPE_TYPES
    return all(w.lower() in _SUBTYPE_TYPES or w.lower().rstrip("s") in _SUBTYPE_TYPES
               for w in re.findall(r"\b[A-Z][\w'-]*", words))


def _fits(entry, spec) -> bool:
    from .cx_condlib import _card_ok
    return _card_ok(entry["card"], spec)


# ----------------------------------------------------------------------------------------------- conditions

def _cond_filter(words: str, verb: str):
    """The card filter for "a creature card" / "an artifact" / "a Pirate" / "a land card", or None."""
    from .cx_condlib import _filter
    words = words.strip()
    if not _known_words(words):
        return None
    words = re.sub(r" card$", "", words)
    if words in ("card", ""):
        return {}
    if verb not in ("destroyed", "sacrificed") and words in ("permanent",):
        return None
    return _filter(words, plural=False)


def parse_cond(phrase: str) -> str:
    """The condition code for "a creature card is exiled this way" / "an artifact is destroyed this way" /
    "you discarded a card this way" / "a Werewolf is dealt damage this way", or ""."""
    p = re.sub(r"\s+", " ", phrase.strip().rstrip(",."))
    yours = False
    m = re.fullmatch(rf"(?:a|an|at least one|one or more) (?P<f>[\w' -]+?) (?:is|was|were|are) {_VERB_RX} this way", p,
                     re.I)
    hand = re.fullmatch(r"you (?P<neg>didn't )?put (?:a|an|one or more) (?P<f>[\w' -]+?) into your hand this way", p,
                        re.I)
    if hand:        # "If you put an artifact card into your hand this way" / "If you didn't put a card into ..."
        spec = _cond_filter(hand["f"], "hand")
        if spec is None or (hand["neg"] and spec):
            return ""
        code = "lib:" + json.dumps(["this_way", "hand", spec, "you"])
        return "lib:" + json.dumps(["not", code]) if hand["neg"] else code
    if m is None:
        m = re.fullmatch(r"you (?P<v>exiled|milled|discarded|sacrificed|sacrifice) (?:a|an|one or more) "
                         r"(?P<f>[\w' -]+?) this way", p, re.I)
        if m:
            verb = m["v"].lower()
            yours = verb in ("milled", "discarded", "sacrificed", "sacrifice")  # "you discarded a card": one of your
            # cards (not another player's in "each player discards a card"); "you exiled": your own effect did it
        else:
            d = re.fullmatch(r"(?:a|an) (?P<f>[\w' -]+?) is dealt damage this way", p, re.I)
            if d is None:
                return ""
            spec = _cond_filter(d["f"], "damaged")
            return "" if spec is None else "lib:" + json.dumps(["this_way", "damaged", spec])
    else:
        verb = m[2].lower()
    verb = _VERBS.get(verb, "")
    if not verb or verb == "gy_yours":
        return ""
    spec = _cond_filter(m["f"], verb)
    if spec is None:
        return ""
    return "lib:" + json.dumps(["this_way", verb, spec] + (["you"] if yours else []))


def check(game, p, args, item, prev=None) -> bool:
    """cx_condlib.check for ["this_way", verb, spec]: something the previous effect did fits."""
    verb, spec = args[:2]
    journal = getattr(item, "tw_journal", None) or []
    if args[2:] == ["you"]:
        journal = [e for e in journal if getattr(e.get("owner"), "name", None) == p.name]
    if verb == "damaged":
        from .cx_condlib import _card_ok
        from .engine.state import Permanent
        return any(isinstance(e.get("damaged"), Permanent) and _card_ok(e["damaged"].card, spec, e["damaged"])
                   for e in journal)
    return any(_fits(e, spec) for e in _entries(journal, verb))


# ----------------------------------------------------------------------------------------------- quantities

def parse_quantity(text: str):
    """("cxq", "tw", verb, spec, opts) for "the number of creature cards milled this way" / "... exiled this way" /
    "... put into their graveyard this way" / "the number of nonartifact creatures destroyed this way" / "the number
    of creatures you controlled that were destroyed this way", or None."""
    from .cx_condlib import _filter
    t = re.sub(r"\s+", " ", text.strip().rstrip("."))
    m = re.fullmatch(rf"the number of (?P<f>[\w' -]+?)(?P<ctl> you controlled that (?:were|was))? {_VERB_RX} this way",
                     t, re.I)
    if m is None:
        return None
    verb = _VERBS.get(m[3].lower())
    words = m["f"]
    if verb is None or not _known_words(words):
        return None
    opts = {"ctl": bool(m["ctl"])}
    if re.fullmatch(r"cards?", words, re.I):
        spec = {}
    elif re.fullmatch(r"(.+?) cards?", words, re.I):     # "creature cards" (or a caller's singular "creature card")
        if verb in ("destroyed", "sacrificed"):
            return None     # permanents are destroyed, not cards: "creature cards destroyed this way" is malformed
        spec = _filter(re.fullmatch(r"(.+?) cards?", words, re.I)[1], plural=False)
    else:
        # permanents ("creatures", "nonartifact creatures", "nontoken creatures"): they left the battlefield
        if verb not in ("destroyed", "exiled", "sacrificed") or not words.lower().endswith("s"):
            return None     # a singular "permanent" comes from callers with their own "sacrificed this way" reading
        spec = {} if words.lower() == "permanents" else _filter(words, plural=True)
        opts["bf"] = True
    if spec is None or opts["ctl"] and not opts.get("bf"):
        return None
    return ("cxq", "tw", verb, spec, opts)


# "<effect> for each <thing> <verb> this way": the effect with an amount of one, its last part counted
_SCALABLE = {"p1_counters", "token", "draw", "gain_life", "lose_life", "drain", "mill", "discard", "add_mana",
             "incubate", "cx_card_choose"}


def _for_each(m):
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    from .cx_grammar import _count_spec
    from .cx_grammar import parse_sentence
    spec = _count_spec(m["d"])
    if not (isinstance(spec, tuple) and (spec[:2] == ("cxq", "tw") or spec[0] == "this_way")) or parse_sentence(m[0]):
        return NO_MATCH         # the effect grammar reads it (it runs after the templates): leave it that way
    body = m["body"].strip().rstrip(",")
    effects, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    if bad or not effects:
        return NO_MATCH
    last = effects[-1]
    if last.target == "prev":
        return NO_MATCH     # "then put a +1/+1 counter on it": "it" (a token just created) isn't reached here
    inner = last.data.get("effects") if last.kind == "cx_players" else [last]
    if not inner or any(e.kind not in _SCALABLE or e.amount != 1 or e.data.get("x") or e.data.get("xq")
                        for e in inner) or last.data.get("xq") or last.data.get("x"):
        return NO_MATCH
    import dataclasses
    # "Create a Thopter token, then put a +1/+1 counter on it for each card put into your graveyard this way": the
    # sentence's earlier parts don't start a journal of their own, so the count still reads the effect before it
    keep = [dataclasses.replace(e, data=dict(e.data, tw_keep=True)) for e in effects[:-1]]
    return keep + [dataclasses.replace(last, data=dict(last.data, xq=spec))]


EFFECT_PATTERNS = [
    (r"(?P<body>.+?),? for each (?P<d>[\w' -]+? (?:exiled|milled|discarded|destroyed|sacrificed|"
     r"put into (?:your|their|a|that player's) graveyard) this way)", _for_each),
]


def value(game, p, spec, item) -> int:
    """How many journal entries of the previous effect fit (cx_grammar_quantity.value)."""
    _, _, verb, card_spec = spec[:4]
    opts = spec[4] if len(spec) > 4 else {}
    journal = getattr(item, "tw_journal", None) or []
    entries = _entries(journal, verb, getattr(p, "name", None))
    if opts.get("bf"):
        entries = [e for e in entries if e["from"] == "battlefield"]
    if opts.get("ctl"):         # "creatures you controlled that were destroyed this way": as they last existed
        entries = [e for e in entries if e.get("controller") == getattr(p, "name", None)]
    return sum(1 for e in entries if _fits(e, card_spec))
