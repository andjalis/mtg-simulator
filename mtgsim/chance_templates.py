"""Chance mechanics: clash and coin flips (the general shapes).

"Clash with an opponent. If you win, <X>." and "Flip a coin. If you win / lose the flip,
<X>." become a gate effect (``clash`` / ``flip_coin``: the kind resolves the chance and
sets item.gate_paid, the pay_gate pattern) followed by the payoff effects with cond
"paid". "Whenever you clash [, and win]" is a you_clash / you_win_clash trigger the
``clash`` kind fires. The revealed clash cards stay where they are (the real wording lets
each player put them on top or bottom: recorded simplification). Die rolls need per-face
amount plumbing the engine doesn't have — a foundation need, not covered here.
"""
from __future__ import annotations

import dataclasses
import re


def _gated(gate_effect, rider):
    from .cards import NO_MATCH, _parse_effects
    from .cx_grammar_cond import _both
    payoff, bad = _parse_effects(rider[0].upper() + rider[1:] + ".")
    if bad or not payoff:
        return NO_MATCH
    return [gate_effect] + [dataclasses.replace(e, cond=_both(e.cond, "paid")) for e in payoff]


def _gated_both(win_rider, lose_rider):
    """Both riders of "If you win the flip, X. If you lose the flip, Y.": X runs on "paid", Y on "unpaid"."""
    from .cards import NO_MATCH, Effect, _parse_effects
    from .cx_grammar_cond import _both
    parsed = []
    for rider, cond in ((win_rider, "paid"), (lose_rider, "unpaid")):
        effects, bad = _parse_effects(rider[0].upper() + rider[1:] + ".")
        if bad or not effects:
            return NO_MATCH
        parsed.append([dataclasses.replace(e, cond=_both(e.cond, cond)) for e in effects])
    return [Effect("flip_coin")] + parsed[0] + parsed[1]


def _fold_both(m):
    from .cards import NO_MATCH
    # Keep the Oracle wording when either rider is unsupported. Internal markers
    # must never become the coverage report's description of the missing mechanic.
    return m[0] if _gated_both(m[1], m[2]) is NO_MATCH else f"FLIPBOTH {m[1]} || {m[2]}."


def _fold_flip(m):
    from .cards import Effect, NO_MATCH
    return (m[0] if _gated(Effect("flip_coin"), m[2]) is NO_MATCH
            else f"FLIPCOIN {m[1].lower()} {m[2]}.")


SUBS = [
    # "Clash with an opponent. If you win, <X>." (also "defending player", "If you won")
    (re.compile(r"clash with (?:an opponent|defending player|target opponent)\. "
                r"if you (?:win|won), ([^.]+)\.?", re.I),
     lambda m: f"CLASHWIN {m[1]}."),
    # "Flip a coin. If you win the flip, <X>. If you lose the flip, <Y>."
    (re.compile(r"flip a coin\. if you win the flip, ([^.]+)\. if you lose the flip, ([^.]+)\.?", re.I),
     _fold_both),
    # "Flip a coin. If/When you win/lose the flip, <X>."
    (re.compile(r"flip a coin\. (?:if|when) you (win|lose) the flip, ([^.]+)\.?", re.I),
     _fold_flip),
]


def _clash(m):
    from .cards import Effect
    return _gated(Effect("clash"), m[1])


def _flip(m):
    from .cards import Effect
    data = {"on_lose": True} if m[1] == "lose" else {}
    return _gated(Effect("flip_coin", data=data), m[2])


def _plain(m):
    """A bare "Flip a coin." sentence: the coin toss on its own."""
    from .cards import Effect
    return Effect("flip_coin")


def _clash_plain(m):
    from .cards import Effect
    return Effect("clash")


def _counted(m):
    from .cards import Effect, _num
    word = m[1].lower()
    return Effect("flip_coin", _num(word) if word != "x" else 0, data={"count": True, "count_x": word == "x"})


def _until_lose(m):
    from .cards import Effect
    return Effect("flip_coin", data={"until_lose": True})


def _per_flip(body, side):
    from .cards import NO_MATCH, _parse_effects
    effects, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    create = re.fullmatch(r"create (.+)", body, re.I)
    if create:
        from .cx_tokens import parse_create
        tokens = parse_create("", create[1])
        if tokens is not NO_MATCH:
            effects, bad = tokens, []
    # Only amounts whose multiplication implements the wording. Repeated scry,
    # destruction, gates, and other actions cannot be reduced to a larger amount.
    scalable = {"draw", "token", "cx_token", "p1_counters", "gain_life", "lose_life", "damage"}
    if bad or not effects or any(e.kind not in scalable or e.data.get("xq") for e in effects):
        return NO_MATCH
    spec = ("cxq", "flips", "won" if side.lower() in ("win", "won") else "lost")
    return [dataclasses.replace(e, data=dict(e.data, xq=spec)) for e in effects]


def parse_rider(sentence, effects):
    from .cards import NO_MATCH
    # A count must belong to a parsed flip instruction in this ability. In
    # particular, leave Yusri's payoffs visible while its chosen-count flip is missing.
    if not any(e.kind == "flip_coin" for e in effects):
        return False
    m = re.fullmatch(r"for each flip you (win|won|lose|lost), (.+)", sentence, re.I)
    n = re.fullmatch(r"(.+) for each flip you (win|won|lose|lost)", sentence, re.I)
    if not m and not n:
        return False
    new = _per_flip(m[2], m[1]) if m else _per_flip(n[1], n[2])
    if new is NO_MATCH:
        return False
    effects.extend(new)
    return True


def face_line(st, line):
    if line == "If you would flip a coin, instead flip two coins and ignore one.":
        st.extra.setdefault("advanced_rules", {})["coin_replacement"] = True
        return None
    return line


def toss(game, p, replacements=None):
    """One retained result; ignored replacement flips neither win nor lose (CR 705.6)."""
    if replacements is None:
        replacements = sum(bool(x.card.advanced_rules.get("coin_replacement"))
                           for x in p.battlefield if not x.abilities_suppressed)
    if replacements:
        results = tuple(toss(game, p, replacements - 1) for _ in range(2))
        chooser = getattr(p.ai, "choose_coin_result", None)
        chosen = chooser(game, p, results) if chooser else any(results)
        return chosen if isinstance(chosen, bool) and chosen in results else results[0]
    return game.rng.random() < 0.5


EFFECT_PATTERNS = [
    (r"flip a coin until you lose a flip", _until_lose),
    (r"flip (x|one|two|three|four|five|six|seven|eight|nine|ten|\d+) coins?", _counted),
    (r"CLASHWIN (.+)", _clash),
    (r"FLIPBOTH (.+?) \|\| (.+)", lambda m: _gated_both(m[1], m[2])),
    (r"FLIPCOIN (win|lose) (.+)", _flip),
    # "Clash with an opponent." with no rider (Oaken Brawler), and a coin flip with no
    # rider sentence ("You may flip a coin.")
    (r"clash with (?:an opponent|defending player|target opponent)", _clash_plain),
    (r"flip a coin", _plain),
]

TRIGGERS = [
    (r"Whenever you clash and win, (.+)", ("you_win_clash",)),
    (r"Whenever you win a clash, (.+)", ("you_win_clash",)),
    (r"Whenever you clash, (.+)", ("you_clash",)),
]
