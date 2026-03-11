"""Typed LLM output validation with retries and response normalization."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from stageflow.helpers import LLMResponse

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_MISSING = object()


class LLMOutputValidationError(ValueError):
    """Raised when LLM output cannot be validated after retries."""

    def __init__(
        self,
        model: type[BaseModel],
        errors: Sequence[str],
        response: LLMResponse | None,
    ) -> None:
        self.model = model
        self.errors = tuple(errors)
        self.response = response
        super().__init__(
            f"Failed to validate LLM output as {model.__name__} after {len(self.errors)} attempt(s)"
        )


@dataclass(frozen=True, slots=True)
class TypedLLMResult(Generic[_ModelT]):
    """A validated typed LLM response."""

    response: LLMResponse
    parsed: _ModelT
    attempts: int
    validation_errors: tuple[str, ...] = ()


class TypedLLMOutput(Generic[_ModelT]):
    """Validate structured LLM output against a Pydantic model."""

    def __init__(self, model: type[_ModelT], *, strict: bool = False) -> None:
        self._model = model
        self._strict = strict

    @property
    def model(self) -> type[_ModelT]:
        """Return the Pydantic model used for validation."""
        return self._model

    def validate_text(self, text: str) -> _ModelT:
        """Extract JSON from text and validate it."""
        last_error: Exception | None = None
        for candidate in self._json_candidates(text):
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue

            if not isinstance(payload, dict):
                last_error = TypeError("LLM output JSON must decode to an object")
                continue

            return self._model.model_validate(payload, strict=self._strict)

        if last_error is not None:
            raise ValueError(f"Could not parse valid JSON object from LLM output: {last_error}")
        raise ValueError("Could not find a JSON object in LLM output")

    def validate_response(self, response: LLMResponse) -> _ModelT:
        """Validate a normalized provider response."""
        last_error: Exception | None = None
        for candidate in _response_text_candidates(response):
            try:
                return self.validate_text(candidate)
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise ValueError("Could not find structured content in normalized LLM response")

    async def generate(
        self,
        client: Any,
        messages: Sequence[dict[str, Any]],
        *,
        model: str,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> TypedLLMResult[_ModelT]:
        """Call the LLM until output validates or retries are exhausted."""
        working_messages = [dict(message) for message in messages]
        errors: list[str] = []
        last_response: LLMResponse | None = None

        for attempt in range(1, max_retries + 2):
            response = await _call_llm(client, messages=working_messages, model=model, **kwargs)
            last_response = response

            try:
                parsed = self.validate_response(response)
                return TypedLLMResult(
                    response=response,
                    parsed=parsed,
                    attempts=attempt,
                    validation_errors=tuple(errors),
                )
            except Exception as exc:
                errors.append(str(exc))
                if attempt > max_retries:
                    break

                working_messages.extend(
                    [
                        {"role": "assistant", "content": response.content},
                        {
                            "role": "user",
                            "content": self._retry_prompt(str(exc)),
                        },
                    ]
                )

        raise LLMOutputValidationError(self._model, errors, last_response)

    def _retry_prompt(self, error: str) -> str:
        schema = json.dumps(self._model.model_json_schema(), sort_keys=True)
        return (
            "Your previous response was invalid. Return ONLY a valid JSON object, with no markdown, "
            f"that matches this schema: {schema}. Validation error: {error}"
        )

    @staticmethod
    def _json_candidates(text: str) -> list[str]:
        stripped = text.strip()
        candidates: list[str] = []
        if stripped:
            candidates.append(stripped)

        fenced = re.findall(r"```(?:json)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
        candidates.extend(block.strip() for block in fenced if block.strip())

        balanced = _first_balanced_json(stripped)
        if balanced is not None and balanced not in candidates:
            candidates.append(balanced)

        return candidates


async def _call_llm(
    client: Any,
    *,
    messages: Sequence[dict[str, Any]],
    model: str,
    **kwargs: Any,
) -> LLMResponse:
    if hasattr(client, "chat"):
        raw = await client.chat(messages=list(messages), model=model, **kwargs)
    elif hasattr(client, "complete"):
        prompt = _messages_to_prompt(messages)
        raw = await client.complete(prompt, messages=list(messages), model=model, **kwargs)
    else:
        raise TypeError("LLM client must expose either an async 'chat' or 'complete' method")

    return _normalize_llm_response(raw, client=client, fallback_model=model)


def _messages_to_prompt(messages: Sequence[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"{message.get('role', 'user').upper()}: {_coerce_text(message.get('content', ''))}"
        for message in messages
    )


def _normalize_llm_response(raw: Any, *, client: Any, fallback_model: str) -> LLMResponse:
    if isinstance(raw, LLMResponse):
        return raw

    provider = getattr(raw, "provider", None) or client.__class__.__name__.lower()
    if isinstance(raw, str):
        return LLMResponse(content=raw, model=fallback_model, provider=provider)

    usage = _field(raw, "usage")
    choice = _first_choice(raw)
    message = _field(raw, "message") or _field(choice, "message")
    content = _select_content(raw, message)
    finish_reason = _field(raw, "finish_reason") or _field(choice, "finish_reason")
    tool_calls = _normalize_tool_calls(
        _field(raw, "tool_calls")
        or _field(message, "tool_calls")
        or _legacy_function_call(message)
        or _legacy_function_call(raw)
    )

    return LLMResponse(
        content=content,
        model=str(_field(raw, "model") or fallback_model),
        provider=str(_field(raw, "provider") or provider),
        input_tokens=_usage_value(usage, "prompt_tokens"),
        output_tokens=_usage_value(usage, "completion_tokens"),
        finish_reason=str(finish_reason) if finish_reason is not None else None,
        tool_calls=tool_calls,
        cached_tokens=_cached_token_count(usage),
        raw_response=raw,
    )


def _usage_value(usage: Any, key: str) -> int:
    if usage is None:
        return 0
    value = usage.get(key, 0) if isinstance(usage, dict) else getattr(usage, key, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _cached_token_count(usage: Any) -> int:
    prompt_details = _field(usage, "prompt_tokens_details")
    if prompt_details is not None:
        for key in ("cached_tokens", "cache_read_input_tokens"):
            value = _field(prompt_details, key)
            if value is not None:
                return _usage_value({key: value}, key)
    return 0


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _first_choice(raw: Any) -> Any:
    choices = _field(raw, "choices")
    if isinstance(choices, Sequence) and not isinstance(choices, (str, bytes)) and choices:
        return choices[0]
    return None


def _select_content(raw: Any, message: Any) -> str:
    for source in (raw, message):
        content = _extract_present(source, "content")
        if content is not _MISSING:
            flattened = _coerce_text(content)
            if flattened:
                return flattened

    refusal = _field(message, "refusal") or _field(raw, "refusal")
    if refusal is not None:
        return _coerce_text(refusal)

    output_text = _field(raw, "output_text")
    if output_text is not None:
        return _coerce_text(output_text)

    output = _field(raw, "output")
    if output is not None:
        flattened = _coerce_text(output)
        if flattened:
            return flattened

    return ""


def _extract_present(value: Any, name: str) -> Any:
    if value is None:
        return _MISSING
    if isinstance(value, dict):
        return value.get(name, _MISSING)
    return getattr(value, name, _MISSING)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parts = [_coerce_text(item) for item in value]
        return "".join(part for part in parts if part)
    if isinstance(value, dict):
        if "text" in value:
            return _coerce_text(value.get("text"))
        if "content" in value:
            return _coerce_text(value.get("content"))
        if "output_text" in value:
            return _coerce_text(value.get("output_text"))
        if "message" in value:
            return _coerce_text(value.get("message"))
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _legacy_function_call(source: Any) -> list[dict[str, Any]] | None:
    function_call = _field(source, "function_call")
    if function_call is None:
        return None
    return [{"id": _field(function_call, "id") or "call_1", "function": function_call}]


def _normalize_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
    if raw_tool_calls is None:
        return []

    calls = raw_tool_calls if isinstance(raw_tool_calls, Sequence) and not isinstance(raw_tool_calls, (str, bytes)) else [raw_tool_calls]
    normalized: list[dict[str, Any]] = []

    for index, call in enumerate(calls, start=1):
        function = _field(call, "function")
        name = _field(function, "name") or _field(call, "name") or _field(call, "type") or ""
        raw_arguments = (
            _field(function, "arguments")
            if function is not None
            else _field(call, "arguments", _field(call, "input", _field(call, "args", {})))
        )
        arguments = _coerce_arguments(raw_arguments)
        call_id = str(
            _field(call, "id")
            or _field(call, "call_id")
            or _field(call, "tool_call_id")
            or f"call_{index}"
        )

        normalized.append(
            {
                "id": call_id,
                "call_id": call_id,
                "name": str(name),
                "arguments": arguments,
                "type": _field(call, "type") or "function",
                "function": {
                    "name": str(name),
                    "arguments": raw_arguments
                    if isinstance(raw_arguments, str)
                    else json.dumps(arguments, ensure_ascii=False, sort_keys=True),
                },
            }
        )

    return normalized


def _coerce_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _response_text_candidates(response: LLMResponse) -> list[str]:
    candidates: list[str] = []
    if response.content.strip():
        candidates.append(response.content)

    if response.tool_calls:
        synthesized = json.dumps(
            {
                "tool_calls": [
                    {
                        "name": call.get("name", ""),
                        "arguments": call.get("arguments", {}),
                        "call_id": call.get("call_id") or call.get("id"),
                    }
                    for call in response.tool_calls
                ]
            },
            ensure_ascii=False,
        )
        if synthesized not in candidates:
            candidates.append(synthesized)

    return candidates


def _first_balanced_json(text: str) -> str | None:
    for start, char in enumerate(text):
        if char not in "[{":
            continue

        closing = "}" if char == "{" else "]"
        depth = 0
        in_string = False
        escaped = False

        for end in range(start, len(text)):
            current = text[end]
            if in_string:
                if escaped:
                    escaped = False
                    continue
                if current == "\\":
                    escaped = True
                    continue
                if current == '"':
                    in_string = False
                continue

            if current == '"':
                in_string = True
                continue
            if current == char:
                depth += 1
                continue
            if current == closing:
                depth -= 1
                if depth == 0:
                    return text[start : end + 1]
        break
    return None


__all__ = [
    "LLMOutputValidationError",
    "TypedLLMOutput",
    "TypedLLMResult",
]
