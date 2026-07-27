from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ..core.causal_signals import has_causal_signal
from ..core.config import load_yaml
from ..core.utils import UNKNOWN, clean_text, fold, has_injection_signal, parse_datetime
from .schema_mapping import infer_field_mapping

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
    "occurrence_started_at",
    "detected_at",
    "resolved_at",
    "service_restored_at",
    "detection_time_hours",
    "resolution_time_hours",
    "reopened",
    "dev_analysis_notes",
    "qa_analysis_notes",
    "version",
    "team",
    "prd_reference",
]


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


def _normalize_duration(value: Any) -> float | str:
    if value == UNKNOWN:
        return UNKNOWN
    try:
        duration = float(str(value).replace(",", "."))
    except ValueError:
        return UNKNOWN
    return round(duration, 4) if duration >= 0 else UNKNOWN


def _initial_effective_fields(mapped: dict[str, Any]) -> dict[str, str]:
    effective = {}
    for field in (
        "severity",
        "bug_type",
        "root_cause_category",
        "affected_module",
        "environment",
    ):
        value = mapped[field]
        effective[f"effective_{field}"] = value
        effective[f"effective_{field}_source"] = (
            "reported" if value != UNKNOWN else "unknown"
        )
    return effective


def _normalize_record(
    raw: dict[str, Any],
    index: int,
    field_mapping: dict[str, str],
    value_maps: dict[str, dict[str, str]],
    source_path: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    mapped = {field: UNKNOWN for field in CANONICAL_FIELDS}
    for raw_key, raw_value in raw.items():
        canonical = field_mapping.get(str(raw_key).strip())
        if canonical and not str(raw_key).startswith("__rca_"):
            mapped[canonical] = clean_text(raw_value)
    row_issues = []
    if mapped["bug_id"] == UNKNOWN:
        mapped["bug_id"] = f"UNKNOWN-L{index}"
        row_issues.append(
            {"code": "missing_id", "source_row": index, "severity": "warning"}
        )
    for field, lookup in value_maps.items():
        mapped[field] = lookup.get(fold(mapped[field]), mapped[field])
    mapped["reopened"] = _normalize_bool(mapped["reopened"])
    for duration_field in ("detection_time_hours", "resolution_time_hours"):
        raw_duration = mapped[duration_field]
        mapped[duration_field] = _normalize_duration(raw_duration)
        if raw_duration != UNKNOWN and mapped[duration_field] == UNKNOWN:
            row_issues.append(
                {
                    "code": "invalid_duration",
                    "field": duration_field,
                    "source_row": index,
                    "value": raw_duration,
                }
            )
    for date_field in (
        "created_at",
        "occurrence_started_at",
        "detected_at",
        "resolved_at",
        "service_restored_at",
    ):
        value = mapped[date_field]
        if value != UNKNOWN and parse_datetime(value) is None:
            row_issues.append(
                {
                    "code": "invalid_date",
                    "field": date_field,
                    "source_row": index,
                    "value": value,
                }
            )
            mapped[date_field] = UNKNOWN
    unsafe_fields = [
        field
        for field in CANONICAL_FIELDS
        if has_injection_signal(mapped.get(field, UNKNOWN))
    ]
    if unsafe_fields:
        row_issues.append(
            {
                "code": "prompt_injection_signal",
                "source_row": index,
                "fields": unsafe_fields,
            }
        )
    mapped.update(_audit_fields(raw, mapped, source_path, index))
    return mapped, row_issues, unsafe_fields


def _audit_fields(
    raw: dict[str, Any],
    mapped: dict[str, Any],
    source_path: str,
    index: int,
) -> dict[str, Any]:
    return {
        "source_file": source_path,
        "source_row": index,
        "source_fields": {
            str(key): clean_text(value)
            for key, value in raw.items()
            if not str(key).startswith("__rca_")
        },
        "cluster_id": UNKNOWN,
        "duplicate_candidate_family_id": UNKNOWN,
        "duplicate_candidate_status": "not_candidate",
        **_initial_effective_fields(mapped),
        "agent_suggested_severity": UNKNOWN,
        "agent_suggested_bug_type": UNKNOWN,
        "agent_suggested_root_cause_category": UNKNOWN,
        "agent_suggestion_confidence": UNKNOWN,
        "agent_suggestion_rationale": UNKNOWN,
        "agent_review_status": "insufficient_evidence",
    }


def normalize(
    raw_records: list[dict[str, Any]], source: str | Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    field_mapping, mapping_report = infer_field_mapping(raw_records)
    value_maps = {
        "severity": _value_map("severity.yml"),
        "bug_type": _value_map("bug-types.yml"),
        "root_cause_category": _value_map("root-causes.yml"),
        "environment": _value_map("environments.yml"),
    }
    bugs: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = [
        {
            "code": "schema_mapping_needs_confirmation",
            "source_field": item["source_field"],
            "canonical_field": item["canonical_field"],
            "confidence": item["confidence"],
            "score": item["score"],
        }
        for item in mapping_report
        if item["status"] == "needs_confirmation"
    ]
    missing = Counter()
    id_counts = Counter()
    injection_rows: list[int] = []
    source_path = str(Path(source).expanduser().resolve())

    for ordinal, raw in enumerate(raw_records, start=2):
        index = int(raw.get("__rca_source_row__", ordinal))
        mapped, row_issues, unsafe_fields = _normalize_record(
            raw,
            index,
            field_mapping,
            value_maps,
            source_path,
        )
        issues.extend(row_issues)
        for field in ("title", "description", "expected_behavior", "actual_behavior"):
            if mapped[field] == UNKNOWN:
                missing[field] += 1
        if unsafe_fields:
            injection_rows.append(index)
        id_counts[mapped["bug_id"]] += 1
        bugs.append(mapped)

    duplicate_ids = sorted(identifier for identifier, count in id_counts.items() if count > 1)
    for identifier in duplicate_ids:
        issues.append({"code": "duplicate_id", "bug_id": identifier, "count": id_counts[identifier]})

    usable_metrics = sum(1 for bug in bugs if bug["title"] != UNKNOWN or bug["description"] != UNKNOWN)
    records_with_causal_signals = sum(
        1 for bug in bugs if has_causal_signal(bug)
    )
    quality = {
        "total_records": len(bugs),
        "usable_for_metrics": usable_metrics,
        "records_with_causal_signals": records_with_causal_signals,
        "causal_signal_coverage_percent": (
            round(records_with_causal_signals / len(bugs) * 100, 1)
            if bugs
            else 0.0
        ),
        "missing_by_field": dict(missing),
        "duplicate_ids": duplicate_ids,
        "prompt_injection_rows": injection_rows,
        "schema_mapping": mapping_report,
        "ingestion_profile": _ingestion_profile(raw_records),
        "unmapped_source_fields": [
            item["source_field"]
            for item in mapping_report
            if item["status"] == "unmapped"
        ],
        "issues": issues,
    }
    return bugs, quality


def _ingestion_profile(
    raw_records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not raw_records:
        return {}
    return {
        str(key).removeprefix("__rca_").removesuffix("__"): value
        for key, value in raw_records[0].items()
        if str(key).startswith("__rca_") and key != "__rca_source_row__"
    }

