"""Additional mill quantities and explicit selections of cards milled this way.

Reuses the existing mill and mill_pick effects, including per-resolution card
tracking. Unknown filters and replacement clauses are deliberately not widened.
"""
from __future__ import annotations

_NUMBERS = dict(zip('eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(),
                    range(11, 20)))
_NUMBERS.update(dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10))))
_ONES = dict(zip('one two three four five six seven eight nine'.split(), range(1, 10)))
_COUNT = '|'.join(_NUMBERS) + r'|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)-(?:' + '|'.join(_ONES) + ')'
_WHO = r'you|target player|target opponent|that player|each opponent|each player'


def _mill(match, *, variable=False):
    from .cards.model import Effect
    # Quantities belong to the resolved effect; the shared X path uses item.x.
    who = (match['who'] or '').lower()
    target = {'target player': 'player', 'target opponent': 'player', 'that player': 'that_player',
              'each opponent': 'each_opponent', 'each player': 'each_player'}.get(who, 'none')
    amount = 0
    if not variable:
        words = match['n'].lower().split('-')
        amount = _NUMBERS[words[0]] + (_ONES[words[1]] if len(words) > 1 else 0)
    effect = Effect('mill', amount, target=target, filter='opp' if who == 'target opponent' else '',
                    data={'x': True} if variable else {})
    return [effect, Effect('gain_life', data={'x': True})] if variable and match['gain'] else effect


def _pick(match):
    from .cards.model import Effect, NO_MATCH
    from .milling import _types, _number
    types = _types(match['what'])
    if types is None:
        return NO_MATCH
    count = match['n'].lower()
    dest = match['dest'].lower()
    return Effect('mill_pick', 0 if count == 'any number of' else _number(count.split()[-1]), data={
        'types': types, 'adventure': False, 'all': count == 'any number of',
        'dest': 'hand' if 'hand' in dest else 'top' if 'top' in dest else 'battlefield',
        'tapped': dest.endswith('tapped')})


EFFECT_PATTERNS = [
    (rf'(?:(?P<who>{_WHO}) )?mills? (?P<n>{_COUNT}) cards?', _mill),
    (rf'(?:(?P<who>{_WHO}) )?mills? X cards?(?P<gain> and you gain X life)?',
     lambda m: _mill(m, variable=True)),
    (r'(?:you may )?(?:put|return) (?P<n>an?|up to (?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)|any number of) '
     r'(?P<what>[\w ,/-]+?) cards? (?:from among (?:the )?cards milled this way|milled this way) '
     r'(?P<dest>into your hand|to your hand|onto the battlefield(?: tapped)?|on top of your library)'
     r'(?: under your control)?', _pick),
]
SUBS = []
