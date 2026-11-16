"""A permanent put into its owner's library at a position (#632):

    The owner of target nonland permanent shuffles it into their library.                    (Cathartic Parting)
    Target creature's owner shuffles it into their library.                                  (Ice Magic)
    At the beginning of the end step, this creature's owner shuffles it into their library.  (Blitz Hellion)
    The owner of target nonland permanent puts it into their library second from the top or on the bottom.
                                                                                             (Deem Inferior)
    Put target nonland historic permanent into its owner's library fourth from the top.      (Lost to Legend)
    Put target permanent you own on the bottom of your library.                              (Tel-Jilad Stylus)

The owner-as-subject sentences are rewritten (SUBS) to the imperative the grammar already reads ("shuffle target
creature into its owner's library", cx_grammar_zones, kind cx_tuck); "Nth from the top" is a verb here with the
same kind and ``where`` = N (Game.put_in_library: N = Nth from the top).

"Second from the top or on the bottom": the owner chooses, in their own interest: second from the top, so they draw
it again soon (a token ceases to exist either way).

Not read: "enchanted creature" (no object for it), "just beneath the top X cards" (X), "then draws two cards" after
the owner's shuffle (the owner draws, Oblation), a spell target (Commit).
"""
from __future__ import annotations

import re

from .cx_grammar import verb
from .cx_grammar_zones import _parts

_NTH = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7}

SUBS = [
    (re.compile(r"\b(?:the owner of (target [^.;]+?)|(target [^.;']+?)'s owner) shuffles it into their library\b",
                re.I),
     lambda m: f"shuffle {m[1] or m[2]} into its owner's library"),
    (re.compile(r"(?<!\w)(?:~|this (?:creature|permanent|artifact|enchantment))'s owner shuffles it into their "
                r"library\b", re.I),
     lambda m: "shuffle ~ into its owner's library"),
    (re.compile(r"\b(?:the owner of (target [^.;]+?)|(target [^.;']+?)'s owner) puts it into their library second "
                r"from the top or on the bottom\b", re.I),
     lambda m: f"put {m[1] or m[2]} into its owner's library second from the top"),
    (re.compile(r"\bput (target [^.;]+? you own) (on top of|on the bottom of) your library\b", re.I),
     lambda m: f"put {m[1]} {m[2]} its owner's library"),
]


@verb(r"put (.+?) into (?:its|their) owner(?:'s|s') librar(?:y|ies) (second|third|fourth|fifth|sixth|seventh) from "
      r"the top", heads=("put",), subjects=("imperative",))
def put_nth(m, clause):
    """"Put target creature into its owner's library third from the top": cx_tuck at that depth (one target only)."""
    if clause.duration:
        return None
    parts = _parts("cx_tuck", m[1])
    if parts is None or len(parts) > 1 or parts[0].obj.kind == "group" or parts[0].obj.copies > 1:
        return None
    parts[0].data = {"where": _NTH[m[2].lower()], "side": "theirs"}
    return parts
