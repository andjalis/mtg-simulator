"""#643: "can't be the target of ..." restrictions on ~, on an enchanted / equipped creature and on groups.

    ~ can't be the target of abilities your opponents control.                         (Shanna, Sisay's Legacy)
    ~ can't be the target of black or red spells your opponents control.               (Fiendslayer Paladin)
    ~ can't be the target of nongreen spells or abilities from nongreen sources.       (Gaea's Revenge)
    ~ can't be the target of Aura spells.                                             (Tetsuo Umezawa)
    Enchanted creature can't be the target of abilities from artifact sources.         (Artifact Ward)
    Creatures you control can't be the targets of blue spells or abilities from blue sources.   (Spellbane Centaur)
    Creatures can't be the targets of spells.                                          (Dense Foliage)

CR 115.4 / 702.11-style restrictions: a spell or ability with a matching quality can't choose the object as a target.
Each line becomes a tuple of clauses ``{"kind": "spell" | "ability", "colors": (...), "non": color, "aura": bool,
"artifact": bool, "opp": bool}`` (a spell clause tests the spell's own colours / subtypes; an ability clause tests its
source, CR 113.7). Where the clause says "your opponents control", the permanent's controller can still target it.

Stored as ``advanced_rules["target_ban"]`` (the card itself), ``["target_ban_host"]`` (the enchanted / equipped
creature), ``["target_ban_group"]`` ((selector, clauses), ...); Game.targetable asks ``banned``.
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_C = r"(?:non)?(?:white|blue|black|red|green)"


def _spells(text: str, opp: bool):
    """ "black or red spells", "nongreen spells", "Aura spells", "spells" -> a spell clause, or None."""
    m = re.fullmatch(rf"(?:({_C})(?: or ({_C}))? )?(Aura )?spells", text)
    if not m:
        return None
    words = [w for w in (m[1], m[2]) if w]
    clause = {"kind": "spell", "opp": opp, "aura": bool(m[3])}
    return _colored(clause, words)


def _abilities(text: str, opp: bool):
    """ "abilities", "abilities from artifact sources", "abilities from black sources" -> an ability clause."""
    m = re.fullmatch(rf"abilities(?: from (artifact|{_C}) sources)?", text)
    if not m:
        return None
    clause = {"kind": "ability", "opp": opp}
    if m[1] == "artifact":
        clause["artifact"] = True
        return clause
    return _colored(clause, [m[1]] if m[1] else [])


def _colored(clause, words):
    if not words:
        return clause
    if any(w.startswith("non") for w in words):
        if len(words) != 1:
            return None
        clause["non"] = _COLORS[words[0][3:]]
        return clause
    clause["colors"] = tuple(_COLORS[w] for w in words)
    return clause


def clauses(text: str):
    """The clauses of "<what> [your opponents control]" or None if any part is unread."""
    text = text.strip()
    m = re.fullmatch(r"spells or abilities( your opponents control)?", text)
    if m:
        opp = bool(m[1])
        return ({"kind": "spell", "opp": opp}, {"kind": "ability", "opp": opp})
    out = []
    for piece in re.split(r" or (?=abilities\b)", text):
        opp = piece.endswith(" your opponents control")
        if opp:
            piece = piece[:-len(" your opponents control")]
        clause = _spells(piece, opp) if "spells" in piece else _abilities(piece, opp) if piece.startswith(
            "abilities") else None
        if clause is None:
            return None
        out.append(clause)
    return tuple(out) or None


_LINE = re.compile(r"(?P<who>~|Enchanted creature|Equipped creature|.+?) can't be the targets? of (?P<what>.+)\.")


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line.strip())
    if not m:
        return False
    found = clauses(m["what"])
    if found is None:
        return False
    rules = st.extra.setdefault("advanced_rules", {})
    who = m["who"]
    if who == "~":
        rules["target_ban"] = tuple(rules.get("target_ban", ())) + found
        return True
    if who in ("Enchanted creature", "Equipped creature"):
        rules["target_ban_host"] = tuple(rules.get("target_ban_host", ())) + found
        return True
    from .permanent_templates import selector
    if re.search(r"\b(?:this turn|until|as long as|if|unless)\b", who, re.I):
        return False
    spec = selector(who, plural=True)
    if spec is None:
        return False
    rules["target_ban_group"] = tuple(rules.get("target_ban_group", ())) + ((spec, found),)
    return True


def _source_of(source):
    """(is_spell, card for the quality checks) of what is targeting: a stack item, a spell card or a permanent."""
    from .cards.model import CardDef
    from .engine.state import Permanent, StackItem
    if isinstance(source, StackItem):
        if source.kind == "spell" and source.card is not None:
            return True, source.card
        src = source.source
        return False, src.card if isinstance(src, Permanent) else getattr(src, "card", None)
    if isinstance(source, Permanent):
        return False, source.card
    if isinstance(source, CardDef):
        return not getattr(source, "is_ability", False), source
    return None, None


def _hits(clause, is_spell, card, by, owner) -> bool:
    if clause["kind"] == "spell" and not is_spell or clause["kind"] == "ability" and is_spell:
        return False
    if clause.get("opp") and by is owner:
        return False
    colors = set(getattr(card, "colors", ()) or ())
    if clause.get("colors") and not colors & set(clause["colors"]):
        return False
    if clause.get("non") and clause["non"] in colors:
        return False
    if clause.get("aura") and not getattr(card, "aura", None) and "Aura" not in getattr(card, "subtypes", ()):
        return False
    if clause.get("artifact") and not getattr(card, "is_artifact", False):
        return False
    return True


def _rules(game, perm):
    """Every clause that applies to perm now (its own, its hosts', groups')."""
    from .permanent_templates import matches
    from .residual_templates import sources
    out = []
    turn = getattr(game, "turn", None)
    for when, found in getattr(perm, "temp_target_bans", ()):
        if when == turn:
            out += list(found)
    if not perm.abilities_suppressed:
        out += list(perm.card.advanced_rules.get("target_ban", ()))
    for att in list(perm.auras) + list(perm.equipment):
        if not att.abilities_suppressed:
            out += list(att.card.advanced_rules.get("target_ban_host", ()))
    if game is not None:
        for src in sources(game, "target_ban_group"):
            for spec, found in src.card.advanced_rules["target_ban_group"]:
                if matches(game, perm, spec, src.controller, src):
                    out += list(found)
    return out


def banned(game, perm, by, source) -> bool:
    """Whether ``by`` can't target ``perm`` with ``source`` because of a "can't be the target of" rule."""
    rules = _rules(game, perm)
    if not rules:
        return False
    is_spell, card = _source_of(source)
    if is_spell is None:
        return False
    return any(_hits(c, is_spell, card, by, perm.controller) for c in rules)


# ------------------------------------------------------------------ "... this turn" (#643)
#   Target creature can't be the target of spells or abilities your opponents control this turn.   (Vines of Vastwood)
#   Creatures / Permanents you control can't be the targets of <what> this turn.   (Veilstone Amulet, Display of Dominance)
# A ``target_ban_temp`` Effect: the clauses go on the target (or on each permanent of the group as the effect resolves,
# CR 611.2c) for this turn, and ``_rules`` reads them while game.turn is that turn.

def _temp(target, group, what):
    from .cards import Effect, NO_MATCH
    found = clauses(what)
    if found is None:
        return NO_MATCH                 # an unread quality: the line stays ignored
    return Effect("target_ban_temp", target=target.lower(), data={"clauses": found, "group": group.lower()})


EFFECT_PATTERNS = [
    (r"target (creature|permanent) can't be the target of (.+?) this turn",
     lambda m: _temp(m[1], "", m[2])),
    (r"(creatures|permanents) you control can't be the targets of (.+?) this turn",
     lambda m: _temp("none", m[1], m[2])),
]


def apply_temp(game, p, eff, target):
    """Resolve a target_ban_temp Effect."""
    from .engine.state import Permanent
    if eff.data.get("group"):
        group = [x for x in p.battlefield if eff.data["group"] == "permanents" or x.is_creature]
    else:
        group = [target] if isinstance(target, Permanent) and target in target.controller.battlefield else []
    for x in group:
        x.temp_target_bans = [b for b in getattr(x, "temp_target_bans", []) if b[0] == game.turn] + \
            [(game.turn, eff.data["clauses"])]
    if group:
        game.log(f"{', '.join(x.card.name for x in group)} can't be targeted by those this turn", p)


def stops(card, item, me) -> bool:
    """HeuristicAI: whether casting ``card`` (a target_ban_temp spell) makes item's targeting of my permanent illegal."""
    is_spell = item.kind == "spell" and item.card is not None
    src = item.card if is_spell else getattr(getattr(item, "source", None), "card", None)
    for e in card.spell_effects:
        if e.kind == "target_ban_temp" and not e.data.get("group"):
            if any(_hits(c, is_spell, src, item.controller, me) for c in e.data["clauses"]):
                return True
    return False
