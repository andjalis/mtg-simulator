"""Small effects for the most common single-sentence gaps.

* "Destroy / Exile / Return target <desc> [to its owner's hand]" where <desc> is a disjunction the base table
  doesn't know ("creature or Vehicle", "artifact, creature, or Vehicle you control"): the description is read
  with the trigger-event library's subject grammar and checked in ``Game.passes_filter`` (``cx_desc``).
* "Target opponent draws N cards." / "Each opponent draws N cards." (two players: the opponent draws).
* "Put [up to N] target <desc> card from your graveyard on top of your library."
* "Return a <desc> card at random from your graveyard to your hand / the battlefield."
* "If a creature would die this turn, exile it instead." (every creature, for the rest of the turn) and
  "If it / that creature would die this turn, exile it instead." (the previous target).
* "for each card in target opponent's hand" / "in each opponent's hand": the opponent's hand size.
* "You win the game." / "You lose the game."; "You have no maximum hand size for the rest of the game.";
  "Put ~ on top of its owner's library."
* Land animations the animate_templates SUBS leave: "[Up to one] target [snow] land / Mountain [you control] becomes
  a N/N ... creature [with kws] [until end of turn]. It's still a land." (or "that's still a land"), and "It /
  That land becomes a 0/0 ... creature ..." after counters were put on it. Without "until end of turn" the land
  stays a creature. The animating player picks one of their own lands.
"""
from __future__ import annotations

import re

KINDS = {"cx_gy_top", "cx_gy_random", "cx_exile_turn", "cx_win"}
_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _num(word):
    word = word.lower()
    return int(word) if word.isdigit() else _N[word]


def _desc_ok(desc: str):
    from .cx_events import _object_subject
    spec = _object_subject("a " + desc)
    return spec is not None and not spec["host"] and not spec["batch"] and not spec["self"]


def _targeted(kind):
    def make(m):
        from .cards.model import NO_MATCH
        from .cards import Effect
        desc = m[1]
        if " or " not in desc and "," not in desc or not _desc_ok(desc):
            return NO_MATCH
        return Effect(kind, target="permanent", data={"cx_desc": desc})
    return make


def _draws(m):
    from .cards import Effect
    return Effect("draw", _num(m[1]), target="each_opponent")


def _gy_top(m):
    from .cards.model import NO_MATCH
    from .cards import Effect
    from .cx_events import _desc_alts
    desc = (m[2] or "").strip()
    if desc and _desc_alts(desc) is None:
        return NO_MATCH
    return Effect("cx_gy_top", _num(m[1]) if m[1] else 1, data={"what": desc, "up_to": bool(m[1])})


def _gy_random(m):
    from .cards.model import NO_MATCH
    from .cards import Effect
    from .cx_events import _desc_alts
    if _desc_alts(m[1]) is None:
        return NO_MATCH
    return Effect("cx_gy_random", 1, data={"what": m[1], "dest": "hand" if m[2] == "your hand" else "bf"})


def _exile_turn(m):
    from .cards import Effect
    return Effect("cx_exile_turn")


def _exile_prev(m):
    from .cards import Effect
    return Effect("exile_instead", target="prev")


def _simple(kind, **kw):
    def make(m):
        from .cards import Effect
        return Effect(kind, **kw)
    return make


EFFECT_PATTERNS = [
    (r"you win the game", _simple("cx_win", data={"win": True})),
    (r"you lose the game", _simple("cx_win", data={"win": False})),
    (r"you have no maximum hand size for the rest of the game",
     _simple("cx_player_flag", data={"flag": "no_max_hand", "who": "you", "forever": True})),
    (r"put ~ on top of its owner's library", _simple("tuck_perm", target="self", data={"depth": 0})),
    (r"destroy target ([\w ,/-]+?)", _targeted("destroy")),
    (r"exile target ([\w ,/-]+?)", _targeted("exile_permanent")),
    (r"return target ([\w ,/-]+?) to its owner's hand", _targeted("bounce")),
    (r"(?:target|each) opponent draws (a|an|one|two|three|\d+) cards?", _draws),
    (r"put (?:up to (one|two|three) )?target ((?:[\w-]+ )*?)cards? from your graveyard on top of your library",
     _gy_top),
    (r"return an? ([\w ,-]+?) card at random from your graveyard to (your hand|the battlefield)", _gy_random),
    (r"if a creature would die this turn, exile it instead", _exile_turn),
    (r"if (?:it|that creature|the creature an opponent controls|that permanent) would die this turn, exile it instead",
     _exile_prev),
]

def _animate(m):
    from .cards.model import NO_MATCH
    from .cards import Effect
    from .animate_templates import _KEYWORDS
    desc = re.sub(r" you control$", "", m["desc"].strip())
    desc = " ".join(w.title() if w in ("mountain", "forest", "plains", "island", "swamp", "cave", "desert") else w
                    for w in desc.split())
    if m["who"] == "t" and desc != "land" and not _desc_ok(desc):
        return NO_MATCH
    kws = frozenset(k.strip() for k in re.split(r",| and ", m["kws"] or "") if k.strip())
    if not kws <= set(_KEYWORDS.split("|")):
        return NO_MATCH
    data = {"selector": {"controller": "mine", "types_all": ["land"]}, "keywords": kws, "permanent": m["perm"] == "1"}
    if m["who"] == "t" and desc != "land":
        data["cx_desc"] = desc
    return Effect("animate_land", int(m["p"]), int(m["t"]), target="permanent" if m["who"] == "t" else "prev",
                  data=data)


_LAND = r"(?:snow |basic |nonbasic )?land|mountain|forest|plains|island|swamp|cave|desert"
_ANIM = re.compile(
    r"(?:(?:up to one )?target (?P<desc>(?:" + _LAND + r")(?: you control)?)|(?P<it>it|that land)) becomes an? "
    r"(?P<p>\d+)/(?P<t>\d+) [\w ]*?creature(?: with (?P<kws>[\w ,]+?))?(?P<eot> until end of turn)?"
    r"(?:\. it's still a land| that's still a land)(?=\.|$)", re.I)


def _anim_sub(m):
    who = "p" if m["it"] else "t"
    desc = (m["desc"] or "").lower()
    if desc.startswith("snow "):
        return m[0]
    return f"CXANIM {who} {m['p']} {m['t']} {0 if m['eot'] else 1} {desc}|{m['kws'] or ''}"

EFFECT_PATTERNS.append(
    (r"cxanim (?P<who>[tp]) (?P<p>\d+) (?P<t>\d+) (?P<perm>[01]) (?P<desc>[\w ]*)\|(?P<kws>[\w ,]*)", _animate))

SUBS = [
    (_ANIM, _anim_sub),
    (re.compile(r"for each card in (?:target|each) opponent's hand", re.I), "for each card in an opponent's hand"),
]


# ---------------------------------------------------------------- engine side

def passes(game, eff, perm, by) -> bool | None:
    """The cx_desc target check, or None when the effect has none."""
    desc = eff.data.get("cx_desc")
    if not desc:
        return None
    from .cx_events import _object_subject, _obj_match
    spec = _object_subject("a " + desc)
    if spec is None:
        return False

    class _Viewer:              # _obj_match reads the watcher's controller for "you control"
        controller = by
    return _obj_match(game, spec, _Viewer, perm)


def _card_fits(card, desc: str) -> bool:
    if not desc:
        return True
    from .engine.state import card_matches
    return card_matches(card, "a " + desc.strip() + " card") or card_matches(card, "a " + desc.strip())


def gy_top(game, p, eff):
    picks = sorted((c for c in p.graveyard if _card_fits(c, eff.data["what"])), key=lambda c: c.cmc, reverse=True)
    for card in picks[:eff.amount]:
        game.move_card(card, p.graveyard, p.library, reason="gy_to_top")     # the library's end is its top
        game.log(f"puts {card.name} on top of their library", p)


def gy_random(game, p, eff):
    pool = [c for c in p.graveyard if _card_fits(c, eff.data["what"])]
    if not pool:
        return
    card = game.rng.choice(pool)
    if eff.data["dest"] == "hand":
        game.move_card(card, p.graveyard, p.hand, reason="return")
        game.log(f"returns {card.name} at random to their hand", p)
    else:
        p.graveyard.remove(card)
        game.enter_battlefield(p, card)


def exile_this_turn(game, perm) -> bool:
    return getattr(game, "cx_exile_turn", None) == game.turn and perm.is_creature


def win(game, p, eff):
    loser = [x for x in game.players if x is not p][0] if eff.data["win"] else p
    if not loser.lost:
        game.audit("loss", seat=game.players.index(loser), cause="a card's effect")
        loser.lost = True
