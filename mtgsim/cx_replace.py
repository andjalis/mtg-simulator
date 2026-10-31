"""Small replacement and choice templates that share one parse hook.

* "[Morbid — ]~ enters with N <kind> counters on it if <condition>." The condition comes from the shared
  condition library (cx_condlib), so every condition it knows works here (Morbid, Revolt, Ferocious,
  "if you cast it from your hand", ...). Engine: ``entry_counters`` from ``enter_battlefield``.
* "If ~ would die, exile it instead." and "If <subject> would die, exile it instead." with the subject
  grammar of the trigger-event library ("a creature an opponent controls", "another nontoken creature").
  Engine: one replacement in ``rules_events.zone_destination``.
* "If you would draw a card[ except the first one you draw in each of your draw steps], draw N cards
  instead." Engine: ``extra_draws`` from ``Game.draw``.
* Two-player choices: "As ~ enters, choose an opponent." names the only opponent, so the line needs no
  engine state and ``two_player_text`` rewrites "the chosen player" to the opponent before parsing.
"""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}


def _rules(st):
    return st.extra.setdefault("advanced_rules", {})


def parse_line(line: str, st) -> bool:
    m = re.fullmatch(r"(?:[A-Z][\w' -]* — )?~ enters(?: the battlefield)? with (a|an|one|two|three|four|five|six|"
                     r"seven|eight|\d+) (?:additional )?(\+1/\+1|-1/-1|[a-z]+) counters? on it if (.+)\.", line)
    if m:
        from .cx_condlib import parse
        from .cards.clauses import _if_cond
        code = parse(m[3]) or _if_cond(m[3])
        if not code:
            return False
        n = int(m[1]) if m[1].isdigit() else _N[m[1]]
        _rules(st).setdefault("cx_etb_if", []).append((code, n, m[2]))
        return True
    if line == "If ~ would die, exile it instead.":
        _rules(st)["cx_exile_self"] = True
        return True
    m = re.fullmatch(r"If (an? .+?|another .+?) would die, exile it instead\.", line)
    if m:
        from .cx_events import _object_subject
        spec = _object_subject(m[1])
        if spec is None or spec["host"] or spec["batch"]:
            return False
        _rules(st).setdefault("cx_exile_if", []).append(m[1])
        return True
    m = re.fullmatch(r"If you would draw a card( except the first one you draw in each of your draw steps)?, "
                     r"draw (two|three) cards instead\.", line)
    if m:
        _rules(st)["cx_draw"] = (_N[m[2]], bool(m[1]))
        return True
    if re.fullmatch(r"(?:As ~ enters(?: the battlefield)?, )?(?:secretly )?choose an opponent(?: at random)?\.", line):
        return True     # two players: the chosen player is the opponent (two_player_text)
    return False


def two_player_text(text: str) -> str:
    """With "choose an opponent", "the chosen player" is the only opponent."""
    if not re.search(r"\bchoose an opponent\b", text) or "chosen name" in text:
        return text
    subs = [
        (r"\bthe (?:last )?chosen player's upkeep\b", "each opponent's upkeep"),
        (r"\b(?:the (?:last )?chosen player|that player) controls\b", "your opponents control"),
        (r"\bthe (?:last )?chosen player's\b", "each opponent's"),
        (r"\b[Tt]he (?:last )?chosen player\b", "each opponent"),
    ]
    for pat, rep in subs:
        text = re.sub(pat, rep, text)
    return text


# ---------------------------------------------------------------- engine side

def _rules_of(perm):
    return perm.card.advanced_rules if not perm.abilities_suppressed else {}


def entry_counters(game, p, perm):
    """'~ enters with N counters on it if <condition>': checked as it enters."""
    for code, n, kind in perm.card.advanced_rules.get("cx_etb_if", ()):
        from .cards import Effect
        from .engine.state import StackItem
        from .cx_condlib import check
        ok = check(game, p, code, None, source=perm)
        if ok is None:
            ok = game.check_cond(p, Effect("condition", cond=code), StackItem(p, [], [], source=perm), None)
        if ok:
            perm.counters[kind] = perm.counters.get(kind, 0) + n


def exiles(game, perm) -> bool:
    """Whether a "would die, exile it instead" static applies to this dying creature."""
    if not perm.is_creature:
        return False
    if _rules_of(perm).get("cx_exile_self"):
        return True
    from .cx_events import _object_subject, _subject_ok
    for pl in game.players:
        for x in pl.battlefield:
            for head in _rules_of(x).get("cx_exile_if", ()):
                spec = _object_subject(head)
                if spec is not None and x is not perm and _subject_ok(game, spec, x, perm):
                    return True
                if spec is not None and x is perm and not spec["other"] and _subject_ok(game, spec, x, perm):
                    return True
    return False


def extra_draws(game, p, replaced) -> int:
    """How many more cards to draw in place of this one ("draw two cards instead"), else 0."""
    if "cx_draw" in replaced:
        return 0
    best = 0
    for x in p.battlefield:
        rule = _rules_of(x).get("cx_draw")
        if not rule:
            continue
        n, except_first = rule
        if except_first and game.active is p and game.step == "draw" and \
                getattr(p, "_advanced_draw_step", None) != (game.turn, getattr(game, "draw_step_serial", 0)):
            continue        # the first card of the draw step is drawn normally
        best = max(best, n - 1)
    return best
