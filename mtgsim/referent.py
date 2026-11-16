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


_STAT = r"(power|toughness|mana value)"
_THAT = r"(?:its|that (?:creature|artifact|enchantment|permanent|spell)'s)"


def _stat_spec(m, first, second):
    """("stat", "prev", stat) for the object the effect before it targeted, or the sum of two of its stats."""
    a = ("stat", "prev", m[first].lower())
    return a if not m[second] else ("arith", a, "+", ("stat", "prev", m[second].lower()))


def _controller_amount(m):
    """"Its controller gains / loses life (mills cards) equal to its mana value / power plus its toughness"
    (Crumble, Illumination, Phthisis, Grisly Spectacle): the object the previous effect targeted, read as it was
    (last known information after a destroy or a counter), and its controller."""
    from .cards import Effect
    kind = {"gains life": "gain_life", "loses life": "lose_life", "mills cards": "mill"}[m[1].lower()]
    return Effect(kind, 1, target="that_controller", data={"xq": _stat_spec(m, 2, 3)})


def _gain_target_stat(m):
    """"You gain life equal to target creature's power" (Soul's Grace): the creature is a target only for the
    amount; read on resolution (``prev`` is the chosen creature)."""
    from .cards import Effect
    return Effect("gain_life", 1, target="creature", data={"xq": ("stat", "prev", m[1].lower()), "side": "any",
                                                           "ref_amount": True})


EFFECT_PATTERNS = [
    (rf"{_THAT} controller (gains life|loses life|mills cards) equal to {_THAT} {_STAT}(?: plus {_THAT} {_STAT})?",
     _controller_amount),
    (rf"you gain life equal to target creature's {_STAT}", _gain_target_stat),
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
