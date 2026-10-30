"""Manifest effect kinds (see mtgsim.manifest).

"manifest dread" (one) is the foundation's kind (engine/kinds/permanents.py);
the variants the foundation kind can't express — "manifest dread twice" and
"manifest dread, then attach this Equipment" — live here.
"""
from . import kind


@kind("manifest")
def manifest(game, p, eff, item, **_):
    from ... import manifest as _manifest
    _manifest.manifest(game, p, eff, item)


@kind("manifest_dread_more")
def manifest_dread_more(game, p, eff, item, **_):
    from ... import manifest as _manifest
    _manifest.manifest_dread(game, p, eff, item)
