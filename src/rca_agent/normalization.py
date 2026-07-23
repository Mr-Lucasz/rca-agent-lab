from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .config import load_yaml
from .utils import UNKNOWN, clean_text, fold, has_injection_signal, parse_datetime

CANONICAL_FIELDS = [
    "bug_id",
    "title",
    "severity",
    "description",
    "expected_behavior",
    "actual_behavior",
    "preconditions",
    "bug_type",
    "root_cause_category",
    "root_cause_cluster",
    "affected_module",
    "environment",
    "status",
    "created_at",
    "detected_at",
    "resolved_at",
    "reopened",
    "dev_analysis_notes",
    "qa_analysis_notes",
    "version",
    "team",
    "prd_reference",
]


def _field_lookup() -> dict[str, str]:
    aliases = load_yaml("aliases.yml").get("fields", {})
    lookup: dict[str, str] = {}
    for canonical, names in aliases.items():
        lookup[fold(canonical).replace(" ", "_")] = canonical
        for name in names:
            lookup[fold(name).replace(" ", "_")] = canonical
    return lookup


def _value_map(filename: str) -> dict[str, str]:
    canonical = load_yaml(filename).get("canonical", {})
    lookup: dict[str, str] = {}
    for target, details in canonical.items():
        aliases = details.get("aliases", []) if isinstance(details, dict) else details
        lookup[fold(target)] = target
        for alias in aliases or []:
            lookup[fold(alias)] = target
    return lookup


def _normalize_bool(value: Any) -> str:
    normalized = fold(value)
    if normalized in {"true", "1", "sim", "yes", "y", "reopened", "reaberto"}:
        return "true"
    if normalized in {"false", "0", "nao", "no", "n", "closed", "fechado"}:
        return "false"
    return UNKNOWN


def normalize(
    raw_records: list[dict[str, Any]], source: str | Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lookup = _field_lookup()
    severity_map = _value_map("severity.yml")
    bug_type_map = _value_map("bug-types.yml")
    cause_map = _value_map("root-causes.yml")
    environment_map = _value_map("environments.yml")
    bugs: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    missing = Counter()
    id_counts = Counter()
    injection_rows: list[int] = []
    source_path = str(Path(source).expanduser().resolve())

    for index, raw in enumerate(raw_records, start=2):
        mapped = {field: UNKNOWN for field in CANONICAL_FIELDS}
        for raw_key, raw_value in raw.items():
            key = fold(raw_key).replace(" ", "_")
            canonical = lookup.get(key)
            if canonical:
                mapped[canonical] = clean_text(raw_value)
        if mapped["bug_id"] == UNKNOWN:
            mapped["bug_id"] = f"UNKNOWN-L{index}"
            issues.append({"code": "missing_id", "source_row": index, "severity": "warning"})
        for field in ("title", "description", "expected_behavior", "actual_behavior"):
            if mapped[field] == UNKNOWN:
                missing[field] += 1
        mapped["severity"] = severity_map.get(fold(mapped["severity"]), mapped["severity"])
        mapped["bug_type"] = bug_type_map.get(fold(mapped["bug_type"]), mapped["bug_type"])
        mapped["root_cause_category"] = cause_map.get(
            fold(mapped["root_cause_category"]), mapped["root_cause_category"]
        )
        mapped["environment"] = environment_map.get(fold(mapped["environment"]), mapped["environment"])
        mapped["reopened"] = _normalize_bool(mapped["reopened"])

        for date_field in ("created_at", "detected_at", "resolved_at"):
            value = mapped[date_field]
            if value != UNKNOWN and parse_datetime(value) is None:
                issues.append(
                    {"code": "invalid_date", "field": date_field, "source_row": index, "value": value}
                )
                mapped[date_field] = UNKNOWN

        unsafe_fields = [
            field for field in CANONICAL_FIELDS if has_injection_signal(mapped.get(field, UNKNOWN))
        ]
        if unsafe_fields:
            injection_rows.append(index)
            issues.append(
                {"code": "prompt_injection_signal", "source_row": index, "fields": unsafe_fields}
            )

        mapped.update(
            {
                "source_file": source_path,
                "source_row": index,
                "cluster_id": UNKNOWN,
                "duplicate_family_id": UNKNOWN,
                "agent_suggested_severity": UNKNOWN,
                "agent_suggested_bug_type": UNKNOWN,
                "agent_suggested_root_cause_category": UNKNOWN,
                "agent_suggestion_confidence": UNKNOWN,
                "agent_suggestion_rationale": UNKNOWN,
                "agent_review_status": "insufficient_evidence",
            }
        )
        id_counts[mapped["bug_id"]] += 1
        bugs.append(mapped)

    duplicate_ids = sorted(identifier for identifier, count in id_counts.items() if count > 1)
    for identifier in duplicate_ids:
        issues.append({"code": "duplicate_id", "bug_id": identifier, "count": id_counts[identifier]})

    usable_metrics = sum(1 for bug in bugs if bug["title"] != UNKNOWN or bug["description"] != UNKNOWN)
    causal_usable = sum(
        1
        for bug in bugs
        if bug["dev_analysis_notes"] != UNKNOWN or bug["qa_analysis_notes"] != UNKNOWN
    )
    quality = {
        "total_records": len(bugs),
        "usable_for_metrics": usable_metrics,
        "usable_for_causal_analysis": causal_usable,
        "causal_coverage_percent": round(causal_usable / len(bugs) * 100, 1),
        "missing_by_field": dict(missing),
        "duplicate_ids": duplicate_ids,
        "prompt_injection_rows": injection_rows,
        "issues": issues,
    }
    return bugs, quality

