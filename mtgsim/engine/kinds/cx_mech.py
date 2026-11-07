"""Handlers for mtgsim/cx_mech.py."""
from __future__ import annotations

from . import kind
from ... import cx_mech


@kind("cx_recover")
def recover(game, item, **_):
    cx_mech.resolve_recover(game, item)
