"""Registration files for mechanic modules: how a new template module joins the parser without editing a shared line.

Every ``NNNN_<name>.py`` file in this package is imported once, in filename order, at the end of
``mtgsim/cards/__init__.py``. A file imports its mechanic module and names what it adds, using any of:

``EFFECT_PATTERNS``     appended to the effect templates (earlier patterns win, so later files only see
                        sentences the earlier ones did not take)
``PRIORITY_PATTERNS``   put in front of every effect template registered so far
``SUBS``                appended to the sentence substitutions
``TRIGGERS``            appended to the trigger templates
``KEYWORDS``            added to the keyword set
``FACE_LINE_PARSERS``   put in front of the whole-line parsers (``handle(st, line)`` returns the line or None)
``LINE_HOOKS``          ``{stage: (fn, ...)}``: ``fn(line, st)`` returns True once it handled the line; each stage
                        runs at one fixed point inside a face-line parser of ``cards/face_lines.py``
                        (see ``face_lines.LINE_HOOK_STAGES``), after the hooks that were written into it by hand
``TARGET_CHOOSERS``     ``{kind: fn(game, me, eff, legal, mine, theirs)}``: how the default AI picks the target of an
                        effect of that kind (``engine/policy.default_choose_target`` asks it first, before its own
                        chain; what ``fn`` returns is the choice, None for no target). One chooser per kind.

Order: files load in sorted filename order and each one's lists are added in that order, so the number prefix
decides precedence. To add a module, create ``NNNN_<your_module>.py`` with the next free number above the highest
one (gaps of ten; two branches picking the same number is fine, the name breaks the tie). Nothing else changes, so
two branches that each add a file never conflict. ``tests/test_registry.py`` checks the names and the fields.
"""
from __future__ import annotations

import importlib
import pkgutil
import re

FILE_NAME = re.compile(r"\d{4}_[a-z0-9_]+")
FIELDS = ("PRIORITY_PATTERNS", "EFFECT_PATTERNS", "SUBS", "TRIGGERS", "KEYWORDS", "FACE_LINE_PARSERS", "LINE_HOOKS",
          "TARGET_CHOOSERS")
# Filled by load_all from the TARGET_CHOOSERS fields; read by engine/policy.default_choose_target. It lives here
# (not in the engine) because the registry loads with mtgsim.cards, before the engine is imported.
TARGET_CHOOSERS: dict = {}


def file_names() -> list:
    """The registration files of this package, in load order."""
    names = sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.ispkg)
    bad = [n for n in names if not FILE_NAME.fullmatch(n)]
    if bad:
        raise ImportError(f"mtgsim/cards/registry: badly named registration file(s) {bad}; use NNNN_<name>.py")
    return names


def load_all(effect_patterns: list, subs: list, triggers: list, keywords: set, parse_module, line_hooks: dict,
             target_choosers: dict = TARGET_CHOOSERS) -> list:
    """Import every registration file in order and add its fields to the given tables (in place).

    Returns the loaded modules (for tests and the coverage tooling)."""
    loaded = []
    for name in file_names():
        mod = importlib.import_module(f"{__name__}.{name}")
        unknown = [a for a in vars(mod) if a.isupper() and a not in FIELDS]
        if unknown:
            raise ImportError(f"{mod.__name__}: unknown registration field(s) {unknown}; known: {FIELDS}")
        if hasattr(mod, "PRIORITY_PATTERNS"):
            effect_patterns[:0] = mod.PRIORITY_PATTERNS
        effect_patterns += getattr(mod, "EFFECT_PATTERNS", ())
        subs += getattr(mod, "SUBS", ())
        triggers += getattr(mod, "TRIGGERS", ())
        keywords.update(getattr(mod, "KEYWORDS", ()))
        if hasattr(mod, "FACE_LINE_PARSERS"):
            parse_module._FACE_LINE_PARSERS = tuple(mod.FACE_LINE_PARSERS) + parse_module._FACE_LINE_PARSERS
        for stage, hooks in getattr(mod, "LINE_HOOKS", {}).items():
            if stage not in line_hooks:
                raise ImportError(f"{mod.__name__}: unknown LINE_HOOKS stage {stage!r}; known: {sorted(line_hooks)}")
            line_hooks[stage].extend(hooks)
        for k, chooser in getattr(mod, "TARGET_CHOOSERS", {}).items():
            if k in target_choosers:
                raise ImportError(f"{mod.__name__}: a target chooser for kind {k!r} is already registered")
            target_choosers[k] = chooser
        loaded.append(mod)
    return loaded
