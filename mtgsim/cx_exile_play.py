"""#316: "You may play / cast that card for as long as it remains exiled."

    Exile the top card of your library. You may play that card for as long as it remains exiled.
    ... exile target permanent card from your graveyard. You may play that card for as long as it remains exiled.
    Counter target spell. If that spell is countered this way, exile it instead ... You may play it without
    paying its mana cost for as long as it remains exiled.

The permission belongs to the exact cards the instruction before it put into exile. A ``cx_exile_watch`` effect
placed just before that instruction notes what every exile zone holds, and the
``cx_exile_play`` effect after it grants the permission on those cards by zone reference. A zone reference no
longer finds a card once it leaves exile (a new object), so "for as long as it remains exiled" needs no further
bookkeeping:

- a card in your own exile goes to ``exile_permissions`` (cast, paid or free) and, for "play", also to
  ``p.impulse`` with no end turn (lands);
- a card in another player's exile goes to ``foreign_permissions`` (cast, paid or free); a land there to
  ``p.foreign_lands``, which ``Game.impulse_cards`` and ``Game.play_land`` read;
- "mana of any type can be spent to cast it" makes the permission's cost the mana cost with every pip generic
  (``exile_permissions.alt_cost``), which is what any type of mana can pay;
- "its owner may play it" grants the permission to the card's owner.

Riders this doesn't read ("mana of any type can be spent", "if you control a Kavu", a tax) keep the sentence
unmatched.
"""
from __future__ import annotations

import re

_THEM = r"(?:that card|it|those cards|them|the exiled cards?)"
_ANY = (r"(?:,? and (?:mana of any type can be spent to cast (?:it|that spell|them|those spells)|you may spend mana as "
        r"though it were mana of any color to cast (?:it|that spell|them|those spells)))?")
_RX = re.compile(
    rf"(?:(?P<who>you|its owner) may (?:look at and )?(?P<verb>play|cast) {_THEM}(?P<free> without paying (?:its|their) mana "
    rf"costs?)? for as long as (?:it remains|they remain) exiled(?P<any>{_ANY})"
    rf"|for as long as (?:that card|it|they|those cards) remains? exiled, (?P<who2>you|its owner) may (?P<verb2>play|cast) "
    rf"(?:it|them)(?P<free2> without paying (?:its|their) mana costs?)?(?P<any2>{_ANY}))", re.I)


_WHOSE = {"that player's": "that_player", "target opponent's": "target", "target player's": "target",
          "each opponent's": "opponents", "your": "you", "their": "that_player", "defending player's": "defending"}
_N = r"(?P<n>the top card|the top (?P<k>two|three|four|five) cards)"


def _exile_top(m):
    """The marker sentence SUBS leaves for "(look at the top card of P's library, then) exile it / the top N cards
    of P's library (face down)" before a "remains exiled" permission: a cx_exile_top_of effect."""
    from .cards.model import Effect
    who, n = m[1], int(m[2])
    if who == "target_opp":
        return Effect("cx_exile_top_of", n, target="player", filter="opp", data={"who": "target", "side": "theirs"})
    if who == "target_player":
        return Effect("cx_exile_top_of", n, target="player", data={"who": "target", "side": "theirs"})
    return Effect("cx_exile_top_of", n, data={"who": who})


_W = r"(that player's|target opponent's|target player's|each opponent's|defending player's)"
_CODE = {"that player's": "that_player", "target opponent's": "target_opp", "target player's": "target_player",
         "each opponent's": "opponents", "defending player's": "defending", "that player": "that_player",
         "target opponent": "target_opp"}
_COUNT = {"the top card": 1, "the top two cards": 2, "the top three cards": 3, "the top four cards": 4}


def _sub(m):
    if m.string[:m.start()].count('"') % 2:
        return m[0]             # inside a quoted ability: left as written
    g = m.groupdict()
    whose = (g["w"] or g["w2"] or g["subj"]).lower()
    n = _COUNT[(g["n"] or g["n2"] or "the top card").lower()]
    return f"Cxexiletop {_CODE[whose]} {n}. "


# Only before the permission: other riders after "exile the top card of target opponent's library" ("you may play
# it this turn", "if it's a land card") read state this effect doesn't keep, so that text stays as it was.
_THEN = (r"(?=(?:you may (?:look at and )?(?:play|cast) (?:that card|it|those cards|them)[^.]*? for as long as "
         r"(?:it remains|they remain) exiled|for as long as (?:that card|it|they|those cards) remains? exiled))")
SUBS = [(re.compile(
    rf"(?:look at the top card of (?P<w>{_W[1:-1]}) library, then exile it|exile (?P<n>the top card|the top (?:two|"
    rf"three|four) cards) of (?P<w2>{_W[1:-1]}) library|(?P<subj>that player|target opponent) exiles (?P<n2>the top "
    rf"card|the top (?:two|three|four) cards) of their library)(?: face down)?\. {_THEN}", re.I), _sub)]

EFFECT_PATTERNS = [(r"Cxexiletop (that_player|target_opp|target_player|opponents|defending) (\d)", _exile_top)]

# instructions that put cards into exile (the permission's cards are the ones that really arrive there)
_EXILERS = ("exile_top", "cx_card_move", "counter", "exile_permanent", "opponent_exile", "cx_exile_top_of", "oring")


def _exiles(eff) -> bool:
    if eff.kind == "cx_card_move":
        return eff.data.get("to") == "exile"
    if eff.kind == "counter":
        return bool(eff.data.get("exile"))
    return eff.kind in _EXILERS


def parse_rider(s: str, effects: list) -> bool:
    m = _RX.fullmatch(s.strip().rstrip("."))
    if not m or not effects or not _exiles(effects[-1]) or effects[-1].cond:
        return False
    play = (m["verb"] or m["verb2"]).lower() == "play"
    free = bool(m["free"] or m["free2"])
    owner = (m["who"] or m["who2"]).lower() == "its owner"
    any_type = bool(m["any"] or m["any2"])
    if free and any_type:
        return False
    base = effects[-1]
    data = {"play": play, "free": "any" if any_type else free, "owner": owner}
    effects[-1:] = [_effect("cx_exile_watch"), base, _effect("cx_exile_play", data)]
    return True


def _effect(kind, data=None):
    from .cards.model import Effect
    return Effect(kind, data=dict(data or {}))


def _exiled(game) -> set:
    return {(id(pl.exile), getattr(c, "physical_id", id(c)), getattr(c, "generation", 0))
            for pl in game.players for c in pl.exile}


def start_watch(game, item):
    """Remember what is in every exile zone now; ``grant`` takes the cards that arrived since."""
    item.cx_exile_watch = _exiled(game)


def grant(game, p, eff, item):
    before = getattr(item, "cx_exile_watch", None)
    if before is None:
        return
    item.cx_exile_watch = None
    seen = [c for pl in game.players for c in pl.exile
            if (id(pl.exile), getattr(c, "physical_id", id(c)), getattr(c, "generation", 0)) not in before]
    for card in seen:
        zone = getattr(card, "zone", None)
        if zone is None or getattr(zone, "name", "") != "exile" or card not in zone:
            continue
        ref = zone.reference(card)
        who = card.owner if eff.data.get("owner") and card.owner is not None else p   # "its owner may play it"
        if card.is_land and eff.data["play"] and zone is not who.exile:
            if not hasattr(who, "foreign_lands"):
                who.foreign_lands = []
            who.foreign_lands.append((zone, ref))          # engine.play: a land from another player's exile
        elif zone is who.exile:
            if not card.is_land:
                if not hasattr(who, "exile_cast_permissions"):
                    who.exile_cast_permissions = []
                who.exile_cast_permissions.append((ref, eff.data["free"]))
            elif eff.data["play"]:
                who.impulse.append((card, 10 ** 9))       # no end turn: until it leaves exile
        elif not card.is_land:
            if not hasattr(who, "foreign_permissions"):
                who.foreign_permissions = []
            who.foreign_permissions.append((zone, ref, eff.data["free"]))
        game.log(f"may {'play' if eff.data['play'] else 'cast'} {card.name} while it remains exiled", who)


def foreign_lands(p) -> list:
    """The lands p may play from another player's exile, still there as the same object (expired ones dropped)."""
    alive = [(zone, ref) for zone, ref in getattr(p, "foreign_lands", ()) if ref.find(zone) is not None]
    if alive or getattr(p, "foreign_lands", None):
        p.foreign_lands = alive
    return [ref.find(zone) for zone, ref in alive]


def foreign_zone(p, card):
    """The exile zone of another player that holds ``card`` as one of p's playable lands, or None."""
    for zone, ref in getattr(p, "foreign_lands", ()):
        found = ref.find(zone)
        if found is not None and found is card:
            return zone
    return None


def exile_top_of(game, p, eff, item, prev, target):
    """Exile the top N cards of each named player's library (the cards stay their owner's)."""
    from .cx_grammar import players
    for pl in players(game, p, eff.data["who"], item, prev, target):
        for _ in range(min(eff.amount, len(pl.library))):
            game.move_card(pl.library[-1], pl.library, pl.exile, reason="exile")
        game.log(f"exiles the top {eff.amount} card(s) of {pl.name}'s library", p)
