"""Bounded hand/library sizes, life, permanent counts and source-state conditions."""
import re

from .cards.model import KEYWORDS, NUMBERS

_NUMBER = r"(?:\d+|zero|" + "|".join(word for word in NUMBERS if word not in ('a', 'an')) + r")"
_PERMANENTS = {'permanent', 'creature', 'land', 'artifact', 'enchantment', 'planeswalker', 'token',
               'nonland permanent', 'artifact creature'}


def _threshold(number, comparison):
    value = int(number) if number.isdigit() else 0 if number == 'zero' else NUMBERS[number]
    operator = '>=' if comparison == ' or more' else '<=' if comparison else '=='
    return operator + str(value)


def _permanent_kind(description):
    singular = description[:-1] if description.endswith('s') else description
    return singular if singular in _PERMANENTS else ''


def parse(phrase):
    phrase = phrase.lower().strip()
    if phrase == "you have no cards in hand":
        return "hand==0"
    if phrase == "you have a card in hand":
        return "hand>=1"
    if phrase == 'you have no cards in your library':
        return 'library==0'
    library = re.fullmatch(r'(?:you have|there are) (?:exactly )?(' + _NUMBER +
                           r')( or more| or fewer| or less)? cards? in your library', phrase)
    if library:
        return 'library' + _threshold(library[1], library[2])
    permanents = re.fullmatch(r'you control (?:(?:exactly )?(' + _NUMBER +
                              r')( or more| or fewer| or less)?|(a|an|no)) (other )?([a-z ]+)', phrase)
    if permanents:
        kind = _permanent_kind(permanents[5])
        if kind:
            threshold = _threshold(permanents[1], permanents[2]) if permanents[1] else '==0' if permanents[3] == 'no' else '>=1'
            return 'control:' + ('other ' if permanents[4] else '') + kind + ':' + threshold
    if phrase in ("~ is tapped", "~ is untapped"):
        return "source_" + phrase.split()[-1]
    creatures = re.fullmatch(r"you control no creatures(?: with ([a-z ]+))?", phrase)
    if creatures and (not creatures[1] or creatures[1] in KEYWORDS):
        return "no_creatures_with:" + (creatures[1] or "")
    match = re.fullmatch(r"you have (?:exactly )?(" + _NUMBER + r")( or more| or fewer| or less)? (cards? in hand|life)", phrase)
    if match:
        word, comparison, resource = match.groups()
        number = int(word) if word.isdigit() else 0 if word == "zero" else NUMBERS[word]
        operator = ">=" if comparison == " or more" else "<=" if comparison else "=="
        return ("life" if resource == "life" else "hand") + operator + str(number)
    return ""


def check(player, condition, item):
    """None means this helper does not own the condition."""
    match = re.fullmatch(r"(hand|life|library)(==|>=|<=)(\d+)", condition)
    if match:
        resource, operator, number = match.groups()
        value = player.life if resource == "life" else len(player.library) if resource == 'library' else len(player.hand)
        number = int(number)
        return value == number if operator == "==" else value >= number if operator == ">=" else value <= number
    control = re.fullmatch(r'control:(other )?([a-z ]+):(==|>=|<=)(\d+)', condition)
    if control:
        other, kind, operator, number = control.groups()
        if kind not in _PERMANENTS:
            return False
        source = getattr(item, 'source', None)
        def matches(permanent):
            card = permanent.card
            return {'permanent': True, 'creature': permanent.is_creature, 'land': card.is_land,
                    'artifact': card.is_artifact, 'enchantment': 'Enchantment' in card.types,
                    'planeswalker': permanent.is_planeswalker, 'token': card.is_token,
                    'nonland permanent': not card.is_land,
                    'artifact creature': card.is_artifact and permanent.is_creature}[kind]
        count = sum(matches(x) for x in player.battlefield if not (other and x is source))
        number = int(number)
        return count == number if operator == '==' else count >= number if operator == '>=' else count <= number
    if condition in ("source_tapped", "source_untapped"):
        source = getattr(item, "source", None)
        return source is not None and bool(source.tapped) == (condition == "source_tapped")
    if condition.startswith("no_creatures_with:"):
        keyword = condition[len("no_creatures_with:"):]
        return not any(not keyword or creature.has(keyword) for creature in player.creatures)
    return None
