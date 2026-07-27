from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator

from .config import schema_path
from .utils import read_json

SchemaLoader = Callable[[str], dict[str, Any]]

_ITEM_SCHEMAS = {
    "agent-review.schema.json": {"evidence": "evidence.schema.json"},
    "analysis.schema.json": {
        "bugs": "bug.schema.json",
        "evidence": "evidence.schema.json",
    },
}


def load_schema(name: str) -> dict[str, Any]:
    """Load a schema from the project's schema repository."""

    return read_json(schema_path(name))


class JsonSchemaValidator:
    """Validates domain documents while keeping schema composition isolated."""

    def __init__(self, schema_loader: SchemaLoader = load_schema) -> None:
        self._load_schema = schema_loader

    def validate(self, value: Any, name: str) -> None:
        schema = self._load_composed_schema(name)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
        if not errors:
            return

        details = "; ".join(
            f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors[:10]
        )
        raise ValueError(f"{name} inválido: {details}")

    def _load_composed_schema(self, name: str) -> dict[str, Any]:
        schema = self._load_schema(name)
        for property_name, item_schema in _ITEM_SCHEMAS.get(name, {}).items():
            schema["properties"][property_name]["items"] = self._load_schema(item_schema)
        return schema


_DEFAULT_VALIDATOR = JsonSchemaValidator()


def validate_schema(value: Any, name: str) -> None:
    """Validate with the default project schema repository."""

    _DEFAULT_VALIDATOR.validate(value, name)
