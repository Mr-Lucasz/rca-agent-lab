from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from ..core.config import load_yaml
from ..core.utils import fold, parse_datetime


def infer_field_mapping(
    raw_records: list[dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Infer canonical columns while retaining confidence and alternatives."""

    config = _mapping_config()
    aliases = load_yaml("aliases.yml").get("fields", {})
    headers = _ordered_headers(raw_records)
    candidates_by_header = {
        header: _rank_candidates(header, raw_records, aliases, config)
        for header in headers
    }
    mapping: dict[str, str] = {}
    claimed: set[str] = set()
    report: list[dict[str, Any]] = []
    ordered = sorted(
        headers,
        key=lambda header: candidates_by_header[header][0]["score"],
        reverse=True,
    )
    for header in ordered:
        candidates = candidates_by_header[header]
        selected = next(
            (
                item
                for item in candidates
                if item["canonical_field"] not in claimed
                and item["score"]
                >= config["thresholds"]["minimum_mapping_score"]
            ),
            None,
        )
        if selected:
            mapping[header] = selected["canonical_field"]
            claimed.add(selected["canonical_field"])
        report.append(_mapping_report(header, selected, candidates, config))
    report.sort(key=lambda item: headers.index(item["source_field"]))
    return mapping, report


def _ordered_headers(raw_records: list[dict[str, Any]]) -> list[str]:
    headers: list[str] = []
    seen: set[str] = set()
    for record in raw_records:
        for key in record:
            header = str(key).strip()
            if header and not header.startswith("__rca_") and header not in seen:
                seen.add(header)
                headers.append(header)
    return headers


def _rank_candidates(
    header: str,
    raw_records: list[dict[str, Any]],
    aliases: dict[str, list[str]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    values = [record.get(header) for record in raw_records if header in record]
    ranked = []
    for canonical, configured_names in aliases.items():
        names = [canonical, *(configured_names or [])]
        header_score, method = _header_score(header, names, config)
        value_score = _value_score(canonical, values, config)
        score = _combined_score(header_score, value_score, config)
        ranked.append(
            {
                "canonical_field": canonical,
                "score": round(score, 3),
                "method": method if header_score >= value_score else "value_profile",
            }
        )
    return sorted(
        ranked,
        key=lambda item: (-item["score"], item["canonical_field"]),
    )


def _header_score(
    header: str,
    names: list[str],
    config: dict[str, Any],
) -> tuple[float, str]:
    scoring = config["header_similarity"]
    normalized = _normalize_header(header)
    compact = normalized.replace("_", "")
    best_score = 0.0
    best_method = "unmatched"
    for name in names:
        candidate = _normalize_header(name)
        candidate_compact = candidate.replace("_", "")
        if normalized == candidate or compact == candidate_compact:
            return 1.0, "exact_alias"
        if min(len(compact), len(candidate_compact)) >= scoring[
            "minimum_containment_length"
        ] and (
            compact in candidate_compact or candidate_compact in compact
        ):
            score = scoring["contained_alias_score"]
            method = "contained_alias"
        else:
            ratio = SequenceMatcher(None, compact, candidate_compact).ratio()
            overlap = _token_overlap(normalized, candidate, config)
            score = max(ratio * scoring["fuzzy_ratio_weight"], overlap)
            method = "fuzzy_header"
        if score > best_score:
            best_score, best_method = score, method
    return best_score, best_method


def _token_overlap(
    left: str,
    right: str,
    config: dict[str, Any],
) -> float:
    left_tokens = set(left.split("_"))
    right_tokens = set(right.split("_"))
    shared = left_tokens & right_tokens
    if not shared:
        return 0.0
    coverage = len(shared) / max(1, min(len(left_tokens), len(right_tokens)))
    scoring = config["header_similarity"]
    return (
        scoring["token_overlap_base"]
        + scoring["token_overlap_coverage_weight"] * coverage
    )


def _value_score(
    canonical: str,
    values: list[Any],
    config: dict[str, Any],
) -> float:
    usable = [value for value in values if value is not None and str(value).strip()]
    if not usable:
        return 0.0
    if canonical in {"severity", "bug_type", "root_cause_category", "environment"}:
        profile = config["value_profiles"]["taxonomy"]
        filename = {
            "severity": "severity.yml",
            "bug_type": "bug-types.yml",
            "root_cause_category": "root-causes.yml",
            "environment": "environments.yml",
        }[canonical]
        known = _configured_values(filename)
        ratio = sum(fold(value) in known for value in usable) / len(usable)
        return (
            profile["base_score"] + profile["ratio_weight"] * ratio
            if ratio >= profile["minimum_match_ratio"]
            else 0.0
        )
    if canonical in {
        "created_at",
        "occurrence_started_at",
        "detected_at",
        "resolved_at",
        "service_restored_at",
    }:
        profile = config["value_profiles"]["date"]
        ratio = sum(parse_datetime(value) is not None for value in usable) / len(usable)
        return profile["score"] if ratio >= profile["minimum_match_ratio"] else 0.0
    if canonical in {"detection_time_hours", "resolution_time_hours"}:
        profile = config["value_profiles"]["duration"]
        ratio = sum(_is_nonnegative_number(value) for value in usable) / len(usable)
        return profile["score"] if ratio >= profile["minimum_match_ratio"] else 0.0
    if canonical == "reopened":
        profile = config["value_profiles"]["boolean"]
        booleans = {"true", "false", "sim", "nao", "yes", "no", "0", "1"}
        ratio = sum(fold(value) in booleans for value in usable) / len(usable)
        return profile["score"] if ratio >= profile["minimum_match_ratio"] else 0.0
    if canonical == "bug_id":
        profile = config["value_profiles"]["identifier"]
        unique_ratio = len({str(value) for value in usable}) / len(usable)
        id_ratio = sum(
            bool(re.search(r"[a-zA-Z].*\d|\d.*[a-zA-Z]", str(value)))
            for value in usable
        ) / len(usable)
        return (
            profile["score"]
            if unique_ratio >= profile["minimum_unique_ratio"]
            and id_ratio >= profile["minimum_pattern_ratio"]
            else 0.0
        )
    return 0.0


def _configured_values(filename: str) -> set[str]:
    canonical = load_yaml(filename).get("canonical", {})
    values: set[str] = set()
    for key, details in canonical.items():
        values.add(fold(key))
        if isinstance(details, dict):
            aliases = details.get("aliases", [])
        else:
            aliases = details or []
        values.update(fold(alias) for alias in aliases)
    return values


def _combined_score(
    header_score: float,
    value_score: float,
    config: dict[str, Any],
) -> float:
    scoring = config["score_combination"]
    if header_score >= scoring["exact_header_floor"]:
        return header_score
    if header_score >= scoring["combined_header_floor"] and value_score:
        return min(
            scoring["maximum_combined_score"],
            header_score * scoring["header_weight"]
            + value_score * scoring["value_weight"]
            + scoring["corroboration_bonus"],
        )
    return max(header_score, value_score * scoring["value_only_weight"])


def _mapping_report(
    header: str,
    selected: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    maximum_alternatives = config["report"]["maximum_alternatives"]
    confirmation_threshold = config["thresholds"][
        "automatic_confirmation_score"
    ]
    if selected is None:
        return {
            "source_field": header,
            "canonical_field": None,
            "confidence": "low",
            "score": candidates[0]["score"],
            "method": "unmapped",
            "status": "unmapped",
            "alternatives": candidates[:maximum_alternatives],
        }
    score = selected["score"]
    return {
        "source_field": header,
        "canonical_field": selected["canonical_field"],
        "confidence": "high" if score >= confirmation_threshold else "medium",
        "score": score,
        "method": selected["method"],
        "status": "mapped" if score >= confirmation_threshold else "needs_confirmation",
        "alternatives": candidates[:maximum_alternatives],
    }


def _mapping_config() -> dict[str, Any]:
    config = load_yaml("schema-mapping.yml")
    required = {
        "thresholds",
        "header_similarity",
        "value_profiles",
        "score_combination",
        "report",
    }
    if not required <= set(config):
        raise ValueError("config/schema-mapping.yml está incompleto.")
    thresholds = config["thresholds"]
    minimum = thresholds.get("minimum_mapping_score")
    confirmation = thresholds.get("automatic_confirmation_score")
    if not all(
        isinstance(value, (int, float)) and 0 <= value <= 1
        for value in (minimum, confirmation)
    ):
        raise ValueError("Limiares de schema mapping devem estar entre 0 e 1.")
    if confirmation < minimum:
        raise ValueError("Confirmação automática não pode ser menor que o mapeamento.")
    return config


def _normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fold(value)).strip("_")


def _is_nonnegative_number(value: Any) -> bool:
    try:
        return float(str(value).replace(",", ".")) >= 0
    except ValueError:
        return False
