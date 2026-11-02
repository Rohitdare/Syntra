"""Citation tag validation shared by Writer and its focused tests."""

from __future__ import annotations

import re
from collections.abc import Iterable

_TAG = re.compile(r"\[(S\d+)\]")


def validate_citations(text: str, allowed_tags: Iterable[str]) -> tuple[bool, set[str]]:
    """Return whether text contains a valid citation and the unknown citation tags."""
    allowed = set(allowed_tags)
    found = set(_TAG.findall(text))
    return bool(found & allowed), found - allowed
