"""Library search: "search your library for up to two basic land cards, put them onto the battlefield tapped,
then shuffle", "... reveal it, put it into your hand", "... then shuffle and put that card on top", and
"Its controller may search their library for a basic land card, put it onto the battlefield, then shuffle."

One effect, ``search``: data what (a card_matches description), n (cards), dest (hand, battlefield, top) and
tapped. The AI takes the best match (engine.choose_tutor) and always searches when it may.
"""
from __future__ import annotations


KINDS = {"search"}
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4}

_SEARCH = (r"(?P<who>you may |its controller may |that player may )?search (?:your|their) library for "
           r"(?P<n>an? |up to (?P<up>one|two|three|four) )(?P<what>[\w ,'/-]+?) cards?"
           r"(?:,? (?:and )?reveal (?:it|them|that card))?"
           r"(?:,? put (?:it|them|that card) (?P<dest>into your hand|onto the battlefield(?P<tapped> tapped)?)"
           r",? then shuffle|,? then shuffle and put (?:that card|it) on top(?: of your library)?)")

EFFECT_PATTERNS = [
    (_SEARCH, lambda m: _search(m)),
    (r"if you search your library this way, shuffle", lambda m: []),
]


def _search(m):
    from .cards import Effect
    dest = "top" if not m["dest"] else "hand" if m["dest"].startswith("into") else "battlefield"
    theirs = (m["who"] or "").startswith(("its", "that"))
    return Effect("search", target="that_controller" if theirs else "none",
                  data={"what": f"a {m['what']} card", "n": _NUM.get(m["up"], 1), "dest": dest,
                        "tapped": bool(m["tapped"])})


def resolve(game, p, eff, target, item):
    from .engine import Player, card_matches, choose_tutor
    d = eff.data
    who = target if eff.target == "that_controller" and isinstance(target, Player) else p
    found = []
    for _ in range(d["n"]):
        cands = [c for c in who.library if card_matches(c, d["what"])]
        if not cands:
            break
        card = choose_tutor(game, who, cands)
        who.library.remove(card)
        found.append(card)
        game.log(f"searches for {card.name}", who)
    who.library.shuffle(game.rng)
    for card in found:
        if d["dest"] == "hand":
            who.hand.append(card)
        elif d["dest"] == "battlefield":
            perm = game.enter_battlefield(who, card)
            perm.tapped = d["tapped"] or perm.tapped
        else:
            who.library.append(card)      # the top of the library is the end of the list
