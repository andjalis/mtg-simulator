"""Named creature tokens and supported single quoted token abilities."""
import re

_COUNT = r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
_BODY = (r"(?P<count>" + _COUNT + r") (?P<tapped>tapped )?(?P<legendary>legendary )?"
         r"(?P<power>\d+)/(?P<toughness>\d+) (?P<description>(?:\w+ )+?)creature tokens?(?P<rest>.*)")
_NAME = r"[A-Z0-9][\w'’,-]*(?: (?:[A-Z0-9][\w'’,-]*|of|the|to|and|a|an|in|with))*"


def build(text, temporary_haste=False, extra_ability=''):
    from .cards.model import NO_MATCH
    from .cards.patterns import _token
    match = re.fullmatch(r"create " + _BODY, text, re.I)
    name = None
    if match is None:
        prefix = re.fullmatch(r"create (.+?), (" + _BODY + r")", text, re.I)
        if prefix is None:
            return NO_MATCH
        name = prefix[1]
        match = prefix
    rest = match['rest'].strip()
    named = re.fullmatch(r"named (.+?)(?: with (.+))?", rest, re.I)
    after_keywords = re.fullmatch(r"with (.+?) named (.+)", rest, re.I)
    abilities = ''
    if named:
        if name:
            return NO_MATCH
        name, abilities = named[1], named[2] or ''
    elif after_keywords:
        if name:
            return NO_MATCH
        abilities, name = after_keywords[1], after_keywords[2]
    elif rest:
        if not rest.lower().startswith('with '):
            return NO_MATCH
        abilities = rest[5:]
    if name and not re.fullmatch(_NAME, name):
        return NO_MATCH  # do not interpret a trailing timing/restriction clause as a name
    quoted = re.fullmatch(r'(?:(.+?)(?:,? and|,) )?"([^"\n]+)"', abilities)
    if '"' in abilities and not quoted:
        return NO_MATCH
    if extra_ability and quoted:
        return NO_MATCH
    if not (name or match['legendary'] or quoted or temporary_haste or extra_ability):
        return NO_MATCH  # ordinary token templates retain their existing path
    effect = _token(match['count'], match['power'], match['toughness'], match['description'],
                    quoted[1] or '' if quoted else abilities, ability=extra_ability or (quoted[2] if quoted else ''))
    if effect is NO_MATCH:
        return NO_MATCH
    effect.data.update({k: v for k, v in {'token_name': name, 'legendary': bool(match['legendary']),
                                         'tapped': bool(match['tapped']),
                                         'temp_keywords': ('haste',) if temporary_haste else ()}.items() if v})
    return effect


EFFECT_PATTERNS = [(r'create .+creature tokens?.*', lambda m: build(m[0])),
                   (r'TOKENHASTE (.+)', lambda m: build(m[1], temporary_haste=True)),
                   (r'TOKENABILITY (.+) \|\| (.+)', lambda m: build(m[1], extra_ability=m[2]))]


def _attach_ability(match):
    from .cards.model import NO_MATCH
    if build(match[1], extra_ability=match[2]) is NO_MATCH:
        return match[0]
    return 'TOKENABILITY ' + match[1] + ' || ' + match[2].rstrip('.') + '.'


SUBS = [(re.compile(r'(create (?:a|one) (?:legendary )?\d+/\d+ (?:\w+ )+?creature token[^."\n]*)\.'
                    r' It gains haste until end of turn\.', re.I), lambda m: 'TOKENHASTE ' + m[1] + '.')]
SUBS += [(re.compile(r'(create [^."\n]+?creature tokens?[^."\n]*)\. (?:It has|They have) "([^".\n]+\.?)"\.?', re.I),
          _attach_ability)]
