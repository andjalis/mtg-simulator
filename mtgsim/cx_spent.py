"""Mana-spent conditions written after their effect (#324).

"<Effect> if {G} was spent to cast ~." and the paired form "<A> if {R} was spent to cast ~ and <B> if {G} was
spent to cast ~." (Firespout, Repel Intruders, Torrent of Souls) are rewritten to the leading form "If <cond>,
<effect>." that the condition library (cx_condlib) already reads, one sentence per clause, so each half is
checked on resolution against the colours the spell's payment recorded. A clause is only moved when the
condition library knows its condition; otherwise the Oracle text stays as it was and stays unmatched.
"""
from __future__ import annotations

import re

# a mana-spent condition, ending at "spent to cast ~"
_SPENT = (r"(?:(?:\{[WUBRG]\})+|at least \w+ (?:white |blue |black |red |green |colorless )?mana(?: of the same color)?"
          r"|no (?:colored )?mana|\w+ or more (?:colors of )?mana) (?:was|were) spent to cast (?:~|it|this spell)")


def _lead(effect: str, cond: str):
    from .cards import _parse_effects
    from .cx_condlib import parse
    if not parse(cond):
        return None
    sentence = f"If {cond}, {effect}."
    effects, bad = _parse_effects(sentence)
    # only when the moved clause really parses: otherwise another template may read the whole sentence
    return sentence if effects and not bad else None


def _move(m):
    first = _lead(m[1], m[2])
    if first is None:
        return m[0]
    if not m[3]:
        return first
    second = m[3]
    elided = re.match(r"(?:\d+|x|an?|one|two|three|four|five) ", second, re.I)
    if elided:      # "~ deals 3 damage to A if ... and 3 damage to B if ...": the verb is the first clause's
        verb = re.match(r"(.+?)\b(?:\d+|X|an?|one|two|three|four|five) ", m[1])
        if verb is None:
            return m[0]
        second = verb[1] + second
    second = _lead(second, m[4])
    return m[0] if second is None else f"{first} {second}"


def _move_stat(m):
    """"<effect on target ...> if its mana value is less than or equal to <spent quantity>": checked against the
    effect's own target as it resolves."""
    return _lead(m[1], m[2]) or m[0]


SUBS = [
    (re.compile(r"(?:^|(?<=\. ))((?:(?! if )[^.])*?\btarget\b(?:(?! if )[^.])*?) if (its (?:mana value|power|toughness) is "
                r"less than or equal to [^.]+? spent to cast ~)\.", re.I), _move_stat),
    (re.compile(r"(?:^|(?<=\. ))([A-Z~](?:(?! if )[^.])*?) if (" + _SPENT + r")(?:,? and ((?:(?! if )[^.])+?) if (" + _SPENT + r"))?\.",
                re.I), _move),
]


def fitting_targets(game, me, eff, legal):
    """AI hint for "... target ... if its mana value is less than or equal to the number of colors of mana spent
    to cast ~" (Prismatic Ending): targets are chosen before the payment, so prefer the ones the converge count
    can reach (colours the caster's untapped mana sources make, at most the spell's mana value). The legality
    of a target is unchanged; when none fits, every legal target stays a choice."""
    import json
    if not eff.cond.startswith('lib:["tgt_stat_le"'):
        return legal
    stat, spec = json.loads(eff.cond[4:])[1:]
    if spec != ["cxq", "converge"]:
        return legal
    from .engine.mana import _mana_of
    from .engine.state import Permanent
    colours = {c for s in me.battlefield if not s.tapped and s.card.produces for c in _mana_of(s)} & set("WUBRG")
    card = getattr(game, "target_source", None)
    card = getattr(card, "card", card)
    bound = min(len(colours), int(getattr(card, "cmc", 5) or 5))
    fit = [x for x in legal if isinstance(x, Permanent)
           and (x.card.cmc if stat == "mana value" else getattr(x, stat, 0)) <= bound]
    return fit or legal


# where spent mana came from ("mana from a Treasure", "from creatures", "from an artifact source", "from a Desert")
SOURCE_KINDS = ("treasure", "artifact", "creature", "desert", "cave")


def source_counts(payment) -> dict:
    """{kind: mana} for the sources that paid a spell: each source's mana counts toward every kind it is (a Treasure
    is also an artifact). Mana already floating in the pool has lost its source and counts toward none."""
    from .engine.mana import _amount
    from .engine.state import _POOL_MANA, FIREBEND_MANA
    pool = {id(c) for c in _POOL_MANA.values()} | {id(FIREBEND_MANA)}
    out = {}
    for src in payment:
        card = src.card
        if id(card) in pool:        # floating mana (an artifact-typed stand-in card): its source is unknown
            continue
        kinds = {"treasure" if card.token_kind == "treasure" or "Treasure" in card.subtypes else "",
                 "artifact" if "Artifact" in card.types else "", "creature" if src.is_creature else "",
                 "desert" if "Desert" in card.subtypes else "", "cave" if "Cave" in card.subtypes else ""} - {""}
        n = max(1, _amount(src))
        for k in kinds:
            out[k] = out.get(k, 0) + n
    return out


def source_kind(word: str):
    """"a Treasure" / "Treasures" / "creatures" / "an artifact source" -> its key, or None."""
    w = re.sub(r"^(?:an? )", "", word.strip().lower())
    w = re.sub(r" sources?$", "", w)
    w = w[:-1] if w.endswith("s") else w
    return w if w in SOURCE_KINDS else None
