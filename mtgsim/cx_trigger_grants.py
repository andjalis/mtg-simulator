"""Static grants of quoted triggered abilities (#338).

    Enchanted creature has "At the beginning of your upkeep, you lose 1 life."           (host grant)
    Equipped creature gets +2/+0 and has "Whenever this creature attacks alone, ..."      (host grant + bonus)
    Sliver creatures you control have "Whenever this creature attacks, it deals 1 ..."   (group grant)

The quoted ability is parsed with the ordinary trigger parser and stored on the granting card as
``trigger_grants`` ((spec, triggers), ...), where spec is ``{"host": True}`` or a permanent selector. The
recipient really has the ability: ``Permanent.triggers`` adds every granted trigger whose source is on the
battlefield, unsuppressed, and attached to it (host) or matching the selector (group). So inside the quote
"~" / "this creature" is the recipient, "you" is the recipient's controller, a new permanent that joins the
group gains the ability, and one that leaves the group (or whose Aura falls off) loses it. Dies and
leaves triggers use the trigger snapshot taken as the recipient leaves (``last_triggers``), which is
taken before its Auras and Equipment are detached.

Rejected (left visible): bodies the trigger parser does not fully match or only approximates, quotes that
name the granting card (``~`` can't tell it from "this creature"), conditional ("As long as ...") and
anthem-plus-grant group lines, and Equipment whose quote harms its holder.
"""
from __future__ import annotations

import re

_HOST = r"(?:Enchanted|Equipped) (?:creature|permanent|land|artifact|enchantment|planeswalker)"
_LINE = re.compile(r'(?:All )?(.+?) (?:gets ([+−-]\d+)/([+−-]\d+) and )?(?:has|have) "((?:When|Whenever|At) [^"]+)"\.?')
# A quoted ability that hurts the permanent that has it or its controller: such an Aura goes on an opponent's
# permanent (auras.finish reads any aura flag as hostile).
_HOSTILE = re.compile(r"\bsacrifice\b|\byou lose\b|deals? \d+ damage to you\b|gains? control of ~|\bexile ~|"
                      r"\bdestroy ~|-1/-1 counter|\btap ~|you get a poison counter", re.I)


# "When this creature dies, return it to the battlefield [tapped] under its owner's control [with a +1/+1 counter on
# it]": the card that died, tracked in its owner's graveyard (cx_return_died), not the "prev" event object.
# A rider after it ("and suspect it", "then create a Wicked Role token attached to it", "and create a Treasure token")
# acts on the returned permanent.
_DIES_RETURN = re.compile(r"When ~ dies, return it to the battlefield( tapped)? under its owner's control"
                          r"( with a \+1/\+1 counter on it)?(?:(?: and|, then) (.+))?\.", re.I)
# Effects that may come before "it" without giving it another antecedent: costs and their "if you do" gates.
_GATES = {"pay_gate", "pay_energy", "link_start", "link_check", "sac_filtered"}


def hostile(text: str) -> bool:
    """Does the quoted ability hurt the permanent that has it, or its controller?"""
    return bool(_HOSTILE.search(text))


def quoted_triggers(text: str):
    """The quoted ability as Triggers, or None unless the parser matches all of it exactly. The stable entry point
    for quoted triggered abilities given to another object (grants here and in cx_grammar_quoted; copy exceptions)."""
    from .cards.parse import _parse_trigger
    from .cards.model import Effect, Trigger
    body = re.sub(r"\bthis (?:creature|permanent|artifact|enchantment|land|planeswalker)\b", "~", text, flags=re.I)
    body = body.rstrip(".") + "."
    m = _DIES_RETURN.fullmatch(body)
    if m:
        then = []
        if m[3]:
            from .cards.parse import _parse_effects
            then, bad = _parse_effects(m[3][0].upper() + m[3][1:] + ".")
            if bad or not then or any(e.target not in ("prev", "none") for e in then):
                return None
        return (Trigger("dies", [Effect("cx_return_died", data={"tapped": bool(m[1]), "counter": bool(m[2]),
                                                               "then": list(then)})]),)
    parsed = _parse_trigger(body)
    if not parsed or not parsed[0] or parsed[1] or parsed[2] is not None:
        return None
    if any(t.event.startswith("host:") for t in parsed[0]):
        return None
    triggers = tuple(parsed[0])
    head = re.match(r"(?:When|Whenever) ~ ([^,]+),", body)
    rest = body[head.end():] if head else ""
    if head and not re.search(r"\b(?:dies|leaves|creature|permanent|artifact|enchantment|land|planeswalker|spell)\b",
                              head[1]) and re.search(r"\b(?:it|he|she)\b", rest) and \
            not re.search(r"\bthat (?:creature|permanent|card)\b", rest):
        # "Whenever ~ deals combat damage to a player, put a +1/+1 counter on it": "it" is the recipient, but a
        # trigger's "prev" is its event object (here none). Bind the leading "it" Effects to the recipient (#356).
        if any("prev" in t.intervening_if or any("prev" in e.cond for e in t.effects) for t in triggers):
            return None              # "if its toughness is 3 or less" would read the event object
        triggers = tuple(_it_is_self(t) for t in triggers)
    return triggers


_body = quoted_triggers


def _it_is_self(trigger):
    import dataclasses
    effects = []
    for i, e in enumerate(trigger.effects):
        lead = all(x.target in ("prev", "self") or x.target == "none" and x.kind in _GATES
                   for x in trigger.effects[:i])
        effects.append(dataclasses.replace(e, target="self") if e.target == "prev" and lead else e)
    return dataclasses.replace(trigger, effects=effects)


def _names_source(st) -> bool:
    """Does a quoted ability on this card name the card itself? Then "~" is ambiguous after name rewriting."""
    oracle, name = getattr(st, "oracle", ""), getattr(st, "name", "")
    return bool(name) and any(name in q for q in re.findall(r'"([^"]*)"', oracle or ""))


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m:
        return False
    subj, quote = m[1], m[4]
    host = re.fullmatch(_HOST, subj)
    extra = st.extra
    if host:
        if subj.startswith("Enchanted") and not extra.get("aura"):
            return False
        if subj.startswith("Equipped") and "Equipment" not in st.type_line:
            return False
        spec = {"host": True}
    else:
        if m[2] or re.match(r"(?:enchanted|equipped)\b", subj, re.I):
            return False             # "Creatures you control get +1/+0 and have ..." needs an anthem in the same layer pass
        from .permanent_templates import selector
        spec = selector(subj, plural=True)
        if spec is None or "keyword" in spec:
            return False
    triggers = _body(quote)
    if triggers is None or _names_source(st):
        return False
    bonus = (int(m[2].replace("−", "-")), int(m[3].replace("−", "-"))) if m[2] else (0, 0)
    # a real bonus outweighs a drawback ("gets +3/+3 and has ... put a -1/-1 counter on ~": Consuming Fervor)
    harmful = hostile(quote) and not (min(bonus) >= 0 and max(bonus) > 0)
    if host and harmful and subj.startswith("Equipped"):
        return False                 # the AI only equips its own creatures
    if m[2]:
        if extra.get("equip_bonus"):
            return False
        extra["equip_bonus"] = bonus
    if host and harmful:
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"hostile_grant"}
    extra["trigger_grants"] = extra.get("trigger_grants", ()) + ((spec, triggers),)
    extra.setdefault("advanced_rules", {})["trigger_grants"] = True      # indexed by residual_templates.sources
    return True


def granted(perm) -> list:
    """Triggered abilities other permanents give ``perm`` right now."""
    game = getattr(perm.controller, "_game", None)
    if game is None:
        return []
    from .permanent_templates import matches
    from .residual_templates import sources
    out = []
    for source in sources(game, "trigger_grants"):        # on the battlefield, abilities not suppressed
        for spec, triggers in source.card.trigger_grants:
            if spec.get("host"):
                ok = (source.aura_host or source.attached_to) is perm
            else:
                ok = matches(game, perm, spec, source.controller, source)
            if ok:
                out.extend(triggers)
    return out


def _token_grant(m):
    """"Create two 1/1 red Devil creature tokens. They have "When this token dies, ..."" is one token description:
    the tokens are created with the ability (cx_tokens reads "with "..."")."""
    desc, quote = m[1], m[3]
    join = " and " if re.search(r"\bwith\b", desc) else " with "
    return desc + join + quote


# "It has" for one token, "They have" for several; the description must end the sentence (no "that's tapped ...").
SUBS = [(re.compile(r'(\b[Cc]reate (?:a|an|one|two|three|four|five|X|\d+) [^."]*?\b(token)s?(?: named [^."]+?)?)'
                    r'\. (?:It has|They have) ("(?:When|Whenever|At) [^"]+")'), _token_grant)]
