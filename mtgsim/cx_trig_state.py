"""State triggers "When you control no <noun phrase>, sacrifice ~." (#404):

    When you control no artifacts, sacrifice ~.              (Covetous Dragon)
    When you control no other creatures, sacrifice ~.        (Emperor Crocodile)
    When you control no enchantments, sacrifice ~.           (Tethered Griffin)

Like the land version (``CardDef.needs_land``), the condition is checked with the state-based actions and the
permanent is sacrificed as soon as you control none; the noun phrase is read by ``permanent_templates.selector``
(the effect grammar's reader) and kept as ``advanced_rules["needs_np"]``.
"""
from __future__ import annotations

import re

_LINE = re.compile(r"When you control no (.+), sacrifice ~\.")


def parse_line(line: str, extra: dict) -> bool:
    m = _LINE.fullmatch(line)
    if not m:
        return False
    from .permanent_templates import selector
    spec = selector(m[1], plural=True)
    if spec is None or "controller" in spec or "owner" in spec:
        return False
    extra.setdefault("advanced_rules", {})["needs_np"] = spec
    return True


def unmet(game, perm) -> bool:
    """True when the permanent's "you control no ..." state trigger applies now."""
    spec = perm.card.advanced_rules.get("needs_np") if perm.card.advanced_rules else None
    if not spec:
        return False
    from .permanent_templates import matches
    return not any(matches(game, x, spec, perm.controller, perm) for x in perm.controller.battlefield)
