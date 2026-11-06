"""Game objects: permanents, players and stack items, plus shared rules constants."""
from __future__ import annotations

import dataclasses
import re

from .. import auras, counting
from ..cards import BASIC_MANA, KEYWORDS, CardDef, Effect, Trigger
from .. import continuous, cx_static_combat
