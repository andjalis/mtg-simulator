"""Library search: "search your library for up to two basic land cards, put them onto the battlefield tapped,
then shuffle", "... reveal it, put it into your hand", "... then shuffle and put that card on top",
"Its controller may search their library for a basic land card, put it onto the battlefield, then shuffle.",
and the opponent-library shapes rewritten to the SEARCHOPP sentinels: Bribery / Acquire
("... for a creature card and put that card onto the battlefield under your control. Then that
player shuffles."), Sadistic Sacrament ("... for up to three cards and exile them"), Quiet
Speculation ("... cards with flashback and put them into that player's graveyard") and Lost Legacy /
Infinite Obliteration ("choose a card name. Search target player's graveyard, hand, and library
for any number of cards with that name and exile them").

One effect, ``search``: data what (a card_matches description), n (cards; 0 = every card with the
chosen name), dest (hand, battlefield, battlefield_mine, exile, gy, top) and tapped. The AI takes
the best match (engine.choose_tutor) and always searches when it may.
"""
from __future__ import annotations

import re


KINDS = {"search"}
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10}

_SEARCH = (r"(?P<who>you may |its controller may |that player may )?search (?:your|their) library for "
           r"(?P<n>an? |up to (?P<up>one|two|three|four) )(?P<what>[\w ,'/-]+?) cards?"
           r"(?: with mana value (?P<mv>\d+) or (?P<mvdir>less|greater))?"
           r"(?:,? (?:and )?reveal (?:it|them|that card))?"
           r"(?:,? put (?:it|them|that card) (?P<dest>into your hand|onto the battlefield(?P<tapped> tapped)?)"
           r",? then shuffle|,? then shuffle and put (?:that card|it) on top(?: of your library)?)")

def _name_sub(m):
    return f"SEARCHOPP NAME {0 if not m[2] else _NUM.get(m[2], 0)} {m[1] or 'any'}."


def _search_opp(m):
    from .cards import Effect
    dest = {"STEAL": "battlefield_mine", "EXILE": "exile", "GY": "gy", "NAME": "exile"}[m["dest"]]
    what = m["what"].strip()
    if what.endswith("card"):
        what = what[:-5].strip()
    data = {"what": f"a {what} card" if what else "a card", "n": int(m["n"]),
            "dest": dest, "opp_library": True}
    if m["dest"] == "NAME":
        what = "" if what in ("card", "any") else what
        data["what"] = f"a {what} card" if what else "a card"
        data["name_filter"] = what
        data["name"] = True
    return Effect("search", target="player", data=data)


EFFECT_PATTERNS = [
    (_SEARCH, lambda m: _search(m)),
    (r"if you search your library this way, shuffle", lambda m: []),
    (r"SEARCHOPP (?P<dest>STEAL|EXILE|GY|NAME) (?P<n>\d+) (?P<what>[^.]+)", _search_opp),
]

SUBS = [
    # Bribery / Acquire / Eternal Dominion: steal a card from an opponent's library.
    (re.compile(r"search (?:target opponent's|target player's|that player's) library for an? "
                r"([\w ,'/-]+?) card and put (?:that card|it) onto the battlefield under your "
                r"control\.?(?:\s*then (?:that|the) player shuffles?)?", re.I),
     lambda m: f"SEARCHOPP STEAL 1 {m[1]}."),
    # Sadistic Sacrament / Denying Wind: exile cards straight out of an opponent's library.
    (re.compile(r"search (?:target opponent's|target player's) library for (?:up to )?(\w+) cards?"
                r"(?:,| and) exile them(?:[.,]?\s*then (?:that|the) player shuffles?)?", re.I),
     lambda m: f"SEARCHOPP EXILE {_NUM.get(m[1], 1)} card."),
    # Bitter Ordeal: "... for a card and exile it."
    (re.compile(r"search (?:target opponent's|target player's) library for a card and exile it"
                r"(?:[.,]?\s*then (?:that|the) player shuffles?)?", re.I),
     lambda m: "SEARCHOPP EXILE 1 card."),
    # Quiet Speculation: put cards from an opponent's library into their graveyard.
    (re.compile(r"search (?:target opponent's|target player's) library for up to (\w+) cards with "
                r"([\w ,'/-]+?) and put them into that player's graveyard\.?(?:\s*then (?:that|the) "
                r"player shuffles?)?", re.I),
     lambda m: f"SEARCHOPP GY {_NUM.get(m[1], 1)} {m[2]}."),
    # Lost Legacy / Infinite Obliteration: name a card, strip the copies from their zones.
    (re.compile(r"choose an? (nonartifact, nonland|nonland|noncreature, nonland|artifact|creature|"
                r"enchantment|instant or sorcery|planeswalker)? ?card name\. search "
                r"(?:target opponent's|target player's|that player's) graveyard, hand, and library "
                r"for (?:any number of|up to (\w+)|all) cards? with (?:that|the chosen) name and "
                r"exile them(?:\.?\s*then (?:that|the) player shuffles?)?", re.I),
     _name_sub),
]


def _search(m):
    from .cards import Effect
    dest = "top" if not m["dest"] else "hand" if m["dest"].startswith("into") else "battlefield"
    theirs = (m["who"] or "").startswith(("its", "that"))
    what = f"a {m['what']} card"
    if m["mv"]:
        # "a Rebel permanent card with mana value 3 or less": card_matches understands the clause.
        what = f"{what} with mana value {m['mv']} or {m['mvdir']}"
    return Effect("search", target="that_controller" if theirs else "none",
                  data={"what": what, "n": _NUM.get(m["up"], 1), "dest": dest,
                        "tapped": bool(m["tapped"])})


def resolve(game, p, eff, target, item):
    from .engine import Player, card_matches, choose_tutor
    d = eff.data
    if d.get("name"):
        _extract_named(game, p, target if isinstance(target, Player) else game.opponent(p), d)
        return
    who = target if eff.target == "that_controller" and isinstance(target, Player) else p
    searcher = who if eff.target == "that_controller" else p
    lib = who.library
    if eff.target == "player" and isinstance(target, Player):
        lib = target.library                 # p is searching their library, for p

    def _matches(c):
        if d["what"] == "a flashback card":  # Quiet Speculation: by flashback alt-cost
            return any(ac.kind == "flashback" for ac in c.alt_costs)
        return card_matches(c, d["what"])

    found = []
    for _ in range(d["n"]):
        cands = [c for c in lib if _matches(c)]
        if not cands:
            break
        card = choose_tutor(game, searcher, cands)
        lib.remove(card)
        found.append(card)
        game.log(f"searches for {card.name}", searcher)
    lib.shuffle(game.rng)
    game.library_searched(p if lib is not who.library else who)
    for card in found:
        if d["dest"] == "hand":
            who.hand.append(card)
        elif d["dest"] == "battlefield":
            perm = game.enter_battlefield(who, card)
            if perm is not None:
                perm.tapped = d["tapped"] or perm.tapped
        elif d["dest"] == "battlefield_mine":
            game.enter_battlefield(p, card)
            game.log(f"puts {card.name} onto the battlefield", p)
        elif d["dest"] == "exile":
            getattr(card, "owner", target).exile.append(card)
            game.log(f"exiles {card.name}", p)
        elif d["dest"] == "gy":
            getattr(card, "owner", target).graveyard.append(card)
        else:
            who.library.append(card)      # the top of the library is the end of the list


def _extract_named(game, p, victim, d):
    """Lost Legacy: name a card (the AI names the most valuable card in the victim's zones),
    then exile that many copies from their graveyard, hand and library."""
    pool = list(victim.graveyard) + list(victim.hand) + list(victim.library)
    if d.get("name_filter"):
        from types import SimpleNamespace
        from .engine.kinds.cards import _hand_matches
        pool = [c for c in pool if _hand_matches(c, SimpleNamespace(filter=d["name_filter"], data={}))]
    if not pool:
        return

    def value(name):
        cards = [c for c in pool if c.name == name]
        return (sum(c.cmc for c in cards), len(cards))

    name = max({c.name for c in pool}, key=value)
    removed = 0
    for zone in (victim.graveyard, victim.hand, victim.library):
        for card in [c for c in list(zone) if c.name == name]:
            if d["n"] and removed >= d["n"]:
                break
            zone.remove(card)
            victim.exile.append(card)
            removed += 1
    victim.library.shuffle(game.rng)
    game.library_searched(p)
    if removed:
        game.log(f"exiles {removed} card(s) named {name}", p)
