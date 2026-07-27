from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from ..core.root_causes import resolve_root_cause
from ..core.utils import UNKNOWN, parse_datetime, percent


def _distribution(bugs: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(bug.get(field, UNKNOWN)) for bug in bugs).items()))


def _date_distribution(bugs: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for bug in bugs:
        value = parse_datetime(bug.get(field))
        if value:
            counts[value.date().isoformat()] += 1
    return dict(sorted(counts.items()))


def _cross_tab(bugs: list[dict[str, Any]], row_field: str, column_field: str) -> dict[str, dict[str, int]]:
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for bug in bugs:
        matrix[str(bug.get(row_field, UNKNOWN))][str(bug.get(column_field, UNKNOWN))] += 1
    return {row: dict(sorted(values.items())) for row, values in sorted(matrix.items())}


def _tokenize_notes(text: str, stopwords: set[str]) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9à-ÿ]{3,}", text.casefold())
        if token not in stopwords and token != UNKNOWN
    ]


def _top_note_terms(
    bugs: list[dict[str, Any]],
    fields: tuple[str, ...],
    stopwords: set[str],
    maximum_terms: int,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for bug in bugs:
        parts = [str(bug.get(field, "")) for field in fields if bug.get(field, UNKNOWN) != UNKNOWN]
        for token in _tokenize_notes(" ".join(parts), stopwords):
            counts[token] += 1
    return dict(counts.most_common(maximum_terms))


def _top_focus(values: dict[str, int]) -> tuple[str, int]:
    if not values:
        return (UNKNOWN, 0)
    label, count = max(values.items(), key=lambda item: (item[1], item[0]))
    return label, count


def _predominant(bugs: list[dict[str, Any]], field: str) -> str:
    values = Counter(str(bug.get(field, UNKNOWN)) for bug in bugs if bug.get(field, UNKNOWN) != UNKNOWN)
    return values.most_common(1)[0][0] if values else UNKNOWN


def _root_cause_profiles(
    bugs: list[dict[str, Any]],
    total: int,
    detection_sources: list[dict[str, Any]],
    maximum_top_modules: int,
    maximum_sample_bug_ids: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bug in bugs:
        grouped[str(bug.get("root_cause_category", UNKNOWN))].append(bug)
    profiles: list[dict[str, Any]] = []
    for cause, group in grouped.items():
        cause_metadata = resolve_root_cause(cause)
        detected = [
            item["hours"]
            for item in _duration_observations(group, detection_sources)
        ]
        modules = Counter(
            bug["affected_module"] for bug in group if bug.get("affected_module", UNKNOWN) != UNKNOWN
        )
        reopened_total = sum(1 for bug in group if bug.get("reopened") == "true")
        production_total = sum(1 for bug in group if bug.get("environment") == "production")
        profiles.append(
            {
                "root_cause_category": cause,
                "signal_axis": cause_metadata["axis"],
                "signal_status": cause_metadata["status"],
                "count": len(group),
                "share_percent": percent(len(group), total),
                "predominant_severity": _predominant(group, "severity"),
                "top_modules": [
                    module
                    for module, _ in modules.most_common(maximum_top_modules)
                ],
                "avg_detection_lead_time_hours": (
                    round(mean(detected), 1) if detected else None
                ),
                "reopened_total": reopened_total,
                "production_total": production_total,
                "sample_bug_ids": [
                    bug["bug_id"]
                    for bug in group[:maximum_sample_bug_ids]
                ],
            }
        )
    return sorted(
        profiles,
        key=lambda item: (-item["count"], -(item["share_percent"] or 0), item["root_cause_category"]),
    )


def _duration_observations(
    bugs: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for bug in bugs:
        for source in sources:
            kind = source.get("kind")
            if kind == "reported":
                value = bug.get(source["field"])
                if isinstance(value, (int, float)) and value >= 0:
                    observations.append(
                        {
                            "bug": bug,
                            "hours": float(value),
                            "source": f"reported:{source['field']}",
                        }
                    )
                    break
            elif kind == "elapsed":
                left = parse_datetime(bug.get(source["start_field"]))
                right = parse_datetime(bug.get(source["end_field"]))
                if left and right and right >= left:
                    observations.append(
                        {
                            "bug": bug,
                            "hours": (right - left).total_seconds() / 3600,
                            "source": (
                                f"elapsed:{source['end_field']}-"
                                f"{source['start_field']}"
                            ),
                        }
                    )
                    break
            else:
                raise ValueError(f"Fonte de duração não suportada: {kind}")
    return observations


def _duration_hours(
    bugs: list[dict[str, Any]],
    start: str,
    end: str,
    reported_field: str,
) -> list[float]:
    """Compatibility wrapper for callers outside the configured KPI engine."""

    return [
        item["hours"]
        for item in _duration_observations(
            bugs,
            [
                {"kind": "reported", "field": reported_field},
                {"kind": "elapsed", "start_field": start, "end_field": end},
            ],
        )
    ]
