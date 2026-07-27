from __future__ import annotations

from typing import Any

Kpi = dict[str, Any]


def enrich_kpis(kpis: list[Kpi]) -> list[Kpi]:
    """Mark configured factual metrics as pending semantic interpretation."""

    for kpi in kpis:
        kpi.update(
            {
                "status": "pending_review",
                "insight": "",
                "detailed_analysis": "",
                "requires_human_review": True,
            }
        )
    return kpis
