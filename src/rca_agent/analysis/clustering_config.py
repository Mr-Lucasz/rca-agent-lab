from __future__ import annotations

from typing import Any

from ..core.config import load_yaml


def load_clustering_config() -> dict[str, Any]:
    config = load_yaml("clustering.yml")
    required = {
        "methodology",
        "features",
        "grouping",
        "priority",
        "confidence",
        "labels",
    }
    if not required <= set(config):
        raise ValueError("config/clustering.yml está incompleto.")
    _validate_grouping(config)
    _validate_priority(config)
    confidence = config["confidence"]
    if not confidence.get("value") or not confidence.get("basis"):
        raise ValueError("Confiança de clustering precisa de valor e base.")
    if (
        config["methodology"].get("inference_scope")
        != "candidate_generation_only"
    ):
        raise ValueError(
            "Clustering não pode ser configurado como confirmação causal."
        )
    return config


def _validate_grouping(config: dict[str, Any]) -> None:
    for name in ("duplicate_candidates", "defect_clusters"):
        method = config["grouping"].get(name, {})
        for field in (
            "similarity_threshold",
            "same_signature_minimum_similarity",
            "boundary_margin",
        ):
            value = method.get(field)
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(
                    f"clustering.grouping.{name}.{field} deve estar entre 0 e 1."
                )
        if method.get("linkage") != "complete":
            raise ValueError(
                f"clustering.grouping.{name}.linkage deve ser 'complete' "
                "para impedir encadeamento por elo único."
            )
    minimum_family_size = config["grouping"]["duplicate_candidates"].get(
        "minimum_family_size"
    )
    if not isinstance(minimum_family_size, int) or minimum_family_size < 2:
        raise ValueError(
            "minimum_family_size deve ser inteiro maior ou igual a 2."
        )
    maximum_terms = config["features"].get("maximum_distinctive_terms")
    if not isinstance(maximum_terms, int) or maximum_terms < 1:
        raise ValueError(
            "maximum_distinctive_terms deve ser inteiro positivo."
        )
    signature = config["features"].get("same_signature", {})
    if (
        not signature.get("required_equal_fields")
        or not signature.get("any_equal_fields")
    ):
        raise ValueError(
            "Critério de assinatura compartilhada está incompleto."
        )


def _validate_priority(config: dict[str, Any]) -> None:
    priority = config["priority"]
    maximum_prioritized = priority.get("maximum_prioritized_clusters")
    if not isinstance(maximum_prioritized, int) or maximum_prioritized < 1:
        raise ValueError(
            "maximum_prioritized_clusters deve ser inteiro positivo."
        )
    score_weights = priority.get("score_weights", {})
    if set(score_weights) != {"record", "production", "reopened"} or not all(
        isinstance(value, (int, float)) and value >= 0
        for value in score_weights.values()
    ):
        raise ValueError("Pesos de prioridade ausentes ou inválidos.")
    signals = priority.get("signals", {})
    if set(signals) != {"production", "reopened", "severity"}:
        raise ValueError("Sinais de prioridade ausentes ou inválidos.")


def load_severity_weights(filename: str) -> dict[str, float]:
    canonical = load_yaml(filename).get("canonical", {})
    weights: dict[str, float] = {}
    for label, details in canonical.items():
        weight = details.get("weight") if isinstance(details, dict) else None
        if not isinstance(weight, (int, float)):
            raise ValueError(
                f"Peso de severidade ausente ou inválido: {label}"
            )
        weights[label] = float(weight)
    return weights
