"""Edicts, "gain life equal to its power", looking at a hand, "can't attack or block alone" and the monarch."""
from __future__ import annotations

EFFECT_PATTERNS = [
    (r"target player sacrifices a creature", lambda m: _e("edict_player", target="player", filter="opp")),
    (r"each player sacrifices a creature", lambda m: _e("edict_each")),
    (r"you gain life equal to its (power|toughness)", lambda m: _e("gain_prev_stat", data={"stat": m[1].lower()})),
    (r"look at target opponent's hand", lambda m: _e("peek_hand", target="player", filter="opp")),
    (r"create (a|one|two|three) (tapped )?powerstone tokens?", lambda m: _e("powerstone", _num(m[1]), data={"tapped": bool(m[2])})),
    (r"you become the monarch", lambda m: _e("become_monarch")),
    (r"(?:it|~) deals damage equal to its power to any target", lambda m: _e("damage", target="any", data={"source_power": True})),
]
SUBS = []


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _num(word):
    from .cards import _num as number
    return number(word)


def parse_rider(s, effects):
    """Sentences that modify the effect before them. Returns True when consumed."""
    import dataclasses
    import re
    if not effects:
        return False
    last = effects[-1]
    if re.fullmatch(r"those creatures don't untap during their controller's next untap step", s, re.I) and last.kind == "tap":
        effects[-1] = dataclasses.replace(last, data=dict(last.data, freeze=True))
        return True
    if re.fullmatch(r"untap those creatures", s, re.I) and last.kind == "pump_all":
        effects[-1] = dataclasses.replace(last, data=dict(last.data, untap=True))
        return True
    if re.fullmatch(r"you gain life equal to the life lost this way", s, re.I) and last.kind in ("drain", "opp_lose_life"):
        effects[-1] = dataclasses.replace(last, data=dict(last.data, gain=True))
        return True
    if re.fullmatch(r"if a creature dealt damage this way would die this turn, exile it instead", s, re.I) and last.kind == "damage":
        effects[-1] = dataclasses.replace(last, data=dict(last.data, exile_dying=True))
        return True
    return False


def parse_line(line, st):
    if line == "~ can't attack or block alone.":
        st.extra.setdefault('advanced_rules', {})['no_solo'] = True
        return True
    import re
    m = re.fullmatch(r"~ enters tapped with (a|one|two|three|four|five) (\w+) counters? on it\.", line)
    if m:
        st.enters_tapped = True
        st.extra['etb_named_counters'] = (m[2].lower(), _num(m[1]))
        return True
    if re.fullmatch(r"Converge — ~ enters with a \+1/\+1 counter on it for each color of mana spent to cast it\.", line):
        st.extra.setdefault('advanced_rules', {})['sunburst'] = True
        return True
    if re.fullmatch(r"You may have ~ assign its combat damage as though it weren't blocked\.", line):
        st.extra.setdefault('advanced_rules', {})['assign_unblocked'] = True
        return True
    if line == "If damage would be dealt to ~, prevent that damage. Remove a +1/+1 counter from ~.":
        st.extra.setdefault('advanced_rules', {})['phantom'] = True
        return True
    if re.fullmatch(r"Provoke(?: \(.*\))?", line):
        from .cards import Effect, Trigger
        st.triggers.append(Trigger('attacks', [Effect('provoke')]))
        return True
    if line == "You have hexproof.":
        st.extra.setdefault('advanced_rules', {})['player_hexproof'] = True
        return True
    return False


def player_targetable(game, player, by):
    """"You have hexproof": the player can't be targeted by opponents' spells and abilities."""
    if player is by:
        return True
    from .residual_templates import sources
    return not any(x.controller is player for x in sources(game, 'player_hexproof'))


def mark_exile_dying(game, creature):
    creature.exile_if_dies = game.turn


def powerstone():
    from .cards import CardDef
    return CardDef(name="Powerstone", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Artifact"}),
                   subtypes=frozenset({"Powerstone"}), is_token=True, token_kind="powerstone",
                   produces=frozenset({"C"}), mana_restriction="artifact", restricted_produces=frozenset({"C"}))


def phantom_prevents(target):
    """Phantom creatures: damage is prevented and a +1/+1 counter removed instead."""
    if target.card.advanced_rules.get('phantom') and target.p1 > 0 and not target.abilities_suppressed:
        target.counters["+1/+1"] = target.p1 - 1
        return True
    return False


def drop_solo(creatures):
    """Remove creatures that can't attack or block alone while nothing else joins them."""
    group = list(creatures)
    while len(group) == 1 and group[0].card.advanced_rules.get('no_solo') and not group[0].abilities_suppressed:
        group = []
    return group


def drop_solo_blocks(blocks):
    """A creature that can't block alone is removed from the declared blocks unless another creature blocks too."""
    blockers = {b for bl in blocks.values() for b in bl}
    if len(blockers) != 1:
        return blocks
    only = next(iter(blockers))
    if only.card.advanced_rules.get('no_solo') and not only.abilities_suppressed:
        return {}
    return blocks


def end_step_draw(game, active):
    monarch = getattr(game, 'monarch', None)
    if monarch is active:
        game.log("draws for the monarchy", active)
        game.draw(active, 1)


def combat_hit(game, source, target):
    if getattr(game, 'monarch', None) is target and source.controller is not target:
        game.monarch = source.controller
        game.log("becomes the monarch", source.controller)
