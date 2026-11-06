"""Phasing: permanents phase in and out (Mirage block, Teferi's suite, modern blink-with-protection).

A phased-out permanent is simply off its controller's battlefield: it stays a Permanent
object (counters, tap state and attachments intact) in a per-game pool, so every effect,
count and combat query treats it as gone, exactly as the rules require. It phases back
in at its controller's untap step (no "enters the battlefield" triggers, CR 702.26), and
permanents with the phasing keyword phase out at that same untap, simultaneously with the
phase-ins: a card that just phased in never phases straight back out.

``phase_out`` effects are templates with the selection in ``data``: a single target, all
permanents one player controls, a type slice, everything a previous effect's target
controls, or "all but the N most valuable" (Disciple of Caelus Nin). "Phases out until
~ leaves the battlefield" (Oubliette, Out of Time, The Moment) stores the anchor and a
rules-event listener returns those permanents when the anchor leaves. The untap-step
hook ``phasing_untap(game, p)`` is for turns.py; until it is landed there, permanents
with phasing keep phasing only through explicit phase-out effects.

Recorded simplifications: "unless you pay" upkeep phase-outs pay when the mana is there
and only phase out broke (Vaporous Djinn, Warping Wurm); "any number of target" and
"up to X target" phase-outs affect one target or the obvious slice; Teferi's Veil rides the
shared "at end of combat" delay; Equipoise hits every opponent's
most valuable lands / artifacts / creatures beyond the controller's own count; Teferi's
Realm phases out the nontoken slice that costs its (active) player the least; the
Adversary cycle's "you may pay {cost} any number of times" pays up to three times
(Spectral's phase-outs take the opponents' most valuable nonland permanents first,
Tainted's riders land the counters and twice-that-many Zombie tokens; Primal's rider
animates the first of the controller's lands as 3/3 Wolves with haste permanently); the "protection from everything / life total can't
change" riders of Teferi's Protection and Perch Protection stay unsupported; King of the
Oathbreakers only hears itself phase in, not other Spirits; The War Doctor's
cross-permanent phase-out listener is not built.
"""
from __future__ import annotations

import re


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _cost(text):
    from .cards.model import parse_mana_cost
    return parse_mana_cost(text)


def _token_data(power, toughness, desc, with_kw=""):
    from .dungeon_mechanics import _token_data as build
    return build(power, toughness, desc, with_kw)


EFFECT_PATTERNS = [
    # --- one permanent phases out -------------------------------------------------
    (r"~ phases out unless you pay ((?:\{[WUBRGC0-9]+\})+)",
     lambda m: _e("phase_out", target="self", data={"unless": _cost(m[1])})),
    (r"~ phases out", lambda m: _e("phase_out", target="self")),
    (r"~ phases out or is sacrificed on a coin flip",
     lambda m: _e("phase_coin", target="self")),
    (r"(?:~|this (?:creature|permanent)) and that creature phase out",
     lambda m: [_e("phase_out", target="self"), _e("phase_out", target="trigger_subject")]),
    (r"it phases out", lambda m: _e("phase_out", target="prev", data={"fallback_self": True})),
    (r"it phases out until ~ leaves the battlefield",
     lambda m: _e("phase_out", target="prev", data={"until_leaves": True})),
    (r"target creature phases out( tapped)? until ~ leaves the battlefield",
     lambda m: _e("phase_out", target="creature", data={"until_leaves": True,
                                                       "tap_on_in": bool(m[1])})),
    (r"(?:equipped|enchanted) (?:creature|permanent) phases out",
     lambda m: _e("phase_out", target="host")),
    (r"up to one target creature phases out", lambda m: _e("phase_out", target="creature")),
    (r"target creature an opponent controls phases out",
     lambda m: _e("phase_out", target="creature", filter="opp")),
    (r"target creature you don't control phases out",
     lambda m: _e("phase_out", target="creature", filter="opp")),
    (r"target creature or planeswalker an opponent controls phases out",
     lambda m: _e("phase_out", target="creature_pw", filter="opp")),
    (r"target creature you control phases out", lambda m: _e("phase_out", target="creature_mine")),
    (r"target creature phases out", lambda m: _e("phase_out", target="creature")),
    (r"target (?:artifact|permanent|nonland permanent) you control phases out",
     lambda m: _e("phase_out", target="nonland_perm", filter="mine")),
    (r"(?:another |up to one |up to two )?target (?:nonland )?permanent phases out",
     lambda m: _e("phase_out", target="permanent")),
    (r"target artifact phases out", lambda m: _e("phase_out", target="artifact")),
    (r"target artifact, creature, or land phases out", lambda m: _e("phase_out", target="permanent")),
    (r"untap target creature you control",
     lambda m: _e("untap_target", target="creature_mine")),
    (r"untap all creatures, then those creatures phase out until ~ leaves the battlefield",
     lambda m: _e("phase_out", target="none", data={"creatures": True, "until_leaves": True})),
    # --- a player's permanents phase out -------------------------------------------
    (r"all permanents you control phase out", lambda m: _e("phase_out", data={"mine": True})),
    (r"all lands you control phase out", lambda m: _e("phase_out", data={"mine_type": "land"})),
    (r"all artifacts and creatures phase out",
     lambda m: _e("phase_out", data={"types": ("Artifact", "Creature")})),
    (r"all nonland permanents they control phase out",
     lambda m: _e("phase_out", data={"of_prev": True})),
    (r"each creature (?:target|that) (?:player|opponent) controls phases out(?: instead)?",
     lambda m: _e("phase_out", data={"each_creature_of_prev": True})),
    (r"any number of target creatures you control phase out",
     lambda m: _e("phase_out", data={"my_creatures_other": True})),
    (r"any number of target nonland permanents you control phase out",
     lambda m: _e("phase_out", data={"mine_nonland": True})),
    (r"any number of other target creatures you control phase out",
     lambda m: _e("phase_out", data={"my_creatures_other": True})),
    (r"you may have any number of them phase out",
     lambda m: _e("phase_out", data={"mine_with_counters": True})),
    (r"permanents you control that had a counter put on them this way phase out",
     lambda m: _e("phase_out", data={"mine_with_counters": True})),
    (r"up to that many creatures and/or planeswalkers you control phase out",
     lambda m: _e("phase_out", data={"mine_kicked": True})),
    (r"up to X target creatures phase out", lambda m: _e("phase_out", target="creature")),
    (r"each player phases out all permanents they control other than ~ except their "
     r"(?:five|\d+) most valuable", lambda m: _e("phase_out", data={"all_but": 5})),
    # --- the phase-in side ----------------------------------------------------------
    (r"simultaneously, all phased-out creatures phase in and all creatures with phasing phase out",
     lambda m: [_e("phase_in_all"), _e("phase_out", data={"phasing": True})]),
    (r"all phased-out creatures phase in", lambda m: _e("phase_in_all")),
    # --- riders that read the phase-out just before them -----------------------------
    (r"put a time counter on ~ for each creature that phased out this way",
     lambda m: _e("phase_out_count", data={"counter": "time"})),
    # --- upkeep phase-outs of a whole type slice -------------------------------------
    # Equipoise: "for each land [artifact, creature] the opponent has beyond ours"
    (r"for each land target player controls in excess of the number you control, choose a "
     r"land that player controls, then the chosen permanents phase out",
     lambda m: _e("phase_out_excess", data={"type": "land"})),
    (r"repeat this process for artifacts and creatures",
     lambda m: [_e("phase_out_excess", data={"type": "Artifact"}),
                _e("phase_out_excess", data={"type": "Creature"})]),
    # Teferi's Realm: the type is chosen as the trigger resolves (see SUBS)
    (r"that player phases out all nontoken permanents of a chosen type",
     lambda m: _e("phase_out_realm")),
    # --- pay a cost any number of times as ~ enters (the Adversary cycle) -------------
    # The pay carries the count on the resolving item (pay_repeat); the "when you pay
    # this cost" riders read it back (phase_out_paid / pay_repeat_counters / tokens).
    (r"you may pay ((?:\{[WUBRGC0-9]+\})+) any number of times",
     lambda m: _e("pay_repeat", data={"cost": _cost(m[1])})),
    (r"when you pay this cost one or more times, put that many \+1/\+1 counters on ~, "
     r"then up to that many other target artifacts, creatures, and/or enchantments phase out",
     lambda m: _e("phase_out_paid")),
    (r"when you pay this cost one or more times, put that many ([\w+/-]+) counters? on ~",
     lambda m: _e("pay_repeat_counters", target="self", data={"counter": m[1]})),
    # Primal Adversary: the counters, then that many of the controller's lands animate
    # permanently (3/3 Wolf creatures with haste that are still lands).
    (r"when you pay this cost one or more times, put that many ([\w+/-]+) counters? on ~, "
     r"then up to that many target lands you control become (\d+)/(\d+) (\w+) creatures? "
     r"with (\w+) that are still lands",
     lambda m: _e("pay_repeat_lands", target="self",
                  data={"counter": m[1], "power": int(m[2]), "toughness": int(m[3]),
                        "subtype": m[4], "keyword": m[5].lower()})),
    # the colour comes before the size in current Oracle text ("black 2/2 Zombie"), after it in the old text
    (r"create twice that many ((?:(?:white|blue|black|red|green|colorless) )*)(\d+)/(\d+) "
     r"((?:\w+ )*?)creature tokens?(?: with ([\w ,]+))?",
     lambda m: _e("pay_repeat_tokens", data=_token_data(m[2], m[3], m[1] + m[4], m[5]))),
]

TRIGGERS = [
    # Teferi's Realm: the effect's context is the player whose upkeep it is
    (r"At the beginning of each player's upkeep, (.+)", ("each_upkeep",)),
    (r"Whenever ~ phases out, (.+)", ("phases_out",)),
    (r"Whenever ~ phases in, (.+)", ("phases_in",)),
    (r"When ~ phases out or leaves the battlefield, (.+)", ("phases_out",)),
    # "or another Spirit you control" is simplified to ~ itself (no broadcast listeners yet).
    (r"Whenever ~ or another \w+ you control becomes the target of a spell, (it phases out)\.",
     ("targeted_by_spell",)),
    (r"Whenever ~ or another \w+ you control phases in, (.+)", ("phases_in",)),
]

SUBS = [
    # Disciple of Caelus Nin: the choose-five ritual is one phase-out of everything but
    # each player's five most valuable permanents.
    (re.compile(r"starting with you, each player chooses up to five permanents they control\. "
                r"All permanents other than ~ that weren't chosen this way phase out\."), 
     "each player phases out all permanents they control other than ~ except their five most valuable"),
    # Oubliette: the tap-on-return rider rides the phase-out itself.
    (re.compile(r"target creature phases out until ~ leaves the battlefield\. "
                r"Tap that creature as it phases in this way\."),
     "target creature phases out tapped until ~ leaves the battlefield"),
    # "Those permanents phase out." after a sentence that named them: fold into one effect.
    (re.compile(r"(?<=this way\.) Those permanents phase out\."),
     " Permanents you control that had a counter put on them this way phase out."),
    (re.compile(r"(?<=~ was kicked\.) Those permanents phase out\."),
     " Up to that many creatures and/or planeswalkers you control phase out."),
    # Frenetic Efreet: the coin flip is one effect.
    (re.compile(r"Flip a coin\. If you win the flip, ~ phases out\. If you lose the flip, "
                r"sacrifice ~\."),
     "~ phases out or is sacrificed on a coin flip."),
    # Teferi's Realm: the choice and the phase-out are one effect (the type is chosen
    # as the trigger resolves, by whoever's upkeep it is).
    (re.compile(r"that player chooses artifact, creature, land, or non-Aura enchantment\. "
                r"All nontoken permanents of that type phase out\."),
     "that player phases out all nontoken permanents of a chosen type."),
]


# --------------------------------------------------------------------------- the pool

def pool(game):
    """(permanent, anchor) pairs of everything phased out; anchor is None or the permanent
    whose leaving returns them."""
    return game.__dict__.setdefault("_phased_out", [])


def phased_out(game):
    return [entry[0] for entry in pool(game)]


def phase_out(game, perm, until=None, tap_on_in=False):
    """Take perm (and everything attached to it) out of the game until its controller's
    untap step, or until the ``until`` anchor leaves the battlefield."""
    if perm not in perm.controller.battlefield:
        return False
    attached = [x for pl in game.players for x in pl.battlefield if getattr(x, "attached_to", None) is perm]
    controller = perm.controller
    controller.battlefield.remove(perm)
    perm.phased_out = True
    pool(game).append((perm, until, tap_on_in))
    game.log(f"{perm.card.name} phases out", controller)
    game.fire(controller, "phases_out", perm)
    for x in attached:
        phase_out(game, x, until=until)
    if until is not None:
        _ensure_listener(game)
    return True


def phase_in(game, perm):
    """Return a phased-out permanent to its controller's battlefield (no enter triggers)."""
    entries = pool(game)
    entry = next((e for e in entries if e[0] is perm), None)
    if entry is None:
        return False
    entries.remove(entry)
    perm.phased_out = False
    perm.controller.battlefield.append(perm)
    if entry[2]:
        perm.tapped = True
    game.log(f"{perm.card.name} phases in", perm.controller)
    game.fire(perm.controller, "phases_in", perm)
    # whatever phased out attached to it (its Auras and Equipment) comes back with it
    for attached, until, _ in [e for e in entries if getattr(e[0], "attached_to", None) is perm
                               and e[1] is None]:
        phase_in(game, attached)
    return True


def phasing_untap(game, p):
    """The untap-step phase dance (CR 702.26): the phase-ins and the phase-outs of
    permanents with phasing happen simultaneously, before anything untaps. Hook for
    turns.py, right at the start of the active player's untap step."""
    out = [x for x in p.battlefield if x.has("phasing")]       # computed first: just-phased-in
    for perm, until, tap in [e for e in pool(game) if e[0].controller is p and e[1] is None]:
        phase_in(game, perm)
    for perm in out:
        phase_out(game, perm)


def _ensure_listener(game):
    """Watch the rules events so "phases out until ~ leaves the battlefield" returns."""
    if game.__dict__.get("_phasing_listener"):
        return
    game.__dict__["_phasing_listener"] = True

    def on_event(event):
        if event.kind == "leaves":
            for perm, until, _ in list(pool(game)):
                if until is event.source:
                    phase_in(game, perm)
    game.rule_events.listeners.append(on_event)


# --------------------------------------------------------------------------- effect kinds

def resolve_phase_out(game, p, eff, target, item, prev):
    d = eff.data
    cost = d.get("unless")
    if cost is not None and game.can_pay(p, cost) \
            and game.hook(p, "pay_optional")(game, p, cost, "unless"):
        game.pay(p, cost)                  # "phases out unless you pay": paid, so it stays
        game.log("pays to keep it from phasing out", p)
        return
    until = item.source if d.get("until_leaves") and item is not None else None
    if target is None and d.get("fallback_self") and item is not None:
        target = item.source        # "it phases out" in a trigger: the trigger's source
    perms = _selection(game, p, eff, target, item, prev)
    n = 0
    for perm in perms:
        if phase_out(game, perm, until=until, tap_on_in=bool(d.get("tap_on_in"))):
            n += 1
    game.__dict__["_last_phase_out_count"] = n
    if n:
        game.log(f"phases out {n} permanent(s)", p)


def _selection(game, p, eff, target, item, prev):
    """Which permanents a phase_out effect takes, given its data selection."""
    from .engine.state import Permanent
    d = eff.data
    if d.get("mine"):
        return [x for x in p.battlefield if item is None or not isinstance(item.source, Permanent)
                or x is not item.source]
    if d.get("mine_type"):
        return [x for x in p.battlefield if x.card.is_land] if d["mine_type"] == "land" else []
    if d.get("types"):
        return [x for pl in game.players for x in pl.battlefield
                if any(t in x.card.types for t in d["types"])]
    if d.get("creatures"):
        return [x for pl in game.players for x in pl.creatures]
    if d.get("phasing"):
        return [x for pl in game.players for x in pl.creatures if x.has("phasing")]
    if d.get("my_creatures_other"):
        return [x for x in p.creatures if item is None or x is not item.source]
    if d.get("mine_nonland"):
        return [x for x in p.battlefield if not x.card.is_land]
    if d.get("mine_with_counters"):
        return [x for x in p.battlefield if x.counters]
    if d.get("mine_kicked"):
        from .engine.policy import perm_value
        kicks = getattr(item, "kicks", 0) if item is not None else 0
        best = sorted((x for x in p.battlefield if x.is_creature or x.is_planeswalker),
                      key=perm_value, reverse=True)
        return best[:kicks]
    if d.get("all_but"):
        from .engine.policy import perm_value
        out = []
        for pl in game.players:
            ranked = sorted((x for x in pl.battlefield
                             if item is None or not isinstance(item.source, Permanent)
                             or x is not item.source), key=perm_value, reverse=True)
            out += ranked[int(d["all_but"]):]
        return out
    if d.get("of_prev"):
        from .engine.state import Player
        who = prev if isinstance(prev, Player) else game.opponent(p)
        return [x for x in who.battlefield if not x.card.is_land]
    if d.get("each_creature_of_prev"):
        subject = target if isinstance(target, Permanent) else prev
        who = subject.controller if isinstance(subject, Permanent) else game.opponent(p)
        return list(who.creatures)
    if isinstance(target, Permanent):
        return [target]
    return []


def resolve_phase_in_all(game, p, eff):
    """"all phased-out creatures phase in" (Time and Tide)."""
    for perm in [x for x in phased_out(game) if x.is_creature]:
        phase_in(game, perm)


def phase_coin(game, p, eff, target, item):
    """Frenetic Efreet: win the flip, phase out; lose it, sacrifice."""
    from .engine.state import Permanent
    src = item.source if item is not None and isinstance(item.source, Permanent) else None
    if src is None:
        return
    if game.rng.random() < 0.5:
        game.log(f"flips a coin and {src.card.name} phases out", p)
        phase_out(game, src)
    else:
        game.log(f"flips a coin and loses ({src.card.name})", p)
        game.sacrifice(src)


def phase_out_excess(game, p, eff, item):
    """Equipoise: the opponent's lands (or artifacts, creatures) beyond p's own count."""
    from .engine.policy import perm_value
    kind = eff.data.get("type")
    has = (lambda x: x.card.is_land) if kind == "land" else \
        (lambda x: x.card.is_creature if kind == "Creature" else kind in x.card.types)
    mine = sum(1 for x in p.battlefield if has(x))
    for opp in game.players:
        if opp is p:
            continue
        theirs = sorted((x for x in opp.battlefield if has(x)), key=perm_value, reverse=True)
        for perm in theirs[:max(0, len(theirs) - mine)]:
            phase_out(game, perm)


def phase_out_realm(game, p, eff, target, item):
    """Teferi's Realm: in whosever upkeep this resolves, they lose the nontoken permanents
    of the type that costs them the least."""
    from .engine.policy import perm_value
    who = getattr(item, "context", None) if item is not None else None
    if who is None or not hasattr(who, "battlefield"):
        who = p
    slices = {}
    for name, has in (("Artifact", lambda x: "Artifact" in x.card.types),
                      ("Creature", lambda x: x.is_creature),
                      ("Land", lambda x: x.card.is_land),
                      ("Enchantment", lambda x: "Enchantment" in x.card.types
                       and "Aura" not in x.card.subtypes)):
        slices[name] = [x for x in who.battlefield if not x.card.is_token and has(x)]
    _, victims = min(slices.items(), key=lambda kv: sum(perm_value(x) for x in kv[1]))
    for perm in victims:
        phase_out(game, perm)


def pay_repeat(game, p, eff, item):
    """"You may pay {1}{U} any number of times": pay while the mana is there (up to three
    times, enough for every realistic board)."""
    cost = eff.data.get("cost") or {"generic": 1, "U": 1}
    n = 0
    while n < 3 and game.can_pay(p, cost):
        game.pay(p, cost)
        n += 1
    if item is not None:
        item.pay_repeat = n
    game.log(f"pays {n} time(s)", p)


def phase_out_paid(game, p, eff, target, item):
    """"When you pay this cost one or more times, ...": that many counters on ~, then that
    many other permanents phase out (the opponents' best first)."""
    from .engine.state import Permanent
    from .engine.policy import perm_value
    n = getattr(item, "pay_repeat", 0) if item is not None else 0
    src = item.source if item is not None else None
    if not n or not isinstance(src, Permanent) or src not in p.battlefield:
        return
    src.counters["+1/+1"] = src.p1 + n
    cands = [x for pl in game.players for x in pl.battlefield if x is not src and not x.card.is_land]
    cands.sort(key=lambda x: (x.controller is not p, perm_value(x)), reverse=True)
    for perm in cands[:n]:
        phase_out(game, perm)


def pay_repeat_counters(game, p, eff, target, item):
    """\"When you pay this cost one or more times, put that many N counters on ~\" (the
    Adversary cycle's counters, valor or +1/+1, land with the payments)."""
    from .engine.state import Permanent
    src = item.source if item is not None else None
    n = getattr(item, "pay_repeat", 0) if item is not None else 0
    if isinstance(src, Permanent) and src in p.battlefield and n:
        name = eff.data.get("counter", "+1/+1")
        src.counters[name] = (src.p1 if name == "+1/+1" else src.counters.get(name, 0)) + n
        game.log(f"puts {n} {name} counter(s) on {src.card.name}", p)


def pay_repeat_lands(game, p, eff, target, item):
    """Primal Adversary's rider: the counters for the payments, then that many of the
    controller's lands become N/N creatures with haste permanently (still lands)."""
    from . import continuous
    from .engine.state import Permanent
    src = item.source if item is not None else None
    n = getattr(item, "pay_repeat", 0) if item is not None else 0
    if isinstance(src, Permanent) and src in p.battlefield and n:
        name = eff.data.get("counter", "+1/+1")
        src.counters[name] = (src.p1 if name == "+1/+1" else src.counters.get(name, 0)) + n
        game.log(f"puts {n} {name} counter(s) on {src.card.name}", p)
    power, toughness = eff.data.get("power", 3), eff.data.get("toughness", 3)
    subtype = eff.data.get("subtype", "Wolf")
    keyword = eff.data.get("keyword", "haste")
    for land in [x for x in p.battlefield if x.card.is_land][:max(0, n)]:
        continuous.add(game, land, "add_types", types=frozenset({"Creature"}))
        continuous.add(game, land, "add_subtypes", subtypes=frozenset({subtype}))
        continuous.add(game, land, "set_base", power=power, toughness=toughness)
        continuous.add(game, land, "grant", keyword=keyword)
        game.log(f"{land.card.name} becomes a {power}/{toughness} {subtype} (still a land)", p)


def pay_repeat_tokens(game, p, eff, item):
    """\"... then create twice that many N tokens\" (Tainted Adversary)."""
    from .cards import Effect
    n = getattr(item, "pay_repeat", 0) if item is not None else 0
    n *= 2
    if n:
        game.create_token(p, Effect("token", n, data=dict(eff.data)))
        game.log(f"creates {n} token(s)", p)


def phase_out_count(game, p, eff, target, item):
    """'Put a time counter on ~ for each creature that phased out this way.'"""
    from .engine.state import Permanent
    n = game.__dict__.get("_last_phase_out_count", 0)
    src = item.source if item is not None else target
    if isinstance(src, Permanent) and n:
        src.counters[eff.data.get("counter", "time")] = src.counters.get(eff.data.get("counter", "time"), 0) + n
        game.log(f"puts {n} time counters on {src.card.name}", p)


# A whole-line keyword: "Phasing" parses like flying. (At the bottom: cards/__init__ imports
# this module at its end, and importing it first must not re-enter a partial cards package.)
from .cards.model import KEYWORDS  # noqa: E402
KEYWORDS.add("phasing")
