"""Blink templates: "Exile <target>, then return it to the battlefield under its owner's control".

The exiled card comes back as a new object (counters, Auras and damage are gone, enters-the-battlefield
triggers fire) and a token is gone for good. The ``blink`` kind (engine/kinds/permanents.py) does the
exile and the return. Optional modifiers: ``tapped``, ``transformed`` (returns on its back face),
``yours`` (under your control instead of its owner's), ``counter`` (a named counter on it) and
``delayed`` (at the beginning of the next end step).
Joined at the end of ``cards/__init__.py``.
"""
from __future__ import annotations

import re

_COUNT = {"one": 1, "two": 2}
_RETURN = (r"to the battlefield( tapped)?( transformed)? under "
           r"(its owner's|their owners'|their owner's|his owner's|her owner's|your) control"
           r"( with a (?:[+-]\d+/[+-]\d+|[a-z]+(?:-[a-z]+)?) counter on (?:it|them))?")


def _counter(text):
    if not text:
        return False
    from .cards.model import KEYWORDS
    name = text.lower().split(' with a ', 1)[1].split(' counter on ', 1)[0]
    if name in KEYWORDS or name in ('finality', 'stun') or re.fullmatch(r'[+-]\d+/[+-]\d+', name):
        return name
    return None                   # e.g. shield counters need their own replacement rules


def entry_counters(data):
    """Keep legacy boolean +1/+1 riders compatible with named return counters."""
    name = data.get('counter')
    return {name if isinstance(name, str) else '+1/+1': 1} if name else None


def entry_face(card, data):
    """The face a returned card enters as: a 'transformed' return enters on its back face."""
    if data.get('transformed') and card.back is not None:
        return card.back
    return card


def _singular(phrase):
    """"creatures you control" -> "creature you control" (the selector reads one noun)."""
    return re.sub(r"\b(\w+?)s\b(?= you control| you own| an opponent controls|$)", r"\1", phrase, count=1)


def _build(count_word, other, phrase, tapped, transformed, who, counter, delayed):
    from . import permanent_templates as pt
    from .cards import Effect, NO_MATCH
    n = _COUNT.get((count_word or "").lower(), 1)
    text = ("up to one " if count_word else "") + (other or "") + "target " + (_singular(phrase) if n > 1 else phrase)
    subj = pt.subject(text)
    if subj is None or subj[0] != "permanent" or _counter(counter) is None:
        return NO_MATCH          # None would mean "matched, no effect": the sentence would be dropped silently
    target, data = subj
    data = dict(data, tapped=bool(tapped), transformed=bool(transformed), yours=who.lower() == "your",
                counter=_counter(counter), delayed=delayed)
    effects = []
    for i in range(n):
        d = dict(data)
        if n > 1:
            d["distinct"] = True
        effects.append(Effect("blink", target=target, data=d))
    return effects


def _self(tapped, transformed, who, counter):
    from .cards import Effect, NO_MATCH
    if _counter(counter) is None:
        return NO_MATCH
    return Effect("blink", target="self", data={"tapped": bool(tapped), "transformed": bool(transformed),
                                                "yours": who.lower() == "your",
                                                "counter": _counter(counter), "delayed": False})


EFFECT_PATTERNS = [
    (r"BLINKROLL (.+)\|(\d+)", lambda m: _roll_effect(m[1], int(m[2]))),
    (r"BLINKTAKE (.+)", lambda m: _linked_exile(m[1])),
    (r"BLINKLINKRETURN " + _RETURN, lambda m: _linked_return(m[1], m[2], m[3], m[4])),
    (r"exile (?:up to (one|two) )?(another |other )?target (.+?)(, then| and then) return (?:it|him|her|that card|those cards|them) "
     + _RETURN, lambda m: _build(m[1], m[2], m[3], m[5], m[6], m[7], m[8], False)),
    (r"exile ~(, then| and then) return (?:it|him|her) " + _RETURN,
     lambda m: _self(m[2], m[3], m[4], m[5])),
    (r"BLINKLATER (?:up to (one|two) )?(another |other )?target (.+?)\|" + _RETURN,
     lambda m: _build(m[1], m[2], m[3], m[4], m[5], m[6], m[7], True)),
]

SUBS = [
    (re.compile(r"exile (?:up to (one|two) )?(another |other )?target ([^.,]+?)\. return (?:it|him|her|that card|the exiled card|those cards|them) "
                + _RETURN + r" at the beginning of the next end step\.", re.I),
     lambda m: "BLINKLATER " + (f"up to {m[1]} " if m[1] else "") + (m[2] or "") + "target " + m[3] + "|"
               + "to the battlefield" + (m[4] or "") + (m[5] or "") + " under " + m[6] + " control" + (m[7] or "") + "."),
]


def _linked_subject(phrase):
    from .permanent_templates import subject
    return subject(phrase)


def _linked_exile(phrase):
    from .cards import Effect, NO_MATCH
    subj = _linked_subject(phrase)
    if subj is None or subj[0] not in ('permanent', 'group'):
        return NO_MATCH
    target, data = subj
    return Effect('blink_link_exile', target='none' if target == 'group' else target,
                  data=dict(data, group=target == 'group'))


def _linked_return(tapped, transformed, who, counter):
    from .cards import Effect, NO_MATCH
    if _counter(counter) is None:
        return NO_MATCH
    return Effect('blink_link_return', data={'tapped': bool(tapped), 'transformed': bool(transformed),
                                             'yours': who.lower() == 'your', 'counter': _counter(counter)})


def prepare_linked(text):
    """Keep separate exile/return abilities linked to their source's exact objects.

    Rewrite only when a simple battlefield exile and an explicit linked return both
    exist. Complex choices, copied cards, attachments and selected subsets stay visible.
    This runs before the legacy two-trigger O-ring rewrite, whose automatic return
    cannot preserve the ordering when the source leaves before its ETB resolves.
    """
    text = prepare_roll(text)
    rx = re.compile(r"return (?:the exiled cards?|all cards exiled with (?:~|it)) " + _RETURN + r"\.", re.I)
    if not rx.search(text):
        return text
    changed = False

    def exile(m):
        nonlocal changed
        phrase = m[1]
        # Don't drop an exclusion while normalizing the noun phrase.
        if phrase.lower().endswith(' other than ~'):
            phrase = 'other ' + phrase[:-len(' other than ~')]
        subj = _linked_subject(phrase)
        if subj is None or subj[0] not in ('permanent', 'group'):
            return m[0]
        changed = True
        return 'BLINKTAKE ' + phrase + '.'

    rewritten = re.sub(r'\bexile ((?:(?:up to one )?(?:another |other )?target |all )[^.\n]+)\.', exile, text, flags=re.I)
    if not changed:
        return text
    rewritten = rx.sub(lambda m: 'BLINKLINKRETURN to the battlefield' + (m[1] or '') + (m[2] or '') + ' under '
                       + m[3] + ' control' + (m[4] or '') + '.', rewritten)
    # A rewritten return that shares a line with its exile would be swallowed by the exile's own
    # trigger pattern ("When ~ enters, ..."), so keep every BLINKLINKRETURN on its own line.
    rewritten = re.sub(r"\.\s+(?=(?:when|whenever)\b[^.\n]*?BLINKLINKRETURN)", ".\n", rewritten, flags=re.I)
    rewritten = re.sub(r"\.\s+(?=BLINKLINKRETURN)", ".\n", rewritten)
    return rewritten


def prepare_roll(text):
    """Recognize the complete two-outcome mass-blink table as one instruction.

    The batch must stay with this spell resolution, even if another copy resolves.
    Matching the entire table also keeps unsupported outcome riders visible.
    """
    returned = r"return those cards to the battlefield under their (?:owner's|owners') control"
    later = returned + r" at the beginning of the next end step\."
    m = re.fullmatch(r"exile (all [^.\n]+), then roll a d20\.\s+1[—–-](\d+) \| " + later
                     + r"\s+(\d+)[—–-]20 \| " + returned + r", then exile them again\. " + later,
                     text.strip(), re.I)
    if not m or not 1 <= int(m[2]) < 20 or int(m[3]) != int(m[2]) + 1:
        return text
    from .permanent_templates import subject
    subj = subject(m[1])
    if subj is None or subj[0] != 'group':
        return text
    return f'BLINKROLL {m[1]}|{m[3]}.'


def _roll_effect(phrase, threshold):
    from .cards import Effect, NO_MATCH
    from .permanent_templates import subject
    subj = subject(phrase)
    if subj is None or subj[0] != 'group':
        return NO_MATCH
    return Effect('blink_roll', data=dict(subj[1], repeat_above=threshold))


def exile_refs(game, permanents):
    """Freeze physical IDs and exile generations, including identical card names."""
    refs = []
    for permanent in permanents:
        owner, card = permanent.owner, permanent.front
        if (permanent in permanent.controller.battlefield and game.leave_battlefield(permanent, 'exile')
                and not card.is_token and card in owner.exile):
            refs.append((owner.exile, owner.exile.reference(card)))
    return refs


def return_refs(game, player, refs, data):
    from .backlog_templates import entry_batch
    returned = []
    with entry_batch(game):
        for zone, ref in refs:
            card = ref.find(zone)
            if card is None:
                continue
            owner = player if data.get('yours') else card.owner
            zone.remove(card)
            face = entry_face(card, data)
            permanent = game.enter_battlefield(owner, face, tapped=bool(data.get('tapped')),
                                               counters=entry_counters(data),
                                               physical_card=card if face is not card else None)
            if permanent is not None:
                returned.append(permanent)
    return returned
