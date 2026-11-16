"""Registers cx_tokens."""
from ... import cx_tokens as _cx_tokens
from ... import chance_templates as _chance_templates

EFFECT_PATTERNS = _cx_tokens.EFFECT_PATTERNS
FACE_LINE_PARSERS = (_chance_templates.face_line, _cx_tokens.face_line)
