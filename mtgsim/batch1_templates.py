"""Edicts, "gain life equal to its power", looking at a hand, "can't attack or block alone" and the monarch."""
from __future__ import annotations

EFFECT_PATTERNS = [
    (r"target player sacrifices a creature", lambda m: _e("edict_player", target="player", filter="opp")),
    (r"each player sacrifices a creature", lambda m: _e("edict_each")),
    (r"you gain life equal to its (power|toughness|mana value)", lambda m: _e("gain_prev_stat", data={"stat": m[1].lower()})),
    (r"(?:that|defending) player sacrifices a creature", lambda m: _e("edict_player", target="that_player")),
    (r"each player sacrifices a land", lambda m: _e("sac_land_each")),
    (r"(?:that|defending) player discards a card at random", lambda m: _e("discard_random_that", target="that_player")),
    (r"(?:defending|that) player discards a card", lambda m: _e("discard", target="that_player")),
    (r"~ deals (\d+) damage to each (attacking creature|creature your opponents control)",
     lambda m: _e("damage_group", int(m[1]), data={"group": "attacking" if m[2].startswith("attacking") else "opp"})),
    (r"destroy target creature that was dealt damage this turn", lambda m: _e("destroy", target="creature", filter="damaged")),
    (r"look at target opponent's hand", lambda m: _e("peek_hand", target="player", filter="opp")),
    (r"create (a|one|two|three) (tapped )?powerstone tokens?", lambda m: _e("powerstone", _num(m[1]), data={"tapped": bool(m[2])})),
    (r"target creature gets \+X/\+(X|0) until end of turn",
     lambda m: _e("pump", 0, target="creature", data={"x": True, "x2": m[1] == "X"})),
    (r"creatures you control get \+X/\+(X|0) until end of turn",
     lambda m: _e("pump_all", 0, data={"x": True, "x2": m[1] == "X", "other": False, "keyword": ""})),
    (r"incubate (\d+)", lambda m: _e("incubate", int(m[1]))),
    (r"tap or untap target (creature|permanent)", lambda m: _e("tap", target=m[1], data={"or_untap": True})),
    (r"switch target creature's power and toughness until end of turn", lambda m: _e("switch_pt", target="creature")),
    (r"target creature has base power and toughness (\d+)/(\d+) until end of turn",
     lambda m: _e("set_base_pt", int(m[1]), amount2=int(m[2]), target="creature")),
    (r"target player loses (\d+) life", lambda m: _e("drain", int(m[1]), target="each_opponent")),
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
    m = re.fullmatch(r"~ gets \+(\d+)/\+(\d+) as long as you control an? (Plains|Island|Swamp|Mountain|Forest)\.", line)
    if m:
        st.extra["pt_if"] = st.extra.get("pt_if", ()) + (("land:" + m[3], int(m[1]), int(m[2])),)
        return True
    m = re.fullmatch(r"~ can't be blocked by (artifact creatures|[Ww]alls|creatures with flying)\.", line)
    if m:
        rules = st.extra.setdefault('advanced_rules', {})
        rules['evade_vs'] = rules.get('evade_vs', ()) + ({"artifact creatures": "artifact", "walls": "Wall", "creatures with flying": "flying"}[m[1].lower()],)
        return True
    m = re.fullmatch(r"~ can't be blocked by (white|blue|black|red|green) creatures\.", line)
    if m:
        rules = st.extra.setdefault('advanced_rules', {})
        rules['evade_vs'] = rules.get('evade_vs', ()) + ("color:" + _COLOR[m[1]],)
        return True
    m = re.fullmatch(r"~ can't be blocked except by (?:(white|blue|black|red|green) creatures|creatures with (flying)(?: or (reach))?)\.", line)
    if m:
        rules = st.extra.setdefault('advanced_rules', {})
        only = ("color:" + _COLOR[m[1]],) if m[1] else tuple(w for w in m[2:] if w)
        rules['evade_except'] = rules.get('evade_except', ()) + (only,)
        return True
    m = re.fullmatch(r"~ can't block creatures with power (\d+) or greater\.", line)
    if m:
        st.extra.setdefault('advanced_rules', {})['cant_block_power'] = int(m[1])
        return True
    if line == "~ can't block and can't be blocked.":
        st.extra['cant_block'] = True
        st.keywords.add('unblockable')
        return True
    if line == "~ can't attack alone.":
        st.extra.setdefault('advanced_rules', {})['no_solo_attack'] = True
        return True
    m = re.fullmatch(r"~ gets \+(\d+)/\+(\d+) for each (creature|land|artifact|instant|sorcery|instant or sorcery|instant and sorcery) cards? in your graveyard\.", line)
    if m:
        st.extra["pt_per"] = "gy:" + m[3].replace(" and ", " or ")
        st.extra["pt_scale"] = (int(m[1]), int(m[2]))
        return True
    m = re.fullmatch(r"~'s (power and toughness are each|power is) equal to the number of (creature|land|artifact|instant and sorcery) cards in your graveyard\.", line)
    if m:
        st.extra["pt_per"] = "gy:" + m[2].replace(" and ", " or ")
        st.extra["pt_scale"] = (1, 1) if "and" in m[1] else (1, 0)
        return True
    m = re.fullmatch(r"~ gets \+(\d+)/\+(\d+) for each Aura attached to it\.", line)
    if m:
        st.extra["pt_per"] = "attached:aura"
        st.extra["pt_scale"] = (int(m[1]), int(m[2]))
        return True
    m = re.fullmatch(r"(?:Each|All) (creature|creatures) you control with (.+) (?:has|have) ([a-z ,]+)\.", line)
    if m:
        from .permanent_templates import selector, keywords
        spec = selector("creatures you control with " + m[2], plural=True)
        kws = keywords(m[3])
        if spec is not None and kws and 'keyword' not in spec:
            st.extra['static_keyword_grants'] = st.extra.get('static_keyword_grants', ()) + ((spec, tuple(kws)),)
            return True
    m = re.fullmatch(r"At the beginning of the upkeep of enchanted creature's controller, (?:that player loses (\d+) life|~ deals (\d+) damage to that player"
                     r"|put a -1/-1 counter on that creature)\.", line)
    if m:
        from .cards import Effect, Trigger
        eff = Effect('host_lose', int(m[1])) if m[1] else Effect('host_damage', int(m[2])) if m[2] else Effect('host_shrink')
        st.triggers.append(Trigger('host_upkeep', [eff]))
        return True
    m = re.fullmatch(r"Other creatures you control with (flying|trample|menace|first strike|lifelink|deathtouch|infect|defender|haste|vigilance|reach) get "
                     r"\+(\d+)/\+(\d+)\.", line)
    if m:
        st.extra["anthem_kw"] = st.extra.get("anthem_kw", ()) + ((m[1], int(m[2]), int(m[3]), True),)
        return True
    m = re.fullmatch(r"Creatures can't attack you or planeswalkers you control unless their controller pays \{(\d+)\} for each of those creatures\.", line)
    if m:
        st.extra.setdefault('advanced_rules', {})['attack_tax'] = int(m[1])
        return True
    m = re.fullmatch(r"Whenever enchanted land is tapped for mana, its controller adds an additional (one mana of any color|two mana in any combination of colors|\{[WUBRG]\}(?:\{[WUBRG]\})?)\.", line)
    if m:
        st.extra.setdefault('advanced_rules', {})['aura_mana'] = {'one': 1, 'two': 2}.get(m[1][:3], m[1].count('{'))
        st.approximations.append("extra mana from an enchanted land is the land's own colour")
        return True
    if _curse_line(line, st):
        return True
    if _level_up_line(line, st):
        return True
    if re.fullmatch(r"Partner(?: with [^.]+|—[^.]+)?", line):
        return True                         # deck construction only: nothing happens in a game
    m = re.fullmatch(r"(Multikicker|Squad) ((?:\{[^ }]+\})+)(?: \(.*\))?", line)
    if m:
        from .cards import parse_mana_cost
        st.extra.setdefault('advanced_rules', {})['multipay'] = (m[1].lower(), parse_mana_cost(m[2]))
        return True
    if re.fullmatch(r"(?:~|This creature|It) enters with an? \+1/\+1 counter on (?:it|him|her) for each time (?:it|he|she|~) was kicked\.", line):
        st.extra.setdefault('advanced_rules', {})['kick_counters_each'] = True
        return True
    m = re.fullmatch(r"Cumulative upkeep(?: ((?:\{[^ }/]+\})+)|—Pay (\d+) life)\.?(?: \(.*\))?", line)
    if m:
        from .cards import parse_mana_cost
        st.extra.setdefault('advanced_rules', {})['cumulative_upkeep'] = (
            ('mana', parse_mana_cost(m[1])) if m[1] else ('life', int(m[2])))
        return True
    m = re.fullmatch(r"Outlast ((?:\{[^ }]+\})+)(?: \(.*\))?", line)
    if m:
        from .cards import Activated, Effect, parse_mana_cost
        st.activated.append(Activated("ability", parse_mana_cost(m[1]), effects=[Effect('p1_counters', 1, target='self')],
                                      extra_costs={"tap": True}, sorcery=True,
                                      text=f"{m[1]}, {{T}}: Put a +1/+1 counter on this creature. Activate only as a sorcery."))
        return True
    m = re.fullmatch(r"(Each player|You) can't cast more than one spell each turn\.", line)
    if m:
        st.extra.setdefault('advanced_rules', {})['one_spell_each' if m[1] == 'Each player' else 'one_spell_you'] = True
        return True
    m = re.fullmatch(r"Whenever enchanted creature (deals|is dealt) damage, you gain that much life\.", line)
    if m:
        rules = st.extra.setdefault('advanced_rules', {})
        rules['soul_link'] = rules.get('soul_link', ()) + (m[1],)
        return True
    m = re.fullmatch(r"Whenever (you|a player) taps? a land for mana, (?:(?:you|that player) adds?|add) one mana of any type that land produced\.", line)
    if m:
        st.extra.setdefault('advanced_rules', {})['land_double'] = 'mine' if m[1] == 'you' else 'all'
        return True
    m = re.fullmatch(r"As long as ~ is paired with another creature, (?:both creatures|each of those creatures) (?:have ([a-z ]+)|gets? \+(\d+)/\+(\d+))\.", line)
    if m:
        rules = st.extra.setdefault('advanced_rules', {})
        grant = dict(rules.get('soulbond') or {})
        if m[1]:
            grant['kw'] = tuple(x.strip() for x in re.split(r",| and ", m[1]) if x.strip())
        else:
            grant['pt'] = (int(m[2]), int(m[3]))
        rules['soulbond'] = grant
        return True
    if re.fullmatch(r"Soulbond(?: \(.*\))?", line):
        st.extra.setdefault('advanced_rules', {}).setdefault('soulbond', {})
        return True
    if re.fullmatch(r"Ascend(?: \(.*\))?", line):
        st.extra.setdefault('advanced_rules', {})['ascend'] = True
        return True
    if re.fullmatch(r"Melee(?: \(.*\))?", line):
        from .cards import Effect, Trigger
        st.triggers.append(Trigger('attacks', [Effect('pump', 1, 1, target='self')]))
        return True
    if re.fullmatch(r"Enlist(?: \(.*\))?", line):
        st.extra.setdefault('advanced_rules', {})['enlist'] = True
        return True
    if re.fullmatch(r"Exploit(?: \(.*\))?", line):
        from .cards import Effect, Trigger
        st.triggers.append(Trigger('etb', [Effect('exploit')]))
        return True
    m = re.fullmatch(r"When ~ exploits a creature, (.+)", line) or re.fullmatch(r"Whenever ~ exploits a creature, (.+)", line)
    m2 = re.fullmatch(r"Whenever a creature you control exploits (a|a nontoken) creature, (.+)", line)
    if m or m2:
        from .cards import Trigger
        from .cards.parse import _parse_effects
        effects, bad = _parse_effects((m or m2)[(m or m2).lastindex])
        if effects and not bad:
            event = 'exploit_self' if m else 'exploit_any_nontoken' if m2[1] == 'a nontoken' else 'exploit_any'
            st.triggers.append(Trigger(event, effects))
            return True
    if line == "Activated abilities of artifacts can't be activated.":
        st.extra.setdefault('advanced_rules', {})['artifact_activation_lock'] = True
        return True
    if line == "Skip your draw step.":
        st.extra.setdefault('advanced_rules', {})['skip_draw'] = True
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


def on_upkeep(game, active):
    """Auras that act at the upkeep of the enchanted creature's controller."""
    curse_event(game, active, 'curse_upkeep')
    for perm in list(active.battlefield):
        if perm.card.advanced_rules.get('cumulative_upkeep') and not perm.abilities_suppressed:
            cumulative_upkeep(game, active, perm)
    for player in game.players:
        for src in list(player.battlefield):
            host = src.aura_host
            if host is not None and host.controller is active:
                for trig in src.triggers:
                    if trig.event == 'host_upkeep':
                        game.queue_trigger(player, trig.effects, src, src.card.name, context=host)


def cumulative_upkeep(game, p, perm):
    """Add an age counter, then pay the upkeep cost once per age counter or sacrifice it (the AI stops paying when it gets steep)."""
    age = perm.counters.get('age', 0) + 1
    perm.counters['age'] = age
    kind, cost = perm.card.advanced_rules['cumulative_upkeep']
    if kind == 'life':
        if p.life - cost * age >= 8:
            game.change_life(p, -cost * age, f"{perm.card.name}: cumulative upkeep")
            return
    else:
        total = {k: v * age for k, v in cost.items()}
        if sum(total.values()) <= 3 and game.can_pay(p, total) and game.pay(p, total) is not None:
            return
    game.log(f"does not pay cumulative upkeep for {perm.card.name}", p)
    game.sacrifice(perm)


def effect_value(game, player, effect, target):
    """AI worth of this module's kinds (None for kinds it does not own)."""
    from .engine.policy import perm_value
    kind = effect.kind
    if kind in ('edict_player', 'edict_each'):
        theirs = [perm_value(c) for c in game.opponent(player).creatures]
        mine = [perm_value(c) for c in player.creatures]
        if not theirs:
            return -1
        return min(theirs) - (min(mine) if kind == 'edict_each' and mine else 0)
    if kind == 'become_monarch':
        return 3
    if kind in ('powerstone', 'provoke', 'incubate'):
        return 1 + (effect.amount if kind == 'incubate' else 0)
    if kind == 'exploit':
        return 0.5
    if kind == 'level_counter':
        src = getattr(game.target_source, 'source', game.target_source)
        blocks = getattr(getattr(src, 'card', None), 'level_blocks', ())
        level = getattr(src, 'counters', {}).get('level', 0)
        if not blocks or level >= max(b[0] for b in blocks):
            return 0                       # already in the last range
        return 1 + 0.5 * sum(b[2][0] + b[2][1] for b in blocks if b[2] and b[0] == level + 1)
    if kind == 'tuck_perm':
        return perm_value(target) if getattr(target, 'controller', None) is game.opponent(player) else -1
    if kind == 'lose_half':
        return game.opponent(player).life / 4
    if kind == 'wheel_all':
        return len(player.hand) * -0.5 + effect.amount * 0.5 - len(game.opponent(player).hand) * -0.25
    if kind == 'shuffle_gy':
        return -1 if target is not game.opponent(player) else 0
    if kind == 'incubator_transform':
        src = getattr(game.target_source, 'source', game.target_source)
        return effect.amount if getattr(src, 'p1', 0) and game.step in ('main1', 'main2') else 0
    return None


def incubator():
    from .cards import CardDef, Effect, Activated
    return CardDef(name="Incubator", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Artifact"}),
                   subtypes=frozenset({"Incubator"}), is_token=True,
                   activated=[Activated("ability", {"generic": 2}, effects=[Effect("incubator_transform")],
                                        extra_costs={}, text="{2}: Transform this artifact.")])


def paired(perm):
    """The creature perm is soulbonded to, or None once the bond has ended."""
    other = perm.partner
    if other is None:
        return None
    if other.partner is perm and other in other.controller.battlefield and other.controller is perm.controller \
            and other.is_creature and perm.is_creature:
        return other
    perm.partner = None
    return None


def soulbond_has(perm, keyword):
    other = paired(perm)
    return other is not None and any(keyword in (m.card.advanced_rules.get('soulbond') or {}).get('kw', ())
                                     for m in (perm, other) if not m.abilities_suppressed)


def soulbond_bonus(perm):
    other = paired(perm)
    if other is None:
        return 0, 0
    bonus = [0, 0]
    for m in (perm, other):
        pt = (m.card.advanced_rules.get('soulbond') or {}).get('pt')
        if pt and not m.abilities_suppressed:
            bonus[0] += pt[0]
            bonus[1] += pt[1]
    return bonus[0], bonus[1]


def soulbond_pair(game, p, perm):
    """When a creature enters, pair it with an unpaired soulbond creature (or pair a soulbond one with any other)."""
    if not perm.is_creature or perm.partner is not None:
        return
    unpaired = [x for x in p.battlefield if x is not perm and x.is_creature and paired(x) is None]
    if 'soulbond' in perm.card.advanced_rules and unpaired:
        pick = max(unpaired, key=lambda x: x.power + x.toughness)
    else:
        pick = next((x for x in unpaired if 'soulbond' in x.card.advanced_rules), None)
    if pick is not None:
        perm.partner, pick.partner = pick, perm
        game.log(f"{perm.card.name} pairs with {pick.card.name}", p)


_LEVEL_KW = r"(?:flying|first strike|double strike|trample|haste|vigilance|lifelink|deathtouch|menace|reach|shadow|defender|indestructible|fear)"


def _level_up_line(line, st):
    """Level up creatures: "Level up {cost}", then "LEVEL 1-3" blocks of a power/toughness line and keywords or abilities."""
    import re
    from .cards import Activated, Effect, parse_mana_cost
    m = re.fullmatch(r"Level up ((?:\{[^ }]+\})+)(?: \(.*\))?", line)
    if m:
        st.activated.append(Activated("ability", parse_mana_cost(m[1]), effects=[Effect('level_counter')], sorcery=True,
                                      text=f"{m[1]}: Put a level counter on this. Level up only as a sorcery."))
        st.extra['_lvl_blocks'] = []
        return True
    blocks = st.extra.get('_lvl_blocks')
    if blocks is None:
        return False
    m = re.fullmatch(r"LEVEL (\d+)(?:-(\d+)|\+)", line)
    if m:
        blocks.append({'lo': int(m[1]), 'hi': int(m[2]) if m[2] else 999, 'a': len(st.activated), 't': len(st.triggers),
                       'pt': None, 'kw': []})
        return True
    if not blocks:
        return False
    m = re.fullmatch(r"(\d+)/(\d+)", line)
    if m and blocks[-1]['pt'] is None:
        blocks[-1]['pt'] = (int(m[1]), int(m[2]))
        return True
    if re.fullmatch(rf"{_LEVEL_KW}(?:, {_LEVEL_KW})*", line, re.I):
        blocks[-1]['kw'] += [k.strip().lower() for k in line.split(',')]
        return True
    return False


def finish_level_up(extra, triggers, activated, approximations, produces=()):
    """Close the LEVEL blocks: gate the abilities each one added to its level range."""
    blocks = extra.pop('_lvl_blocks', None)
    if blocks is None:
        return
    for i, b in enumerate(blocks):
        a_end = blocks[i + 1]['a'] if i + 1 < len(blocks) else len(activated)
        t_end = blocks[i + 1]['t'] if i + 1 < len(blocks) else len(triggers)
        for act in activated[b['a']:a_end]:
            act.extra_costs = dict(act.extra_costs, level_range=(b['lo'], b['hi']))
        for trig in triggers[b['t']:t_end]:
            trig.min_level = b['lo']
            if b['hi'] != 999:
                approximations.append("a level-range trigger keeps working above its range")
    if produces:
        approximations.append("a mana ability inside a level range works at every level")
    extra['level_blocks'] = tuple((b['lo'], b['hi'], b['pt'], tuple(b['kw'])) for b in blocks)


def level_block(perm):
    """The (power, toughness, keywords) of the level range perm is in, or None."""
    blocks = perm.card.level_blocks
    if not blocks:
        return None
    level = perm.counters.get('level', 0)
    for lo, hi, pt, kws in blocks:
        if lo <= level <= hi:
            return pt, kws
    return None


def _curse_line(line, st):
    """Curses ("Enchant player" Auras): upkeep and attack triggers and static rules on the enchanted player."""
    import re
    from .cards import Effect, Trigger, _parse_effects
    rules = st.extra.setdefault('advanced_rules', {})
    m = re.fullmatch(r"At the beginning of enchanted player's upkeep, (?:that player (loses|mills) (\w+) (?:life|cards)|"
                     r"that player exiles (\w+) cards from their graveyard|~ deals (\d+) damage to that player"
                     r"( or a planeswalker that player controls)?|~ deals damage to that player equal to the number of Curses attached to them)\.", line)
    if m:
        if m[1] == 'loses':
            eff = Effect('curse_lose', _num(m[2]))
        elif m[1] == 'mills':
            eff = Effect('curse_mill', _num(m[2]))
        elif m[3]:
            eff = Effect('curse_exile_gy', _num(m[3]))
        elif m[4]:
            eff = Effect('curse_damage', int(m[4]))
            if m[5]:
                st.approximations.append("the planeswalker option is ignored")
        else:
            eff = Effect('curse_damage', 0, data={'per_curse': True})
        st.triggers.append(Trigger('curse_upkeep', [eff]))
        return True
    m = re.fullmatch(r"Creatures enchanted player controls get ([+−-])(\d+)/([+−-])(\d+)\.", line)
    if m:
        sign = lambda c: -1 if c in '−-' else 1
        rules['curse_pt'] = (sign(m[1]) * int(m[2]), sign(m[3]) * int(m[4]))
        return True
    simple = {"Enchanted player can't cast more than one spell each turn.": 'curse_one_spell',
              "If a source would deal damage to enchanted player, it deals double that damage to that player instead.": 'curse_double',
              "Creatures enchanted player controls attack each combat if able.": 'curse_must_attack'}
    if line in simple:
        rules[simple[line]] = True
        return True
    m = re.fullmatch(r"Whenever enchanted player is attacked, (.+?\.) Each opponent attacking that player does the same\.", line)
    if m:
        effects, bad = _parse_effects(m[1])
        if effects and not bad:
            st.triggers.append(Trigger('curse_attacked', effects))
            return True
    if line == "Whenever a creature enters under enchanted player's control, that player loses 1 life and you gain 1 life.":
        st.triggers.append(Trigger('curse_creature_enters', [Effect('drain', 1, target='each_opponent', data={'gain': True})]))
        return True
    return False


def curses_on(game, player):
    """The Curses attached to this player."""
    if game is None:
        return []
    return [x for pl in game.players for x in pl.battlefield
            if x.curse_target is player and not x.abilities_suppressed]


def curse_event(game, player, event, context=None):
    """Queue the triggers of every Curse on player for this event."""
    for curse in curses_on(game, player):
        for trig in curse.triggers:
            if trig.event == event:
                game.queue_trigger(curse.controller, trig.effects, curse, curse.card.name,
                                   context=player if context is None else context)


def spell_kind_ok(card, kind):
    """Whether this spell card is a creature / noncreature / instant / ... / white / ... spell."""
    if kind == 'noncreature':
        return not card.is_creature
    from .engine.play import SPELL_KINDS
    if kind in SPELL_KINDS:
        return SPELL_KINDS[kind](card)
    return kind.capitalize() in card.types


def spell_limited(game, p):
    """Rule of Law: only one spell per turn for everyone (or just you under Moderation)."""
    from .residual_templates import sources
    if game.spells_cast_turn(p) < 1:
        return False
    return bool(sources(game, 'one_spell_each') or [x for x in sources(game, 'one_spell_you') if x.controller is p]
                or any(c.card.advanced_rules.get('curse_one_spell') for c in curses_on(game, p)))


def soul_link(game, source, target, amount):
    """Spirit Link: whenever the enchanted creature deals (or is dealt) damage, the Aura's controller gains that much life."""
    from .engine.state import Permanent
    for side, perm in (('deals', source), ('is dealt', target)):
        if isinstance(perm, Permanent):
            for aura in perm.auras:
                if side in aura.card.advanced_rules.get('soul_link', ()) and not aura.abilities_suppressed:
                    game.change_life(aura.controller, amount, f"{aura.card.name}: {side} damage")


def has_blessing(game, player, item=None):
    """The city's blessing: ten or more permanents while a permanent (or the resolving spell) has Ascend; kept for the game."""
    if getattr(player, 'blessing', False):
        return True
    ascends = any(x.card.advanced_rules.get('ascend') for x in player.battlefield) or \
        item is not None and item.card is not None and item.card.advanced_rules.get('ascend')
    if ascends and len(player.battlefield) >= 10:
        player.blessing = True
    return bool(getattr(player, 'blessing', False))


def enlist(game, p, attackers):
    """Enlist: as the creature attacks, tap a non-attacking creature without summoning sickness; add its power."""
    for a in attackers:
        if not a.card.advanced_rules.get('enlist') or a.abilities_suppressed:
            continue
        pool = [c for c in p.creatures if c not in attackers and not c.tapped and (not c.sick or c.has("haste")) and c.power >= 2]
        if pool:
            helper = max(pool, key=lambda c: c.power)
            helper.tapped = True
            a.pump_p += helper.power
            game.log(f"{a.card.name} enlists {helper.card.name} (+{helper.power})", p)


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


_COLOR = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _is(blocker, kind):
    return blocker.has(kind) if not kind.startswith("color:") else kind[6:] in blocker.card.colors


def block_restricted(blocker, attacker):
    """Blocking limits from evasion ("can't be blocked by walls") and from the blocker ("can't block power 2 or greater")."""
    for kind in attacker.card.advanced_rules.get('evade_vs', ()):
        if kind == 'artifact' and blocker.card.is_artifact or kind == 'flying' and blocker.has('flying') \
                or kind.startswith('color:') and _is(blocker, kind) or kind in blocker.card.subtypes:
            return True
    for only in attacker.card.advanced_rules.get('evade_except', ()):
        if not any(_is(blocker, kind) for kind in only):
            return True
    limit = blocker.card.advanced_rules.get('cant_block_power')
    return bool(limit and attacker.power >= limit)


def skips_draw(game, player):
    from .residual_templates import sources
    return any(x.controller is player for x in sources(game, 'skip_draw'))


def drop_solo(creatures):
    """Remove creatures that can't attack or block alone while nothing else joins them."""
    group = list(creatures)
    while len(group) == 1 and (group[0].card.advanced_rules.get('no_solo') or group[0].card.advanced_rules.get('no_solo_attack')) \
            and not group[0].abilities_suppressed:
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
