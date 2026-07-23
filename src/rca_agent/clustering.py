from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from .utils import UNKNOWN, fold

STOPWORDS = {
    "a", "ao", "as", "com", "da", "das", "de", "do", "dos", "e", "em", "na", "nas",
    "no", "nos", "o", "os", "para", "por", "que", "sem", "um", "uma", "the", "and",
    "for", "with", "when", "bug", "erro", "falha",
}

BUG_TYPE_LABELS = {
    "security": "falhas de segurança",
    "integration": "falhas de integração",
    "data": "incidentes de dados",
    "functional": "falhas funcionais",
    "visual": "quebras visuais",
    "reliability": "falhas de confiabilidade",
    UNKNOWN: "sinais mistos",
}


def _signature_tokens(bug: dict[str, Any]) -> list[str]:
    values = []
    for prefix, field in (
        ("module", "affected_module"),
        ("type", "bug_type"),
        ("cause", "root_cause_category"),
        ("team", "team"),
        ("version", "version"),
        ("env", "environment"),
    ):
        value = fold(bug.get(field, ""))
        if value and value != UNKNOWN:
            values.extend(f"{prefix}:{token}" for token in re.findall(r"[a-z0-9]{3,}", value))
    return values


def _cluster_name(module: str, bug_type: str) -> str:
    label = BUG_TYPE_LABELS.get(bug_type, bug_type.replace("-", " "))
    if module == UNKNOWN:
        return f"Cluster de {label}"
    return f"{module.title()} · {label}"


def tokens(bug: dict[str, Any]) -> set[str]:
    text = fold(
        " ".join(
            str(bug.get(field, ""))
            for field in ("title", "description", "actual_behavior", "qa_analysis_notes", "dev_analysis_notes")
        )
    )
    textual = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text)
        if token not in STOPWORDS and token != UNKNOWN
    }
    return textual | set(_signature_tokens(bug))


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _components(bugs: list[dict[str, Any]], threshold: float) -> list[list[int]]:
    token_sets = [tokens(bug) for bug in bugs]
    graph: dict[int, set[int]] = defaultdict(set)
    for left in range(len(bugs)):
        for right in range(left + 1, len(bugs)):
            same_module = (
                bugs[left]["affected_module"] != UNKNOWN
                and bugs[left]["affected_module"] == bugs[right]["affected_module"]
            )
            similarity = jaccard(token_sets[left], token_sets[right])
            same_signature = (
                same_module
                and (
                    bugs[left]["bug_type"] == bugs[right]["bug_type"]
                    or bugs[left]["root_cause_category"] == bugs[right]["root_cause_category"]
                    or bugs[left]["team"] == bugs[right]["team"]
                )
            )
            if similarity >= threshold or (similarity >= threshold - 0.12 and same_signature):
                graph[left].add(right)
                graph[right].add(left)
    seen: set[int] = set()
    components: list[list[int]] = []
    for index in range(len(bugs)):
        if index in seen:
            continue
        stack = [index]
        component: list[int] = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(graph[current] - seen)
        components.append(sorted(component))
    return components


def build_clusters(bugs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    families = _components(bugs, threshold=0.58)
    for family_number, indexes in enumerate(
        sorted(families, key=lambda item: (-len(item), item[0])), start=1
    ):
        family_id = f"DF-{family_number:03d}"
        for index in indexes:
            bugs[index]["duplicate_family_id"] = family_id

    clusters_indexes = _components(bugs, threshold=0.36)
    raw_clusters: list[dict[str, Any]] = []
    severity_weight = {"critical": 5, "high": 3, "medium": 2, "low": 1, UNKNOWN: 0}
    for indexes in clusters_indexes:
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
        term_counts = Counter(term for bug in group for term in tokens(bug))
        production = sum(1 for bug in group if bug["environment"] == "production")
        reopened = sum(1 for bug in group if bug["reopened"] == "true")
        severity_score = sum(severity_weight.get(bug["severity"], 0) for bug in group)
        score = round(len(group) * 2 + severity_score + production * 2 + reopened * 2, 1)
        leading_module = module_counts.most_common(1)[0][0]
        leading_type = type_counts.most_common(1)[0][0]
        raw_clusters.append(
            {
                "bug_ids": [bug["bug_id"] for bug in group],
                "source_rows": [bug["source_row"] for bug in group],
                "size": len(group),
                "name": _cluster_name(leading_module, leading_type),
                "shared_characteristics": {
                    "modules": dict(module_counts),
                    "bug_types": dict(type_counts),
                    "root_cause_signals": dict(cause_counts),
                    "environments": dict(Counter(bug["environment"] for bug in group)),
                    "distinctive_terms": [term for term, _ in term_counts.most_common(8)],
                },
                "production_count": production,
                "reopened_count": reopened,
                "severity_score": severity_score,
                "investigation_score": score,
                "cluster_confidence": "medium" if len(group) > 1 else "low",
                "boundary_cases": [],
            }
        )

    raw_clusters.sort(
        key=lambda cluster: (
            -cluster["investigation_score"],
            -cluster["size"],
            cluster["bug_ids"][0],
        )
    )
    for number, cluster in enumerate(raw_clusters, start=1):
        cluster_id = f"CL-{number:03d}"
        cluster["cluster_id"] = cluster_id
        cluster["priority_rank"] = number
        cluster["prioritized"] = number <= min(3, len(raw_clusters))
        bug_ids = set(cluster["bug_ids"])
        for bug in bugs:
            if bug["bug_id"] in bug_ids and bug["source_row"] in cluster["source_rows"]:
                bug["cluster_id"] = cluster_id
    return raw_clusters

