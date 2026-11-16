"""A "where X is ..." definition carried to the later sentences of the same ability (#746).

    Then you draw X cards and gain X life, where X is the number of artifact tokens you control.
    The Ice Dancer deals X damage to each opponent.                                   (The Ice Dancer)

The second sentence's X is the first sentence's X, but it parses on its own as an X-cost amount (``data["x"]``), which
a trigger or a spell without {X} resolves as 0. ``carry(effects)`` runs after a text's sentences are parsed: an effect
still marked ``x`` after an effect counted by a "where X is" (``_parse_effects`` gives those ``xq`` and ``xq_size``)
gets that count instead. Only counts that stand on their own are carried: a quantity of another object ("its power",
"that spell's mana value") may not mean the same thing in the later sentence.
"""
from __future__ import annotations

import dataclasses

_OWN = ("count", "cxq", "domain", "party", "devotion")


def carry(effects) -> None:
    last = None
    for i, e in enumerate(effects):
        if "xq_size" in e.data and isinstance(e.data.get("xq"), tuple):
            spec = e.data["xq"]
            last = spec if spec and spec[0] in _OWN else None
        elif last is not None and e.data.get("x") is True and not e.data.get("xq"):
            data = {k: v for k, v in e.data.items() if k != "x"}
            data.update(xq=last, xq_size=False)
            effects[i] = dataclasses.replace(e, amount=max(e.amount, 1), data=data)
