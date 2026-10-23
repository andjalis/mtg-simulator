"""Effects on every player, and riders on what an effect just tapped.

    Each player sacrifices a creature.          Each player sacrifices two nontoken creatures.   Each player sacrifices a land.
    Target player shuffles their graveyard into their library.        Shuffle your graveyard into your library.
    Target player shuffles up to four target cards from their graveyard into their library.  (the best four)
    Tap up to two target creatures. Those creatures don't untap during their controller's next untap step.
    Tap all creatures target player controls. (Aimed at an opponent.)
    Each player draws two cards.      Defending player gets a poison counter.      Untap up to three lands.
    Each player shuffles their hand and graveyard into their library, then draws seven cards.

"Target player shuffles their graveyard into their library" is aimed at its caster (refilling a library); each player
sacrifices their least valuable permanents of the kind.
"""
from __future__ import annotations

KINDS = {"each_sac", "gy_shuffle", "skip_untap_tapped", "tap_all_opp", "each_draw", "poison", "untap_lands", "wheel"}
_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}
_NUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}


def _effect(kind, amount=1, data=None):
    from .cards import Effect
    return Effect(kind, amount, target="none", data=data or {})


EFFECT_PATTERNS = [
    (r"each player shuffles their hand and graveyard into their library, then draws (seven|three|four|five) cards",
     lambda m: _effect("wheel", {"seven": 7, "three": 3, "four": 4, "five": 5}[m[1].lower()])),
    (r"each player draws (a card|two cards|three cards)", lambda m: _effect("each_draw", _N[m[1].split()[0].lower()])),
    (r"(?:target player|target opponent|defending player|that player|each opponent) gets? (a|two|three) poison counters?",
     lambda m: _effect("poison", _N[m[1].lower()])),
    (r"untap up to (two|three|four|five|six|seven) lands", lambda m: _effect("untap_lands", _NUM[m[1].lower()])),
    (r"each player sacrifices (a|an|one|two|three) (nontoken )?(creature|land)s?(?: of their choice)?",
     lambda m: _effect("each_sac", _N[m[1].lower()], {"kind": m[3].lower(), "nontoken": bool(m[2])})),
    (r"(?:target player|you) shuffles? up to (two|three|four|five) target cards from (?:their|your) graveyard into "
     r"(?:their|your) library", lambda m: _effect("gy_shuffle", data={"up_to": _NUM[m[1].lower()]})),
    (r"(?:target player|each player|you) shuffles? (?:their|your) graveyards? into (?:their|your) librar(?:y|ies)|"
     r"(?:then )?shuffle your graveyard into your library",
     lambda m: _effect("gy_shuffle", data={"each": m[0].lower().startswith("each")})),
    (r"tap all (creatures|nonland permanents) (?:your opponents control|target (?:opponent|player) controls)",
     lambda m: _effect("tap_all_opp", data={"what": m[1].lower()})),
    (r"(?:those creatures|they|those permanents) don't untap during (?:their controllers?'s?|that player's) next untap steps?",
     lambda m: _effect("skip_untap_tapped")),
]


def resolve(game, p, eff, target, item):
    if eff.kind == "each_sac":
        from .engine import perm_value
        for pl in game.players:
            pool = [x for x in pl.battlefield if (x.is_creature if eff.data["kind"] == "creature" else x.card.is_land)
                    and not (eff.data.get("nontoken") and x.card.is_token)]
            for x in sorted(pool, key=lambda x: (not x.tapped, perm_value(x)))[:eff.amount]:
                game.sacrifice(x)
    elif eff.kind == "gy_shuffle":
        for pl in (game.players if eff.data.get("each") else [p]):
            if pl.graveyard:
                cards = sorted(pl.graveyard, key=lambda c: -c.cmc)[:eff.data["up_to"]] if eff.data.get("up_to") \
                    else list(pl.graveyard)
                for c in cards:
                    pl.graveyard.remove(c)
                pl.library.extend(cards)
                pl.library.shuffle(game.rng)
                game.log("shuffles their graveyard into their library", pl)
    elif eff.kind == "tap_all_opp":
        game.tapped_now = [x for x in game.opponent(p).battlefield if not x.tapped
                           and (x.is_creature if eff.data["what"] == "creatures" else not x.card.is_land)]
        for x in game.tapped_now:
            x.tapped = True
    elif eff.kind == "wheel":                    # Timetwister
        for pl in game.players:
            cards = list(pl.hand) + list(pl.graveyard)
            pl.hand.clear()
            pl.graveyard.clear()
            pl.library.extend(cards)
            pl.library.shuffle(game.rng)
        for pl in game.players:
            game.draw(pl, eff.amount)
    elif eff.kind == "each_draw":
        for pl in game.players:
            game.draw(pl, eff.amount)
    elif eff.kind == "poison":
        foe = game.opponent(p)
        foe.counters["poison"] = foe.counters.get("poison", 0) + eff.amount
        game.log(f"{foe} gets {eff.amount} poison", p)
    elif eff.kind == "untap_lands":
        for x in [x for x in p.battlefield if x.card.is_land and x.tapped][:eff.amount]:
            x.tapped = False
    elif eff.kind == "skip_untap_tapped":
        for x in getattr(game, "tapped_now", ()):
            if x in x.controller.battlefield:
                x.skip_untap = max(x.skip_untap, 1)
