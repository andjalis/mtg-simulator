"""Face-down characteristics, payments and special actions shared by five mechanics.

Only the controller's policy consults the underlying card. Opposing policies use
Permanent.card, which is a nameless, colorless 2/2, including on the stack.
"""
from __future__ import annotations

import re
import itertools

CAST_KINDS = ("morph", "megamorph", "disguise")
MANIFEST_KINDS = ("manifest", "manifest_dread", "cloak")


def parse_cost(line):
    if not line.startswith(("Morph", "Megamorph", "Disguise")):
        return None
    from .cards import AltCost, parse_mana_cost
    m = re.fullmatch(r"(Morph|Megamorph|Disguise) ((?:\{(?:\d+|[WUBRGC]|[WUBRG]/[WUBRG])\})+)", line)
    if m:
        hybrid = tuple(a + b for a, b in re.findall(r"\{([WUBRG])/([WUBRG])\}", m[2]))
        return AltCost(m[1].lower(), parse_mana_cost(m[2]), hybrid=hybrid)
    m = re.fullmatch(r"(Morph|Megamorph|Disguise)—(.+)\.", line)
    if not m:
        return None
    text = m[2]
    extra = None
    match = re.fullmatch(r"Pay (\d+) life", text)
    if match:
        extra = ("life", int(match[1]))
    match = re.fullmatch(r"Reveal a (white|blue|black|red|green) card in your hand", text)
    if match:
        extra = ("reveal", dict(white="W", blue="U", black="B", red="R", green="G")[match[1]])
    match = re.fullmatch(r"Discard (a card|a Zombie card)", text)
    if match:
        extra = ("discard", "Zombie" if "Zombie" in match[1] else "")
    match = re.fullmatch(r"Return (two Islands|a Bird) you control to (?:their|its) owner's hand", text)
    if match:
        extra = ("return", (2, "Island") if match[1] == "two Islands" else (1, "Bird"))
    match = re.fullmatch(r"Sacrifice (another creature|two Mountains)", text)
    if match:
        extra = ("sacrifice", (1, "creature") if match[1] == "another creature" else (2, "Mountain"))
    if extra is None:
        return None
    alt = AltCost(m[1].lower(), {})
    alt.face_up_extra = extra
    return alt


def appearance(kind):
    from .cards import CardDef
    return CardDef(name="", mana_cost={}, cmc=0, types=frozenset({"Creature"}),
                   power=2, toughness=2, ward=2 if kind in ("disguise", "cloak") else 0,
                   mana_cost_missing=True, colors=frozenset())


def spell(base, kind):
    from .cards import AltCost
    card = appearance(kind)
    card.origin = (base, kind, AltCost(kind, {"generic": 3}))
    return card


def enter(game, player, card, kind):
    player.face_down_turn = game.turn
    return game.enter_battlefield(player, appearance(kind), face_down=(card, kind))


def prepare(perm, card, kind):
    # This must happen before ETB observers and state-based actions, not after.
    perm.front = perm.hidden = card
    perm.face_down_kind = kind


def visible_card(perm, viewer):
    return perm.hidden if perm.hidden is not None and viewer is perm.controller else perm.card


def modified(perm):
    return bool(any(perm.counters.values()) or perm.equipment or
                any(a.controller is perm.controller for a in perm.auras))


def reveal_spell(game, item):
    if item.kind == "spell":
        base, kind, _ = game._origin(item.card)
        if kind in CAST_KINDS:
            game.log(f"reveals {base.name} as the face-down spell leaves the stack", item.controller)


def up_options(perm):
    if perm.hidden is None:
        return []
    card = perm.hidden
    out = [a for a in card.alt_costs if a.kind in CAST_KINDS]
    if getattr(perm, "face_down_kind", "") in MANIFEST_KINDS and card.is_creature:
        # A missing printed mana cost cannot be paid (unlike a printed {0}).
        if not card.mana_cost_missing:
            from .cards import AltCost
            out.append(AltCost("mana_cost", {k: v for k, v in card.mana_cost.items() if k != "X"}, hybrid=card.hybrid))
    return out


def _extra_candidates(player, perm, alt):
    what, value = getattr(alt, "face_up_extra", ("", None))
    if what == "life":
        return player.life >= value
    if what in ("reveal", "discard"):
        cards = [c for c in player.hand if (what == "reveal" and value in (
                     c.colors if c.colors is not None else c.mana_cost)) or
                 (what == "discard" and (not value or value in c.subtypes or c.changeling))]
        return sorted(cards, key=lambda c: c.cmc)[:1]
    if what in ("return", "sacrifice"):
        count, subtype = value
        pool = [x for x in player.battlefield if
                (subtype == "creature" and x is not perm and x.is_creature) or subtype in x.card.subtypes
                or (subtype == "Bird" and x.card.changeling)]
        pool.sort(key=lambda x: x.card.cmc)
        return pool[:count] if len(pool) >= count else []
    return True


def _payments(alt):
    for colors in itertools.product(*alt.hybrid):
        cost = dict(alt.cost)
        for pair, color in zip(alt.hybrid, colors):
            cost[pair[0]] -= 1
            cost[color] = cost.get(color, 0) + 1
        yield cost


def can_turn_up(game, player, perm, alt):
    return (perm in player.battlefield and perm.controller is player and perm.hidden is not None
            and bool(_extra_candidates(player, perm, alt)) and any(
                game.can_pay(player, cost, spell="ability") for cost in _payments(alt)))


def turn_up(game, player, perm, method=None, *, free=False):
    """Take one special action. The change is immediate; only its triggers use the stack."""
    if perm not in player.battlefield or perm.controller is not player or perm.hidden is None:
        return False
    if free:
        if not perm.hidden.types.isdisjoint({"Instant", "Sorcery"}):
            game.log(f"reveals {perm.hidden.name}; it stays face down", player)
            return False
        alt = None
    else:
        alt = next((a for a in up_options(perm) if (method is None or a.kind == method)
                    and can_turn_up(game, player, perm, a)), None)
        if alt is None:
            return False
        chosen = _extra_candidates(player, perm, alt)
        cost = next(cost for cost in _payments(alt) if game.can_pay(player, cost, spell="ability"))
        if game.pay(player, cost) is None:
            return False
        what, value = getattr(alt, "face_up_extra", ("", None))
        if what == "life":
            game.change_life(player, -value, "morph cost")
        elif what == "reveal":
            game.log(f"reveals {chosen[0].name} for morph", player)
        elif what == "discard":
            game.discard_card(player, chosen[0])
        elif what in ("return", "sacrifice"):
            for obj in chosen:
                if what == "return":
                    game.leave_battlefield(obj, "hand")
                else:
                    game.sacrifice(obj)
    perm.card, perm.hidden = perm.hidden, None
    perm.face_down_kind = ""
    player.face_up_turn = game.turn
    if alt is not None and alt.kind == "megamorph":
        perm.counters["+1/+1"] = perm.p1 + 1
    game.log(f"turns {perm.card.name} face up", player)
    game.fire(player, "turned_face_up", perm)
    game.fire(player, "ally_turned_face_up", context=perm, subject=perm)
    # Face-up characteristics do not cause ETB events or reset summoning sickness,
    # damage, attachments, combat membership or counters.
    game.state_based_actions()
    game.settle()
    return True


def auto_turn_up(game, player):
    """Minimal play policy: improve a body, use a trigger, or escape a lethal hit."""
    for perm in list(player.battlefield):
        if perm.hidden is None:
            continue
        card = perm.hidden
        lethal = any(e.target in ("creature", "creature_pw", "any", "nonland_perm") and t is perm
                     for item in game.stack for e, t in zip(item.effects, item.targets))
        better = (card.power or 0) > 2 or (card.toughness or 0) > 2 or bool(card.keywords)
        trigger = any(t.event == "turned_face_up" for t in card.triggers)
        options = up_options(perm)
        if better or trigger or lethal or any(a.kind == "megamorph" for a in options):
            for alt in options:
                extra = getattr(alt, "face_up_extra", ("", None))
                if extra[0] == "life" and player.life <= extra[1]:
                    continue
                if can_turn_up(game, player, perm, alt):
                    return turn_up(game, player, perm, alt.kind)
    return False


def parse_effect(text):
    """Exact templates only: unbound pronouns and complex riders stay unsupported."""
    from .cards import Effect, _num
    text = text.rstrip(".")
    m = re.fullmatch(r"(?:you may )?manifest dread(?: (twice))?(?:, then attach (?:~|this equipment) to that creature)?",
                     text, re.I)
    if m:
        return [Effect("manifest_dread", 2 if m[1] else 1, data={"attach": "attach" in text.lower()})]
    if text.lower() == "its controller manifests dread":
        return [Effect("manifest_dread", 1, target="that_controller")]
    if text.lower() == "turn target face-down creature face up":
        return [Effect("turn_face_up", target="creature", filter="face_down")]
    if re.fullmatch(r"reveal target face-down permanent\. If it's a creature card, you may turn it face up", text, re.I):
        return [Effect("turn_face_up", target="nonland_perm", filter="face_down", data={"creature_only": True})]
    m = re.fullmatch(r"(?:you may )?(manifest|cloak) the top (card|\w+ cards) of your library"
                     r"(?:, then (?:put (a|two|\d+) \+1/\+1 counters? on it|attach ~ to it))?", text, re.I)
    if m:
        n = 1 if m[2].lower() == "card" else _num(m[2].split()[0])
        return [Effect(m[1].lower(), n, data={"counters": _num(m[3]) if m[3] else 0,
                                             "attach": "attach" in text.lower()})]
    m = re.fullmatch(r"(?:you may )?(manifest|cloak) a card from your hand", text, re.I)
    if m:
        return [Effect(m[1].lower(), 1, data={"zone": "hand"})]
    m = re.fullmatch(r"Look at the top (\w+) cards of your library, cloak (\w+) of them, and put the rest "
                     r"on the bottom of your library in a random order", text, re.I)
    if m:
        return [Effect("cloak", _num(m[2]), data={"look": _num(m[1]), "bottom_random": True})]
    return None


def loot(game, player):
    if not player.library:
        return
    game.draw(player, 1)
    if max(getattr(player, "face_down_turn", -1), getattr(player, "face_up_turn", -1)) != game.turn:
        if player.hand:
            game.discard_card(player, player.ai.choose_discard(game, player))


def resolve(game, player, eff, target, item):
    """Put actual cards into play; a face-down permanent is never a token."""
    from . import copies
    if eff.target == "that_controller":
        if target not in game.players:
            return
        player = target
    kind = eff.kind
    created = []
    if eff.data.get("look"):
        pool = [player.library.pop() for _ in range(min(eff.data["look"], len(player.library)))]
        pool.sort(key=copies.score, reverse=True)
        cards, rest = pool[:eff.amount], pool[eff.amount:]
        if eff.data.get("bottom_random"):
            game.rng.shuffle(rest)
        player.library[0:0] = rest
    elif eff.data.get("zone") == "hand":
        cards = sorted(player.hand, key=copies.score)[:eff.amount]
        for card in cards:
            player.hand.remove(card)
    else:
        cards = []
        for _ in range(eff.amount or 1):
            if kind == "manifest_dread":
                pool = [player.library.pop() for _ in range(min(2, len(player.library)))]
                if not pool:
                    continue
                pool.sort(key=copies.score)
                card, rest = pool[0], pool[1:]
                # Move the other card after the face-down permanent enters, per
                # manifest dread's instruction order.
                perm = enter(game, player, card, kind)
                created.append(perm)
                player.graveyard.extend(rest)
            elif player.library:
                cards.append(player.library.pop())
    for card in cards:
        created.append(enter(game, player, card, kind))
    for perm in created:
        counters = eff.data.get("counters", 0)
        if counters:
            perm.counters["+1/+1"] = perm.p1 + counters
        source = item.source if item is not None else None
        if eff.data.get("attach") and source is not None and source in source.controller.battlefield \
                and "Equipment" in source.card.subtypes and perm in player.battlefield:
            source.attached_to = perm
        game.log(kind.replace("_", " "), player)
    return created
