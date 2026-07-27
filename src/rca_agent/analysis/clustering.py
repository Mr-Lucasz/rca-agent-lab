from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..core.utils import UNKNOWN, fold
from .clustering_config import load_clustering_config, load_severity_weights

Bug = dict[str, Any]


def _signature_tokens(bug: Bug, config: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for prefix, field in config["features"]["signature_fields"].items():
        value = fold(bug.get(field, ""))
        if value and value != UNKNOWN:
            values.extend(
                f"{prefix}:{token}" for token in re.findall(r"[a-z0-9]{3,}", value)
            )
    return values


def _cluster_name(module: str, bug_type: str, config: dict[str, Any]) -> str:
    label = config["labels"].get(bug_type, bug_type.replace("-", " "))
    if module == UNKNOWN:
        return f"Cluster de {label}"
    return f"{module.title()} · {label}"


def tokens(bug: Bug, config: dict[str, Any] | None = None) -> set[str]:
    config = config or load_clustering_config()
    text = fold(
        " ".join(
            str(bug.get(field, ""))
            for field in config["features"]["text_fields"]
        )
    )
    stopwords = {fold(item) for item in config["features"]["stopwords"]}
    textual = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text)
        if token not in stopwords and token != UNKNOWN
    }
    return textual | set(_signature_tokens(bug, config))


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _same_signature(
    left: Bug,
    right: Bug,
    method: dict[str, Any],
) -> bool:
    signature = method["same_signature"]
    required_match = all(
        left.get(field, UNKNOWN) != UNKNOWN
        and left.get(field) == right.get(field)
        for field in signature["required_equal_fields"]
    )
    any_match = any(
        left.get(field, UNKNOWN) != UNKNOWN
        and left.get(field) == right.get(field)
        for field in signature["any_equal_fields"]
    )
    return required_match and any_match


def _pair_passes(
    left: int,
    right: int,
    bugs: list[Bug],
    similarities: dict[tuple[int, int], float],
    method: dict[str, Any],
) -> bool:
    pair = (min(left, right), max(left, right))
    similarity = similarities[pair]
    threshold = (
        method["same_signature_minimum_similarity"]
        if _same_signature(bugs[left], bugs[right], method)
        else method["similarity_threshold"]
    )
    return similarity >= threshold


def _complete_linkage_components(
    bugs: list[Bug],
    similarities: dict[tuple[int, int], float],
    method: dict[str, Any],
) -> list[list[int]]:
    groups = [[index] for index in range(len(bugs))]
    while True:
        candidates: list[tuple[float, int, int]] = []
        for left_index in range(len(groups)):
            for right_index in range(left_index + 1, len(groups)):
                cross_pairs = [
                    (left, right)
                    for left in groups[left_index]
                    for right in groups[right_index]
                ]
                if all(
                    _pair_passes(left, right, bugs, similarities, method)
                    for left, right in cross_pairs
                ):
                    average_similarity = sum(
                        similarities[(min(left, right), max(left, right))]
                        for left, right in cross_pairs
                    ) / len(cross_pairs)
                    candidates.append(
                        (average_similarity, left_index, right_index)
                    )
        if not candidates:
            break
        _, left_index, right_index = max(
            candidates,
            key=lambda item: (
                item[0],
                -min(groups[item[1]]),
                -min(groups[item[2]]),
            ),
        )
        groups[left_index] = sorted(groups[left_index] + groups[right_index])
        del groups[right_index]
    return sorted(groups, key=lambda group: (-len(group), group[0]))


def _similarities(bugs: list[Bug], config: dict[str, Any]) -> dict[tuple[int, int], float]:
    token_sets = [tokens(bug, config) for bug in bugs]
    return {
        (left, right): jaccard(token_sets[left], token_sets[right])
        for left in range(len(bugs))
        for right in range(left + 1, len(bugs))
    }


def _boundary_cases(
    group: list[int],
    bugs: list[Bug],
    similarities: dict[tuple[int, int], float],
    method: dict[str, Any],
) -> list[dict[str, Any]]:
    group_set = set(group)
    cases: list[dict[str, Any]] = []
    for (left, right), similarity in similarities.items():
        if left not in group_set and right not in group_set:
            continue
        same_signature = _same_signature(bugs[left], bugs[right], method)
        threshold = (
            method["same_signature_minimum_similarity"]
            if same_signature
            else method["similarity_threshold"]
        )
        if abs(similarity - threshold) <= method["boundary_margin"]:
            cases.append(
                {
                    "left_bug_id": bugs[left]["bug_id"],
                    "left_source_row": bugs[left]["source_row"],
                    "right_bug_id": bugs[right]["bug_id"],
                    "right_source_row": bugs[right]["source_row"],
                    "similarity": round(similarity, 4),
                    "decision_threshold": threshold,
                    "same_signature": same_signature,
                    "relation": "included" if left in group_set and right in group_set else "excluded",
                }
            )
    return cases


def build_clusters(bugs: list[Bug]) -> list[dict[str, Any]]:
    config = load_clustering_config()
    signature = config["features"]["same_signature"]
    for method in config["grouping"].values():
        method["same_signature"] = signature
    similarities = _similarities(bugs, config)
    _assign_duplicate_candidates(bugs, similarities, config)
    cluster_method = config["grouping"]["defect_clusters"]
    clusters_indexes = _complete_linkage_components(
        bugs,
        similarities,
        cluster_method,
    )
    weights = config["priority"]["score_weights"]
    severity_weight = load_severity_weights(
        config["priority"]["signals"]["severity"]["weights_config"]
    )
    raw_clusters = [
        _build_raw_cluster(
            indexes,
            bugs,
            similarities,
            config,
            weights,
            severity_weight,
        )
        for indexes in clusters_indexes
    ]
    return _rank_and_assign_clusters(raw_clusters, bugs, config)


def _assign_duplicate_candidates(
    bugs: list[Bug],
    similarities: dict[tuple[int, int], float],
    config: dict[str, Any],
) -> None:
    duplicate_method = config["grouping"]["duplicate_candidates"]
    families = _complete_linkage_components(
        bugs,
        similarities,
        duplicate_method,
    )
    candidate_families = [
        indexes
        for indexes in families
        if len(indexes) >= duplicate_method["minimum_family_size"]
    ]
    for family_number, indexes in enumerate(candidate_families, start=1):
        family_id = f"DF-{family_number:03d}"
        for index in indexes:
            bugs[index]["duplicate_candidate_family_id"] = family_id
            bugs[index]["duplicate_candidate_status"] = "candidate"


def _build_raw_cluster(
    indexes: list[int],
    bugs: list[Bug],
    similarities: dict[tuple[int, int], float],
    config: dict[str, Any],
    weights: dict[str, float],
    severity_weight: dict[str, float],
) -> dict[str, Any]:
    group = [bugs[index] for index in indexes]
    module_counts = Counter(bug["affected_module"] for bug in group)
    type_counts = Counter(
        bug["agent_suggested_bug_type"]
        if bug["agent_suggested_bug_type"] != UNKNOWN
        else bug["bug_type"]
        for bug in group
    )
    cause_counts = Counter(
        bug["agent_suggested_root_cause_category"]
        if bug["agent_suggested_root_cause_category"] != UNKNOWN
        else bug["root_cause_category"]
        for bug in group
    )
    term_counts = Counter(
        term for bug in group for term in tokens(bug, config)
    )
    priority_signals = config["priority"]["signals"]
    production_signal = priority_signals["production"]
    reopened_signal = priority_signals["reopened"]
    severity_signal = priority_signals["severity"]
    production = sum(
        1
        for bug in group
        if bug[production_signal["field"]] == production_signal["value"]
    )
    reopened = sum(
        1
        for bug in group
        if bug[reopened_signal["field"]] == reopened_signal["value"]
    )
    severity_score = sum(
        severity_weight.get(bug[severity_signal["field"]], 0)
        for bug in group
    )
    score = round(
        len(group) * weights["record"]
        + severity_score
        + production * weights["production"]
        + reopened * weights["reopened"],
        1,
    )
    leading_module = module_counts.most_common(1)[0][0]
    leading_type = type_counts.most_common(1)[0][0]
    cluster_method = config["grouping"]["defect_clusters"]
    return {
        "bug_ids": [bug["bug_id"] for bug in group],
        "source_rows": [bug["source_row"] for bug in group],
        "size": len(group),
        "name": _cluster_name(leading_module, leading_type, config),
        "shared_characteristics": {
            "modules": dict(module_counts),
            "bug_types": dict(type_counts),
            "root_cause_signals": dict(cause_counts),
            "environments": dict(
                Counter(bug["environment"] for bug in group)
            ),
            "distinctive_terms": [
                term
                for term, _ in term_counts.most_common(
                    config["features"]["maximum_distinctive_terms"]
                )
            ],
        },
        "production_count": production,
        "reopened_count": reopened,
        "severity_score": severity_score,
        "investigation_score": score,
        "cluster_confidence": config["confidence"]["value"],
        "confidence_basis": config["confidence"]["basis"],
        "methodology": {
            "config": "config/clustering.yml",
            "calibration_status": config["methodology"][
                "calibration_status"
            ],
            "inference_scope": config["methodology"]["inference_scope"],
            "linkage": cluster_method["linkage"],
        },
        "boundary_cases": _boundary_cases(
            indexes,
            bugs,
            similarities,
            cluster_method,
        ),
    }


def _rank_and_assign_clusters(
    raw_clusters: list[dict[str, Any]],
    bugs: list[Bug],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_clusters.sort(
        key=lambda cluster: (
            -cluster["investigation_score"],
            -cluster["size"],
            cluster["bug_ids"][0],
        )
    )
    maximum_prioritized = config["priority"]["maximum_prioritized_clusters"]
    for number, cluster in enumerate(raw_clusters, start=1):
        cluster_id = f"CL-{number:03d}"
        cluster["cluster_id"] = cluster_id
        cluster["priority_rank"] = number
        cluster["prioritized"] = number <= min(
            maximum_prioritized,
            len(raw_clusters),
        )
        source_keys = set(
            zip(cluster["bug_ids"], cluster["source_rows"], strict=True)
        )
        for bug in bugs:
            if (bug["bug_id"], bug["source_row"]) in source_keys:
                bug["cluster_id"] = cluster_id
    return raw_clusters
