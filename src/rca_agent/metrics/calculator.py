from __future__ import annotations

from typing import Any

from ..core.causal_signals import causal_signal_config, has_causal_signal
from ..core.config import load_yaml
from ..core.utils import percent
from .kpis import MetricSnapshot, build_kpis, kpi_spec
from .primitives import (
    _cross_tab,
    _date_distribution,
    _distribution,
    _root_cause_profiles,
    _top_note_terms,
)


def calculate_metrics(bugs: list[dict[str, Any]]) -> dict[str, Any]:
    analytical_bugs = _analytical_bugs(bugs)
    snapshot = MetricSnapshot.from_bugs(analytical_bugs)
    descriptive = _descriptive_config()
    cross_tabs = descriptive["cross_tabs"]
    profile_config = descriptive["root_cause_profiles"]
    note_terms = _build_note_terms(analytical_bugs, descriptive)
    return {
        "kpis": build_kpis(analytical_bugs, snapshot),
        "distributions": {
            field: _distribution(analytical_bugs, field)
            for field in descriptive["distributions"]["fields"]
        },
        "cross_tabs": {
            name: _cross_tab(
                analytical_bugs,
                specification["row"],
                specification["column"],
            )
            for name, specification in cross_tabs.items()
        },
        "timelines": {
            name: _date_distribution(analytical_bugs, field)
            for name, field in descriptive["timelines"].items()
        },
        "note_terms": note_terms,
        "causal_signal_patterns": _build_causal_signal_patterns(
            analytical_bugs,
            note_terms,
        ),
        "highlights": _build_highlights(snapshot),
        "root_cause_profiles": _root_cause_profiles(
            analytical_bugs,
            snapshot.total,
            kpi_spec("detection_lead_time_hours")["calculation"]["sources"],
            profile_config["maximum_top_modules"],
            profile_config["maximum_sample_bug_ids"],
        ),
        "effective_value_sources": {
            field: _distribution(bugs, f"effective_{field}_source")
            for field in (
                "severity",
                "bug_type",
                "root_cause_category",
                "affected_module",
                "environment",
            )
        },
        "cross_tab_meta": {
            name: {
                key: specification[key]
                for key in ("label", "row_label", "column_label")
            }
            for name, specification in cross_tabs.items()
        },
        "methodology": {
            "descriptive_config": "config/descriptive-analysis.yml",
            "kpi_config": "config/kpis.yml",
        },
    }


def _descriptive_config() -> dict[str, Any]:
    config = load_yaml("descriptive-analysis.yml")
    required = {
        "distributions",
        "cross_tabs",
        "timelines",
        "note_terms",
        "causal_signals",
        "root_cause_profiles",
    }
    if not required <= set(config):
        raise ValueError("config/descriptive-analysis.yml está incompleto.")
    maximum_terms = config["note_terms"].get("maximum_terms")
    if not isinstance(maximum_terms, int) or maximum_terms < 1:
        raise ValueError("note_terms.maximum_terms deve ser inteiro positivo.")
    return config


def _analytical_bugs(
    bugs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for bug in bugs:
        analytical = dict(bug)
        for field in (
            "severity",
            "bug_type",
            "root_cause_category",
            "affected_module",
            "environment",
        ):
            analytical[field] = bug.get(f"effective_{field}", bug.get(field))
        result.append(analytical)
    return result


def _build_note_terms(
    bugs: list[dict[str, Any]],
    descriptive: dict[str, Any],
) -> dict[str, dict[str, int]]:
    config = descriptive["note_terms"]
    stopwords = {
        str(item).casefold()
        for item in config["stopwords"]
        if str(item).strip()
    }
    return {
        name: _top_note_terms(
            bugs,
            tuple(fields),
            stopwords,
            config["maximum_terms"],
        )
        for name, fields in config["groups"].items()
    }


def _build_causal_signal_patterns(
    bugs: list[dict[str, Any]],
    note_terms: dict[str, dict[str, int]],
) -> dict[str, Any]:
    config = causal_signal_config()
    sources = config["sources"]
    unknown = str(config["unknown_value"])
    signal_bugs = [bug for bug in bugs if has_causal_signal(bug)]
    source_coverage = {
        name: sum(
            1
            for bug in bugs
            if str(bug.get(source["field"], unknown)).strip()
            not in {"", unknown}
        )
        for name, source in sources.items()
    }
    multi_source_records = sum(
        1
        for bug in signal_bugs
        if sum(
            str(bug.get(source["field"], unknown)).strip()
            not in {"", unknown}
            for source in sources.values()
        )
        > 1
    )
    return {
        "interpretation_scope": config["interpretation_scope"],
        "total_records": len(bugs),
        "records_with_signals": len(signal_bugs),
        "coverage_percent": percent(len(signal_bugs), len(bugs)),
        "source_coverage": source_coverage,
        "multi_source_records": multi_source_records,
        "contextual_distributions": {
            field: _distribution(signal_bugs, field)
            for field in config["contextual_dimensions"]
        },
        "note_terms": note_terms,
        "bug_ids": [bug["bug_id"] for bug in signal_bugs],
    }


def _build_highlights(snapshot: MetricSnapshot) -> dict[str, dict[str, Any]]:
    return {
        "top_module": {
            "label": snapshot.top_module,
            "count": snapshot.top_module_count,
        },
        "top_bug_type": {
            "label": snapshot.top_type,
            "count": snapshot.top_type_count,
        },
        "top_root_cause": {
            "label": snapshot.top_root_cause,
            "count": snapshot.top_root_cause_count,
        },
        "production": {
            "count": snapshot.production,
            "total": len(snapshot.known_environment),
        },
        "reopened": {
            "count": snapshot.reopened,
            "total": len(snapshot.known_reopened),
        },
    }
