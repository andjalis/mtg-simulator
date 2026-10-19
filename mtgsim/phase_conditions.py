"""Bounded hand-size, life-total and source-state conditions for effect templates."""
import re

from .cards.model import KEYWORDS, NUMBERS

_NUMBER = r"(?:\d+|zero|" + "|".join(word for word in NUMBERS if word not in ('a', 'an')) + r")"


def parse(phrase):
    phrase = phrase.lower().strip()
    if phrase == "you have no cards in hand":
        return "hand==0"
    if phrase == "you have a card in hand":
        return "hand>=1"
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
    match = re.fullmatch(r"(hand|life)(==|>=|<=)(\d+)", condition)
    if match:
        resource, operator, number = match.groups()
        value = player.life if resource == "life" else len(player.hand)
        number = int(number)
        return value == number if operator == "==" else value >= number if operator == ">=" else value <= number
    if condition in ("source_tapped", "source_untapped"):
        source = getattr(item, "source", None)
        return source is not None and bool(source.tapped) == (condition == "source_tapped")
    if condition.startswith("no_creatures_with:"):
        keyword = condition[len("no_creatures_with:"):]
        return not any(not keyword or creature.has(keyword) for creature in player.creatures)
    return None
