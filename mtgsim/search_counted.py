"""Counted library searches with a player scope and a destination plan (#339).

One sentence = who searches + how many + which cards + where they go + when the library is shuffled:

    Search your library for three cards, put them into your hand, then shuffle.          (Behold the Beyond)
    Search your library for up to three creature cards, put them into your graveyard, then shuffle.
    Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield
        tapped and the other into your hand, then shuffle.                                 (Cultivate)
    Search your library for a card, then shuffle and put that card on top.               (Vampiric Tutor)
    Each player searches their library for up to two basic land cards, puts them onto the battlefield,
        then shuffles.                                                                     (Avatar of Growth)
    Target player searches their library for a basic land card, puts it onto the battlefield tapped,
        then shuffles.                                                                     (Fertilid)

The sentence is read in parts and refused (NO_MATCH, the sentence stays ignored) unless every part is
understood:

- subject: you (none), "target player" (the default AI picks a side: data["side"]), "each player", "each
  opponent", "its controller" / "that player" / "that creature's controller" (target that_controller);
  an optional "may" (the searcher always searches: hidden-zone searches may fail to find anyway);
- quantity: "a"/"an", a number, "up to N", "X" / "up to X" (data["x_count"]: the spell's or ability's X,
  or the X its permanent entered with), "any number of";
  ", where X is ..." sets data["xq"] (amount 1, which Game.resolve scales): at the end of the sentence
  through the generic wrapper in cards.parse, in the middle ("up to X basic land cards, where X is ...,
  put them ...") here;
- filter: a noun phrase card_matches understands, validated word by word (unknown words refuse the
  sentence rather than match nothing); alternatives ("instant or sorcery", "Plains, Island, ... or Forest",
  "basic land cards and/or Gate cards") become card_matches alternatives; suffixes "with mana value N or
  less/greater", "with mana value X or less", "named ~";
- plan: "put it/them into your hand / graveyard", "onto the battlefield [tapped]", "exile it/them",
  "put one onto the battlefield tapped and the other into your hand", or "then shuffle and put that card /
  those cards on top [in any order]"; "reveal ..." is information only;
- shuffle: after the move ("then shuffle", or a following "Then shuffle." sentence, which parses to
  nothing) or before it (the top-of-library plan).

Effect ``search_plan``: amount = the count, data what (card_matches description), searcher (you / target /
that / each / each_opp), upto, all ("any number of"), plan [[dest, count or None (the rest), tapped]],
shuffle ("after" / "before"), x_count, mv_x ("less"/"greater": mana value compared with the spell's X).
Each searching player searches their own library; the picks are physical cards removed from it, so none is
duplicated or lost.
"""
from __future__ import annotations

import re

KINDS = {"search_plan"}

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10}
_N = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)"

_SUBJECTS = {
    "": "you", "you": "you", "target player": "target", "each player": "each", "each opponent": "each_opp",
    "its controller": "that", "that player": "that", "that creature's controller": "that",
    "its owner": "that",
}
_SUBJ = r"(?:target player|each player|each opponent|its controller|that player|that creature's controller|its owner)"

_SENTENCE = re.compile(
    rf"(?:(?P<subj>{_SUBJ}) )?(?P<may>may )?search(?:es)? (?P<lib>your|their) library(?P<gy> and(?:/or)? graveyard)? for (?P<rest>.+)", re.I)

_TYPES = {"creature", "land", "artifact", "enchantment", "planeswalker", "instant", "sorcery", "battle"}
_COLORS = {"white", "blue", "black", "red", "green"}
_ADJ = {"basic", "nonbasic", "snow", "legendary", "permanent", "historic", "multicolored", "colorless"} | \
    _COLORS | {"non" + c for c in _COLORS} | {"non" + t for t in _TYPES}

_PRONOUN = r"(?:it|them|that card|those cards|the card|the cards)"
_DEST = (r"(?P<where>into (?:your|their) (?P<zone>hand or graveyard|hand|graveyard)|"
         r"onto the battlefield(?P<tapped> tapped)?"
         r"(?: with (?P<ctr>an additional|a|one|two|three|four|five) \+1/\+1 counters? on it)?)")


def _quantity(text):
    """(count, upto, all, x, rest) for the quantity at the start of text, or None."""
    m = re.match(rf"(?:(an?)|up to ({_N}|x)|({_N}|x)|(any number of)) (.+)", text, re.I)
    if not m:
        return None
    if m[1]:
        return 1, False, False, False, m[5]
    if m[4]:
        return 0, False, True, False, m[5]
    word = (m[2] or m[3]).lower()
    if word == "x":
        return 0, bool(m[2]), False, True, m[5]
    n = _NUM.get(word) or int(word)
    return n, bool(m[2]), False, False, m[5]


def _alternative(words):
    """One card_matches alternative ("basic land", "Dragon creature", "nonland") or None."""
    out, types = [], 0
    for w in words:
        lw = w.lower()
        if lw in _TYPES:
            types += 1
            out.append(lw)
        elif lw in _ADJ:
            out.append(lw)
        elif re.fullmatch(r"(?:non-)?[A-Z][a-z'-]+", w):   # a subtype (Goblin, Forest, Aura, Gate) or non-Human
            out.append(w)
        else:
            return None
    if not out or types > 1:      # card_matches reads two type words as either type: refuse
        return None
    return " ".join(out)


_SUFFIXES = (
    (r" (?:with|that (?:each )?have) different names", "distinct"),     # Shared Summons, Tiamat
    (r" not named ~", "not_self"),                                          # Tiamat
    (r" that each have mana value (\d+|x)", "mv_each"),                    # Uncage the Menagerie
)


def _filter(text):
    named = re.fullmatch(r"(.+?) with the same name as (target .+)", text, re.I)
    if named:          # "a card with the same name as target nontoken creature" (Mask of the Mimic)
        out = _filter(named[1])
        if out is None or out[1] or out[2]:
            return None
        return out[0], None, {"name_target": named[2]}
    return _filter_plain(text)


def _filter_plain(text):
    """(card_matches description, mv_x, extras) for a noun phrase like "basic land cards", or None. extras:
    distinct (different names), not_self (not named ~), mv_x "equal" (each has mana value X)."""
    mv_x = None
    suffix = ""
    extras = {}
    stripped = True
    while stripped:          # trailing qualifiers, in any order ("... not named ~ that each have different names")
        stripped = False
        for rx, key in _SUFFIXES:
            m = re.search(rx + "$", text, re.I)
            if m and key not in extras:
                extras[key] = m[1].lower() if m.groups() else True
                text, stripped = text[:m.start()], True
    if "mv_each" in extras:
        v = extras.pop("mv_each")
        if v == "x":
            mv_x = "equal"
        else:
            suffix = f" with mana value {v}"
    m = re.fullmatch(r"(.+?) cards? with mana value (equal to|less than or equal to|less than|greater than) (.+)",
                     text, re.I)
    if m and not mv_x and not suffix:     # "equal to 1 plus the sacrificed creature's mana value" (Birthing Pod)
        from .cards.clauses import _xq
        spec = _xq(m[3])
        if spec is None:
            return None
        extras["mv_q"] = (m[2].lower(), spec)
        text = m[1] + " card"
    m = re.fullmatch(r"(.+?) cards? with mana value (\d+|x) or (less|greater)", text, re.I)
    if m:
        if mv_x or suffix or "mv_q" in extras:
            return None
        if m[2].lower() == "x":
            mv_x = m[3].lower()
        else:
            suffix = f" with mana value {m[2]} or {m[3].lower()}"
        text = m[1] + " card"
    named = re.fullmatch(r"(?:(.+?) cards? or an? )?cards? named (~|[A-Z][\w',-]*(?: [\w',-]+)*)", text)
    if named:
        if extras or suffix or mv_x or (named[2] != "~" and ("~" in named[2] or " or " in named[2])):
            return None      # "named ~'s Chosen" would read the resolving card's name; "X or Y" is two names
        desc = f"a card named {named[2]}"
        if named[1]:         # "a basic land card or a card named Starship Enterprise"
            other = _filter(named[1] + " card")
            if other is None or other[1] or other[2]:
                return None
            desc = f"{other[0]} or {desc}"
        return desc, None, {}
    m = re.fullmatch(r"(.*?) ?cards?", text, re.I)
    if not m:
        return None
    body = m[1]
    if not body:
        return "a card" + suffix, mv_x, extras
    # "basic land cards and/or Gate cards": an inner "cards" separates two alternatives
    body = re.sub(r" cards? (?=(?:and/or|or) )", " ", body, flags=re.I)
    pieces = [p for p in re.split(r",? (?:and/or|or) |, ", body, flags=re.I) if p]
    alts = []
    for piece in pieces:
        alt = _alternative(piece.split())
        if alt is None:
            return None
        alts.append(alt)
    return " or ".join(f"{'an' if a[0] in 'aeiou' else 'a'} {a} card{suffix}" for a in alts), mv_x, extras


def _plan(tail, single):
    """(plan, shuffle) for the steps after the filter ("put them into your hand, then shuffle"), or None."""
    t = tail.rstrip().rstrip(".")
    t = re.sub(rf"^(?:,|,? and) reveals? (?:{_PRONOUN}|those cards)", "", t, flags=re.I)
    m = re.fullmatch(rf"(?:,|,? and) (?:then )?puts? {_PRONOUN} {_DEST}(?P<shuffle>,? (?:and )?then shuffles?)?",
                     t, re.I)
    if m:
        dest = "battlefield" if m["where"].lower().startswith("onto") else m["zone"].lower().replace(" or ", "_or_")
        if m["ctr"]:         # "with an additional +1/+1 counter on it" (Neoform): entry counters
            n = 1 if m["ctr"].lower() in ("an additional", "a") else _NUM[m["ctr"].lower()]
            return [[dest, None, bool(m["tapped"]), n]], "after" if m["shuffle"] else ""
        return [[dest, None, bool(m["tapped"])]], "after" if m["shuffle"] else ""
    m = re.fullmatch(rf"(?:,|,? and) (?:then )?puts? {_PRONOUN} onto the battlefield(?P<tapped> tapped)? if "
                     r"(?:it's an? (?P<type>[a-z]+) card|its mana value is (?P<mv>\d+) or less) and into your hand "
                     r"otherwise(?P<shuffle>,? then shuffle)", t, re.I)
    if m and single:          # Archdruid's Charm, Guidelight Pathmaker: where it goes depends on the card found
        cond = {"type": m["type"].lower()} if m["type"] else {"mv_max": int(m["mv"])}
        if m["type"] and m["type"].lower() not in _TYPES:
            return None
        return [["bf_if", None, bool(m["tapped"]), 0, cond]], "after"
    m = re.fullmatch(rf"(?:,|,? and) (?:then )?exiles? {_PRONOUN}(?P<shuffle>,? (?:and )?then shuffles?)?", t, re.I)
    if m:
        return [["exile", None, False]], "after" if m["shuffle"] else ""
    split_dest = r"(into (?:your|their) hand|into (?:your|their) graveyard|onto the battlefield( tapped)?)"
    m = re.fullmatch(rf"(?:,|,? and) puts? (one|two)(?: of them)? {split_dest} and the (?:other|rest) "
                     rf"(into (?:your|their) hand|into (?:your|their) graveyard)(?P<shuffle>,? (?:and )?then shuffles?)?",
                     t, re.I)
    if m and not single:      # "put one into your hand and the other into your graveyard" (Fork in the Road)
        def dest(text):
            return "battlefield" if text.lower().startswith("onto") else text.lower().rsplit(" ", 1)[1]
        first, other = dest(m[2]), dest(m[4])
        if first == other:
            return None
        return [[first, _NUM[m[1].lower()], bool(m[3])], [other, None, False]], "after" if m["shuffle"] else ""
    m = re.fullmatch(rf",? (?:and )?then shuffles? and puts? {_PRONOUN} on top(?: of (?:your|their) library)?"
                     rf"(?P<order> in any order)?", t, re.I)
    if m:
        return [["top", None, False]], "before"
    return None


def parse(text):
    """The search_plan Effect for one sentence, or None."""
    from .cards import Effect
    m = _SENTENCE.fullmatch(text.strip().rstrip("."))
    if not m:
        return None
    subj = (m["subj"] or "").lower()
    searcher = _SUBJECTS[subj]
    if (m["lib"].lower() == "your") != (searcher == "you"):
        return None
    if searcher == "you" and m["may"]:
        return None          # "you may search" is the generic "you may" wrapper's
    rest, xq = m["rest"], None
    mid = re.search(r", where X is ([^,]+)(?=,)", rest, re.I)
    if mid:        # "for up to X basic land cards, where X is the number of lands you control, put them ..."
        from .cards.clauses import _xq
        xq = _xq(mid[1])
        if not xq:
            return None
        rest = rest[:mid.start()] + rest[mid.end():]
    split = re.match(r"(.+?)(?=(?:,|,? and) (?:reveals?|puts?|exiles?|then)\b)(.+)", rest, re.I)
    if not split:
        return None
    that_many = re.fullmatch(r"(up to )?(that many|that-many-sacrificed) (.+)", split[1], re.I)
    if that_many:
        # "up to that many land cards": the amount of the event that triggered it (a trigger whose event carries
        # one, cx_tokens), or the permanents just sacrificed by "Sacrifice any number of ..." (SUBS below);
        # any other antecedent ("exile all attacking creatures ... that many") is refused
        from . import cx_tokens
        if that_many[2].lower() == "that many" and not cx_tokens._that_many_ok:
            return None
        q = (0, bool(that_many[1]), False, False, that_many[3])
    else:
        q = _quantity(split[1])
    if q is None:
        return None
    count, upto, every, x, noun = q
    what = _filter(noun)
    if what is None:
        return None
    desc, mv_x, extras = what
    single = count == 1 and not upto and not every and not x
    planned = _plan(split[2], single)
    if planned is None:
        return None
    plan, shuffle = planned
    shuffle = shuffle or "after"     # "... onto the battlefield. Then shuffle." (the next sentence is a no-op)
    if every and plan[0][0] == "exile":
        return None          # "exile any number of": which cards is a real choice the AI doesn't model
    data = {"what": desc, "searcher": searcher, "upto": upto, "all": every, "plan": plan, "shuffle": shuffle}
    if m["gy"]:
        if plan[0][0] in ("top", "exile") or len(plan) > 1:
            return None      # these plans are written for the library only
        data["graveyard"] = True     # the graveyard too; the library is shuffled only if it was searched
    if xq:
        if not x or mv_x:
            return None      # the where-X is the count; "mana value X" would read the spell's X instead
        count, data["xq"] = 1, xq          # Game.resolve multiplies amount by the quantity
    elif x:
        data["x_count"] = True     # not data["x"]: Game.resolve reads that from the stack item only
    if mv_x:
        data["mv_x"] = mv_x
    if that_many:
        if xq or x or mv_x:
            return None
        data["that_much"] = True     # amount: the event's (Game._that_much) or the count sacrificed (Game.resolve)
    data.update(extras)
    target = "none"
    if searcher == "target":
        target, data["side"] = "player", "mine"
    elif searcher == "that":
        target = "that_controller"
    if data.get("name_target"):
        from .permanent_templates import subject
        subj = subject(data.pop("name_target"))
        if subj is None or subj[0] != "permanent" or searcher != "you" or subj[1].get("optional_target"):
            return None
        target = "permanent"
        data.update(subj[1], name_as_target=True)
    return Effect("search_plan", count, target=target, data=data)


def _build(m):
    from .cards import NO_MATCH
    eff = parse(m[0])
    return NO_MATCH if eff is None else eff


# "Sacrifice any number of lands[ you control]. Search your library for up to that many land cards, ..." (Scapeshift,
# Genesis Device): "that many" is the count just sacrificed; marked so the search sentence knows its antecedent.
SUBS = [
    # "Search your library for X and reveal it. Put it onto the battlefield [tapped] if it's a land card / if its mana
    # value is N or less. Otherwise, put it into your hand. Then shuffle. / If you search your library this way,
    # shuffle." (Archdruid's Charm, Guidelight Pathmaker): one sentence for parse
    (re.compile(r"\b(search your library for an? [^.]+?) and reveal it\. put it (onto the battlefield(?: tapped)?) "
                r"(if it's an? [a-z]+ card|if its mana value is \d+ or less)\. otherwise, put it into your hand\. "
                r"(?:then shuffle|if you search your library this way, shuffle)\.", re.I),
     lambda m: f"{m[1]}, put it {m[2]} {m[3]} and into your hand otherwise, then shuffle."),
    # "Search your library for up to two X cards [and reveal them]. Put one into your hand and the other into your
    # graveyard[, then shuffle]." (Fork in the Road, Final Parting, Flourishing Bloom-Kin): one sentence for parse
    (re.compile(r"\b(search your library for (?:up to )?two [^.]+?)(?: and reveal them)?\. "
                r"(put one(?: of them)? (?:into your hand|into your graveyard|onto the battlefield(?: tapped)?) and the "
                r"other (?:into your hand|into your graveyard))", re.I),
     lambda m: m[1] + ", " + m[2][0].lower() + m[2][1:]),
    (re.compile(r"\b(sacrifice any number of [a-z ,/]+?)(?:\.|, then) search your library for up to that many\b", re.I),
     lambda m: m[1] + ". Search your library for up to that-many-sacrificed"),
]

EFFECT_PATTERNS = [
    (r"(?:(?:target player|each player|each opponent|its controller|that player|that creature's controller|"
     r"its owner) )?(?:may )?search(?:es)? (?:your|their) library(?: and(?:/or)? graveyard)? for .+", _build),
]


# ---- resolution ---------------------------------------------------------------------------------

def _searchers(game, p, eff, target, item):
    who = eff.data.get("searcher", "you")
    if who == "you":
        return [p]
    if who in ("target", "that"):
        from .engine import Permanent, Player
        if isinstance(target, Player):
            return [target]
        ctx = getattr(item, "context", None)
        if who == "that" and isinstance(ctx, Permanent):
            return [ctx.controller]   # "When enchanted creature dies, that creature's controller ..." (the dead creature)
        return []
    others = [x for x in game.players if x is not p]
    return [p] + others if who == "each" else others


def _rank_lands(game, me, cands):
    """Lands first by the colour the player needs most (policy.choose_basic's measure)."""
    from .engine.policy import COLORS
    have = {col: sum(col in x.card.produces for x in me.battlefield if x.card.is_land) for col in COLORS}
    need = {col: sum(c.mana_cost.get(col, 0) for c in me.hand + me.library) for col in COLORS}
    return max(cands, key=lambda c: max((need[col] / (1 + have[col]) for col in c.produces), default=0))


def _pick(game, me, cands, dest):
    """The next card the searching player takes for a destination."""
    from .engine.policy import _wants_land, choose_tutor
    if dest == "graveyard":        # binning: the biggest creature (reanimation), else the biggest card
        return max(cands, key=lambda c: (c.is_creature, c.cmc))
    if dest == "exile":            # thinning: what this player wants least
        want = _wants_land(game, me)
        return max(cands, key=lambda c: (c.is_land != want, -c.cmc if want else c.cmc))
    if all(c.is_land for c in cands):
        return _rank_lands(game, me, cands)
    return choose_tutor(game, me, cands)


def resolve(game, p, eff, target, item):
    from .engine import card_matches
    d = eff.data
    ref = (item.card or getattr(item.source, "card", None)) if item is not None else None
    # X: the spell's or ability's X, or the X a permanent entered with (its enters trigger: Sporocyst, Rocco)
    x = getattr(item, "x", 0) or getattr(getattr(item, "source", None), "entered_x", 0) or 0

    # "mana value equal to 1 plus the sacrificed creature's mana value": the quantity, read once before searching
    mv_q = (d["mv_q"][0], game.x_quantity(p, d["mv_q"][1], item, None)) if d.get("mv_q") else None

    from .engine.state import Permanent
    if d.get("name_as_target") and not isinstance(target, Permanent):
        return                       # its only target is gone (the spell fizzles before this)
    named = target.card.name if d.get("name_as_target") else None

    def fits(c):
        if not card_matches(c, d["what"], ref=ref):
            return False
        if named is not None and c.name != named:
            return False
        if d.get("mv_x") == "less":
            return c.cmc <= x
        if d.get("mv_x") == "greater":
            return c.cmc >= x
        if d.get("mv_x") == "equal":
            return c.cmc == x
        if d.get("not_self") and ref is not None and c.name == ref.name:
            return False
        if mv_q is not None:
            op, n = mv_q
            return c.cmc == n if op == "equal to" else c.cmc < n if op == "less than" else \
                c.cmc > n if op == "greater than" else c.cmc <= n
        return True

    for who in _searchers(game, p, eff, target, item):
        lib = who.library
        yard = who.graveyard if d.get("graveyard") else None     # "search your library and/or graveyard"
        limit = len(lib) + len(yard or ()) if d.get("all") else x if d.get("x_count") else max(0, eff.amount)
        plan = d["plan"]
        moves = []           # (card, dest, tapped, +1/+1 counters)
        searched = yard is None      # the library is searched (and shuffled) unless the graveyard alone sufficed
        for dest, n, tapped, *more in plan:
            counters = more[0] if more else 0
            if dest == "bf_if":       # its own destination once found (resolved below); picked like a tutor
                dest = ("bf_if", more[1])
            room = limit - len(moves) if n is None else min(n, limit - len(moves))
            for _ in range(max(0, room)):
                # graveyard copies first: on a tie the pick (max) keeps the first, so the library stays unsearched
                cands = [c for c in yard or () if fits(c)] + [c for c in lib if fits(c)]
                if d.get("distinct"):          # "with different names": none named like a card already taken
                    taken = {move[0].name for move in moves}
                    cands = [c for c in cands if c.name not in taken]
                if not cands:
                    searched = True       # came up short: the library was looked through too
                    break
                card = _pick(game, who, cands, dest if dest not in ("top",) and isinstance(dest, str) else "hand")
                if yard is not None and card in yard:     # the public copy first: no library search needed
                    yard.remove(card)
                    game.log(f"takes {card.name} from their graveyard", who)
                else:
                    lib.remove(card)
                    searched = True
                    game.log(f"searches for {card.name}", who)
                moves.append((card, dest, tapped, counters))
        if d.get("shuffle") == "before":
            lib.shuffle(game.rng)
        for card, dest, tapped, counters in reversed(moves) if plan[0][0] == "top" else moves:
            if isinstance(dest, tuple):          # ("bf_if", condition): the battlefield if the card meets it
                cond = dest[1]
                ok = (cond["type"].title() in card.types) if "type" in cond else card.cmc <= cond["mv_max"]
                dest = "battlefield" if ok and card.is_permanent else "hand"
            if dest in ("hand", "hand_or_graveyard"):    # "into your hand or graveyard": the AI keeps it
                who.hand.append(card)
            elif dest == "graveyard":
                who.graveyard.append(card)
                game.log(f"puts {card.name} into their graveyard", who)
            elif dest == "exile":
                who.exile.append(card)
                game.log(f"exiles {card.name}", who)
            elif dest == "top":
                lib.append(card)        # the top of the library is the end of the list; the first pick ends on top
            else:
                game.enter_battlefield(who, card, tapped=tapped, counters={"+1/+1": counters} if counters else None)
        if not searched:
            continue
        if d.get("shuffle") == "after":
            lib.shuffle(game.rng)
        game.library_searched(who)


def _mv_x_ok(d, c) -> bool:
    """A card's mana value against the X the AI is judging an activation with (data["x_now"], set by
    policy.ability_worth); without a chosen X the comparison isn't made."""
    x, op = d.get("x_now"), d.get("mv_x")
    if x is None or not op:
        return True
    return c.cmc <= x if op == "less" else c.cmc >= x if op == "greater" else c.cmc == x


def value(game, me, eff):
    """The default AI's worth of a search_plan it controls (ai._extra_value): about 1.5 per card found for
    the hand or the battlefield, less for the top, the graveyard and exile; what opponents find counts
    against it ("each player searches": worth casting only when we find more)."""
    from .engine import card_matches
    d = eff.data
    n = 2 if d.get("all") or d.get("x_count") else max(1, eff.amount)
    worth = {"hand": 1.5, "hand_or_graveyard": 1.5, "battlefield": 1.5, "bf_if": 1.5, "top": 1.0, "graveyard": 0.3, "exile": 0.1}

    def found(player):
        pool = list(player.library) + (list(player.graveyard) if d.get("graveyard") else [])
        k = min(n, sum(card_matches(c, d["what"]) and _mv_x_ok(d, c) for c in pool))
        v = 0.0
        for dest, count, *_ in d["plan"]:
            take = k if count is None else min(count, k)
            v += worth.get(dest, 0.5) * take
            k -= take
        return v

    who = d.get("searcher", "you")
    opps = [x for x in game.players if x is not me]
    if who == "each_opp":
        return -sum(found(x) for x in opps)
    if who == "each":
        return found(me) - sum(found(x) for x in opps)
    return found(me)


def sac_upgrade(game, me, perm, effects, victim):
    """Whether sacrificing victim to pay for these effects searches up something better (Birthing Pod: "mana
    value equal to 1 plus the sacrificed creature's mana value"), judged with victim's stats as the sacrifice;
    or, for "mana value X or less" (Fiend Artisan), with the X the AI chose (data["x_now"])."""
    from types import SimpleNamespace
    from .engine import card_matches
    from .engine.policy import perm_value
    from .ai import card_value
    for e in effects:
        d = e.data
        if e.kind != "search_plan" or not (d.get("mv_q") or d.get("x_now") is not None) or \
                d.get("searcher", "you") != "you" or d["plan"][0][0] != "battlefield":
            continue
        if not d.get("mv_q"):
            found = [c for c in me.library if card_matches(c, d["what"]) and _mv_x_ok(d, c)]
            if found and max(card_value(c) for c in found) > perm_value(victim):
                return True
            continue
        item = SimpleNamespace(source=perm, card=None, x=0, context=None, this_way=None,
                               gate_sac_stats=(victim.power, victim.toughness, victim.card.cmc))
        op, n = d["mv_q"][0], game.x_quantity(me, d["mv_q"][1], item, None)
        ok = {"equal to": lambda v: v == n, "less than": lambda v: v < n, "greater than": lambda v: v > n}.get(
            op, lambda v: v <= n)
        found = [c for c in me.library if card_matches(c, d["what"]) and ok(c.cmc)]
        if found and max(card_value(c) for c in found) > perm_value(victim):
            return True
    return False


def choose_name_target(game, me, eff):
    """The default AI's target for "a card with the same name as target creature": the legal creature whose name
    most cards in its library share (its own side first on a tie, then the more valuable)."""
    from .engine import card_matches
    from .engine.policy import perm_value
    legal = [x for x in game.legal_targets(me, eff) if hasattr(x, "card")]
    scored = [(sum(c.name == x.card.name and card_matches(c, eff.data["what"]) for c in me.library),
               x.controller is me, perm_value(x), x) for x in legal]
    best = max(scored, key=lambda t: t[:3], default=None)
    return best[3] if best and best[0] > 0 else None

