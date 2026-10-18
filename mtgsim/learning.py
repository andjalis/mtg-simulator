"""Learn uses a player's outside-game Lesson pool or a discard followed by a draw."""
from __future__ import annotations


def has_learn(card):
    return (any(e.kind == 'learn' for e in card.spell_effects + card.etb_effects)
            or any(e.kind == 'learn' for t in card.triggers for e in t.effects)
            or any(e.kind == 'learn' for a in card.activated for e in a.effects)
            or card.adventure is not None and has_learn(card.adventure))


def choose(game, me, lessons):
    from .ai import card_value
    if lessons:
        return 'lesson', max(lessons, key=lambda c: (game.spell_payable(me, c), card_value(c)))
    pitches = game.hook(me, 'choose_rummage')(game, me, 1)
    return ('discard', pitches[0]) if pitches else None


def value(game, me):
    if any('Lesson' in c.subtypes for c in me.sideboard):
        return 2.0  # one additional card
    return 0.3 if game.hook(me, 'choose_rummage')(game, me, 1) else 0.0


def resolve(game, p):
    from .cards import CardDef
    lessons = [c for c in p.sideboard if 'Lesson' in c.subtypes]
    choice = game.hook(p, 'choose_learn')(game, p, list(lessons))
    if not isinstance(choice, (tuple, list)) or len(choice) != 2:
        return
    mode, card = choice
    if not isinstance(card, CardDef):
        return
    if mode == 'lesson' and card in lessons:
        p.sideboard.remove(card)
        p.hand.append(card)
        game.log(f'reveals {card.name} (learn), putting it into hand', p)
    elif mode == 'discard' and card in p.hand:
        game.discard_card(p, card)
        game.draw(p)
        game.log(f'discards {card.name} and draws (learn)', p)
