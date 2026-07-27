from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import mean
from typing import Any

from ..core.config import load_yaml
from ..core.utils import UNKNOWN, percent
from .narratives import enrich_kpis
from .primitives import _distribution, _duration_observations, _top_focus

Bug = dict[str, Any]
KpiSpec = dict[str, Any]


def configured_kpis() -> list[KpiSpec]:
    config = load_yaml("kpis.yml")
    specs = config.get("kpis")
    if not isinstance(specs, list) or not specs:
        raise ValueError("config/kpis.yml deve declarar uma lista não vazia em 'kpis'.")
    identifiers: set[str] = set()
    required = {
        "id",
        "label",
        "unit",
        "chart",
        "definition",
        "formula",
        "limitation",
        "calculation",
    }
    for spec in specs:
        if not isinstance(spec, dict) or not required <= set(spec):
            raise ValueError("Cada KPI deve declarar contrato, cálculo e limitações.")
        identifier = str(spec["id"])
        if identifier in identifiers:
            raise ValueError(f"KPI duplicado em config/kpis.yml: {identifier}")
        identifiers.add(identifier)
        calculation = spec["calculation"]
        if not isinstance(calculation, dict) or not calculation.get("type"):
            raise ValueError(f"KPI {identifier} não declara calculation.type.")
    return specs


def kpi_spec(identifier: str) -> KpiSpec:
    for spec in configured_kpis():
        if spec["id"] == identifier:
            return spec
    raise KeyError(f"KPI não configurado: {identifier}")


@dataclass(frozen=True)
class MetricSnapshot:
    total: int
    known_environment: list[Bug]
    production: int
    known_reopened: list[Bug]
    reopened: int
    modules: dict[str, int]
    bug_types: dict[str, int]
    root_causes: dict[str, int]
    top_module: str
    top_module_count: int
    top_type: str
    top_type_count: int
    top_root_cause: str
    top_root_cause_count: int

    @classmethod
    def from_bugs(cls, bugs: list[Bug]) -> "MetricSnapshot":
        known_environment = [bug for bug in bugs if bug["environment"] != UNKNOWN]
        known_reopened = [bug for bug in bugs if bug["reopened"] != UNKNOWN]
        modules = _distribution(bugs, "affected_module")
        bug_types = _distribution(bugs, "bug_type")
        root_causes = _distribution(bugs, "root_cause_category")
        top_module, top_module_count = _top_focus(modules)
        top_type, top_type_count = _top_focus(bug_types)
        top_root_cause, top_root_cause_count = _top_focus(root_causes)
        return cls(
            total=len(bugs),
            known_environment=known_environment,
            production=sum(
                1 for bug in known_environment if bug["environment"] == "production"
            ),
            known_reopened=known_reopened,
            reopened=sum(1 for bug in known_reopened if bug["reopened"] == "true"),
            modules=modules,
            bug_types=bug_types,
            root_causes=root_causes,
            top_module=top_module,
            top_module_count=top_module_count,
            top_type=top_type,
            top_type_count=top_type_count,
            top_root_cause=top_root_cause,
            top_root_cause_count=top_root_cause_count,
        )


def build_kpis(bugs: list[Bug], snapshot: MetricSnapshot) -> list[dict[str, Any]]:
    del snapshot  # Highlights use the snapshot; KPI selection and methods come from config.
    return enrich_kpis([_calculate_kpi(spec, bugs) for spec in configured_kpis()])


def _calculate_kpi(spec: KpiSpec, bugs: list[Bug]) -> dict[str, Any]:
    calculation = spec["calculation"]
    calculation_type = calculation["type"]
    result = _run_calculation(calculation_type, calculation, bugs)
    return {
        "id": spec["id"],
        "label": spec["label"],
        "value": result["value"],
        "unit": spec["unit"],
        "numerator": result["numerator"],
        "denominator": result["denominator"],
        "sample_size": result["denominator"],
        "formula": spec["formula"],
        "limitations": [spec["limitation"]] if spec["limitation"] else [],
        "chart": spec["chart"],
        "context_value": result["numerator"],
        "context_total": result["denominator"],
        "definition": spec["definition"],
        "supporting_bug_ids": result["supporting_bug_ids"],
        "methodology": {
            "config": "config/kpis.yml",
            "calculation_type": calculation_type,
            **result.get("methodology", {}),
        },
    }


def _run_calculation(
    calculation_type: str,
    calculation: dict[str, Any],
    bugs: list[Bug],
) -> dict[str, Any]:
    if calculation_type == "count_records":
        return _result(
            len(bugs),
            len(bugs),
            len(bugs),
            bugs,
        )
    if calculation_type == "categorical_rate":
        excluded = {str(item) for item in calculation.get("excluded_values", [])}
        eligible = [
            bug for bug in bugs if str(bug.get(calculation["field"], UNKNOWN)) not in excluded
        ]
        numerator_values = {
            str(item) for item in calculation.get("numerator_values", [])
        }
        matching = [
            bug
            for bug in eligible
            if str(bug.get(calculation["field"], UNKNOWN)) in numerator_values
        ]
        return _result(
            percent(len(matching), len(eligible)),
            len(matching),
            len(eligible),
            matching,
        )
    if calculation_type == "any_present_rate":
        excluded = {str(item) for item in calculation.get("excluded_values", [])}
        matching = [
            bug
            for bug in bugs
            if any(str(bug.get(field, UNKNOWN)) not in excluded for field in calculation["fields"])
        ]
        return _result(
            percent(len(matching), len(bugs)),
            len(matching),
            len(bugs),
            matching,
        )
    if calculation_type == "category_set_rate":
        numerator_values = {
            str(item) for item in calculation.get("numerator_values", [])
        }
        matching = [
            bug
            for bug in bugs
            if str(bug.get(calculation["field"], UNKNOWN)) in numerator_values
        ]
        return _result(
            percent(len(matching), len(bugs)),
            len(matching),
            len(bugs),
            matching,
        )
    if calculation_type == "category_count":
        values = {str(item) for item in calculation.get("values", [])}
        matching = [
            bug
            for bug in bugs
            if str(bug.get(calculation["field"], UNKNOWN)) in values
        ]
        return _result(len(matching), len(matching), len(bugs), matching)
    if calculation_type == "dominant_share":
        return _dominant_share(calculation, bugs)
    if calculation_type == "duration_mean":
        return _duration_mean(calculation, bugs)
    raise ValueError(f"calculation.type não suportado: {calculation_type}")


def _dominant_share(
    calculation: dict[str, Any],
    bugs: list[Bug],
) -> dict[str, Any]:
    excluded = {
        str(item) for item in calculation.get("excluded_values", [])
    }
    counts = Counter(
        str(bug.get(calculation["field"], UNKNOWN))
        for bug in bugs
        if str(bug.get(calculation["field"], UNKNOWN)) not in excluded
    )
    dominant, _ = _top_focus(dict(counts))
    if dominant == UNKNOWN:
        dominant = None
    matching = [
        bug
        for bug in bugs
        if dominant is not None
        and str(bug.get(calculation["field"], UNKNOWN)) == dominant
    ]
    return _result(
        percent(len(matching), len(bugs)),
        len(matching),
        len(bugs),
        matching,
        methodology={"dominant_value": dominant},
    )


def _duration_mean(
    calculation: dict[str, Any],
    bugs: list[Bug],
) -> dict[str, Any]:
    observations = _duration_observations(bugs, calculation["sources"])
    durations = [item["hours"] for item in observations]
    source_counts = dict(
        Counter(item["source"] for item in observations)
    )
    return _result(
        round(mean(durations), 1) if durations else None,
        round(sum(durations), 1) if durations else None,
        len(durations),
        [item["bug"] for item in observations],
        methodology={"source_counts": source_counts},
    )


def _result(
    value: float | int | None,
    numerator: float | int | None,
    denominator: float | int | None,
    supporting_bugs: list[Bug],
    *,
    methodology: dict[str, Any] | None = None,
) -> dict[str, Any]:
    maximum_supporting_ids = load_yaml("kpis.yml")["methodology"][
        "maximum_supporting_bug_ids"
    ]
    if not isinstance(maximum_supporting_ids, int) or maximum_supporting_ids < 1:
        raise ValueError("maximum_supporting_bug_ids deve ser inteiro positivo.")
    return {
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "supporting_bug_ids": [
            str(bug["bug_id"])
            for bug in supporting_bugs[:maximum_supporting_ids]
        ],
        "methodology": methodology or {},
    }
