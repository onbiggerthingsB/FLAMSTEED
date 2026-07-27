"""Betting-content projection shared by archive and publisher builders.

Keys are removed recursively. Publisher bundles additionally scan every string
value so betting vocabulary cannot leak through provenance or prose.
"""

from __future__ import annotations

import copy
import re

from wcmodel.releases import BETTING_FIELD_DENYLIST, BETTING_VOCAB

_BETTING_WORD = re.compile(
    r"\b(?:" + "|".join(re.escape(word) for word in sorted(BETTING_VOCAB)) + r")\b",
    re.IGNORECASE,
)
_PUBLISHER_BANNER = (
    "Model forecasts · probabilities, not picks · not betting advice"
)
_APPROVED_DISCLAIMER = re.compile(r"\bnot betting advice\b", re.IGNORECASE)


def strip_betting(obj):
    """Return *obj* with every denylisted dictionary key removed."""
    if isinstance(obj, dict):
        return {
            key: strip_betting(value)
            for key, value in obj.items()
            if key not in BETTING_FIELD_DENYLIST
        }
    if isinstance(obj, list):
        return [strip_betting(value) for value in obj]
    return obj


def scan_betting_keys(obj) -> set[str]:
    """Return all denylisted keys found recursively in *obj*."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in BETTING_FIELD_DENYLIST:
                found.add(key)
            found |= scan_betting_keys(value)
    elif isinstance(obj, list):
        for value in obj:
            found |= scan_betting_keys(value)
    return found


def scan_betting_strings(obj) -> list[str]:
    """Return string values containing whole-word publisher-banned vocabulary."""
    found: list[str] = []
    if isinstance(obj, str):
        # Revision 2 mandates this exact disclaimer in the normalized banner
        # while also listing "betting" in the wire vocabulary. Exempt only the
        # approved negative phrase; any other occurrence remains a hard hit.
        candidate = _APPROVED_DISCLAIMER.sub("", obj)
        if _BETTING_WORD.search(candidate.lower()):
            found.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            found.extend(scan_betting_strings(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(scan_betting_strings(value))
    return found


def normalize_publisher_provenance(meta: dict) -> dict:
    """Return a publisher-safe copy of a bundle's metadata envelope."""
    out = copy.deepcopy(meta)
    provenance = out.get("provenance")
    if isinstance(provenance, dict):
        provenance["banner"] = _PUBLISHER_BANNER
        provenance.pop("is_synthetic", None)
    return out
