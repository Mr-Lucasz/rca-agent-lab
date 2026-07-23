from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .utils import project_root


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    path = project_root() / "config" / name
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Configuração inválida: {path}")
    return value


def schema_path(name: str) -> Path:
    return project_root() / "schemas" / name

