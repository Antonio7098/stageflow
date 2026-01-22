"""Typed output helper that validates StageOutput payloads."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from stageflow.core import StageOutput

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_PayloadT = _ModelT | dict[str, Any] | None
AsyncPayloadFactory = Callable[[], Awaitable[_PayloadT]]
VersionFactory = Callable[[], str]


class TypedStageOutput(Generic[_ModelT]):
    """Validate and serialize payloads before producing StageOutput.

    Example:
        ```python
        class SummaryPayload(BaseModel):
            text: str
            confidence: float = Field(ge=0, le=1)

        typed = TypedStageOutput(SummaryPayload, strict=False)

        # Validate dict payloads
        output = typed.ok({"text": "done", "confidence": 0.9})

        # Validate async producers
        async def build_payload():
            return {"text": "done", "confidence": 0.9}

        output = await typed.ok_async(build_payload)
        ```
    """

    def __init__(
        self,
        model: type[_ModelT],
        *,
        strict: bool = False,
        context: dict[str, Any] | None = None,
        default_version: str | None = None,
        version_factory: VersionFactory | None = None,
    ) -> None:
        if default_version and version_factory:
            raise ValueError("Provide either default_version or version_factory, not both")

        self._model = model
        self._strict = strict
        self._context = context or {}
        self._default_version = default_version
        self._version_factory = version_factory

    @property
    def model(self) -> type[_ModelT]:
        """Return the underlying Pydantic model type."""

        return self._model

    def validate(self, payload: _PayloadT = None, **kwargs: Any) -> _ModelT:
        """Validate a payload and return the typed model instance."""

        instance = self._coerce_to_model(payload, kwargs)
        return instance

    def serialize(self, payload: _PayloadT = None, **kwargs: Any) -> dict[str, Any]:
        """Validate and return a `dict` representation of the payload."""

        model = self.validate(payload, **kwargs)
        return model.model_dump()

    def ok(
        self,
        payload: _PayloadT = None,
        *,
        version: str | None = None,
        **kwargs: Any,
    ) -> StageOutput:
        """Validate payload and produce a `StageOutput.ok` result."""

        model = self.validate(payload, **kwargs)
        resolved_version = self._resolve_version(version)
        return StageOutput.ok(data=model.model_dump(), version=resolved_version)

    async def ok_async(
        self,
        payload_factory: Awaitable[_PayloadT] | AsyncPayloadFactory,
        *,
        version: str | None = None,
        **kwargs: Any,
    ) -> StageOutput:
        """Await a payload factory before validating and returning output."""

        payload = await self._resolve_payload(payload_factory)
        return self.ok(payload=payload, version=version, **kwargs)

    async def serialize_async(
        self,
        payload_factory: Awaitable[_PayloadT] | AsyncPayloadFactory,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Async variant of :meth:`serialize`."""

        payload = await self._resolve_payload(payload_factory)
        return self.serialize(payload=payload, **kwargs)

    async def validate_async(
        self,
        payload_factory: Awaitable[_PayloadT] | AsyncPayloadFactory,
        **kwargs: Any,
    ) -> _ModelT:
        """Async variant of :meth:`validate`."""

        payload = await self._resolve_payload(payload_factory)
        return self.validate(payload=payload, **kwargs)

    async def _resolve_payload(
        self,
        payload_factory: Awaitable[_PayloadT] | AsyncPayloadFactory,
    ) -> _PayloadT:
        if inspect.isawaitable(payload_factory):
            return await payload_factory  # type: ignore[return-value]
        if callable(payload_factory):
            return await payload_factory()
        raise TypeError("payload_factory must be awaitable or callable returning awaitable")

    def _coerce_to_model(self, payload: _PayloadT, kwargs: dict[str, Any]) -> _ModelT:
        if isinstance(payload, self._model) and not kwargs:
            return payload

        if isinstance(payload, BaseModel):
            data: dict[str, Any] = payload.model_dump()
        elif isinstance(payload, dict):
            data = payload
        elif payload is None:
            data = {}
        else:
            raise TypeError(
                "TypedStageOutput payload must be a dict, BaseModel, or None"
            )

        if kwargs:
            data = {**data, **kwargs}

        return self._model.model_validate(
            data,
            strict=self._strict,
            context=self._context or None,
        )

    def register_contract(
        self,
        stage: str,
        *,
        version: str | None = None,
        description: str | None = None,
    ) -> Any:
        """Register this model with the shared contract registry.

        Args:
            stage: Logical stage name for the contract entry.
            version: Optional explicit version override. Defaults to
                the configured default_version/version_factory.
            description: Optional documentation snippet stored with the entry.
        """

        from .registry import registry as default_registry

        resolved_version = self._resolve_version(version)
        if resolved_version is None:
            raise ValueError("version must be provided or configured to register contract")

        return default_registry.register(
            stage=stage,
            version=resolved_version,
            model=self._model,
            description=description,
        )

    def _resolve_version(self, override: str | None) -> str | None:
        if override is not None:
            return override
        if self._version_factory:
            return self._version_factory()
        return self._default_version

    @staticmethod
    def timestamp_version() -> str:
        """Utility to produce an ISO-8601 timestamp version."""

        return datetime.now(UTC).isoformat()
