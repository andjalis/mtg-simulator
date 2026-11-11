"""Referent statistics for follow-up amounts, tokens and temporary base stats."""
import re


_COLOR = "white|blue|black|red|green|colorless"
_TOKEN = rf"create (?:a|an|one) ({_COLOR}) ([A-Z][a-z]+(?: [A-Z][a-z]+)*) creature token"
_TOKEN_STATS = r"with power equal to that creature's power and toughness equal to that creature's toughness"


def _token(m):
    from .cards import Effect
    color = dict(zip("white blue black red green".split(), "WUBRG")).get(m[1].lower())
    return Effect("token", 1, data={"name": m[2], "referent_pt": True,
                                    "colors": frozenset({color}) if color else frozenset()})


EFFECT_PATTERNS = [
    (_TOKEN + " " + _TOKEN_STATS, _token),
    (r"(?:you may have )?~'s base (power|toughness) become(?:s)? equal to that creature's \1 until end of turn",
     lambda m: _base(m[1].lower())),
    (r"(?:you may have )?~'s base power and toughness become equal to that creature's power and toughness until end of turn",
     lambda m: _base("both")),
]
SUBS = [(re.compile(r"(" + _TOKEN + r")\. its power is equal to that creature's power and its toughness is equal to "
                    r"that creature's toughness", re.I), r"\1 " + _TOKEN_STATS)]


def _base(stat):
    from .cards import Effect
    return Effect("set_base_referent", target="self", data={"stat": stat})


def remember_card(item, card):
    """Freeze characteristics before moving a card, including before it becomes a permanent."""
    if item is not None:
        item.referent_card_stats = ({"power": card.power or 0, "toughness": card.toughness or 0,
                                     "mana value": card.cmc} if card is not None else None)


def card_stat(item, stat):
    if item is None:
        return 0
    if hasattr(item, "referent_card_stats"):
        return (item.referent_card_stats or {}).get(stat, 0)
    # Older reveal/dig handlers already retain the revealed card on the stack item.
    card = getattr(item, "moved_card", None) or getattr(item, "link_card", None)
    return (card.cmc if stat == "mana value" else getattr(card, stat, 0) or 0) if card else 0


def permanent(item, prev=None, game=None):
    """A previous target or trigger subject, then the ability's own source, then a reanimated card."""
    from .engine.state import Permanent
    for obj in (prev, getattr(item, "context", None), getattr(item, "source", None)):
        if isinstance(obj, Permanent):
            return obj
    card = getattr(item, "moved_card", None)
    if game is not None and card is not None:
        for pl in game.players:
            for perm in pl.battlefield:
                if perm.card is card:
                    return perm
    return None
