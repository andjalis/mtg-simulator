"""Copy effects: token copies of permanents, clones that enter as a copy, and copies of spells.

Rules text is matched by the patterns below, which mtgsim.cards adds to its own templates; the
engine hands the effect kinds in KINDS to resolve() here.

    Create a token that's a copy of target creature you control[, except ...].
    Create X tokens that are copies of target artifact or creature you control.
    For each nontoken creature you control, create a token that's a copy of that creature.
    Create a token that's a copy of ~.
    You may have ~ enter as a copy of any creature on the battlefield[, except ...].
    When you next cast an instant or sorcery spell this turn, copy that spell [twice].
    Copy target instant or sorcery spell you control.  /  (cast trigger) copy that spell.

    ~ becomes a copy of target creature you control until end of turn.  (reverts in the cleanup step)
    Copy target activated or triggered ability you control [from a creature source] [X times].

Simplifications: the permanent or spell to copy is picked when the effect resolves (so "target"
only checks hexproof on the opponent's permanents), the legend rule isn't modelled (so "except it
isn't legendary" changes nothing), and a token sacrificed "at the beginning of the next end step"
goes at its controller's end step.

This module imports mtgsim.cards and mtgsim.engine lazily, inside functions, because both import it.
"""
from __future__ import annotations

import dataclasses
import re

KINDS = {"copy_perm", "copy_spell", "copy_next_spell", "copy_sac", "become_copy", "copy_ability"}

_KW = (r"flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|"
       r"indestructible|menace|reach|defender|flash|prowess")
_COLORS = {"white", "blue", "black", "red", "green", "colorless"}
_TYPES = {"artifact": "Artifact", "creature": "Creature", "enchantment": "Enchantment", "land": "Land",
          "planeswalker": "Planeswalker", "instant": "Instant", "sorcery": "Sorcery"}
_SAC_QUOTE = re.compile(r'"At the beginning of the end step, sacrifice ~\.?"\.?')
_N = r"(a|an|one|two|three|four|five|X)"


# ------------------------------------------------------------------ parsing

def _num(word: str):
    from .cards import _num as num
    return "x" if word == "X" else num(word)


def parse_except(text: str, mods: dict | None = None) -> dict | None:
    """The changes in "..., except it has haste and it's a 1/1 Hero in addition to its other types",
    as a dict (pt, haste/keywords, types, subtypes, keep_name, sac_end), or None if a clause isn't known."""
    mods = dict(mods or {})
    text = text.strip().rstrip(".")
    if _SAC_QUOTE.search(text + "."):
        mods["sac_end"] = True
        text = _SAC_QUOTE.sub("", text + ".").strip().rstrip(".").strip()
        text = re.sub(r"(?:,? and|,)$", "", text).strip()
    pron = r"(?:it|he|she|they|the tokens?|the copy|his|its)"
    for clause in re.split(rf",? and (?={pron}\b)|, (?={pron}\b)", text, flags=re.I):
        c = clause.strip()
        if not c:
            continue
        if re.fullmatch(r"(?:it|he|she|they|the tokens?|the copy)(?:'s| is| isn't| is not| aren't| are not|'re)"
                        r" (?:not )?legendary", c, flags=re.I):
            continue          # the legend rule isn't modelled
        if re.fullmatch(r"(?:his|her|its) name is ~", c, flags=re.I):
            mods["keep_name"] = True
            continue
        m = re.fullmatch(rf"(?:it|he|she|they) (?:has|have|gains?) ((?:{_KW})(?:(?:, | and |, and )(?:{_KW}))*)",
                         c, flags=re.I)
        if m:
            mods["keywords"] = mods.get("keywords", frozenset()) | frozenset(
                k.strip().lower() for k in re.split(r", and |, | and ", m[1]))
            continue
        m = re.fullmatch(r"(?:it's|it is|he's|she's|they're) (?:an? )?(?:(\d+)/(\d+) )?((?:[\w-]+ )*?[\w-]+)?"
                         r"(?: in addition to (?:its|his|her|their) other (?:colors and )?(?:creature )?types)?",
                         c, flags=re.I)
        if m and (m[1] or m[3]):
            if m[1]:
                mods["pt"] = (int(m[1]), int(m[2]))
            for w in (m[3] or "").split():
                if w.lower() in _COLORS or w.lower() == "legendary":
                    continue
                if w.lower() in _TYPES:
                    mods["types"] = mods.get("types", frozenset()) | {_TYPES[w.lower()]}
                elif w[0].isupper():
                    mods["subtypes"] = mods.get("subtypes", frozenset()) | {w}
                else:
                    return None
            continue
        return None
    return mods


def _perm_copy(m, **data):
    from .cards import NO_MATCH, Effect
    mods = {}
    if "COPYHASTE" in m["flags"]:
        mods["keywords"] = frozenset({"haste"})
    if "COPYSACEND" in m["flags"]:
        mods["sac_end"] = True
    if m["exc"]:
        mods = parse_except(m["exc"], mods)
        if mods is None:
            return NO_MATCH
    return Effect("copy_perm", target=data.pop("target", "none"), data={**data, "mods": mods})


def _target_copy(m):
    # The current permanent selector handles noun phrases, not relative clauses.
    # Keep restrictions such as "that entered ... this turn" visible as gaps.
    if re.search(r"\b(?:that|which)\b", m["what"], re.I):
        from .cards import NO_MATCH
        return NO_MATCH
    n = _num(m["n"]) if m["n"] else 1
    scope = (m["scope"] or "").strip()
    return _perm_copy(m, what=m["what"], n=n, other=bool(m["other"]),
                      who="mine" if scope == "you control" else "opp" if scope else "any")


_EXCEPT = r"(?:, except (?P<exc>.+?))?(?P<flags>(?: COPY[A-Z]+)*)"
_MANY = rf"(?:a token that's a copy|(?P<n>{_N[1:-1]}) tokens that are copies)"

EFFECT_PATTERNS = [
    (rf"create {_MANY} of (?P<other>another )?target (?P<what>[\w ,-]+?)(?P<scope> you control| an opponent "
     rf"controls)?{_EXCEPT}", _target_copy),
    (rf"create {_MANY} of (?:~|this equipment|this artifact|this enchantment){_EXCEPT}",
     lambda m: _perm_copy(m, what="self", n=_num(m["n"]) if m["n"] else 1, target="self")),
    (rf"for each (?P<other>other )?(?P<what>[\w ,-]+?) you control, create a token that's a copy of that "
     rf"(?:creature|permanent|artifact){_EXCEPT}",
     lambda m: _perm_copy(m, what=m["what"], n=1, other=bool(m["other"]), who="mine", each=True)),
    (r"you may choose new targets for the cop(?:y|ies)", lambda m: None),
    (r"(?:you may )?copy (?:that spell|it)( twice)?(?: and you may choose new targets for the copy)?",
     lambda m: _effect("copy_spell", of="that", n=2 if m[1] else 1)),
    (r"copy target (?P<what>instant or sorcery |instant |sorcery |creature )?spell you control",
     lambda m: _effect("copy_spell", of="target", what=(m["what"] or "").strip(), n=1)),
    (r"when you (?:next cast an? (?P<a>instant or sorcery|creature) spell|cast your next (?P<b>instant or sorcery) "
     r"spell(?: with mana value (?P<cmc>\d+) or less)?) this turn, copy (?:that spell|it)(?P<twice> twice)?"
     r"(?:, except the copy isn't legendary)?(?: and you may choose new targets for the cop(?:y|ies))?",
     lambda m: _effect("copy_next_spell", what=m["a"] or m["b"], max_cmc=int(m["cmc"] or 99),
                       n=2 if m["twice"] else 1)),
    (r"(?:you may have )?(?:~|it|this creature|this permanent) becomes? a copy of (?P<what>target creature you control|"
     r"another creature you control|target creature|another target creature|up to one other target creature|"
     r"another creature)(?P<until> until end of turn)?(?:, except (?P<exc>.+?))?(?P<until2> until end of turn)?",
     lambda m: _become(m)),
    (r"the \"legend rule\" doesn't apply to permanents you control this turn", lambda m: None),
    (r"copy target (?:activated or triggered|triggered|activated) ability you control(?P<creature> from a creature "
     r"source)?(?: (?P<x>X) times)?",
     lambda m: _effect("copy_ability", creature=bool(m["creature"]), n="x" if m["x"] else 1)),
    (r"this ability can't be copied(?: and X can't be 0)?", lambda m: None),
    (r"copy the next spell you cast this turn when you cast it",
     lambda m: _effect("copy_next_spell", what="", max_cmc=99, n=1)),
]


def _become(m):
    from .cards import NO_MATCH, Effect
    mods = parse_except(m["exc"]) if m["exc"] else {}
    if mods is None:
        return NO_MATCH
    mine = "you control" in m["what"] or m["what"] == "another creature"
    return Effect("become_copy", target="none", data={"what": "creature", "who": "mine" if mine else "any",
                                                       "other": True, "mods": mods})


def _effect(kind, **data):
    from .cards import Effect
    return Effect(kind, data=data)


# Run before sentences are split: fold "It gains haste. Sacrifice it at the beginning of the next end
# step." into the copy sentence before it, and drop ability words in front of "When you next cast".
SUBS = [
    (re.compile(r"(create (?:a token that's a copy|\w+ tokens that are copies) of [^.\"]+?)\.(?: (?:That token|It|"
                r"The token) gains? haste\.)?( Sacrifice (?:it|that token|the token|them) at the beginning of the "
                r"next end step\.)", re.I),
     lambda m: f"{m[1]}{' COPYHASTE' if 'haste' in m[0][len(m[1]):] else ''} COPYSACEND."),
    (re.compile(r"(create (?:a token that's a copy|\w+ tokens that are copies) of [^.\"]+?)\. (?:That token|It) "
                r"gains haste\.", re.I), lambda m: f"{m[1]} COPYHASTE."),
    (re.compile(r"\b[A-Z]\w+ — (?=When you next cast)"), lambda m: ""),
]

_CLONE = re.compile(
    r"(?:[A-Z][\w' ]+ — )?You may have ~ enter(?: the battlefield)?(?P<tapped> tapped)? as a copy of "
    r"(?P<what>any creature on the battlefield|an? (?:creature|artifact or creature|creature or artifact) you control|"
    r"any creature card in a graveyard|any land card in a graveyard)(?:, except (?P<exc>.+?))?\."
    r"(?P<exile> When you do, exile that card\.)?")


_CAST_COPY = re.compile(
    r"(?:[A-Z][\w' ]+ — )?When you cast ~(?P<creature> while you control a creature)?, (?P<another>if you've cast "
    r"another spell this turn, )?(?:you may )?copy (?:it|~)(?P<x> X times)?(?P<life> if you gained life this turn)?\."
    r"(?: You may choose new targets for the cop(?:y|ies)\.)?")


def parse_line(line: str) -> dict | None:
    """CardDef fields for a whole rules line about copies ("You may have ~ enter as a copy of ...",
    "When you cast ~, copy it."), or None."""
    m = _CAST_COPY.fullmatch(line)
    if m:
        cond = "creature" if m["creature"] else "another" if m["another"] else "gained_life" if m["life"] else ""
        return {"cast_copy": {"cond": cond, "n": "x" if m["x"] else 1}}
    m = _CLONE.fullmatch(line)
    if not m:
        return None
    mods = parse_except(m["exc"]) if m["exc"] else {}
    if mods is None:
        return None
    what = m["what"]
    zone = "graveyard" if "graveyard" in what else "battlefield"
    who = "mine" if "you control" in what else "any"
    kind = "land" if "land card" in what else "artifact or creature" if "artifact" in what else "creature"
    return {"clone": {"zone": zone, "who": who, "what": kind, "mods": mods, "tapped": bool(m["tapped"]),
                      "exile": bool(m["exile"])}}


# ------------------------------------------------------------------ the engine side

def fits(card, what: str, perm=None) -> bool:
    """Whether a card (or permanent) is one of "artifact or creature", "nonland permanent", "Elemental",
    "nontoken creature", "artifact token", "artifact, creature, or land" ..."""
    is_creature = perm.is_creature if perm is not None else card.is_creature
    for alt in re.split(r",? or |, ", what.strip()):
        ok = True
        for w in alt.split():
            lw = w.lower()
            if lw in ("permanent", "nonlegendary"):
                continue
            if lw == "token":
                ok &= card.is_token
            elif lw == "nontoken":
                ok &= not card.is_token
            elif lw == "nonland":
                ok &= not card.is_land
            elif lw == "noncreature":
                ok &= not is_creature
            elif lw == "nonartifact":
                ok &= not card.is_artifact
            elif lw.startswith("non-"):
                ok &= w[4:] not in card.subtypes
            elif lw == "creature":
                ok &= is_creature
            elif lw in _TYPES:
                ok &= _TYPES[lw] in card.types
            elif w[0].isupper():
                ok &= w in card.subtypes or card.changeling
            else:
                ok = False
        if ok:
            return True
    return False


def score(card) -> float:
    return card.cmc + ((card.power or 0) + (card.toughness or 0)) / 2 + 0.5 * len(card.keywords)


def make_copy(card, mods: dict, token: bool = True, name: str | None = None):
    """A CardDef copying card, with the "except" changes."""
    from .cards import Effect, Trigger
    changes = {"is_token": token, "clone": None, "alt_costs": []}
    if name:
        changes["name"] = name
    if mods.get("pt"):
        changes["power"], changes["toughness"] = mods["pt"]
        changes["types"] = card.types | {"Creature"}
    if mods.get("types"):
        changes["types"] = changes.get("types", card.types) | mods["types"]
    if mods.get("subtypes"):
        changes["subtypes"] = card.subtypes | mods["subtypes"]
    if mods.get("keywords"):
        changes["keywords"] = card.keywords | mods["keywords"]
    if mods.get("sac_end"):
        changes["triggers"] = list(card.triggers) + [Trigger("end_step", [Effect("copy_sac", target="self")])]
    return dataclasses.replace(card, **changes)


def candidates(game, p, eff, source=None) -> list:
    """The permanents eff could copy."""
    d = eff.data
    if eff.target == "self":
        return [source] if source is not None else []
    who = d.get("who", "mine")
    pool = [x for pl in game.players for x in pl.battlefield
            if (who == "any" or (x.controller is p) == (who == "mine")) and game.targetable(x, p)]
    return [x for x in pool if fits(x.card, d.get("what", "permanent"), x)
            and not (d.get("other") and x is source)]


def value(game, me, eff, source=None) -> float:
    """What eff is worth to me now, or -1 when it would do nothing."""
    k, d = eff.kind, eff.data
    if k == "copy_perm":
        cands = candidates(game, me, eff, source)
        if not cands:
            return -1 if eff.target != "self" else 1.0
        n = d.get("n", 1)
        n = 1 if n == "x" else n          # X isn't known before casting
        best = sorted((score(x.card) for x in cands), reverse=True)
        v = sum(best) if d.get("each") else best[0] * max(n, 1)
        return v / 2 if d.get("mods", {}).get("sac_end") else v
    if k == "become_copy":
        if source is None:
            return -1
        cands = candidates(game, me, eff, source)
        gain = max((score(x.card) for x in cands), default=0) - score(source.card)
        return gain if gain > 0 else -1
    if k == "copy_ability":
        return 2.0 if _abilities(game, me, eff) else -1
    if k == "copy_spell":
        if d.get("of") == "target":
            own = [i for i in game.stack if i.is_spell and i.controller is me and _spell_fits(i.card, d.get("what"))]
            return max((i.card.cmc for i in own), default=-1)
        return 2.0
    if k == "copy_next_spell":
        return 1.0 if any(_spell_fits(c, d.get("what")) and c.cmc <= d.get("max_cmc", 99)
                          for c in me.hand if not c.is_land) else -1
    return 0.0


def _abilities(game, p, eff, item=None) -> list:
    """The activated or triggered abilities on the stack that eff could copy."""
    return [i for i in game.stack if not i.is_spell and i.controller is p and i is not item
            and not any(e.kind == "copy_ability" for e in i.effects)
            and (not eff.data.get("creature") or (i.source is not None and i.source.is_creature))]


def revert(perm):
    """End of turn: a permanent that became a copy is itself again."""
    if getattr(perm, "copy_revert", None) is not None:
        perm.card, perm.copy_revert = perm.copy_revert, None


def _spell_fits(card, what) -> bool:
    if card is None:
        return False
    if what == "instant or sorcery":
        return card.is_instant or card.is_sorcery
    return {"instant": card.is_instant, "sorcery": card.is_sorcery, "creature": card.is_creature}.get(what or "", True)


def resolve(game, p, eff, target, item=None):
    k, d = eff.kind, eff.data
    source = item.source if item is not None else None
    if k == "copy_sac":
        if target is not None and target in target.controller.battlefield:
            game.log(f"sacrifices {target.card.name} (copy)", target.controller)
            game.sacrifice(target)
    elif k == "copy_perm":
        cands = candidates(game, p, eff, target if eff.target == "self" else source)
        if eff.target == "self" and not cands and source is not None:
            cands = [source]     # last known information: the source has left the battlefield
        if not cands:
            return
        n = d.get("n", 1)
        if n == "x":
            n = getattr(item, "x", 0)
        chosen = cands if d.get("each") else [max(cands, key=lambda x: score(x.card))]
        for perm in chosen:
            for _ in range(n):
                game.enter_battlefield(p, make_copy(perm.copiable_card, d.get("mods", {})))
            game.log(f"creates {n} token cop{'y' if n == 1 else 'ies'} of {perm.card.name}", p)
    elif k == "become_copy":
        target = source
        if target is None or target not in target.controller.battlefield:
            return
        cands = candidates(game, p, eff, target)
        best = max(cands, key=lambda x: score(x.card), default=None)
        if best is None:
            return
        if getattr(target, "copy_revert", None) is None:
            target.copy_revert = target.copiable_card
        mods = d.get("mods", {})
        target.card = make_copy(best.copiable_card, mods, token=target.copy_revert.is_token,
                                name=target.copy_revert.name if mods.get("keep_name") else None)
        game.log(f"{target.copy_revert.name} becomes a copy of {best.card.name} until end of turn", p)
    elif k == "copy_ability":
        from .engine import StackItem
        found = _abilities(game, p, eff, item)
        if not found:
            return
        orig = found[-1]
        n = d.get("n", 1)
        n = getattr(item, "x", 0) if n == "x" else n
        for _ in range(n):
            targets = game.auto_targets(p, orig.effects)
            targets = [t if t is not None else old for t, old in zip(targets, orig.targets)]
            cp = StackItem(p, list(orig.effects), targets, source=orig.source, name=orig.name, context=orig.context,
                           kind=orig.kind)
            cp.x = getattr(orig, "x", 0)
            game.stack.append(cp)
        game.log(f"copies {orig.name} x{n}", p)
    elif k == "copy_spell":
        spell = None
        if d.get("of") == "that":
            spell = item.context if item is not None else None
        else:
            own = [i for i in game.stack if i.is_spell and i.controller is p and _spell_fits(i.card, d.get("what"))]
            spell = own[-1] if own else None
        if spell is not None and spell in game.stack and spell.card is not None:
            for _ in range(d.get("n", 1)):
                copy_spell(game, p, spell)
    elif k == "copy_next_spell":
        game.copy_next = [c for c in getattr(game, "copy_next", []) if c[2] == game.turn]
        game.copy_next.append((p, d, game.turn))
        game.log("will copy the next matching spell this turn", p)


def copy_spell(game, p, spell):
    """Put a copy of spell (a StackItem) on the stack under p's control, with new targets where better."""
    from .engine import StackItem
    card = spell.card
    if card.is_permanent:
        face = getattr(card, "cast_face", None) or game._origin(card)[0]
        card = dataclasses.replace(face, is_token=True)
    targets = game.auto_targets(p, spell.effects)
    targets = [t if t is not None else old for t, old in zip(targets, spell.targets)]
    copy = StackItem(p, list(spell.effects), targets, card=card, name=f"copy of {spell.card.name}", kind="copy")
    copy.x = getattr(spell, "x", 0)
    game.stack.append(copy)
    game.log(f"copies {spell.card.name}" + (f" -> {targets}" if any(targets) else ""), p)
    game.check_ward(copy)


def on_cast(game, p, item):
    """A spell was just cast: "when you cast ~, copy it", and "when you next cast ... this turn, copy it"."""
    counts = getattr(game, "spells_cast", {})
    if counts.get("turn") != game.turn:
        counts = {"turn": game.turn}
    before = counts.get(p.name, 0)
    item.storm_count = sum(counts.get(who.name, 0) for who in game.players)
    counts[p.name] = before + 1
    game.spells_cast = counts
    spec = getattr(item.card, "cast_copy", None)
    if spec:
        cond = spec["cond"]
        if (cond == "creature" and not p.creatures) or (cond == "another" and not before) or \
                (cond == "gained_life" and not p.life_gained_turn):
            pass
        else:
            for _ in range(getattr(item, "x", 0) if spec["n"] == "x" else spec["n"]):
                copy_spell(game, p, item)
    pending = [c for c in getattr(game, "copy_next", []) if c[2] == game.turn]
    keep = []
    for who, d, turn in pending:
        if who is p and _spell_fits(item.card, d.get("what")) and item.card.cmc <= d.get("max_cmc", 99):
            for _ in range(d.get("n", 1)):
                copy_spell(game, p, item)
        else:
            keep.append((who, d, turn))
    game.copy_next = keep


def wants_spell(effects) -> bool:
    """Whether a cast trigger's effects copy "that spell" (so the trigger needs the spell as context)."""
    return any((e.kind == "copy_spell" and e.data.get("of") == "that") or e.cond.startswith("mana") or e.kind == "increment"
               for e in effects)


def clone_on_enter(game, p, card):
    """The card a clone enters as: (card to use, card that goes to the graveyard later)."""
    spec = card.clone
    if not spec:
        return card, card
    if spec["zone"] == "graveyard":
        pool = [(c, pl) for pl in game.players for c in pl.graveyard if fits(c, spec["what"])]
        choice = max(pool, key=lambda t: score(t[0]), default=None)
        if choice is None:
            return card, card
        src, owner = choice
        if spec["exile"]:
            owner.graveyard.remove(src)
            owner.exile.append(src)
        src_card = src
    else:
        pool = [x for pl in game.players for x in pl.battlefield
                if (spec["who"] == "any" or pl is p) and fits(x.card, spec["what"], x)]
        best = max(pool, key=lambda x: score(x.card), default=None)
        if best is None:
            return card, card
        src_card = best.copiable_card
    copied = make_copy(src_card, spec["mods"], token=card.is_token,
                       name=card.name if spec["mods"].get("keep_name") else None)
    if spec["tapped"]:
        copied = dataclasses.replace(copied, enters_tapped=True)
    game.log(f"{card.name} enters as a copy of {src_card.name}", p)
    return copied, card
