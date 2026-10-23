"""Sentence-level templates: substitutions that rewrite oracle text before matching, trigger templates,
and the clause helpers for "if ~ was bargained" riders, "if <condition>," gates and ", where X is" quantities."""
from __future__ import annotations

import re

from .model import _num
from .patterns import _N_WORDS


# Substitutions below that simplify the card, and the note each one records on it.
_SUB_NOTES = [
    (re.compile(r"target creature or planeswalker you control gains", re.I), "the target is a creature, not a planeswalker"),
    (re.compile(r"return target spell or permanent to its owner's hand", re.I), "returns a nonland permanent, not a spell"),
    (re.compile(r"damage divided as you choose among one or two", re.I), "the divided damage all goes to one target"),
]

_SUBS = [
    (re.compile(r"(?:target opponent reveals their hand\. you choose|look at target opponent's hand\. you may exile) an? "
                r"(nonland|noncreature, nonland|nonartifact, nonland|instant or sorcery) card from it(?:\. exile that card)? "
                r"until ~ leaves the battlefield\.", re.I), lambda m: f"HANDEXILE {m[1].lower()}."),
    (re.compile(r"^(~ gains [a-z]+ until end of turn)\. tap it\.", re.I), r"\1. Tap ~."),
    # Thorin: the Equipment are attached by the same ability, so its rider always follows
    (re.compile(r"when one or more equipment become attached to that creature this way, (that creature deals damage)", re.I),
     r"\1"),
    # The AI never aims its removal at its own creature, so "another" target is any target.
    (re.compile(r"destroy another target (creature or planeswalker|creature|nonland permanent)", re.I), r"destroy target \1"),
    (re.compile(r"return target spell or permanent to its owner's hand", re.I),
     "return target nonland permanent to its owner's hand"),
    # Planeswalkers rarely matter as the target: "creature or planeswalker you control gains ..." is the creature.
    (re.compile(r"target creature or planeswalker you control gains", re.I), "target creature you control gains"),
    # Two players: "for each opponent, tap ... that player controls" is the one opponent.
    (re.compile(r"for each opponent, (tap up to one target creature) that player controls", re.I),
     r"\1 an opponent controls"),
    (re.compile(r"tap up to one target creature\. it loses all abilities for as long as ~ remains on the battlefield\.",
                re.I), lambda m: "TAPSILENCE."),
    (re.compile(r"counter up to one target activated or triggered ability\. if an ability of an artifact, creature, or "
                r"planeswalker is countered this way, that permanent loses all abilities for as long as ~ remains on the "
                r"battlefield\.", re.I), lambda m: "COUNTERABILITY."),
    (re.compile(r"exile (?:another )?target creature you control\. return (?:it|that card) to the battlefield under its "
                r"owner's control at the beginning of the next end step\.", re.I), lambda m: "BLINKEND."),
    (re.compile(r"counter target spell unless its controller pays \{(\d+)\}\. counter that spell unless its controller pays "
                r"\{(\d+)\} instead if ~ was cast using teamwork\.", re.I), lambda m: f"COUNTERTW {m[1]} {m[2]}."),
    (re.compile(r"tap another target nonland permanent\. its activated abilities can't be activated for as long as it "
                r"remains tapped\.", re.I), lambda m: "NETTAP."),
    (re.compile(r"you may discard a card\. if you do, draw (a card|two cards)\.", re.I),
     lambda m: f"OPTCOST discard {_num(m[1].split()[0])}."),
    (re.compile(r"you may sacrifice (another |an? )?(creature or artifact|artifact or creature|artifact|creature|"
                r"enchantment or creature|artifact or creature)\. if you do, draw (a card|two cards)\.", re.I),
     lambda m: f"OPTCOST sac{'other' if (m[1] or '').startswith('another') else ''}:{m[2].replace(' or ', '|')} "
               f"{_num(m[3].split()[0])}."),
    (re.compile(r"you may sacrifice an artifact or discard a card\. if you do, draw a card\.", re.I),
     lambda m: "OPTCOST either 1."),
    (re.compile(r"gain control of target creature until end of turn\. untap that creature\. it gains haste until end "
                r"of turn\.", re.I), lambda m: "THREATEN."),
    (re.compile(r"create (a|an|x|one|two|three) 1/1 red mercenary creature tokens? with \"\{t\}: target creature you "
                r"control gets \+1/\+0 until end of turn\.\s*activate only as a sorcery\.\"", re.I),
     lambda m: f"MERCENARY {m[1]}."),
    (re.compile(r"put each card exiled with ~ into its owner's graveyard, then create a 2/2 colorless robot artifact "
                r"creature token for each card put into a graveyard this way\. sacrifice ~\.", re.I),
     lambda m: "STARCAGE."),
    (re.compile(r"you may have ~ become a legendary equipment artifact named everflame, heroes' legacy\. if you do, "
                r"it gains equip \{3\} and \"equipped creature gets \+3/\+3\" and loses all other abilities\.", re.I),
     lambda m: "IRENCRAG."),
    (re.compile(r"if evidence was collected, exile a card from an opponent's graveyard\. then search its owner's "
                r"graveyard, hand, and library for any number of cards with that name and exile them\. that player "
                r"shuffles, then draws a card for each card exiled from their hand this way\.", re.I),
     lambda m: "COVERUP."),
    (re.compile(r"put x \+1/\+1 counters on target attacking creature, where x is the number of permanents you've "
                r"sacrificed this turn\. if x is three or greater, that creature gains lifelink until end of turn\.",
                re.I), lambda m: "OBSESS."),
    (re.compile(r"you may sacrifice another creature or artifact\. if you do, draw a card and create a treasure token\.",
                re.I), lambda m: "SACDRAWTREASURE."),
    (re.compile(r"destroy up to one other target creature\. its controller amasses (\w+) x, where x is that creature's "
                r"power\. if you controlled that creature, draw a card\.", re.I), lambda m: f"AZOG {m[1]}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (\w+) of them into your hand and the "
                r"rest on the bottom of your library(?: in (?:a random|any|any random) order)?\. if there is an "
                r"instant card and a sorcery card in your graveyard, instead put two of them into your hand and the "
                r"rest on the bottom of your library in any order\.", re.I),
     lambda m: f"DIGFLOW {_num(m[1])}."),
    (re.compile(r"(create a \d+/\d+ (?:\w+ )+?creature token) named [\w' ,-]+?\. it gains haste until end of turn\.",
                re.I), lambda m: f"{m[1]} with haste."),
    (re.compile(r"you may discard a card\. if you do, draw a card\.", re.I), lambda m: "RUMMAGE 1."),
    (re.compile(r"each opponent loses X life, where X is your devotion to (white|blue|black|red|green)\. you gain "
                r"life equal to the life lost this way\.", re.I),
     lambda m: f"DEVOTIONDRAIN {dict(white='W', blue='U', black='B', red='R', green='G')[m[1].lower()]}."),
    (re.compile(r"defending player reveals the top card of their library\. if it's a land card, that player puts "
                r"it into their hand\.", re.I), lambda m: "GOBLINGUIDE."),
    (re.compile(r"target (?:player|opponent) reveals their hand\. you choose a noncreature, nonland card from it\. "
                r"that player discards that card\.", re.I), lambda m: "TARGETDISCARDNONCREATURE."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (one) of them into your hand and the (?:other|rest) "
                r"on the bottom of your library(?: in any order)?\.", re.I),
     lambda m: f"DIG {_num(m[1])} {_num(m[2])}."),
    (re.compile(r"search your library for a basic land card, put it onto the battlefield tapped, then shuffle\."
                r"( then if you control four or more lands, untap that land\.)?", re.I),
     lambda m: "FETCHBASIC UNTAP4." if m[1] else "FETCHBASIC."),
    (re.compile(r"you may discard up(?: to)? (\w+) cards\. if you do, draw that many cards\.", re.I),
     lambda m: f"RUMMAGE {_num(m[1])}."),
    (re.compile(r"destroy target nonbasic land an opponent controls\. its controller searches their library for a basic "
                r"land card, puts it (?:onto|on) the battlefield tapped with a stun counter on it, then shuffles\.", re.I),
     lambda m: "STUNLANDSWAP."),
    (re.compile(r"exile up to one target nonland card of each card type from your graveyard\. copy those cards\. you may "
                r"cast any number of spells with total mana value (\d+) or less from among the copies without paying "
                r"their mana costs\.", re.I), lambda m: f"THEORIX {m[1]}."),
    (re.compile(r"if (?:this spell|~) was cast from a graveyard, exile it, then put it onto the battlefield transformed "
                r"under its owner's control with a finality counter on it\.", re.I), lambda m: "FLIPFROMGY."),
    (re.compile(r"reveal the top card of your library\. if it's an? (permanent|land|creature) card, put it into your "
                r"hand\.", re.I), lambda m: f"REVEALTOP {m[1].lower()}."),
    (re.compile(r"destroy target nonbasic land an opponent controls\. that land's controller may search their library for "
                r"a basic land card, put it onto the battlefield, then shuffle\. you may search your library for a basic "
                r"land card, put it onto the battlefield, then shuffle\.", re.I), lambda m: "BOTHLANDSWAP."),
    (re.compile(r"choose up to one target creature\. put a \+1/\+1 counter and a counter from among flying, first "
                r"strike, lifelink, or vigilance on it\.", re.I), lambda m: "ELSPETHPLUS."),
    (re.compile(r"exile up to one target card from a graveyard\. if a creature card was exiled this way, each "
                r"opponent loses (\d+) life and you gain \d+ life\.", re.I), lambda m: f"GYHATE {m[1]}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (\w+) of them into your hand and the "
                r"rest on the bottom of your library(?: in (?:a random|any|any random) order)?\.", re.I),
     lambda m: f"DIG {_num(m[1])} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. you may reveal (an? .+? card) from among them and "
                r"put it into your hand\. put the rest on the bottom of your library in (?:a random|any) order\.",
                re.I), lambda m: f"DIGFILTER {_num(m[1])} {m[2]}."),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. put (\w+) of them into your hand and the "
                r"(?:rest|other|others) into your graveyard\.", re.I),
     lambda m: f"DIGGY {_num(m[1])} {_num(m[2])}."),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may (?:put|reveal) (an? [\w ]+? card|an? [\w ]+ "
                r"card and/or an? [\w ]+ card) from among them (?:and put it )?into your hand\. put the rest into your "
                r"graveyard\.", re.I),
     lambda m: f"DIGFILTERGY {_num(m[1])} {m[2].replace(' card and/or a ', ' or ').replace(' card and/or an ', ' or ')}."),
    (re.compile(r"look at the top \w+ cards of your library, where X is the number of lands you control\. put "
                r"(\w+) of those cards into your hand\. put the rest on the bottom of your library in (?:a random|"
                r"any) order\.", re.I), lambda m: f"DIGLANDS {_num(m[1])}."),
    (re.compile(r"look at the top \w+ cards of your library, where X is the number of (artifacts|creatures|lands) "
                r"you control\. put (\w+) of those cards into your hand and the rest on the bottom of your library "
                r"in (?:a random|any) order\.", re.I), lambda m: f"DIGCOUNT {m[1][:-1]} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put up to (two) noncreature, nonland permanent "
                r"cards with mana value (\d+) or less from among them onto the battlefield\. put the rest on the "
                r"bottom of your library in a random order\.", re.I),
     lambda m: f"DIGPUTNONCREATURE {_num(m[1])} {m[3]} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. you may put a permanent card with mana value "
                r"(\d+) or less from among them onto the battlefield(?: with a shield counter on it)?\. put the rest "
                r"on the bottom of your library in a random order\.", re.I),
     lambda m: f"DIGPUT {_num(m[1])} {m[2]}."),
    (re.compile(r"exile the top (card|\w+ cards) of your library\. until (?:the end of your next turn|end of turn), you "
                r"may play (?:that card|those cards)(?: this turn)?\.", re.I),
     lambda m: f"IMPULSE {1 if m[1] == 'card' else _num(m[1].split()[0])}."),
    (re.compile(r"target (?:player|opponent) reveals their hand\. you choose a nonland card from it\. that player discards "
                r"that card\.", re.I), lambda m: "TARGETDISCARD."),
    (re.compile(r"then return a creature or planeswalker card with mana value X or less from your graveyard to "
                r"the battlefield, where X is the amount of \{S\} spent to cast ~\.", re.I),
     lambda m: "REANIMATESNOW."),
    (re.compile(r"each player sacrifices all other creatures they control\. then each player returns all creature "
                r"cards from their graveyard that weren't put there this way to the battlefield\.", re.I),
     lambda m: "LASTGIFT."),
    (re.compile(r"you may discard a card\. if you do, search your library for a creature card, reveal it, put it "
                r"into your hand, then shuffle\.", re.I), lambda m: "DISCARDTUTOR."),
    # Face-down permanents aren't modelled, so the "unless" clause never applies.
    (re.compile(r"you may draw a card\. if you do, discard a card unless a permanent entered the battlefield face "
                r"down under your control this turn or you turned a permanent face up this turn\.", re.I),
     lambda m: "Draw a card. Then discard a card."),
    (re.compile(r"return it to the battlefield under its owner's control\. it's an enchantment\.(?: \(It's not a "
                r"creature\.\))?", re.I), lambda m: "RETURNENCHANT."),
    (re.compile(r"you may pay \{2\}\{R\} any number of times\. when you pay this cost one or more times, .*",
                re.I | re.S), lambda m: "ADVERSARY."),
]


_TRIGGERS = [
    (r"When ~ becomes level (\d+), (.+)", ("class_level",)),
    (r"Whenever you proliferate, (.+)", ("proliferate",)),
    (r"Whenever you exert a creature, (.+)", ("exert",)),
    (r"Whenever an opponent searches their library, (.+)", ("opp_searches",)),
    (r"When(?:ever)? ~ enters or attacks, (.+)", ("etb", "attacks")),
    (r"When ~ enters and at the beginning of your upkeep, (.+)", ("etb", "upkeep")),
    (r"When(?:ever)? ~ enters?(?: the battlefield)?, (.+)", ("etb",)),
    (r"Whenever ~ attacks while (?!saddled)(.+)", ("attacks",)),
    (r"Whenever ~ attacks, (.+)", ("attacks",)),
    (r"Whenever ~ (?:blocks or becomes blocked|becomes blocked or blocks)(?: by a creature)?, (.+)", ("blocks", "becomes_blocked")),
    (r"Whenever ~ attacks or blocks, (.+)", ("attacks", "blocks")),
    (r"Whenever ~ blocks, (.+)", ("blocks",)),
    (r"Whenever ~ blocks a creature with flying, (.+)", ("blocks",)),
    (r"Whenever ~ becomes blocked(?: by a creature)?, (.+)", ("becomes_blocked",)),
    (r"Whenever ~ attacks and isn't blocked, (.+)", ("unblocked",)),
    (r"Whenever ~ blocks a creature, (.+)", ("blocks",)),
    (r"Whenever ~ is dealt damage, (.+)", ("dealt_damage",)),
    (r"Whenever ~ deals damage to (?:a player|an opponent), (.+)", ("damages_player",)),
    (r"Whenever ~ deals combat damage to a creature, (.+)", ("combat_damage_creature",)),
    (r"Whenever (?:a|another) creature dies, (.+)", ("creature_dies",)),
    # Dennick, Pious Apparition: the creature cards that die (discarded or milled ones are not seen)
    (r"Whenever one or more creature cards are put into graveyards from anywhere, (.+)", ("creature_dies",)),
    (r"Whenever (?:a player|an opponent) casts a spell, (.+)", ("any_cast",)),
    (r"At the beginning of each combat, (.+)", ("each_begin_combat",)),
    (r"At the beginning of your draw step, (.+)", ("draw_step",)),
    (r"Whenever (?:equipped|enchanted) creature attacks, (.+)", ("host:attacks",)),
    (r"When(?:ever)? (?:equipped|enchanted) creature dies, (.+)", ("host:dies",)),
    (r"When you cast ~, (.+)", ("cast_self",)),
    (r"When you cycle ~, (.+)", ("cycle_self",)),
    (r"Whenever one or more creatures you control deal combat damage to a player, (.+)", ("allies_hit_player",)),
    (r"Whenever a creature enters, (.+)", ("any_creature_enters",)),
    (r"At the beginning of each player's draw step, (.+)", ("each_draw_step",)),
    (r"Whenever you scry, (.+)", ("you_scry",)),
    (r"At end of combat, (.+)", ("end_combat",)),
    (r"When ~ becomes monstrous, (.+)", ("monstrous",)),
    (r"Whenever one or more \+1/\+1 counters are put on ~, (.+)", ("p1_added",)),
    (r"Whenever (?:equipped|enchanted) creature deals combat damage to a player, (.+)", ("host:combat_damage_player",)),
    (r"Whenever a creature dealt damage by ~ this turn dies, (.+)", ("damaged_dies",)),
    (r"When(?:ever)? ~ dies, (?:if it was a creature, )?(.+)", ("dies",)),
    (r"Whenever ~ deals combat damage to a player, (.+)", ("combat_damage_player",)),
    (r"Whenever a creature you control deals combat damage to a player, (.+)", ("ally_combat_damage",)),
    (r"Whenever you cast a noncreature spell, (.+)", ("cast_noncreature",)),
    (r"Whenever you cast an instant or sorcery spell, (.+)", ("cast_instant_sorcery",)),
    (r"Whenever you cast an instant or sorcery spell that targets a creature, (.+)", ("cast_instant_sorcery",)),
    (r"Whenever ~ becomes the target of a spell or ability you control for the first time each turn, (.+)",
     ("targeted_mine",)),
    (r"When(?:ever)? ~ becomes the target of a spell or ability, (.+)", ("targeted",)),
    (r"When ~ is turned face up, (.+)", ("turned_face_up",)),
    (r"Whenever you cast a spell that targets ~, (.+)", ("heroic",)),
    (r"Whenever you cast a spell during an opponent's turn, (.+)", ("cast_spell",)),
    (r"Whenever you cast a spell, (.+)", ("cast_spell",)),
    (r"Whenever you cast an? ([A-Z]\w+|creature|artifact|enchantment|outlaw|multicolored|historic|white|blue|black|red|"
     r"green|colorless) spell, (.+)", ("cast_spell",)),
    (r"Whenever you gain life, (.+)", ("gain_life",)),
    (r"Whenever (?:the Ring tempts you|you choose a creature as your Ring-bearer), (.+)", ("ring_tempts",)),
    (r"Whenever you attack, (.+)", ("you_attack",)),
    (r"Whenever you attack with one or more ([A-Z]\w+), (.+)", ("you_attack",)),
    (r"Whenever a creature you control attacks, (.+)", ("creature_attacks",)),
    (r"Whenever an? ([A-Z]\w+) you control attacks, (.+)", ("creature_attacks",)),
    (r"When(?:ever)? ~ enters or leaves the battlefield, (.+)", ("etb", "leaves")),
    (r"When(?:ever)? ~ leaves the battlefield, (.+)", ("leaves",)),
    (r"Whenever a player casts a spell with mana value (\d+) or less, (.+)", ("any_cast",)),
    (r"Whenever a player casts an? (white|blue|black|red|green|artifact|creature|enchantment|instant|sorcery) spell, (.+)",
     ("any_cast",)),
    (r"At the beginning of your upkeep, (.+)", ("upkeep",)),
    (r"At the beginning of each(?: player's)? upkeep, (.+)", ("each_upkeep",)),
    (r"At the beginning of each opponent's upkeep, (.+)", ("opp_upkeep",)),
    (r"At the beginning of each opponent's draw step, (.+)", ("opp_draw_step",)),
    (r"At the beginning of your end step, (.+)", ("end_step",)),
    (r"At the beginning of (?:each|the|each player's) end step, (.+)", ("each_end_step",)),
    (r"At the beginning of your first main phase, (.+)", ("main1_begin",)),
    (r"Survival — At the beginning of your second main phase, if ~ is tapped, (.+)", ("survival",)),
    (r"At the beginning of your second main phase, (.+)", ("main2_begin",)),
    (r"Whenever a creature an opponent controls dies, (.+)", ("opp_creature_dies",)),
    (r"Whenever another creature you control enters or dies, if that creature's power is greater than ~'s, (.+)",
     ("other_creature_enters", "other_creature_dies")),
    (r"Whenever a land you control enters, (.+)", ("land_enters",)),
    (r"When(?:ever)? (~ or )?(another|an?) ((?:[\w-]+(?:,? or |, | ))*?(?:creature|artifact|enchantment|planeswalker|"
     r"[A-Z]\w+)s?) you control( with mana value \d+ or greater| with (?:flying|reach|haste|trample|lifelink|deathtouch))? enters(?: and whenever an? ([A-Z]\w+) you control "
     r"enters| and whenever you fully unlock a Room)?, (.+)",
     ("permanent_enters",)),
    (r"Whenever you draw a card, (.+)", ("you_draw",)),
    (r"Whenever you sacrifice (an? [\w ]+?), (.+)", ("sacrifice",)),
    (r"Whenever an opponent draws a card, (.+)", ("opp_draw",)),
    (r"Whenever ~ becomes the target of a spell, (.+)", ("targeted_by_spell",)),
    (r"When(?:ever)? ~ enters or dies, (.+)", ("etb", "dies")),
    (r"When ~ is put into a graveyard from the battlefield, (.+)", ("dies",)),
    (r"At the beginning of combat on your turn, (.+)", ("begin_combat",)),
    (r"Whenever you draw your second card each turn, (.+)", ("draw_second",)),
    (r"Whenever you cast your second spell each turn, (.+)", ("cast_second",)),
    (r"Whenever a creature you control attacks alone, (.+)", ("attacks_alone",)),
    (r"Whenever you commit a crime, (.+)", ("crime",)),
    (r"Whenever you scry or surveil, (.+)", ("scry_surveil",)),
    (r"Whenever (?:one or more|an?) (?:(.+?) )?cards? (?:leaves?|leave) your graveyard( during your turn)?, (.+)",
     ("gy_leave",)),
    (r"Whenever you discard (?:a card|one or more cards), (.+)", ("you_discard",)),
    (r"Whenever you cast a spell with mana value (\d+) or greater, (.+)", ("cast_cmc",)),
    (r"Whenever ~ attacks while saddled, (.+)", ("attacks",)),
    (r"Whenever ~ becomes tapped, (.+)", ("becomes_tapped",)),
    (r"Whenever ~ enters or becomes tapped, (.+)", ("etb", "becomes_tapped")),
    (r"Whenever you expend (\d+), (.+)", ("expend",)),
    (r"Whenever (a|another) ([\w, -]+?) you control( with (?:a|an|one or more) (?:\+1/\+1 )?counters? on it)? dies, "
     r"(.+)", ("ally_dies",)),
    (r"Whenever (a|an|another) ([\w, -]+?) you control is put into a graveyard from the battlefield, (.+)",
     ("perm_to_gy",)),
]


_OPT_RIDER = re.compile(r"(?:then )?if (?:~|it|the spell) was bargained, (.+)|(?:then )?if the gift (was|wasn't) promised, (.+)",
                        re.I)


def _opt_rider(s: str, effects: list):
    """"If ~ was bargained / the gift was promised, X [instead]": X's effects carry cond bargained / gifted (or !gifted).
    With "instead" the earlier effect of the same kind (else every unconditional one) only happens otherwise.
    Returns the new effects, or None when X doesn't parse."""
    from .parse import _parse_effects  # deferred: parse imports this module
    m = _OPT_RIDER.fullmatch(s)
    if m is None:
        return None
    cond = "bargained" if m[1] else ("gifted" if m[2].lower() == "was" else "!gifted")
    rest = (m[1] or m[3]).strip()
    instead = bool(re.search(r"\binstead$", rest, re.I)) or re.match(r"instead,? ", rest, re.I) is not None
    rest = re.sub(r",? instead$|^instead,? ", "", rest, flags=re.I)
    new, bad = _parse_effects(rest[0].upper() + rest[1:] + ".")
    if bad or not new:
        return None
    if instead:
        same = [e for e in effects if not e.cond and e.kind == new[0].kind]
        for e in same or [e for e in effects if not e.cond]:
            e.cond = "!" + cond
    for e in new:
        e.cond = e.cond or cond
    return new


def _xq(text: str):
    """The quantity in ", where X is ...": a tuple the engine evaluates, or None when it isn't a known one."""
    t = text.strip().rstrip(".")
    tl = t.lower()
    from ..counting import _singular
    if tl in ("your life total", "your speed", "the amount of life you gained this turn",
             "the number of cards in your hand"):
        return ({"your life total": ("life",), "your speed": ("speed",),
                 "the amount of life you gained this turn": ("gained",),
                 "the number of cards in your hand": ("hand",)}[tl])
    m = re.fullmatch(r"(~|its|that creature|that spell)'s? (power|toughness|mana value)", t, re.I) or \
        re.fullmatch(r"(its) (power|toughness)", t, re.I)
    if m:
        return ("stat", "prev" if m[1] == "that creature" else "self", m[2])
    m = re.fullmatch(r"the greatest (power|toughness) among creatures you control", t, re.I)
    if m:
        return ("greatest", m[1])
    m = re.fullmatch(r"the number of ([\w+/ -]+?) counters on ~", t, re.I)
    if m:
        return ("counters", m[1])
    m = re.fullmatch(r"the number of ([\w -]+?) cards? in your graveyard", t, re.I)
    if m:
        return ("gy", _singular(m[1]))
    if tl == "the number of cards in your graveyard":
        return ("gy", "")
    if tl == "the number of creatures in your party":
        return ("party",)
    if tl in ("the number of colors of mana spent to cast this spell", "the number of colors of mana spent to cast ~"):
        return ("colors_spent",)                   # converge
    m = re.fullmatch(r"the number of ([\w -]+?) you control", t, re.I)
    if m and " with " not in m[1] and " that " not in m[1]:
        return ("count", _singular(m[1]))
    return None


_IF_CONDS = [
    (r"you attacked this turn", "attacked_turn"),
    (r"an opponent controls more lands than you", "opp_more_lands"),
    (r"a creature died this turn", "creature_died"),
    (r"a creature died under an opponent's control this turn", "opp_creature_died"),
    (r"you control another (outlaw|\w+)", None),
    (r"you control (two|three|four) or more tapped creatures", None),
    (r"you control a creature with power (\d+) or greater", None),
    (r"you sacrificed a permanent this turn", "sacrificed_turn"),
    (r"you chose a creature other than ~ as your Ring-bearer", "ring_other"),
    (r"you don't control a Ring-bearer", "no_ring_bearer"),
]


def _if_cond(phrase: str) -> str:
    """The engine condition name for the "if <phrase>," of a sentence, or ""."""
    from .. import phase_conditions, turn_conditions
    condition = phase_conditions.parse(phrase) or turn_conditions.parse(phrase)
    if condition:
        return condition
    phrase = phrase.strip()
    for rx, name in _IF_CONDS:
        m = re.fullmatch(rx, phrase, re.I)
        if not m:
            continue
        if name:
            return name
        if "another" in rx:
            return f"ctl_other:{m[1].capitalize() if m[1].lower() != 'outlaw' else 'outlaw'}"
        if "tapped" in rx:
            return f"tapped_creatures>={_N_WORDS.get(m[1].lower(), 2)}"
        return f"power_ge:{m[1]}"
    return ""
