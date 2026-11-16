"""Instant-speed plays that only make sense on the opponent's turn and that the AI had no window for (#853):

- "Target player can't play lands this turn" (Solfatara, Turf Wound, Moonhold, Pardic Miner's ability) belongs in the
  opponent's upkeep, before their land drop. The engine gives no empty-stack priority in the upkeep, so
  ``upkeep_denial`` is called once there for the non-active player instead of opening a full window (which would
  move every other instant-speed play: Clues, flashback, loyalty abilities).
- "<Spell> deals damage to target spell's controller equal to that spell's mana value" (Parallectric Feedback,
  Refuse) answers an opponent's spell on the stack: ``punish_spell``, used by HeuristicAI's respond."""
from __future__ import annotations

DENY_FLAGS = frozenset({"no_lands"})
MINER_LANDS = 4          # sacrificing a creature to deny a land drop: only while the opponent is still short of mana


def _denies(effects) -> bool:
    return any(e.kind == "cx_player_flag" and (e.data or {}).get("who") == "target"
               and (e.data or {}).get("flag") in DENY_FLAGS for e in effects)


def _aim(effects, victim):
    return [victim if e.target in ("player", "opponent") else None for e in effects]


def upkeep_denial(game, active) -> bool:
    """In ``active``'s upkeep (stack empty): the other player casts or activates one land denial at them."""
    if game.over or game.stack:
        return False
    me = game.opponent(active)
    if not getattr(me.ai, "respond", None):        # scripted / baseline AIs without instant-speed play
        return False
    if not any(_denies(c.spell_effects) for c in me.hand) and \
            not any(_denies(ab.effects) for x in me.battlefield for ab in x.card.activated):
        return False
    from .residual_templates import lands_locked
    if lands_locked(active):
        return False
    for card in me.hand:
        if card.instant_speed and _denies(card.spell_effects) and game.can_cast_now(me, card):
            if game.cast(me, card, _aim(card.spell_effects, active)):
                game.settle()
                return True
    if sum(x.card.is_land for x in active.battlefield) >= MINER_LANDS:
        return False
    for perm in list(me.battlefield):
        for i, ab in enumerate(perm.card.activated):
            if not _denies(ab.effects):
                continue
            if (ab.extra_costs or {}).get("sac_self") and perm.is_creature and perm.card.cmc > 2:
                continue        # not worth a real creature
            if game.activate_ability(me, perm, i, _aim(ab.effects, active)):
                game.settle()
                return True
    return False


def punish_spell(game, me, item, options):
    """Cast a "damage to target spell's controller equal to its mana value" instant at an opponent's spell when the
    damage is lethal or at least 4."""
    if not getattr(item, "is_spell", False) or item.controller is me or item.card is None:
        return None
    victim = item.controller
    dmg = item.card.cmc
    if dmg <= 0 or (dmg < 4 and dmg < victim.life):
        return None
    for card in options:
        effs = card.spell_effects
        if effs and all(e.kind == "damage" and e.target == "spell" and (e.data or {}).get("spell_controller")
                        for e in effs):
            return card, [item for _ in effs]
    return None
