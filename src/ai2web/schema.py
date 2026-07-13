"""Minimal JSON-Schema-subset validator for action input schemas. Port of
@ai2web/core validateSchema: pragmatic (object with typed/required properties,
primitives, arrays, enum) rather than the whole of JSON Schema. Used by the server
to validate incoming requests against an action's declared input_schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class SchemaResult:
    valid: bool
    errors: List[str] = field(default_factory=list)


def _type_of(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):  # bool is a subclass of int; check first
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "unknown"


def validate_schema(value: Any, schema: Any, path: str = "input") -> SchemaResult:
    """Validate a value against a JSON-Schema-subset. Empty/absent schema accepts anything."""
    errors: List[str] = []
    if not isinstance(schema, dict) or not schema:
        return SchemaResult(True, errors)

    declared = schema.get("type")
    if declared:
        if declared == "integer":
            ok = isinstance(value, int) and not isinstance(value, bool)
        else:
            ok = _type_of(value) == declared
        if not ok:
            errors.append(f"{path}: expected {declared}, got {_type_of(value)}")
            return SchemaResult(False, errors)  # wrong base type: stop

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path}: value is not one of the allowed options")

    is_object = isinstance(value, dict)
    if (declared == "object" or (not declared and is_object)) and is_object:
        props = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if key not in value:
                errors.append(f"{path}.{key}: required")
        for key, sub in props.items():
            if key in value:
                errors.extend(validate_schema(value[key], sub, f"{path}.{key}").errors)

    if (declared == "array" or (not declared and isinstance(value, list))) and isinstance(value, list) and schema.get("items"):
        for i, item in enumerate(value):
            errors.extend(validate_schema(item, schema["items"], f"{path}[{i}]").errors)

    return SchemaResult(len(errors) == 0, errors)
