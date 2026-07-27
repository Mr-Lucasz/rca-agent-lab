from __future__ import annotations

from typing import Any

from .config import load_yaml


def causal_signal_config() -> dict[str, Any]:
    section = load_yaml("descriptive-analysis.yml").get("causal_signals")
    if not isinstance(section, dict):
        raise ValueError("Configuração causal_signals ausente ou inválida.")
    sources = section.get("sources")
    dimensions = section.get("contextual_dimensions")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("causal_signals.sources deve conter ao menos uma fonte.")
    if not isinstance(dimensions, dict) or not dimensions:
        raise ValueError(
            "causal_signals.contextual_dimensions deve conter ao menos um campo."
        )
    for name, source in sources.items():
        if not isinstance(source, dict):
            raise ValueError(f"Fonte causal inválida: {name}")
        if not all(
            isinstance(source.get(key), str) and source[key].strip()
            for key in ("field", "source_type", "label")
        ):
            raise ValueError(f"Fonte causal incompleta: {name}")
    return section


def causal_signal_fields() -> tuple[str, ...]:
    return tuple(
        source["field"]
        for source in causal_signal_config()["sources"].values()
    )


def has_causal_signal(bug: dict[str, Any]) -> bool:
    config = causal_signal_config()
    unknown = str(config["unknown_value"])
    return any(
        str(bug.get(source["field"], unknown)).strip() not in {"", unknown}
        for source in config["sources"].values()
    )
