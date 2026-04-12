"""Typed tool schema helpers for provider-native tool calling."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError


class ToolSchemaError(ValueError):
    """Raised when a tool advertises an invalid provider schema contract."""


class ToolArgumentsValidationError(ToolSchemaError):
    """Raised when provider tool-call arguments fail typed validation."""


def resolve_input_model(tool: Any) -> type[BaseModel] | None:
    """Return the typed input model for a tool if it exposes one."""
    input_model = getattr(tool, "input_model", None)
    if input_model is None:
        return None
    if not isinstance(input_model, type) or not issubclass(input_model, BaseModel):
        raise ToolSchemaError(
            f"Tool {getattr(tool, 'name', tool)!r} input_model must be a Pydantic BaseModel subclass"
        )
    return input_model


def build_tool_input_schema(tool: Any) -> dict[str, Any]:
    """Build the provider schema for a tool."""
    input_model = resolve_input_model(tool)
    if input_model is not None:
        return input_model.model_json_schema()

    schema = getattr(tool, "input_schema", None)
    if schema is None:
        return {"type": "object", "properties": {}}
    if not isinstance(schema, dict):
        raise ToolSchemaError(
            f"Tool {getattr(tool, 'name', tool)!r} input_schema must be a dictionary"
        )
    if not schema:
        return {"type": "object", "properties": {}}
    return schema


def validate_tool_arguments(tool: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate parsed tool-call arguments against the tool contract."""
    input_model = resolve_input_model(tool)
    if input_model is None:
        return arguments

    try:
        parsed = input_model.model_validate(arguments)
    except ValidationError as exc:
        raise ToolArgumentsValidationError(
            f"Tool {getattr(tool, 'action_type', tool)!r} arguments failed validation: {exc}"
        ) from exc

    return parsed.model_dump(mode="python")


__all__ = [
    "ToolArgumentsValidationError",
    "ToolSchemaError",
    "build_tool_input_schema",
    "resolve_input_model",
    "validate_tool_arguments",
]
