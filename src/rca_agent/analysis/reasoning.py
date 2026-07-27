from __future__ import annotations

from typing import Any

from ..core.causal_signals import causal_signal_config
from ..core.config import load_yaml
from ..core.utils import UNKNOWN, redact


def build_evidence(bugs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reliability_config = load_yaml("evidence-reliability.yml")
    source_config = reliability_config.get("source_types", {})
    evidence: list[dict[str, Any]] = []
    counter = 1
    signal_sources = causal_signal_config()["sources"].values()
    fields = (
        *(
            (source["field"], source["source_type"])
            for source in signal_sources
        ),
        ("actual_behavior", "actual_behavior"),
        ("description", "description"),
        ("title", "title"),
    )
    for bug in bugs:
        for field, source_type in fields:
            value = bug.get(field, UNKNOWN)
            if value == UNKNOWN:
                continue
            reliability = source_config.get(source_type)
            if not isinstance(reliability, dict):
                raise ValueError(
                    f"Fonte sem regra em config/evidence-reliability.yml: {source_type}"
                )
            evidence.append(
                {
                    "evidence_id": f"EV-{counter:04d}",
                    "source_type": source_type,
                    "source_ref": f"{bug['source_file']}#row={bug['source_row']}:{field}",
                    "bug_id": bug["bug_id"],
                    "excerpt": redact(value),
                    "reliability": reliability["default_reliability"],
                    "reliability_basis": reliability["basis"],
                    "evidence_role": reliability["evidence_role"],
                    "epistemic_status": reliability["epistemic_status"],
                    "observed_at": None,
                }
            )
            counter += 1
    return evidence

