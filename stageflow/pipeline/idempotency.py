"""Idempotency enforcement utilities for WORK stages.

Provides an interceptor that short-circuits duplicate executions based on an
idempotency key stored in the PipelineContext. Results are cached in an
IdempotencyStore so concurrent duplicates return the previously computed
StageResult instead of running the stage again.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from stageflow.pipeline.interceptors import (
    BaseInterceptor,
    CriticalInterceptorError,
    ErrorAction,
    InterceptorResult,
)
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

logger = logging.getLogger("stageflow.idempotency")


class IdempotencyError(CriticalInterceptorError):
    """Base exception for idempotency failures."""

    def __init__(self, message: str) -> None:
        super().__init__(message, interceptor_name="idempotency")


class IdempotencyParamMismatch(IdempotencyError):
    """Raised when cached parameters differ from the active request."""

    def __init__(self, key: str, *, expected: str | None, actual: str | None) -> None:
        super().__init__(
            f"Idempotency key '{key}' parameter mismatch: expected={expected}, actual={actual}"
        )
        self.key = key
        self.expected = expected
        self.actual = actual


@dataclass(slots=True)
class CachedStageResult:
    """Cached StageResult enriched with parameter hash metadata."""

    result: StageResult
    params_hash: str | None = None
    expires_at: float | None = None


class IdempotencyStore(Protocol):
    """Storage backend for cached StageResults."""

    async def get(self, key: str) -> CachedStageResult | None: ...

    async def set(
        self, key: str, entry: CachedStageResult, *, ttl_seconds: int | None = None
    ) -> None: ...

    async def delete(self, key: str) -> None: ...


class InMemoryIdempotencyStore(IdempotencyStore):
    """Simple asyncio-safe in-memory idempotency store."""

    def __init__(self) -> None:
        self._entries: dict[str, CachedStageResult] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> CachedStageResult | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at is not None and entry.expires_at <= time.time():
                del self._entries[key]
                return None
            return CachedStageResult(
                result=_clone_stage_result(entry.result),
                params_hash=entry.params_hash,
                expires_at=entry.expires_at,
            )

    async def set(
        self, key: str, entry: CachedStageResult, *, ttl_seconds: int | None = None
    ) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        async with self._lock:
            self._entries[key] = CachedStageResult(
                result=_clone_stage_result(entry.result),
                params_hash=entry.params_hash,
                expires_at=expires_at,
            )

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._entries.pop(key, None)


class IdempotencyInterceptor(BaseInterceptor):
    """Interceptor that enforces idempotency for WORK stages."""

    name = "idempotency"
    priority = 4  # Run at the outer edge, before timeouts/circuit breakers

    _LOCK_HANDLE_KEY = "_idempotency_lock.handle"
    _LOCK_OWNER_KEY = "_idempotency_lock.owner"

    def __init__(
        self,
        *,
        store: IdempotencyStore | None = None,
        key_extractor: Callable[[PipelineContext], str | None] | None = None,
        params_extractor: Callable[[PipelineContext], dict[str, Any]] | None = None,
        ttl_seconds: int | None = 24 * 60 * 60,
        validate_params: bool = True,
    ) -> None:
        self._store = store or InMemoryIdempotencyStore()
        self._key_extractor = key_extractor or self._default_key_extractor
        self._params_extractor = params_extractor or self._default_params_extractor
        self._ttl_seconds = ttl_seconds
        self._validate_params = validate_params
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._key_locks_guard = asyncio.Lock()

    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        key = self._key_extractor(ctx)
        if not key:
            return None

        cached = await self._store.get(key)
        if cached is not None:
            return self._short_circuit(stage_name, key, cached, ctx)

        lock = await self._get_or_create_lock(key)
        await lock.acquire()
        ctx.data[self._LOCK_HANDLE_KEY] = lock

        cached_after_lock = await self._store.get(key)
        if cached_after_lock is not None:
            self._release_key_lock(ctx, force=True)
            return self._short_circuit(stage_name, key, cached_after_lock, ctx)

        ctx.data[self._LOCK_OWNER_KEY] = True
        return None

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        try:
            if result.status != "completed":
                return

            key = self._key_extractor(ctx)
            if not key:
                return

            params_hash = self._hash_params(self._params_extractor(ctx))
            entry = CachedStageResult(
                result=_clone_stage_result(result),
                params_hash=params_hash,
            )
            await self._store.set(key, entry, ttl_seconds=self._ttl_seconds)
            logger.info(
                "Stored idempotent result",
                extra={"stage": stage_name, "idempotency_key": key, "params_hash": params_hash},
            )
        finally:
            self._release_key_lock(ctx)

    async def on_error(self, _stage_name: str, _error: Exception, ctx: PipelineContext) -> ErrorAction:
        self._release_key_lock(ctx)
        return ErrorAction.FAIL

    def _short_circuit(
        self,
        stage_name: str,
        key: str,
        cached: CachedStageResult,
        ctx: PipelineContext,
    ) -> InterceptorResult:
        current_hash = self._hash_params(self._params_extractor(ctx))
        if (
            self._validate_params
            and cached.params_hash
            and current_hash
            and cached.params_hash != current_hash
        ):
            raise IdempotencyParamMismatch(key, expected=cached.params_hash, actual=current_hash)

        logger.info("Idempotency hit", extra={"stage": stage_name, "idempotency_key": key})
        return InterceptorResult(stage_ran=False, result=cached.result)

    async def _get_or_create_lock(self, key: str) -> asyncio.Lock:
        async with self._key_locks_guard:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._key_locks[key] = lock
            return lock

    def _release_key_lock(self, ctx: PipelineContext, *, force: bool = False) -> None:
        lock = ctx.data.pop(self._LOCK_HANDLE_KEY, None)
        should_release = force or ctx.data.pop(self._LOCK_OWNER_KEY, False)
        if not should_release or lock is None:
            return
        if lock.locked():
            lock.release()

    @staticmethod
    def _default_key_extractor(ctx: PipelineContext) -> str | None:
        key = ctx.data.get("idempotency_key")
        return str(key) if key else None

    @staticmethod
    def _default_params_extractor(ctx: PipelineContext) -> dict[str, Any]:
        params = ctx.data.get("idempotency_params", {})
        return params if isinstance(params, dict) else {}

    @staticmethod
    def _hash_params(params: dict[str, Any] | None) -> str | None:
        if not params:
            return None
        try:
            payload = json.dumps(params, sort_keys=True, default=str)
        except TypeError:
            payload = repr(params)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clone_stage_result(result: StageResult) -> StageResult:
    """Return a deep copy of a StageResult for safe caching."""

    return StageResult(
        name=result.name,
        status=result.status,
        started_at=result.started_at,
        ended_at=result.ended_at,
        data=deepcopy(result.data),
        error=result.error,
    )


__all__ = [
    "CachedStageResult",
    "IdempotencyError",
    "IdempotencyInterceptor",
    "IdempotencyParamMismatch",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
]
