"""Alternative costs: "[If <condition>, ]you may <costs> rather than pay ~'s mana cost."

    You may pay 1 life and exile a blue card from your hand rather than pay ~'s mana cost.     (Force of Will)
    If you control a Swamp, you may pay 4 life rather than pay ~'s mana cost.                  (Snuff Out)
    You may sacrifice two Mountains rather than pay ~'s mana cost.                             (Fireblast)
    You may return two Islands you control to their owner's hand rather than pay ~'s mana cost. (Gush)
    If an opponent gained life this turn, you may pay {B} rather than pay ~'s mana cost.      (Needlebite Trap)

Each line becomes an ``AltCost("cond_alt_<i>")`` holding the mana part and the life; the condition and the other
parts are ``advanced_rules["alt_if"][i] = (condition code, ((part, count, filter), ...))``, the parts being
sac, pitch (exile from hand), discard, bounce (return to hand), tap and exile_gy. ``variants`` offers the cast while
the condition holds and every part can be paid; a cast that needs more than mana and life is only offered when the
mana cost can't be paid. ``pay`` pays the parts as the spell is cast (Game.cast)."""
from __future__ import annotations

import re

_Q = r"(?P<q>a|an|one|two|three|four|five|another)"
_QN = {"a": 1, "an": 1, "one": 1, "another": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_LINE = re.compile(r"(?:If (?P<c>.+?), )?you may (?P<costs>.+?) rather than pay (?:~'s|this spell's) mana cost\.",
                   re.I)
_PARTS = [
    ("mana", re.compile(r"pay (?P<m>(?:\{[^}]+\})+)")),
    ("life", re.compile(r"pay (?P<n>\d+) life")),
    ("sac", re.compile(rf"sacrifice {_Q} (?P<f>[\w ,-]+?)")),
    ("pitch", re.compile(rf"exile {_Q} (?P<f>[\w -]+?) cards? from your hand")),
    ("discard2", re.compile(rf"discard {_Q} (?P<f>[\w-]+) card and another card")),
    ("discard", re.compile(rf"discard {_Q} (?P<f>[\w -]+?) card")),
    ("bounce", re.compile(rf"return {_Q} (?P<f>[\w -]+?) you control to (?:its|their) owner's hand")),
    ("tap", re.compile(rf"tap {_Q} untapped (?P<f>[\w -]+?) you control")),
    ("exile_gy", re.compile(rf"exile {_Q} (?P<f>[\w -]+?) card from your graveyard")),
]


def _parts(text: str):
    from .cx_condlib import _filter
    from .cards.model import parse_mana_cost
    mana, life, parts = None, 0, []
    for piece in re.split(r", and |, | and (?!another card)", text):
        for name, rx in _PARTS:
            m = rx.fullmatch(piece.strip())
            if not m:
                continue
            if name == "mana":
                mana = parse_mana_cost(m["m"])
            elif name == "life":
                life = int(m["n"])
            else:
                n = _QN[m["q"].lower()]
                spec = _filter(m["f"], plural=n > 1)
                if spec is None:
                    return None
                if name == "discard2":
                    parts += [("discard", 1, spec), ("discard", 1, {})]
                else:
                    parts.append((name, n, spec))
            break
        else:
            return None
    return mana, life, tuple(parts)


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m:
        return False
    code = ""
    if m["c"]:
        from .cx_condlib import parse
        code = parse(m["c"])
        if not code:
            return False
    got = _parts(m["costs"])
    if got is None:
        return False
    mana, life, parts = got
    if not code and not life and not parts:
        return False            # a plain "You may pay {X} rather than pay ~'s mana cost" (face_lines: AltCost "alt")
    from .cards.model import AltCost
    rules = st.extra.setdefault("advanced_rules", {})
    index = len(rules.get("alt_if", ()))
    rules["alt_if"] = rules.get("alt_if", ()) + ((code, parts),)
    st.alt_costs.append(AltCost(f"cond_alt_{index}", mana or {"generic": 0}, life=life))
    return True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _candidates(game, p, card, part, n, spec):
    from .cx_condlib import _card_ok
    if part == "pitch" or part == "discard":
        return [c for c in p.hand if c is not card and _card_ok(c, spec)]
    if part == "exile_gy":
        return [c for c in p.graveyard if _card_ok(c, spec)]
    if part == "tap":
        return [x for x in p.battlefield if not x.tapped and _card_ok(x.card, spec, x)]
    return [x for x in p.battlefield if _card_ok(x.card, spec, x)]


def _payable(game, p, card, parts) -> bool:
    used: set = set()
    for part, n, spec in parts:
        pool = [c for c in _candidates(game, p, card, part, n, spec) if id(c) not in used]
        if len(pool) < n:
            return False
        used.update(id(c) for c in pool[:n])
    return True


def variants(game, p, card) -> list:
    out = []
    rules = card.advanced_rules.get("alt_if") if card.advanced_rules else None
    if not rules:
        return out
    from .cards.model import Effect
    normal = None
    for a in card.alt_costs:
        if not a.kind.startswith("cond_alt_"):
            continue
        code, parts = rules[int(a.kind[9:])]
        if code and not game.check_cond(p, Effect("alt", cond=code), None, None):
            continue
        if not _payable(game, p, card, parts) or a.life and p.life <= a.life:
            continue
        if parts:
            if normal is None:
                normal = game.spell_payable(p, card)
            if normal:
                continue
        out.append(game._variant(card, a.kind, a))
    return out


def _cheapest(things):
    def value(x):
        c = getattr(x, "card", x)
        return (not getattr(c, "is_land", False), getattr(c, "cmc", 0))
    return sorted(things, key=value)


def pay(game, p, card, kind: str) -> bool:
    """Pay the non-mana parts of a cond_alt cast; False when they can't be paid."""
    code, parts = card.advanced_rules["alt_if"][int(kind[9:])]
    if not _payable(game, p, card, parts):
        return False
    for part, n, spec in parts:
        for thing in _cheapest(_candidates(game, p, card, part, n, spec))[:n]:
            if part == "pitch":
                game.move_card(thing, p.hand, p.exile, reason="cost")
            elif part == "discard":
                game.discard_card(p, thing)
            elif part == "exile_gy":
                game.move_card(thing, p.graveyard, p.exile, reason="cost")
            elif part == "tap":
                thing.tapped = True
                game.fire(p, "becomes_tapped", thing)
            elif part == "sac":
                game.sacrifice(thing)
            elif part == "bounce":
                game.leave_battlefield(thing, "hand")
        game.log(f"pays {part} x{n} for {card.name}", p)
    return True
