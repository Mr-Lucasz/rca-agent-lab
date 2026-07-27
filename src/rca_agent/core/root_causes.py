from __future__ import annotations

from typing import Any

from .config import load_yaml
from .utils import UNKNOWN, fold


def resolve_root_cause(
    cause: Any,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve configured categories without discarding organization-specific labels."""

    entries = catalog or load_yaml("root-causes.yml").get("canonical", {})
    reported = str(cause or UNKNOWN).strip() or UNKNOWN
    reported_folded = fold(reported)
    for canonical_key, entry in entries.items():
        candidates = [
            canonical_key,
            entry.get("display_name", ""),
            *entry.get("aliases", []),
        ]
        if reported_folded in {fold(candidate) for candidate in candidates}:
            return {
                "canonical_key": canonical_key,
                "display_name": entry.get("display_name", reported),
                "axis": entry.get("axis", "unassessed"),
                "status": entry.get("status", "triage_signal"),
                "matched_catalog": True,
            }

    return {
        "canonical_key": None,
        "display_name": reported,
        "axis": "organization_specific_unassessed",
        "status": "triage_signal",
        "matched_catalog": False,
    }
