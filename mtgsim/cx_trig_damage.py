"""Damage trigger heads from any source, with "that much" payoffs (#521).

    Whenever a creature deals damage to ~, ~ deals that much damage to that creature.                 (Tephraderm)
    Whenever a spell deals damage to ~, ~ deals that much damage to that spell's controller.
    Whenever ~ deals damage to a creature or opponent, ~ deals that much damage to you.               (Flesh Reaver)
    Whenever a noncreature source you control deals damage, you gain that much life.                  (Tamanoa)
    Whenever a red creature or spell deals damage, ~ deals that much damage to that creature's or spell's controller.
    Whenever an instant or sorcery spell you control deals damage to an opponent, ~ deals that much damage to
        target creature that player controls.                                                         (Satyr Firedancer)
    Whenever equipped creature deals damage to a blocking creature, ~ deals that much damage to each other creature
        defending player controls.                                                                    (Kusari-Gama)
    Whenever an Archer you control deals damage to a creature, that Archer deals that much damage to that
        creature's controller.                                                                        (Greatbow Doyen)
    Whenever a Dinosaur you control is dealt damage, it deals that much damage to any target that isn't a Dinosaur.

The engine's damage events (``deals_damage`` / ``dealt_damage``) fire only for permanent sources, so spells and
"any source" heads need their own reading: ``Game.deal_damage`` calls ``observe`` for every damage it deals, with
the source (a Permanent, or the CardDef of a resolving spell), the recipient, the damaging player and the amount.

Roles: S is the head's subject (the source for "deals damage", the damaged permanent for "is dealt damage"), O the
other side (the recipient, or the source). The payoff's damage source is ~ or S ("it", "that Archer"); "that
creature" is whichever of S and O is not the payoff's source; "that spell's controller" / "that creature's or
spell's controller" is the damaging player. A head without an object ("deals damage") triggers once per source
for damage dealt at the same time (one resolution or one combat damage step), for the total; a head with an object
triggers per recipient.

Refused: any subject, object or payoff wording outside this closed set (the line stays ignored).
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_HEAD = re.compile(r"Whenever (?P<subj>.+?) (?:deals damage(?: to (?P<obj>.+?))?|(?P<dealt>is dealt damage)), "
                   r"(?P<body>.+?)\.?")
_SRC = re.compile(r"an? (?P<adj>(?:(?:red|white|blue|black|green|noncreature) )*)"
                  r"(?P<noun>creature or spell|creature|spell|source|instant or sorcery spell)"
                  r"(?P<mine> you control)?")
_PERM = re.compile(r"an? (?P<desc>[\w -]+?)(?P<mine> you control)?")


def _subject(text: str, dealt: bool):
    """The head's subject -> spec dict, or None."""
    if text == "~":
        return {"self": True}
    if text == "equipped creature" and not dealt:
        return {"host": True}
    if not dealt:
        m = _SRC.fullmatch(text)
        if m:
            nouns = {"creature or spell": ("creature", "spell"), "instant or sorcery spell": ("instant", "sorcery")}
            return {"adj": tuple(m["adj"].split()), "nouns": nouns.get(m["noun"], (m["noun"],)),
                    "mine": bool(m["mine"])}
    m = _PERM.fullmatch(text)
    if not m or re.search(r"\b(?:spell|source|or)\b", m["desc"]):
        return None
    from .cx_events import _desc_alts
    alts = _desc_alts(m["desc"])
    return {"alts": alts, "mine": bool(m["mine"])} if alts else None


def _object(text):
    """'to <object>' -> spec dict, or None. No object: {}."""
    if text is None:
        return {}
    if text == "~":
        return {"self": True}
    players, alts = [], []
    from .cx_events import _desc_alts
    for part in re.sub(r"^an? ", "", text).split(" or "):
        if part in ("opponent", "player"):
            players.append(part)
            continue
        got = _desc_alts(part)
        if not got:
            return None
        alts += got
    return {"players": tuple(players), "alts": alts}


_PAYOFF = re.compile(r"(?P<src>~|it|that [A-Z]\w+) deals that much damage to (?P<to>.+)")
_TO = {"you": "you", "each opponent": "each_opponent", "that creature": "that_creature",
       "that spell's controller": "damager", "that creature's or spell's controller": "damager",
       "that creature's controller": "that_creature_controller",
       "each other creature defending player controls": "defenders_others",
       "target creature that player controls": "target_creature_of_player"}


def _payoff(body: str, subj: dict, obj: dict, dealt: bool):
    from .cards.model import Effect
    if body == "you gain that much life":
        return Effect("cx_dmg_payoff", data={"gain": True})
    m = _PAYOFF.fullmatch(body)
    if not m:
        return None
    to = _TO.get(m["to"])
    any_not = re.fullmatch(r"any target that isn't an? ([A-Z]\w+)", m["to"])
    if to is None and any_not:
        to = "any_not"
    if to is None:
        return None
    src = "self" if m["src"] == "~" else "subject"
    if src == "subject" and (subj.get("self") or "alts" not in subj and not subj.get("nouns") == ("creature",)):
        return None                 # "it" / "that Archer": the subject must be a permanent other than ~
    if to == "that_creature" and not (src == "self" and (subj.get("self") or subj.get("nouns") == ("creature",))):
        return None
    if to == "that_creature_controller" and (src != "subject" or obj.get("players") or not obj.get("alts")):
        return None
    if to == "defenders_others" and not any("blocking" in alt for alt in obj.get("alts", ())):
        return None
    if to == "target_creature_of_player" and (obj.get("alts") or not obj.get("players")):
        return None
    if to == "damager" and "spell" not in subj.get("nouns", ()):
        return None                 # "that spell's controller": the head's source must be able to be a spell
    data = {"src": src, "to": to}
    if any_not:
        data["not_subtype"] = any_not[1]
    return Effect("cx_dmg_payoff", data=data)


def parse(line: str):
    """(triggers, [], None) for a damage head of this family, else None."""
    from .cards.model import Trigger
    m = _HEAD.fullmatch(line)
    if not m:
        return None
    dealt = bool(m["dealt"])
    subj = _subject(m["subj"], dealt)
    obj = _object(m["obj"])
    if subj is None or obj is None or dealt and obj:
        return None
    eff = _payoff(m["body"], subj, obj, dealt)
    if eff is None:
        return None
    return [Trigger("cx_dmg", [eff], data={"subj": subj, "obj": obj, "dealt": dealt})], [], None


# ---------------------------------------------------------------- engine side

def _is_spell(game, src) -> bool:
    item = getattr(game, "resolving_item", None)
    return item is not None and item.is_spell and item.card is src


def _src_fits(game, spec, src, by, watcher) -> bool:
    from .engine.state import Permanent
    from .cx_events import _perm_fits
    if spec.get("self"):
        return src is watcher
    if spec.get("host"):
        return isinstance(src, Permanent) and src is getattr(watcher, "attached_to", None)
    perm = isinstance(src, Permanent)
    controller = src.controller if perm else by
    if spec.get("mine") and controller is not watcher.controller:
        return False
    if "alts" in spec:
        return perm and _perm_fits(game, src, spec["alts"])
    card = src.card if perm else src
    spell = not perm and _is_spell(game, src)
    for adj in spec["adj"]:
        if adj == "noncreature" and (perm and src.is_creature or not perm and "Creature" in card.types):
            return False
        if adj in _COLORS and _COLORS[adj] not in card.colors:
            return False
    for noun in spec["nouns"]:
        if noun == "creature" and perm and src.is_creature:
            return True
        if noun == "spell" and spell:
            return True
        if noun in ("instant", "sorcery") and spell and noun.capitalize() in card.types:
            return True
        if noun == "source" and (perm or src is not None):
            return True
    return False


def _obj_fits(game, spec, target, watcher) -> bool:
    from .engine.state import Permanent, Player
    from .cx_events import _perm_fits
    if not spec:
        return True
    if spec.get("self"):
        return target is watcher
    if isinstance(target, Player):
        return "player" in spec["players"] or "opponent" in spec["players"] and target is not watcher.controller
    return isinstance(target, Permanent) and bool(spec["alts"]) and _perm_fits(game, target, spec["alts"])


def observe(game, source, target, by, amount):
    """Queue the triggers of this family that a damage event matches."""
    from .engine.state import Permanent
    if amount <= 0:
        return
    for pl in game.players:
        for watcher in list(pl.battlefield):
            for i, trig in enumerate(watcher.triggers):
                if trig.event != "cx_dmg":
                    continue
                spec = trig.data
                if spec["dealt"]:
                    if not (isinstance(target, Permanent) and _dealt_fits(game, spec["subj"], target, watcher)):
                        continue
                    roles = (target, source)
                elif _src_fits(game, spec["subj"], source, by, watcher) and _obj_fits(game, spec["obj"], target, watcher):
                    roles = (source, target)
                else:
                    continue
                _queue(game, watcher, i, trig, roles, by, amount, batch=not spec["dealt"] and not spec["obj"])


def _dealt_fits(game, spec, perm, watcher) -> bool:
    from .cx_events import _perm_fits
    if spec.get("self"):
        return perm is watcher
    if spec.get("mine") and perm.controller is not watcher.controller:
        return False
    return "alts" in spec and _perm_fits(game, perm, spec["alts"])


def _queue(game, watcher, i, trig, roles, by, amount, batch):
    import dataclasses
    stamp = (game.turn, game.step, id(getattr(game, "resolving_item", None)))
    if batch:
        key = (id(watcher), i, id(roles[0]))
        batches = getattr(game, "cx_dmg_batches", None)
        if batches is None or batches[0] != stamp:
            batches = game.cx_dmg_batches = (stamp, {})
        queued = batches[1].get(key)
        if queued is not None and any(entry[1] and entry[1][0] is queued for entry in game.pending):
            queued.amount += amount             # the same source, damage dealt at the same time: one trigger
            return
    eff = dataclasses.replace(trig.effects[0], amount=amount,
                              data=dict(trig.effects[0].data, subject=roles[0], other=roles[1], damager=by))
    if eff.data.get("to") in ("target_creature_of_player", "any_not"):
        target = choose(game, watcher.controller, eff, watcher)
        if target is None:
            return                  # no legal target: the trigger is removed from the stack (CR 603.3d)
        eff.data["target_obj"] = target
    if batch:
        game.cx_dmg_batches[1][key] = eff
    game.queue_trigger(watcher.controller, [eff], watcher, watcher.card.name, roles[0])


def resolve(game, p, eff, item):
    """The payoff: that much damage (or life) as the trigger recorded it."""
    from .engine.state import Permanent, Player
    d = eff.data
    n = eff.amount
    if d.get("gain"):
        game.change_life(p, n, "life gain")
        return
    watcher = item.source if item is not None else None
    subject, other = d.get("subject"), d.get("other")
    src = watcher if d["src"] == "self" else subject
    if not isinstance(src, Permanent):
        return
    to = d["to"]
    victims = []
    if to == "you":
        victims = [p]
    elif to == "each_opponent":
        victims = [x for x in game.players if x is not p]
    elif to in ("that_creature", "that_creature_controller"):
        creature = other if src is subject else subject
        if isinstance(creature, Permanent):
            victims = [creature] if to == "that_creature" else [creature.controller]
            if to == "that_creature" and creature not in creature.controller.battlefield:
                victims = []
    elif to == "damager":
        victims = [d["damager"]] if isinstance(d.get("damager"), Player) else []
    elif to == "defenders_others":
        if isinstance(other, Permanent):
            victims = [c for c in other.controller.creatures if c is not other]
    elif to in ("target_creature_of_player", "any_not"):
        target = d.get("target_obj")
        victims = [target] if target is not None and _still_legal(game, p, eff, target, watcher) else []
    for v in victims:
        game.deal_damage(v, n, by=p, source=src)


def candidates(game, p, eff, source):
    """Legal targets for the targeted payoffs."""
    from .engine.state import Permanent
    d = eff.data
    if d["to"] == "target_creature_of_player":
        player = d.get("other")
        pool = list(getattr(player, "creatures", []))
    else:
        sub = d["not_subtype"]
        pool = [x for pl in game.players for x in pl.creatures + list(getattr(pl, "planeswalkers", []))
                if sub not in x.card.subtypes] + list(game.players)
    return [x for x in pool if not isinstance(x, Permanent) or game.targetable(x, p, source)]


def _still_legal(game, p, eff, target, source) -> bool:
    from .engine.state import Permanent
    if isinstance(target, Permanent) and target not in target.controller.battlefield:
        return False
    return any(x is target for x in candidates(game, p, eff, source))


def choose(game, p, eff, source):
    """The controller's pick: an opposing creature the damage kills (the best one), else the opponent, else the
    best opposing creature. Mandatory: any legal target if nothing on the other side is legal."""
    from .engine.policy import perm_value
    from .engine.state import Permanent
    legal = candidates(game, p, eff, source)
    theirs = [x for x in legal if (x.controller if isinstance(x, Permanent) else x) is not p]
    kills = [x for x in theirs if isinstance(x, Permanent) and x.toughness - x.damage <= eff.amount]
    if kills:
        return max(kills, key=perm_value)
    players = [x for x in theirs if not isinstance(x, Permanent)]
    if players:
        return players[0]
    if theirs:
        return max(theirs, key=perm_value)
    return max(legal, key=lambda x: -perm_value(x) if isinstance(x, Permanent) else 0, default=None)
