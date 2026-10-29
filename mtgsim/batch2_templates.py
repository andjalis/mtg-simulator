"""Small library and hand effects: tucking, second from the top, shuffling a graveyard, wheels, halving life."""

EFFECT_PATTERNS = [
    (r"look at target player's hand", lambda m: _e("peek_hand", target="player")),
    (r"target player shuffles their graveyard into their library", lambda m: _e("shuffle_gy", target="player")),
    (r"put target nonland permanent on top of its owner's library", lambda m: _e("tuck_perm", target="nonland_perm")),
    (r"put target (creature|nonland permanent) into its owner's library second from the top",
     lambda m: _e("tuck_perm", target="creature" if m[1] == "creature" else "nonland_perm", data={"depth": 1})),
    (r"each player discards their hand, then draws (\w+) cards", lambda m: _e("wheel_all", _num(m[1]))),
    (r"each player shuffles their hand and graveyard into their library, then draws (\w+) cards",
     lambda m: _e("wheel_all", _num(m[1]), data={"shuffle_gy": True})),
    (r"(that|target) (?:player|opponent) loses half their life, rounded (up|down)",
     lambda m: _e("lose_half", target="that_player" if m[1] == "that" else "player", data={"up": m[2] == "up"})),
    (r"(each opponent|defending player|target player|target opponent|each player) gets? (a|one|two|three|\d+) poison counters?",
     lambda m: _e("poison", _num(m[2]), target="player" if m[1].startswith("target") else "that_player" if m[1].startswith("def") else "each_opponent" if m[1] == "each opponent" else "each_player")),
    (r"destroy all (non\w+) creatures", lambda m: _e("destroy_group", data={"types": "Creature", "not": m[1][3:].title()})),
    (r"destroy all (plains|islands|swamps|mountains|forests)",
     lambda m: _e("destroy_group", data={"sub": m[1][:-1].title()})),
    (r"double target creature's power until end of turn", lambda m: _e("double_power", target="creature")),
    (r"gain control of target creature an opponent controls until end of turn",
     lambda m: _e("threaten", target="creature", filter="opp", data={"plain": True})),
    (r"each player sacrifices (two|three) creatures", lambda m: _e("edict_each", _num(m[1]))),
    (r"discard your hand", lambda m: _e("discard_hand")),
    (r"target player draws (four|five|six|seven|\d+) cards?", lambda m: _e("draw", _num(m[1]))),
    (r"target (?:player|opponent) discards a card at random", lambda m: _e("discard_random_target", target="player")),
    (r"destroy all nonland permanents", lambda m: _e("destroy_group", data={"not": "Land"})),
    (r"destroy all tapped creatures", lambda m: _e("destroy_group", data={"types": "Creature", "tapped": True})),
    (r"you lose half your life, rounded (up|down)", lambda m: _e("lose_half", data={"up": m[1] == "up", "self": True})),
    (r"target player takes an extra turn after this one", lambda m: _e("extra_turn")),
    (r"look at the top card of target player's library", lambda m: _e("peek_hand", target="player")),
    (r"put target attacking or blocking creature on top of its owner's library",
     lambda m: _e("tuck_perm", target="creature", filter="attacking_blocking")),
    (r"counter target (sorcery|instant|planeswalker|land|enchantment|artifact|creature or planeswalker|"
     r"artifact or enchantment|instant or sorcery) spell",
     lambda m: _e("counter", target="spell", filter="types:" + ",".join(w.title() for w in m[1].split(" or ")))),
    (r"sacrifice (?:it|that creature|that token|them) at the beginning of the next end step", lambda m: _e("sac_at_end", target="prev")),
    (r"return (another|a) (?:([\w ]+?) )?creature you control to its owner's hand",
     lambda m: _e("return_own", data={"kind": "creature", "other": m[1] == "another", "colors": _colors(m[2] or "")})),
    (r"return a permanent you control to its owner's hand", lambda m: _e("return_own", data={"kind": "permanent"})),
]
SUBS = []

_COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _colors(text):
    """'red or green' -> ('R','G'); anything else (a type word) matches every creature."""
    words = [w for w in text.split() if w != "or"]
    return tuple(_COLOR_WORDS[w] for w in words) if words and all(w in _COLOR_WORDS for w in words) else ()


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _num(word):
    from .cards import _num as number
    return number(word)
