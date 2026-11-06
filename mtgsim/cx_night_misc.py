"""Small one-sentence effects from the night census.

* "Each player may discard their hand and draw seven cards." (Raphael's Technique, Ruin Grinder, Variable Chaser) is
  the existing ``wheel_all``. The "may" is always taken: a simplification, since an AI holding a strong hand might
  decline."""
from __future__ import annotations


def _wheel_seven(m):
    from .cards.model import Effect
    return Effect("wheel_all", 7)


def _destroy_theirs(m):
    from .cards.model import Effect
    return Effect("destroy", target="artifact_enchantment", filter="opp")


_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4}


def _exile_gy(m):
    from .cards.model import Effect
    return Effect("exile_gy_n", _NUMS[m[1]], target="none")


def _shuffle_gy(m):
    from .cards.model import Effect
    return Effect("shuffle_gy_n", _NUMS[m[1]], target="none")


def _hand_cycle(m):
    from .cards.model import Effect
    return Effect("hand_cycle", target="none", data={"bottom": "bottom" in m[0]})


def _simple(kind, target="none"):
    def build(m):
        from .cards.model import Effect
        return Effect(kind, target=target)
    return build


def _freeze_theirs(m):
    from .cards.model import Effect
    return Effect("skip_untap", target="creature", data={"side": "theirs"})


EFFECT_PATTERNS = [
    (r"target creature an opponent controls doesn't untap during its controller's next untap step", _freeze_theirs),
    (r"target player sacrifices an attacking creature", _simple("edict_attacking", "player")),
    (r"each player sacrifices a nontoken creature", _simple("edict_each_nontoken")),
    (r"target opponent puts a card from their hand on top of their library", _simple("opp_hand_to_top", "player")),
    # Whirlpool Drake: shuffle the hand into the library; Arjun: put it on the bottom. Either way draw that many.
    (r"shuffle the cards from your hand into your library, then draw that many cards", _hand_cycle),
    (r"put the cards in your hand on the bottom of your library in any order, then draw that many cards", _hand_cycle),
    (r"exile up to (one|two|three|four) target cards? from a single graveyard", _exile_gy),
    # "Target player" is always the caster for the AI: shuffling your own graveyard back is the only useful use
    (r"target player shuffles up to (one|two|three|four) target cards from their graveyard into their library",
     _shuffle_gy),
    # Aberrant, Scion of Calamity, Sunder Shaman: "that player" is the player the creature just damaged, the opponent
    # in a two-player game, so this is the plain "destroy target artifact or enchantment" aimed at the opponent.
    (r"destroy target artifact or enchantment that player controls", _destroy_theirs),
    (r"each player may discard their hand and draw seven cards", _wheel_seven),
]


def damage_floor(game, player, amount: int) -> int:
    """Ali from Cairo: damage that would reduce your life total to less than 1 reduces it to 1 instead."""
    from .residual_templates import sources
    if player.life >= 1 and any(x.controller is player for x in sources(game, "life_floor")):
        return min(amount, player.life - 1)
    return amount
