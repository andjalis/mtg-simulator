"""Votes (#634 VOTE): will of the council, council's dilemma and the extra-vote statics.

    Will of the council — Starting with you, each player votes for time or knowledge. If time gets more votes,
    take an extra turn after this one. If knowledge gets more votes or the vote is tied, draw three cards.
                                                                                            (Plea for Power)
    Council's dilemma — Starting with you, each player votes for death or taxes. Each opponent sacrifices a
    creature for each death vote and discards a card for each taxes vote.                 (Capital Punishment)
    Put two +1/+1 counters on ~ for each sprout vote. You gain 3 life for each harvest vote. (Orchard Elemental)
    While voting, you get an additional vote. / While voting, you may vote an additional time.

Parsing: the head sentence ("starting with you, each player votes for A or B") is a ``vote`` Effect; the sentences
after it are folded into it by ``parse_rider``: "If A gets more votes[ or the vote is tied], X" is a majority branch,
"X for each A vote" / "For each A vote, X" / "X equal to [twice] the number of A votes" a per-vote branch. A body
that doesn't parse, or that targets, leaves the sentence ignored (and the card partial).

Resolution (``kinds/votes.py``): starting with the controller, each player casts their votes (one, plus one for each
"While voting" static they control). A player votes in their own interest, from what both can see: the controller
for the option whose outcome is worth the most to them (``policy._mode_value``), an opponent for the option worth
the least to the controller. Then the majority branch that won (ties as printed) resolves, and each per-vote branch
resolves once per vote it got.
"""
from __future__ import annotations

import re
from collections import Counter

_OPT = r"([a-z][a-z' ]*?)"
EFFECT_PATTERNS = [
    (rf"(?:(?:will of the council|council's dilemma) — )?starting with you, each player votes for {_OPT} or "
     rf"([a-z][a-z' ]*)", lambda m: _head(m)),
]


def _head(m):
    from .cards import Effect
    a, b = m[1].strip().lower(), m[2].strip().lower()
    if a == b:
        from .cards.model import NO_MATCH
        return NO_MATCH
    return Effect("vote", data={"options": (a, b), "branches": {}, "per_vote": {}})


def _body(text: str):
    """The effects of a branch body, or None when it doesn't parse fully or names a target."""
    from .cards.parse import _parse_effects
    from .engine.state import TARGETED
    text = text.strip().rstrip(".")
    if not text:
        return None
    effects, bad = _parse_effects(text[0].upper() + text[1:] + ".")
    # "each opponent ..." reads as a player target (the opponent, as everywhere in a two-player game); a real
    # choice of target in a vote's outcome is left unread
    if bad or not effects or any(e.target in TARGETED and e.target not in ("self", "prev", "player") for e in effects):
        return None
    return effects


_SUBJECT = re.compile(r"^((?:each|target) (?:opponent|player)|you) ", re.I)


def _per_vote(s: str, options):
    """[(option, effects)] for a per-vote sentence, or None."""
    m = re.fullmatch(r"for each (.+?) vote, (.+)", s, re.I)
    if m:
        effects = _body(m[2])
        return [(m[1].lower(), effects)] if effects and m[1].lower() in options else None
    m = re.fullmatch(r"(.+? for each (.+?) vote) and (.+? for each (.+?) vote)", s, re.I)
    if m:
        first = _per_vote(m[1], options)
        second = m[3]
        subject = _SUBJECT.match(m[1])
        if subject and not _SUBJECT.match(second):      # "Each opponent sacrifices ... and discards ..."
            second = subject[1] + " " + second
        rest = _per_vote(second, options)
        return first + rest if first and rest else None
    m = re.fullmatch(r"(.+?) for each (.+?) vote", s, re.I)
    if m:
        effects = _body(m[1])
        return [(m[2].lower(), effects)] if effects and m[2].lower() in options else None
    m = re.fullmatch(r"(.*?)\ba number of (.+?) equal to (twice )?the number of (.+?) votes(.*)", s, re.I)
    if m and m[4].lower() in options:
        noun = m[2] if m[3] else re.sub(r"\b(counters|tokens|cards)\b", lambda x: x[1][:-1], m[2])
        effects = _body(f"{m[1]}{'two' if m[3] else 'a'} {noun}{m[5]}")
        return [(m[4].lower(), effects)] if effects else None
    return None


def parse_rider(s: str, effects) -> bool:
    """Fold a sentence after a vote into it: a majority branch or a per-vote branch."""
    if not effects or effects[-1].kind != "vote":
        return False
    vote = effects[-1]
    options = vote.data["options"]
    m = re.fullmatch(r"if (.+?) gets more votes( or the vote is tied)?, (.+)", s, re.I)
    if m:
        opt, tie = m[1].lower(), bool(m[2])
        body = _body(m[3])
        if opt not in options or body is None or opt in vote.data["branches"] or \
                (tie and any(t for t, _ in vote.data["branches"].values())):
            return False
        vote.data["branches"][opt] = (tie, body)
        return True
    pairs = _per_vote(s, options)
    if not pairs:
        return False
    for opt, body in pairs:
        vote.data["per_vote"][opt] = vote.data["per_vote"].get(opt, []) + body
    return True


def face_line(st, line):
    if line in ("While voting, you get an additional vote.", "While voting, you may vote an additional time."):
        rules = st.extra.setdefault("advanced_rules", {})
        rules["extra_votes"] = rules.get("extra_votes", 0) + 1
        return None
    return line


# ------------------------------------------------------------------ the engine side

def _count(game, player) -> int:
    return 1 + sum(x.card.advanced_rules.get("extra_votes", 0) for x in player.battlefield
                   if not x.abilities_suppressed)


def _effect_value(game, me, e, source) -> float:
    """What one effect of an outcome is worth to me: the kinds votes use, read off the board both players see;
    any other kind falls back to the AI's mode value."""
    from .engine.policy import _mode_value, perm_value
    opp = game.opponent(me)
    k, n = e.kind, e.amount
    if k == "edict":                        # "each opponent sacrifices a creature": their least valuable ones
        return sum(sorted(perm_value(x) for x in opp.creatures)[:n])
    if k in ("drain", "lose_life") and e.target in ("each_opponent", "player"):
        return 50.0 if n >= opp.life else 0.6 * n
    if k == "discard" and e.target == "player":
        return 1.5 * min(n, len(opp.hand))
    if k == "draw" and e.target == "none":
        return 1.5 * n if len(me.library) > n else -10.0
    if k == "extra_turn":
        return 6.0
    if k == "gain_life":
        return 0.3 * n
    if k == "p1_counters":
        count = len(me.creatures) if e.target == "my_creatures" else 1 if e.target == "self" and (
            source is None or source in me.battlefield) else 0
        return 1.0 * n * count
    if k == "token":
        kind = e.data.get("kind")
        each = 1.0 if kind in ("treasure", "clue", "food") else \
            (int(e.data.get("power") or 0) + int(e.data.get("toughness") or 0)) / 2 or 1.0
        return each * max(n, 1)
    if k == "debuff" and e.target == "opp_creatures":
        return sum(perm_value(x) if x.toughness - x.damage <= e.amount2 else 0.3 for x in opp.creatures)
    if k == "destroy_group" and e.data.get("not") == "Land":
        return sum((1 if pl is opp else -1) * perm_value(x) for pl in game.players for x in pl.battlefield
                   if not x.card.is_land and not x.has("indestructible"))
    if k == "sacrifice_self":
        return -perm_value(source) if source is not None and source in me.battlefield else 0.0
    if k == "search_plan":
        return 1.0
    return max(_mode_value(game, me, [e]), -5.0)


def _outcome_value(game, controller, eff, votes, source=None) -> float:
    """What the outcome of these votes is worth to the controller."""
    total = 0.0
    for opt, effects in _winning(eff, votes):
        total += sum(_effect_value(game, controller, e, source) for e in effects)
    for opt, effects in eff.data["per_vote"].items():
        if votes.get(opt):
            total += votes[opt] * sum(_effect_value(game, controller, e, source) for e in effects)
    return total


def _winning(eff, votes):
    a, b = eff.data["options"]
    for opt, (tie, effects) in eff.data["branches"].items():
        other = b if opt == a else a
        if votes.get(opt, 0) > votes.get(other, 0) or (tie and votes.get(opt, 0) == votes.get(other, 0)):
            yield opt, effects


def cast_votes(game, controller, eff, log=True, source=None) -> Counter:
    """Each player's votes, starting with the controller; each votes for the outcome best for them."""
    votes: Counter = Counter()
    order = [controller] + [pl for pl in game.players if pl is not controller]
    for pl in order:
        n = _count(game, pl)
        best = None
        for opt in eff.data["options"]:
            trial = votes.copy()
            trial[opt] += n
            v = _outcome_value(game, controller, eff, trial, source)
            v = v if pl is controller else -v
            if best is None or v > best[0]:
                best = (v, opt)
        votes[best[1]] += n
        if log:
            game.log(f"votes for {best[1]}" + (f" ({n} votes)" if n > 1 else ""), pl)
    return votes


def resolve(game, p, eff, item):
    from .engine.state import Permanent
    source = item.source if item is not None and isinstance(item.source, Permanent) else None
    votes = cast_votes(game, p, eff, source=source)
    item_votes = dict(votes)
    if item is not None:
        item.votes = item_votes
    prev = None
    runs = [effects for _, effects in _winning(eff, votes)]
    for opt, effects in eff.data["per_vote"].items():
        runs += [effects] * votes.get(opt, 0)
    for effects in runs:
        for e in effects:
            if game.over:
                return
            if game.check_cond(p, e, item, prev):
                target = None
                if e.target == "player":            # "each opponent": the opponent (see _body)
                    from .engine.policy import default_choose_target
                    target = default_choose_target(game, p, e)
                game.resolve(p, e, target, item, prev)


def value(game, me, eff) -> float:
    """The AI's value for a vote it controls: the outcome both players' votes would produce now."""
    src = getattr(game.target_source, "source", None)
    return _outcome_value(game, me, eff, cast_votes(game, me, eff, log=False, source=src), src)
