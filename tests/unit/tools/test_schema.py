"""Tests for typed tool schema helpers."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from stageflow.tools import ToolArgumentsValidationError, ToolDefinition, ToolOutput, ToolSchemaError
from stageflow.tools.base import BaseTool, ToolInput
from stageflow.tools.registry import ToolRegistry
from stageflow.tools.schema import build_tool_input_schema


class ExampleToolArgs(BaseModel):
    text: str
    repeat: int = 1


class TypedTool(BaseTool):
    name = "typed"
    description = "Typed tool"
    action_type = "TYPED"
    input_model = ExampleToolArgs

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:  # noqa: ARG002
        return ToolOutput(success=True, data=input.action.payload)


class InvalidTypedTool(BaseTool):
    name = "invalid"
    description = "Invalid tool"
    action_type = "INVALID"
    input_model = dict

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:  # noqa: ARG002
        return ToolOutput(success=True)


def test_base_tool_input_schema_uses_input_model() -> None:
    tool = TypedTool()

    schema = tool.input_schema

    assert schema["type"] == "object"
    assert schema["properties"]["text"]["type"] == "string"
    assert schema["required"] == ["text"]


def test_build_tool_input_schema_rejects_invalid_input_model() -> None:
    with pytest.raises(ToolSchemaError):
        build_tool_input_schema(InvalidTypedTool())


def test_tool_registry_validates_and_normalizes_typed_arguments() -> None:
    registry = ToolRegistry()
    registry.register(TypedTool())

    resolved, unresolved = registry.parse_and_resolve(
        [
            {
                "id": "call_1",
                "function": {
                    "name": "TYPED",
                    "arguments": '{"text": "hello", "repeat": "2"}',
                },
            }
        ]
    )

    assert unresolved == []
    assert resolved[0].arguments == {"text": "hello", "repeat": 2}


def test_tool_registry_reports_invalid_typed_arguments_as_unresolved() -> None:
    registry = ToolRegistry()
    registry.register(TypedTool())

    resolved, unresolved = registry.parse_and_resolve(
        [
            {
                "id": "call_1",
                "function": {
                    "name": "TYPED",
                    "arguments": '{"repeat": 2}',
                },
            }
        ]
    )

    assert resolved == []
    assert len(unresolved) == 1
    assert "failed validation" in unresolved[0].error


async def _noop_handler(_input) -> ToolOutput:
    return ToolOutput.ok()


def test_tool_definition_to_dict_uses_input_model_schema() -> None:
    definition = ToolDefinition(
        name="typed",
        action_type="TYPED",
        handler=_noop_handler,
        input_model=ExampleToolArgs,
    )

    serialized = definition.to_dict()

    assert serialized["input_schema"]["properties"]["repeat"]["type"] == "integer"
    assert serialized["input_schema"]["required"] == ["text"]


def test_tool_arguments_validation_error_is_specialized_schema_error() -> None:
    assert issubclass(ToolArgumentsValidationError, ToolSchemaError)
