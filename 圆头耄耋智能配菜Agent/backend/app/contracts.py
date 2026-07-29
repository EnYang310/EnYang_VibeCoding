import json
from typing import Any, Dict, Type

from pydantic import BaseModel

from .models import MODEL_CONTRACT_VERSION


WIRE_SCHEMA_KEYS = frozenset(
    {
        "$defs",
        "$ref",
        "type",
        "properties",
        "required",
        "items",
        "additionalProperties",
        "enum",
        "anyOf",
    }
)


def _compact_schema(
    value: Any,
    *,
    mapping_keys: bool = False,
) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if mapping_keys or key in WIRE_SCHEMA_KEYS:
                result[key] = _compact_schema(
                    item,
                    mapping_keys=key in {"properties", "$defs"},
                )
        return result
    if isinstance(value, list):
        return [_compact_schema(item) for item in value]
    return value


def kimi_mfjs_schema(
    response_model: Type[BaseModel],
) -> Dict[str, Any]:
    return _compact_schema(response_model.model_json_schema())


def _resolve_local_ref(reference: str, definitions: Dict[str, Any]) -> Any:
    prefix = "#/$defs/"
    if not reference.startswith(prefix):
        raise ValueError("contract skeleton 只支持本地 $defs 引用")
    name = reference[len(prefix):].replace("~1", "/").replace("~0", "~")
    if name not in definitions:
        raise ValueError(f"contract skeleton 找不到定义: {name}")
    return definitions[name]


def _skeleton_from_schema(
    schema: Dict[str, Any],
    definitions: Dict[str, Any],
) -> Any:
    if "$ref" in schema:
        target = _resolve_local_ref(schema["$ref"], definitions)
        return _skeleton_from_schema(target, definitions)

    if "enum" in schema:
        return "|".join(str(item) for item in schema["enum"])

    if "anyOf" in schema:
        return "|".join(
            str(_skeleton_from_schema(item, definitions))
            for item in schema["anyOf"]
        )

    schema_type = schema.get("type")
    if schema_type == "object":
        return {
            name: _skeleton_from_schema(child, definitions)
            for name, child in schema.get("properties", {}).items()
        }
    if schema_type == "array":
        return [_skeleton_from_schema(schema.get("items", {}), definitions)]
    if schema_type in {"string", "integer", "number", "boolean", "null"}:
        return schema_type
    return "value"


def compact_contract_skeleton(
    response_model: Type[BaseModel],
) -> str:
    schema = kimi_mfjs_schema(response_model)
    skeleton = _skeleton_from_schema(schema, schema.get("$defs", {}))
    return json.dumps(
        skeleton,
        ensure_ascii=False,
        separators=(",", ":"),
    )
