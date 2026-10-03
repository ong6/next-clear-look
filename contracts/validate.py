#!/usr/bin/env python3
"""Validate OpenAPI structure, operation coverage, examples, and SSE schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate_spec


ROOT = Path(__file__).resolve().parent
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_ref(document: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in value:
        ref = value["$ref"]
        if not ref.startswith("#/"):
            raise ValueError(f"unsupported reference in validator: {ref}")
        current: Any = document
        for part in ref[2:].split("/"):
            current = current[part.replace("~1", "/").replace("~0", "~")]
        value = current
    return value


def validate_instance(spec: dict[str, Any], schema: dict[str, Any], value: Any, label: str) -> None:
    wrapped = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "components": spec["components"],
        "allOf": [schema],
    }
    errors = sorted(Draft202012Validator(wrapped).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(f"{list(item.path)}: {item.message}" for item in errors[:5])
        raise ValueError(f"{label}: {details}")


def main() -> None:
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    validate_spec(spec)

    operations: dict[str, dict[str, Any]] = {}
    for path_item in spec["paths"].values():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                operation_id = operation.get("operationId")
                if not operation_id or operation_id in operations:
                    raise ValueError(f"missing or duplicate operationId: {operation_id}")
                operations[operation_id] = operation

    coverage = load_json(ROOT / "examples" / "operation-examples.json")
    if set(coverage) != set(operations):
        missing = sorted(set(operations) - set(coverage))
        extra = sorted(set(coverage) - set(operations))
        raise ValueError(f"operation example coverage mismatch: missing={missing}, extra={extra}")

    for operation_id, entry in coverage.items():
        operation = operations[operation_id]
        request_file = entry.get("request")
        if request_file:
            request_body = resolve_ref(spec, operation["requestBody"])
            media = next(iter(request_body["content"].values()))
            validate_instance(spec, media["schema"], load_json(ROOT / "examples" / request_file), f"{operation_id} request")
        for response_example in entry["responses"]:
            filename = response_example["file"]
            status = str(response_example["status"])
            if filename is None or filename.endswith((".png", ".sse")):
                continue
            response = resolve_ref(spec, operation["responses"][status])
            media = next(iter(response["content"].values()))
            validate_instance(spec, media["schema"], load_json(ROOT / "examples" / filename), f"{operation_id} {status} {filename}")

    envelope = load_json(ROOT / "events" / "envelope.schema.json")
    Draft202012Validator.check_schema(envelope)
    event_examples = load_json(ROOT / "examples" / "sse-events.json")
    schemas = sorted(path for path in (ROOT / "events").glob("*.schema.json") if path.name != "envelope.schema.json")
    if len(schemas) != len(event_examples):
        raise ValueError(f"event schema/example mismatch: {len(schemas)} schemas, {len(event_examples)} examples")
    by_type = {item["type"]: item for item in event_examples}
    for path in schemas:
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        event_type = path.name.removesuffix(".schema.json")
        local_schema = {"allOf": [envelope, schema["allOf"][1]]}
        Draft202012Validator(local_schema).validate(by_type[event_type])
        event = by_type[event_type]
        if event["mode"] == "replay" and event["emitted_at"] != event["clock_time"]:
            raise ValueError(f"{event_type}: replay emitted_at must equal clock_time")

    print(f"validated {len(operations)} operations, {len(schemas)} SSE event schemas, and all generated examples")


if __name__ == "__main__":
    main()
