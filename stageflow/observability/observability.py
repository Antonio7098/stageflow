"""Observability services and helpers.

Central place for logging external provider calls (LLM, STT, TTS) into the
`ProviderCall` table for debugging, cost tracking, and eval tooling.
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import PipelineEvent, PipelineRun, ProviderCall

logger = logging.getLogger("observability")


def summarize_pipeline_error(exc: Exception) -> dict[str, Any]:
    code = "UNKNOWN"
    stage: str | None = None
    retryable = False

    exc_type = type(exc).__name__
    message = str(exc)

    if isinstance(exc, IntegrityError):
        code = "DB_INTEGRITY_ERROR"
        stage = "db"
        retryable = False
        orig_type = getattr(getattr(exc, "orig", None), "__class__", None)
        if orig_type is not None:
            orig_name = orig_type.__name__
            if orig_name == "ForeignKeyViolationError":
                code = "DB_FK_VIOLATION"
            elif orig_name == "UniqueViolationError":
                code = "DB_UNIQUE_VIOLATION"

    elif isinstance(exc, TimeoutError):
        code = "TIMEOUT"
        retryable = True

    error_summary: dict[str, Any] = {
        "code": code,
        "type": exc_type,
        "message": message[:500],
        "retryable": retryable,
    }
    if stage is not None:
        error_summary["stage"] = stage
    return error_summary


def error_summary_to_string(error_summary: dict[str, Any]) -> str:
    code = error_summary.get("code") or "UNKNOWN"
    msg = error_summary.get("message") or ""
    return f"{code}: {msg}".strip()


def error_summary_to_stages_patch(error_summary: dict[str, Any]) -> dict[str, Any]:
    return {"failure": {"error": error_summary}}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_to_jsonable(v) for v in value)
    return value


def _try_emit_pipeline_event(*, type: str, data: dict[str, Any] | None) -> None:
    try:
        from app.ai.framework.events.sink import get_event_sink

        get_event_sink().try_emit(type=type, data=data)
    except Exception:  # pragma: no cover - defensive path
        logger.exception(
            "Failed to emit pipeline event",
            extra={"service": "observability", "event_type": type},
        )


def _attach_provider_call_id(exc: BaseException, provider_call_id: UUID) -> None:
    try:
        exc._provider_call_id = provider_call_id
    except Exception as exc:  # pragma: no cover - defensive path
        logger.error(
            "Failed to attach provider call ID to exception",
            extra={"service": "observability", "provider_call_id": str(provider_call_id)},
            exc_info=True,
        )


def _parse_context_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _resolve_context_ids(
    *,
    request_id: UUID | None,
    pipeline_run_id: UUID | None,
    session_id: UUID | None,
    user_id: UUID | None,
    org_id: UUID | None,
) -> tuple[UUID | None, UUID | None, UUID | None, UUID | None, UUID | None]:
    try:
        from app.logging_config import (
            org_id_var,
            pipeline_run_id_var,
            request_id_var,
            session_id_var,
            user_id_var,
        )

        ctx_request_id = _parse_context_uuid(request_id_var.get())
        ctx_pipeline_run_id = _parse_context_uuid(pipeline_run_id_var.get())
        ctx_session_id = _parse_context_uuid(session_id_var.get())
        ctx_user_id = _parse_context_uuid(user_id_var.get())
        ctx_org_id = _parse_context_uuid(org_id_var.get())
    except Exception:  # pragma: no cover - defensive path
        ctx_request_id = None
        ctx_pipeline_run_id = None
        ctx_session_id = None
        ctx_user_id = None
        ctx_org_id = None

    return (
        request_id or ctx_request_id,
        pipeline_run_id or ctx_pipeline_run_id,
        session_id or ctx_session_id,
        user_id or ctx_user_id,
        org_id or ctx_org_id,
    )


CircuitState = Literal["closed", "open", "half_open"]


class CircuitBreakerOpenError(Exception):
    """Raised when an LLM call is denied by an open circuit breaker."""

    pass


class CircuitBreaker:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._states: dict[tuple[str, str, str | None], dict[str, Any]] = {}

    async def note_attempt(self, *, operation: str, provider: str, model_id: str | None) -> None:
        settings = get_settings()
        now = time.monotonic()
        key = (operation, provider, model_id)

        async with self._lock:
            state = self._states.get(key)
            if state is None:
                self._states[key] = {
                    "state": "closed",
                    "opened_at": None,
                    "failures": deque(),
                    "half_open_successes": 0,
                }
                return

            if state["state"] == "open":
                opened_at = state.get("opened_at")
                if (
                    opened_at is not None
                    and (now - float(opened_at)) >= settings.circuit_breaker_open_seconds
                ):
                    prev_state = state["state"]
                    state["state"] = "half_open"
                    state["half_open_successes"] = 0
                    _try_emit_pipeline_event(
                        type="circuit.half_opened",
                        data={
                            "operation": operation,
                            "provider": provider,
                            "model_id": model_id,
                            "previous_state": prev_state,
                            "new_state": state["state"],
                            "reason": "open_duration_elapsed",
                        },
                    )

    async def record_success(self, *, operation: str, provider: str, model_id: str | None) -> None:
        settings = get_settings()
        key = (operation, provider, model_id)

        async with self._lock:
            state = self._states.get(key)
            if state is None:
                self._states[key] = {
                    "state": "closed",
                    "opened_at": None,
                    "failures": deque(),
                    "half_open_successes": 0,
                }
                return

            if state["state"] == "half_open":
                state["half_open_successes"] = int(state.get("half_open_successes") or 0) + 1
                if (
                    int(state["half_open_successes"])
                    >= settings.circuit_breaker_half_open_probe_count
                ):
                    prev_state = state["state"]
                    state["state"] = "closed"
                    state["opened_at"] = None
                    failures = state.get("failures")
                    if isinstance(failures, deque):
                        failures.clear()
                    state["half_open_successes"] = 0
                    _try_emit_pipeline_event(
                        type="circuit.closed",
                        data={
                            "operation": operation,
                            "provider": provider,
                            "model_id": model_id,
                            "previous_state": prev_state,
                            "new_state": state["state"],
                            "reason": "half_open_probe_succeeded",
                        },
                    )

    async def record_failure(
        self,
        *,
        operation: str,
        provider: str,
        model_id: str | None,
        reason: str,
    ) -> None:
        settings = get_settings()
        now = time.monotonic()
        key = (operation, provider, model_id)

        async with self._lock:
            state = self._states.get(key)
            if state is None:
                state = {
                    "state": "closed",
                    "opened_at": None,
                    "failures": deque(),
                    "half_open_successes": 0,
                }
                self._states[key] = state

            if state["state"] == "half_open":
                prev_state = state["state"]
                state["state"] = "open"
                state["opened_at"] = now
                state["half_open_successes"] = 0
                _try_emit_pipeline_event(
                    type="circuit.opened",
                    data={
                        "operation": operation,
                        "provider": provider,
                        "model_id": model_id,
                        "previous_state": prev_state,
                        "new_state": state["state"],
                        "reason": reason or "half_open_probe_failed",
                    },
                )
                return

            failures = state.get("failures")
            if not isinstance(failures, deque):
                failures = deque()
                state["failures"] = failures

            window_seconds = settings.circuit_breaker_failure_window_seconds
            cutoff = now - float(window_seconds)
            while failures and float(failures[0]) < cutoff:
                failures.popleft()
            failures.append(now)

            if (
                state["state"] == "closed"
                and len(failures) >= settings.circuit_breaker_failure_threshold
            ):
                prev_state = state["state"]
                state["state"] = "open"
                state["opened_at"] = now
                state["half_open_successes"] = 0
                _try_emit_pipeline_event(
                    type="circuit.opened",
                    data={
                        "operation": operation,
                        "provider": provider,
                        "model_id": model_id,
                        "previous_state": prev_state,
                        "new_state": state["state"],
                        "reason": reason or "failure_threshold_exceeded",
                        "failure_count": len(failures),
                        "window_seconds": window_seconds,
                    },
                )

    async def is_open(self, *, operation: str, provider: str, model_id: str | None) -> bool:
        """Check if the circuit breaker is currently open for the given operation/provider/model.

        Returns:
            True if the circuit is open and calls should be blocked, False otherwise.
            In observe-only mode, always returns False (never blocks calls).
        """
        # In observe-only mode, never block calls
        settings = get_settings()
        if settings.circuit_breaker_observe_only:
            return False

        key = (operation, provider, model_id)

        async with self._lock:
            state = self._states.get(key)
            if state is None:
                return False

            if state["state"] == "open":
                # Check if open duration has elapsed (should transition to half_open)
                settings = get_settings()
                opened_at = state.get("opened_at")
                if (
                    opened_at is not None
                    and (time.monotonic() - float(opened_at))
                    >= settings.circuit_breaker_open_seconds
                ):
                    # Transition to half_open
                    prev_state = state["state"]
                    state["state"] = "half_open"
                    state["half_open_successes"] = 0
                    _try_emit_pipeline_event(
                        type="circuit.half_opened",
                        data={
                            "operation": operation,
                            "provider": provider,
                            "model_id": model_id,
                            "previous_state": prev_state,
                            "new_state": state["state"],
                            "reason": "open_duration_elapsed",
                        },
                    )
                    return False
                return True

            return False


_circuit_breaker = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    """Get the global circuit breaker instance."""
    return _circuit_breaker


class ProviderCallLogger:
    """Logger for external provider API calls."""

    def __init__(self, db: AsyncSession, *, db_lock: asyncio.Lock | None = None) -> None:
        self.db = db
        self._db_lock = db_lock or asyncio.Lock()

    async def update_provider_call(self, call_row: ProviderCall, **fields: Any) -> None:
        async with self._db_lock:
            for key, value in fields.items():
                setattr(call_row, key, value)

    def _emit_provider_call_event(
        self,
        *,
        event: str,
        operation: str,
        provider: str,
        model_id: str | None,
        provider_call_id: UUID,
        latency_ms: int | None,
        success: bool | None,
        error: str | None,
        timeout: bool | None,
        service: str,
    ) -> None:
        _try_emit_pipeline_event(
            type=f"provider.call.{event}",
            data={
                "operation": operation,
                "provider": provider,
                "model_id": model_id,
                "provider_call_id": provider_call_id,
                "latency_ms": latency_ms,
                "success": success,
                "error": error,
                "timeout": timeout,
                "service": service,
            },
        )

    async def call_llm_generate(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        prompt_messages: list[dict[str, Any]] | None,
        call: Callable[[], Awaitable[Any]],
        timeout_seconds: int | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ) -> tuple[Any, ProviderCall]:
        settings = get_settings()
        effective_timeout_seconds = (
            int(timeout_seconds)
            if timeout_seconds is not None
            else settings.provider_timeout_llm_seconds
        )

        (
            effective_request_id,
            effective_pipeline_run_id,
            effective_session_id,
            effective_user_id,
            effective_org_id,
        ) = _resolve_context_ids(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
        )

        # Enforce circuit breaker before attempting the call
        is_denied = await _circuit_breaker.is_open(
            operation="llm.generate",
            provider=provider,
            model_id=model_id,
        )

        if is_denied:
            # Emit denial event
            _try_emit_pipeline_event(
                type="llm.breaker.denied",
                data={
                    "operation": "llm.generate",
                    "provider": provider,
                    "model_id": model_id,
                    "reason": "circuit_open",
                },
            )

            logger.warning(
                "LLM generate call denied by circuit breaker",
                extra={
                    "service": "observability",
                    "operation": "llm.generate",
                    "provider": provider,
                    "model_id": model_id,
                    "session_id": str(effective_session_id) if effective_session_id else None,
                    "user_id": str(effective_user_id) if effective_user_id else None,
                    "request_id": str(effective_request_id) if effective_request_id else None,
                },
            )

            # Raise a specific exception for breaker denial
            raise CircuitBreakerOpenError(
                f"LLM call denied by circuit breaker: provider={provider}, model_id={model_id}"
            )

        json_prompt_messages = (
            _to_jsonable(prompt_messages) if prompt_messages is not None else None
        )
        call_row = ProviderCall(
            id=uuid4(),
            request_id=effective_request_id,
            pipeline_run_id=effective_pipeline_run_id,
            session_id=effective_session_id,
            user_id=effective_user_id,
            interaction_id=interaction_id,
            org_id=effective_org_id,
            service=service,
            operation="llm",
            provider=provider,
            model_id=model_id,
            prompt_messages=json_prompt_messages,
            prompt_text=None,
            output_content=None,
            output_parsed=None,
            latency_ms=None,
            tokens_in=None,
            tokens_out=None,
            audio_duration_ms=None,
            cost_cents=None,
            success=True,
            error=None,
        )
        async with self._db_lock:
            self.db.add(call_row)

            # Flush immediately so callers can safely reference call_row.id via FK
            # (e.g. Interaction.llm_provider_call_id) before a later commit.
            await self.db.flush()

        self._emit_provider_call_event(
            event="started",
            operation="llm.generate",
            provider=provider,
            model_id=model_id,
            provider_call_id=call_row.id,
            latency_ms=None,
            success=None,
            error=None,
            timeout=None,
            service=service,
        )
        await _circuit_breaker.note_attempt(
            operation="llm.generate", provider=provider, model_id=model_id
        )

        started_at = time.time()
        try:
            response = await asyncio.wait_for(call(), timeout=effective_timeout_seconds)
        except asyncio.CancelledError as exc:
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error="cancelled",
            )
            self._emit_provider_call_event(
                event="failed",
                operation="llm.generate",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=call_row.error,
                timeout=False,
                service=service,
            )
            _attach_provider_call_id(exc, call_row.id)
            raise
        except TimeoutError as exc:
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error=f"timeout after {effective_timeout_seconds}s",
            )
            self._emit_provider_call_event(
                event="failed",
                operation="llm.generate",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=str(exc) or call_row.error,
                timeout=True,
                service=service,
            )
            await _circuit_breaker.record_failure(
                operation="llm.generate",
                provider=provider,
                model_id=model_id,
                reason="timeout",
            )
            _attach_provider_call_id(exc, call_row.id)
            raise
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            self._emit_provider_call_event(
                event="failed",
                operation="llm.generate",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
                timeout=False,
                service=service,
            )
            await _circuit_breaker.record_failure(
                operation="llm.generate",
                provider=provider,
                model_id=model_id,
                reason="error",
            )
            _attach_provider_call_id(exc, call_row.id)
            raise

        latency_ms = int((time.time() - started_at) * 1000)
        updates: dict[str, Any] = {
            "latency_ms": latency_ms,
            "success": True,
        }
        if hasattr(response, "content") and response.content is not None:
            updates["output_content"] = str(response.content)
        if hasattr(response, "tokens_in") and response.tokens_in is not None:
            updates["tokens_in"] = int(response.tokens_in)
        if hasattr(response, "tokens_out") and response.tokens_out is not None:
            updates["tokens_out"] = int(response.tokens_out)
        if hasattr(response, "model") and response.model and not call_row.model_id:
            updates["model_id"] = str(response.model)

        await self.update_provider_call(call_row, **updates)

        self._emit_provider_call_event(
            event="succeeded",
            operation="llm.generate",
            provider=provider,
            model_id=call_row.model_id,
            provider_call_id=call_row.id,
            latency_ms=latency_ms,
            success=True,
            error=None,
            timeout=False,
            service=service,
        )
        await _circuit_breaker.record_success(
            operation="llm.generate",
            provider=provider,
            model_id=call_row.model_id,
        )
        return response, call_row

    async def call_llm_stream(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        prompt_messages: list[dict[str, Any]] | None,
        stream: Callable[[], AsyncGenerator[str, None]],
        ttft_timeout_seconds: int | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ) -> tuple[AsyncGenerator[str, None], ProviderCall]:
        settings = get_settings()
        effective_ttft_timeout_seconds = (
            int(ttft_timeout_seconds)
            if ttft_timeout_seconds is not None
            else settings.provider_timeout_llm_stream_ttft_seconds
        )

        (
            effective_request_id,
            effective_pipeline_run_id,
            effective_session_id,
            effective_user_id,
            effective_org_id,
        ) = _resolve_context_ids(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
        )
        # Enforce circuit breaker before attempting the stream call
        is_denied = await _circuit_breaker.is_open(
            operation="llm.stream",
            provider=provider,
            model_id=model_id,
        )

        if is_denied:
            # Emit denial event
            _try_emit_pipeline_event(
                type="llm.breaker.denied",
                data={
                    "operation": "llm.stream",
                    "provider": provider,
                    "model_id": model_id,
                    "reason": "circuit_open",
                },
            )

            logger.warning(
                "LLM stream call denied by circuit breaker",
                extra={
                    "service": "observability",
                    "operation": "llm.stream",
                    "provider": provider,
                    "model_id": model_id,
                    "session_id": str(effective_session_id) if effective_session_id else None,
                    "user_id": str(effective_user_id) if effective_user_id else None,
                    "request_id": str(effective_request_id) if effective_request_id else None,
                },
            )

            # Raise a specific exception for breaker denial so callers can handle it
            raise CircuitBreakerOpenError(
                f"LLM stream call denied by circuit breaker: provider={provider}, model_id={model_id}"
            )

        json_prompt_messages = (
            _to_jsonable(prompt_messages) if prompt_messages is not None else None
        )
        call_row = ProviderCall(
            id=uuid4(),
            request_id=effective_request_id,
            pipeline_run_id=effective_pipeline_run_id,
            session_id=effective_session_id,
            user_id=effective_user_id,
            interaction_id=interaction_id,
            org_id=effective_org_id,
            service=service,
            operation="llm",
            provider=provider,
            model_id=model_id,
            prompt_messages=json_prompt_messages,
            prompt_text=None,
            output_content=None,
            output_parsed=None,
            latency_ms=None,
            tokens_in=None,
            tokens_out=None,
            audio_duration_ms=None,
            cost_cents=None,
            success=True,
            error=None,
        )
        async with self._db_lock:
            self.db.add(call_row)

            # Flush immediately so callers can safely reference call_row.id via FK
            # (e.g. Interaction.llm_provider_call_id) before a later commit.
            await self.db.flush()

        self._emit_provider_call_event(
            event="started",
            operation="llm.stream",
            provider=provider,
            model_id=model_id,
            provider_call_id=call_row.id,
            latency_ms=None,
            success=None,
            error=None,
            timeout=None,
            service=service,
        )
        await _circuit_breaker.note_attempt(
            operation="llm.stream", provider=provider, model_id=model_id
        )

        started_at = time.time()
        inner = stream()

        async def _wrapped() -> AsyncGenerator[str, None]:
            ttft_ms: int | None = None
            finished = False
            try:
                try:
                    first = await asyncio.wait_for(
                        inner.__anext__(),
                        timeout=effective_ttft_timeout_seconds,
                    )
                except StopAsyncIteration:
                    finished = True
                    return

                ttft_ms = int((time.time() - started_at) * 1000)
                _try_emit_pipeline_event(
                    type="provider.call.ttft",
                    data={
                        "operation": "llm.stream",
                        "provider": provider,
                        "model_id": call_row.model_id,
                        "provider_call_id": call_row.id,
                        "ttft_ms": ttft_ms,
                        "service": service,
                    },
                )
                yield first

                async for chunk in inner:
                    yield chunk

                finished = True
            except asyncio.CancelledError as exc:
                latency_ms = int((time.time() - started_at) * 1000)
                await self.update_provider_call(
                    call_row,
                    latency_ms=latency_ms,
                    success=False,
                    error="cancelled",
                )
                self._emit_provider_call_event(
                    event="failed",
                    operation="llm.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    provider_call_id=call_row.id,
                    latency_ms=latency_ms,
                    success=False,
                    error=call_row.error,
                    timeout=False,
                    service=service,
                )
                _attach_provider_call_id(exc, call_row.id)
                raise
            except TimeoutError as exc:
                latency_ms = int((time.time() - started_at) * 1000)
                await self.update_provider_call(
                    call_row,
                    latency_ms=latency_ms,
                    success=False,
                    error=f"ttft_timeout after {effective_ttft_timeout_seconds}s",
                )
                self._emit_provider_call_event(
                    event="failed",
                    operation="llm.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    provider_call_id=call_row.id,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc) or call_row.error,
                    timeout=True,
                    service=service,
                )
                try:
                    await inner.aclose()
                except Exception:
                    logger.exception("Failed to close LLM stream after timeout")
                await _circuit_breaker.record_failure(
                    operation="llm.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    reason="timeout",
                )
                _attach_provider_call_id(exc, call_row.id)
                raise
            except Exception as exc:  # noqa: BLE001
                latency_ms = int((time.time() - started_at) * 1000)
                await self.update_provider_call(
                    call_row,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc),
                )
                self._emit_provider_call_event(
                    event="failed",
                    operation="llm.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    provider_call_id=call_row.id,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc),
                    timeout=False,
                    service=service,
                )
                try:
                    await inner.aclose()
                except Exception:
                    logger.exception("Failed to close LLM stream after error")
                await _circuit_breaker.record_failure(
                    operation="llm.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    reason="error",
                )
                _attach_provider_call_id(exc, call_row.id)
                raise
            finally:
                if finished:
                    latency_ms = int((time.time() - started_at) * 1000)
                    await self.update_provider_call(
                        call_row,
                        latency_ms=latency_ms,
                        success=True,
                    )
                    self._emit_provider_call_event(
                        event="succeeded",
                        operation="llm.stream",
                        provider=provider,
                        model_id=call_row.model_id,
                        provider_call_id=call_row.id,
                        latency_ms=latency_ms,
                        success=True,
                        error=None,
                        timeout=False,
                        service=service,
                    )
                    await _circuit_breaker.record_success(
                        operation="llm.stream",
                        provider=provider,
                        model_id=call_row.model_id,
                    )

        return _wrapped(), call_row

    async def call_stt_transcribe(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        audio_duration_ms: int | None,
        call: Callable[[], Awaitable[Any]],
        timeout_seconds: int | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ) -> tuple[Any, ProviderCall]:
        settings = get_settings()
        effective_timeout_seconds = (
            int(timeout_seconds)
            if timeout_seconds is not None
            else settings.provider_timeout_stt_seconds
        )

        (
            effective_request_id,
            effective_pipeline_run_id,
            effective_session_id,
            effective_user_id,
            effective_org_id,
        ) = _resolve_context_ids(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
        )

        # Enforce circuit breaker before attempting the call
        is_denied = await _circuit_breaker.is_open(
            operation="stt.transcribe",
            provider=provider,
            model_id=model_id,
        )

        if is_denied:
            # Emit denial event
            _try_emit_pipeline_event(
                type="stt.breaker.denied",
                data={
                    "operation": "stt.transcribe",
                    "provider": provider,
                    "model_id": model_id,
                    "reason": "circuit_open",
                },
            )

            logger.warning(
                "STT transcribe call denied by circuit breaker",
                extra={
                    "service": "observability",
                    "operation": "stt.transcribe",
                    "provider": provider,
                    "model_id": model_id,
                    "session_id": str(effective_session_id) if effective_session_id else None,
                    "user_id": str(effective_user_id) if effective_user_id else None,
                    "request_id": str(effective_request_id) if effective_request_id else None,
                },
            )

            # Raise a specific exception for breaker denial
            raise CircuitBreakerOpenError(
                f"STT call denied by circuit breaker: provider={provider}, model_id={model_id}"
            )

        call_row = ProviderCall(
            id=uuid4(),
            request_id=effective_request_id,
            pipeline_run_id=effective_pipeline_run_id,
            session_id=effective_session_id,
            user_id=effective_user_id,
            interaction_id=interaction_id,
            org_id=effective_org_id,
            service=service,
            operation="stt",
            provider=provider,
            model_id=model_id,
            prompt_messages=None,
            prompt_text=None,
            output_content=None,
            output_parsed=None,
            latency_ms=None,
            tokens_in=None,
            tokens_out=None,
            audio_duration_ms=audio_duration_ms,
            cost_cents=None,
            success=True,
            error=None,
        )
        async with self._db_lock:
            self.db.add(call_row)

            # Flush immediately so callers can safely reference call_row.id via FK
            # (e.g. Interaction.stt_provider_call_id) before a later commit.
            await self.db.flush()
            # Commit to make the row visible to other transactions/sessions that may
            # reference it via foreign key before this session commits later.
            with suppress(Exception):
                await self.db.commit()

        self._emit_provider_call_event(
            event="started",
            operation="stt.transcribe",
            provider=provider,
            model_id=model_id,
            provider_call_id=call_row.id,
            latency_ms=None,
            success=None,
            error=None,
            timeout=None,
            service=service,
        )
        await _circuit_breaker.note_attempt(
            operation="stt.transcribe", provider=provider, model_id=model_id
        )

        started_at = time.time()
        try:
            result = await asyncio.wait_for(call(), timeout=effective_timeout_seconds)
        except asyncio.CancelledError as exc:
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error="cancelled",
            )
            self._emit_provider_call_event(
                event="failed",
                operation="stt.transcribe",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=call_row.error,
                timeout=False,
                service=service,
            )
            _attach_provider_call_id(exc, call_row.id)
            raise
        except TimeoutError as exc:
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error=f"timeout after {effective_timeout_seconds}s",
            )
            self._emit_provider_call_event(
                event="failed",
                operation="stt.transcribe",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=str(exc) or call_row.error,
                timeout=True,
                service=service,
            )
            await _circuit_breaker.record_failure(
                operation="stt.transcribe",
                provider=provider,
                model_id=model_id,
                reason="timeout",
            )
            _attach_provider_call_id(exc, call_row.id)
            raise
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            self._emit_provider_call_event(
                event="failed",
                operation="stt.transcribe",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
                timeout=False,
                service=service,
            )
            await _circuit_breaker.record_failure(
                operation="stt.transcribe",
                provider=provider,
                model_id=model_id,
                reason="error",
            )
            _attach_provider_call_id(exc, call_row.id)
            raise

        latency_ms = int((time.time() - started_at) * 1000)
        updates: dict[str, Any] = {
            "latency_ms": latency_ms,
            "success": True,
        }
        if hasattr(result, "transcript") and result.transcript is not None:
            updates["output_content"] = str(result.transcript)
        if hasattr(result, "duration_ms") and result.duration_ms is not None:
            updates["audio_duration_ms"] = int(result.duration_ms)
        await self.update_provider_call(call_row, **updates)

        self._emit_provider_call_event(
            event="succeeded",
            operation="stt.transcribe",
            provider=provider,
            model_id=model_id,
            provider_call_id=call_row.id,
            latency_ms=latency_ms,
            success=True,
            error=None,
            timeout=False,
            service=service,
        )
        await _circuit_breaker.record_success(
            operation="stt.transcribe",
            provider=provider,
            model_id=model_id,
        )
        return result, call_row

    async def call_tts_synthesize(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        prompt_text: str | None,
        call: Callable[[], Awaitable[Any]],
        timeout_seconds: int | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ) -> tuple[Any, ProviderCall]:
        settings = get_settings()
        effective_timeout_seconds = (
            int(timeout_seconds)
            if timeout_seconds is not None
            else settings.provider_timeout_tts_seconds
        )

        (
            effective_request_id,
            effective_pipeline_run_id,
            effective_session_id,
            effective_user_id,
            effective_org_id,
        ) = _resolve_context_ids(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
        )

        # Enforce circuit breaker before attempting the call
        is_denied = await _circuit_breaker.is_open(
            operation="tts.synthesize",
            provider=provider,
            model_id=model_id,
        )

        if is_denied:
            # Emit denial event
            _try_emit_pipeline_event(
                type="tts.breaker.denied",
                data={
                    "operation": "tts.synthesize",
                    "provider": provider,
                    "model_id": model_id,
                    "reason": "circuit_open",
                },
            )

            logger.warning(
                "TTS synthesize call denied by circuit breaker",
                extra={
                    "service": "observability",
                    "operation": "tts.synthesize",
                    "provider": provider,
                    "model_id": model_id,
                    "session_id": str(effective_session_id) if effective_session_id else None,
                    "user_id": str(effective_user_id) if effective_user_id else None,
                    "request_id": str(effective_request_id) if effective_request_id else None,
                },
            )

            # Raise a specific exception for breaker denial
            raise CircuitBreakerOpenError(
                f"TTS call denied by circuit breaker: provider={provider}, model_id={model_id}"
            )

        call_row = ProviderCall(
            id=uuid4(),
            request_id=effective_request_id,
            pipeline_run_id=effective_pipeline_run_id,
            session_id=effective_session_id,
            user_id=effective_user_id,
            interaction_id=interaction_id,
            org_id=effective_org_id,
            service=service,
            operation="tts",
            provider=provider,
            model_id=model_id,
            prompt_messages=None,
            prompt_text=prompt_text,
            output_content=None,
            output_parsed=None,
            latency_ms=None,
            tokens_in=None,
            tokens_out=None,
            audio_duration_ms=None,
            cost_cents=None,
            success=True,
            error=None,
        )
        async with self._db_lock:
            self.db.add(call_row)

            # Flush immediately so callers can safely reference call_row.id via FK
            # (e.g. Interaction.tts_provider_call_id) before a later commit.
            await self.db.flush()

        self._emit_provider_call_event(
            event="started",
            operation="tts.synthesize",
            provider=provider,
            model_id=model_id,
            provider_call_id=call_row.id,
            latency_ms=None,
            success=None,
            error=None,
            timeout=None,
            service=service,
        )
        await _circuit_breaker.note_attempt(
            operation="tts.synthesize", provider=provider, model_id=model_id
        )

        started_at = time.time()
        try:
            result = await asyncio.wait_for(call(), timeout=effective_timeout_seconds)
        except asyncio.CancelledError as exc:
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error="cancelled",
            )
            self._emit_provider_call_event(
                event="failed",
                operation="tts.synthesize",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=call_row.error,
                timeout=False,
                service=service,
            )
            _attach_provider_call_id(exc, call_row.id)
            raise
        except TimeoutError as exc:
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error=f"timeout after {effective_timeout_seconds}s",
            )
            self._emit_provider_call_event(
                event="failed",
                operation="tts.synthesize",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=str(exc) or call_row.error,
                timeout=True,
                service=service,
            )
            await _circuit_breaker.record_failure(
                operation="tts.synthesize",
                provider=provider,
                model_id=model_id,
                reason="timeout",
            )
            _attach_provider_call_id(exc, call_row.id)
            raise
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.time() - started_at) * 1000)
            await self.update_provider_call(
                call_row,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            self._emit_provider_call_event(
                event="failed",
                operation="tts.synthesize",
                provider=provider,
                model_id=model_id,
                provider_call_id=call_row.id,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
                timeout=False,
                service=service,
            )
            await _circuit_breaker.record_failure(
                operation="tts.synthesize",
                provider=provider,
                model_id=model_id,
                reason="error",
            )
            _attach_provider_call_id(exc, call_row.id)
            raise

        latency_ms = int((time.time() - started_at) * 1000)
        updates: dict[str, Any] = {
            "latency_ms": latency_ms,
            "success": True,
        }
        if hasattr(result, "duration_ms") and result.duration_ms is not None:
            updates["audio_duration_ms"] = int(result.duration_ms)
        await self.update_provider_call(call_row, **updates)

        self._emit_provider_call_event(
            event="succeeded",
            operation="tts.synthesize",
            provider=provider,
            model_id=model_id,
            provider_call_id=call_row.id,
            latency_ms=latency_ms,
            success=True,
            error=None,
            timeout=False,
            service=service,
        )
        await _circuit_breaker.record_success(
            operation="tts.synthesize",
            provider=provider,
            model_id=model_id,
        )
        return result, call_row

    async def call_tts_stream(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        prompt_text: str | None,
        stream: Callable[[], AsyncGenerator[bytes, None]],
        ttft_timeout_seconds: int | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ) -> tuple[AsyncGenerator[bytes, None], ProviderCall]:
        settings = get_settings()
        effective_ttft_timeout_seconds = (
            int(ttft_timeout_seconds)
            if ttft_timeout_seconds is not None
            else settings.provider_timeout_tts_seconds
        )

        (
            effective_request_id,
            effective_pipeline_run_id,
            effective_session_id,
            effective_user_id,
            effective_org_id,
        ) = _resolve_context_ids(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
        )

        # Enforce circuit breaker before attempting the stream call
        is_denied = await _circuit_breaker.is_open(
            operation="tts.stream",
            provider=provider,
            model_id=model_id,
        )

        if is_denied:
            # Emit denial event
            _try_emit_pipeline_event(
                type="tts.breaker.denied",
                data={
                    "operation": "tts.stream",
                    "provider": provider,
                    "model_id": model_id,
                    "reason": "circuit_open",
                },
            )

            logger.warning(
                "TTS stream call denied by circuit breaker",
                extra={
                    "service": "observability",
                    "operation": "tts.stream",
                    "provider": provider,
                    "model_id": model_id,
                    "session_id": str(effective_session_id) if effective_session_id else None,
                    "user_id": str(effective_user_id) if effective_user_id else None,
                    "request_id": str(effective_request_id) if effective_request_id else None,
                },
            )

            # Raise a specific exception for breaker denial so callers can handle it
            raise CircuitBreakerOpenError(
                f"TTS stream call denied by circuit breaker: provider={provider}, model_id={model_id}"
            )

        call_row = ProviderCall(
            id=uuid4(),
            request_id=effective_request_id,
            pipeline_run_id=effective_pipeline_run_id,
            session_id=effective_session_id,
            user_id=effective_user_id,
            interaction_id=interaction_id,
            org_id=effective_org_id,
            service=service,
            operation="tts",
            provider=provider,
            model_id=model_id,
            prompt_messages=None,
            prompt_text=prompt_text,
            output_content=None,
            output_parsed=None,
            latency_ms=None,
            tokens_in=None,
            tokens_out=None,
            audio_duration_ms=None,
            cost_cents=None,
            success=True,
            error=None,
        )
        async with self._db_lock:
            self.db.add(call_row)

            # Flush immediately so callers can safely reference call_row.id via FK
            # (e.g. Interaction.tts_provider_call_id) before a later commit.
            await self.db.flush()

        self._emit_provider_call_event(
            event="started",
            operation="tts.stream",
            provider=provider,
            model_id=model_id,
            provider_call_id=call_row.id,
            latency_ms=None,
            success=None,
            error=None,
            timeout=None,
            service=service,
        )
        await _circuit_breaker.note_attempt(
            operation="tts.stream", provider=provider, model_id=model_id
        )

        started_at = time.time()
        inner = stream()

        async def _wrapped() -> AsyncGenerator[bytes, None]:
            finished = False
            try:
                try:
                    first = await asyncio.wait_for(
                        inner.__anext__(),
                        timeout=effective_ttft_timeout_seconds,
                    )
                except StopAsyncIteration:
                    finished = True
                    return

                ttft_ms = int((time.time() - started_at) * 1000)
                _try_emit_pipeline_event(
                    type="provider.call.ttft",
                    data={
                        "operation": "tts.stream",
                        "provider": provider,
                        "model_id": call_row.model_id,
                        "provider_call_id": call_row.id,
                        "ttft_ms": ttft_ms,
                        "service": service,
                    },
                )
                yield first

                async for chunk in inner:
                    yield chunk

                finished = True
            except asyncio.CancelledError as exc:
                latency_ms = int((time.time() - started_at) * 1000)
                await self.update_provider_call(
                    call_row,
                    latency_ms=latency_ms,
                    success=False,
                    error="cancelled",
                )
                self._emit_provider_call_event(
                    event="failed",
                    operation="tts.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    provider_call_id=call_row.id,
                    latency_ms=latency_ms,
                    success=False,
                    error=call_row.error,
                    timeout=False,
                    service=service,
                )
                _attach_provider_call_id(exc, call_row.id)
                raise
            except TimeoutError as exc:
                latency_ms = int((time.time() - started_at) * 1000)
                await self.update_provider_call(
                    call_row,
                    latency_ms=latency_ms,
                    success=False,
                    error=f"ttft_timeout after {effective_ttft_timeout_seconds}s",
                )
                self._emit_provider_call_event(
                    event="failed",
                    operation="tts.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    provider_call_id=call_row.id,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc) or call_row.error,
                    timeout=True,
                    service=service,
                )
                try:
                    await inner.aclose()
                except Exception:
                    logger.exception("Failed to close TTS stream after timeout")
                await _circuit_breaker.record_failure(
                    operation="tts.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    reason="timeout",
                )
                _attach_provider_call_id(exc, call_row.id)
                raise
            except Exception as exc:  # noqa: BLE001
                latency_ms = int((time.time() - started_at) * 1000)
                await self.update_provider_call(
                    call_row,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc),
                )
                self._emit_provider_call_event(
                    event="failed",
                    operation="tts.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    provider_call_id=call_row.id,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc),
                    timeout=False,
                    service=service,
                )
                try:
                    await inner.aclose()
                except Exception:
                    logger.exception("Failed to close TTS stream after error")
                await _circuit_breaker.record_failure(
                    operation="tts.stream",
                    provider=provider,
                    model_id=call_row.model_id,
                    reason="error",
                )
                _attach_provider_call_id(exc, call_row.id)
                raise
            finally:
                if finished:
                    latency_ms = int((time.time() - started_at) * 1000)
                    await self.update_provider_call(
                        call_row,
                        latency_ms=latency_ms,
                        success=True,
                    )
                    self._emit_provider_call_event(
                        event="succeeded",
                        operation="tts.stream",
                        provider=provider,
                        model_id=call_row.model_id,
                        provider_call_id=call_row.id,
                        latency_ms=latency_ms,
                        success=True,
                        error=None,
                        timeout=False,
                        service=service,
                    )
                    await _circuit_breaker.record_success(
                        operation="tts.stream",
                        provider=provider,
                        model_id=call_row.model_id,
                    )

        return _wrapped(), call_row

    @asynccontextmanager
    async def time_llm_call(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        prompt_messages: list[dict[str, Any]] | None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ):
        """Async context manager to time and log an LLM call.

        Usage pattern::

            async with call_logger.time_llm_call(...) as log:
                response = await llm.generate(...)
                log["output_content"] = response.content
                log["output_parsed"] = parsed
                log["tokens_in"] = response.tokens_in
                log["tokens_out"] = response.tokens_out
                log["cost_cents"] = cost_cents
        """

        start = time.time()
        payload: dict[str, Any] = {
            "output_content": None,
            "output_parsed": None,
            "tokens_in": None,
            "tokens_out": None,
            "cost_cents": None,
            "success": True,
            "error": None,
        }

        try:
            yield payload
        except Exception as exc:  # pragma: no cover - defensive path
            latency_ms = int((time.time() - start) * 1000)
            try:
                await self.log_llm_call(
                    service=service,
                    provider=provider,
                    model_id=model_id,
                    prompt_messages=prompt_messages,
                    output_content=payload.get("output_content"),
                    output_parsed=payload.get("output_parsed"),
                    latency_ms=latency_ms,
                    tokens_in=payload.get("tokens_in"),
                    tokens_out=payload.get("tokens_out"),
                    cost_cents=payload.get("cost_cents"),
                    success=False,
                    error=str(exc),
                    session_id=session_id,
                    user_id=user_id,
                    interaction_id=interaction_id,
                    request_id=request_id,
                    pipeline_run_id=pipeline_run_id,
                    org_id=org_id,
                )
            except Exception:
                logger.exception("Failed to log timed LLM provider call (error path)")
            raise
        else:
            latency_ms = int((time.time() - start) * 1000)
            try:
                await self.log_llm_call(
                    service=service,
                    provider=provider,
                    model_id=model_id,
                    prompt_messages=prompt_messages,
                    output_content=payload.get("output_content"),
                    output_parsed=payload.get("output_parsed"),
                    latency_ms=latency_ms,
                    tokens_in=payload.get("tokens_in"),
                    tokens_out=payload.get("tokens_out"),
                    cost_cents=payload.get("cost_cents"),
                    success=bool(payload.get("success", True)),
                    error=payload.get("error"),
                    session_id=session_id,
                    user_id=user_id,
                    interaction_id=interaction_id,
                    request_id=request_id,
                    pipeline_run_id=pipeline_run_id,
                    org_id=org_id,
                )
            except Exception:  # pragma: no cover - defensive path
                logger.exception("Failed to log timed LLM provider call (success path)")

    async def log_llm_call(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        prompt_messages: list[dict[str, Any]] | None,
        output_content: str | None,
        output_parsed: dict[str, Any] | None,
        latency_ms: int | None,
        tokens_in: int | None,
        tokens_out: int | None,
        cost_cents: int | None,
        success: bool,
        error: str | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ) -> ProviderCall:
        """Log an LLM API call to provider_calls.

        This method is used by chat, triage, assessment, and summary services.
        """

        json_prompt_messages = (
            _to_jsonable(prompt_messages) if prompt_messages is not None else None
        )
        json_output_parsed = _to_jsonable(output_parsed) if output_parsed is not None else None

        call = ProviderCall(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            session_id=session_id,
            user_id=user_id,
            interaction_id=interaction_id,
            org_id=org_id,
            service=service,
            operation="llm",
            provider=provider,
            model_id=model_id,
            prompt_messages=json_prompt_messages,
            prompt_text=None,
            output_content=output_content,
            output_parsed=json_output_parsed,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            audio_duration_ms=None,
            cost_cents=cost_cents,
            success=success,
            error=error,
        )

        self.db.add(call)
        # Note: No flush/commit here - let the calling service batch commits

        logger.debug(
            "Provider LLM call logged",
            extra={
                "service": service,
                "provider": provider,
                "model_id": model_id,
                "success": success,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_cents": cost_cents,
            },
        )

        return call

    async def log_stt_call(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        audio_duration_ms: int | None,
        output_content: str | None,
        latency_ms: int | None,
        cost_cents: int | None,
        success: bool,
        error: str | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ) -> ProviderCall:
        """Log an STT API call (transcription)."""

        call = ProviderCall(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            session_id=session_id,
            user_id=user_id,
            interaction_id=interaction_id,
            org_id=org_id,
            service=service,
            operation="stt",
            provider=provider,
            model_id=model_id,
            prompt_messages=None,
            prompt_text=None,
            output_content=output_content,
            output_parsed=None,
            latency_ms=latency_ms,
            tokens_in=None,
            tokens_out=None,
            audio_duration_ms=audio_duration_ms,
            cost_cents=cost_cents,
            success=success,
            error=error,
        )

        self.db.add(call)
        # Note: No flush/commit here - let the calling service batch commits

        logger.debug(
            "Provider STT call logged",
            extra={
                "service": service,
                "provider": provider,
                "model_id": model_id,
                "success": success,
                "latency_ms": latency_ms,
                "audio_duration_ms": audio_duration_ms,
                "cost_cents": cost_cents,
            },
        )

        return call

    async def log_tts_call(
        self,
        *,
        service: str,
        provider: str,
        model_id: str | None,
        prompt_text: str | None,
        audio_duration_ms: int | None,
        latency_ms: int | None,
        cost_cents: int | None,
        success: bool,
        error: str | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        interaction_id: UUID | None = None,
        request_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        org_id: UUID | None = None,
    ) -> ProviderCall:
        """Log a TTS API call (speech synthesis)."""

        call = ProviderCall(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            session_id=session_id,
            user_id=user_id,
            interaction_id=interaction_id,
            org_id=org_id,
            service=service,
            operation="tts",
            provider=provider,
            model_id=model_id,
            prompt_messages=None,
            prompt_text=prompt_text,
            output_content=None,
            output_parsed=None,
            latency_ms=latency_ms,
            tokens_in=None,
            tokens_out=None,
            audio_duration_ms=audio_duration_ms,
            cost_cents=cost_cents,
            success=success,
            error=error,
        )

        self.db.add(call)
        # Note: No flush/commit here - let the calling service batch commits

        logger.debug(
            "Provider TTS call logged",
            extra={
                "service": service,
                "provider": provider,
                "model_id": model_id,
                "success": success,
                "latency_ms": latency_ms,
                "audio_duration_ms": audio_duration_ms,
                "cost_cents": cost_cents,
            },
        )

        return call


class PipelineRunLogger:
    """Persist aggregated pipeline run metrics."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_run(
        self,
        *,
        pipeline_run_id: UUID | None = None,
        service: str,
        request_id: UUID | None = None,
        org_id: UUID | None = None,
        session_id: UUID | None,
        user_id: UUID | None,
        interaction_id: UUID | None,
        stt_provider_call_id: UUID | None,
        llm_provider_call_id: UUID | None,
        tts_provider_call_id: UUID | None,
        total_latency_ms: int | None,
        ttft_ms: int | None,
        ttfa_ms: int | None,
        ttfc_ms: int | None,
        tokens_in: int | None,
        tokens_out: int | None,
        input_audio_duration_ms: int | None,
        output_audio_duration_ms: int | None,
        tts_chunk_count: int | None,
        total_cost_cents: int | None,
        tokens_per_second: int | None,
        success: bool,
        error: str | None,
        stages: dict | None,
        metadata: dict | None = None,
    ) -> PipelineRun:
        run: PipelineRun | None = None
        if pipeline_run_id is not None:
            run = await self.db.get(PipelineRun, pipeline_run_id)

        if run is None:
            create_kwargs: dict[str, Any] = {
                "service": service,
                "request_id": request_id,
                "org_id": org_id,
                "session_id": session_id,
                "user_id": user_id,
                "interaction_id": interaction_id,
                "stt_provider_call_id": stt_provider_call_id,
                "llm_provider_call_id": llm_provider_call_id,
                "tts_provider_call_id": tts_provider_call_id,
                "total_latency_ms": total_latency_ms,
                "ttft_ms": ttft_ms,
                "ttfa_ms": ttfa_ms,
                "ttfc_ms": ttfc_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "input_audio_duration_ms": input_audio_duration_ms,
                "output_audio_duration_ms": output_audio_duration_ms,
                "tts_chunk_count": tts_chunk_count,
                "total_cost_cents": total_cost_cents,
                "tokens_per_second": tokens_per_second,
                "success": success,
                "error": error,
                "stages": _to_jsonable(stages) if stages is not None else None,
            }
            if pipeline_run_id is not None:
                create_kwargs["id"] = pipeline_run_id

            run = PipelineRun(**create_kwargs)
            self.db.add(run)
            return run

        run.service = service
        run.request_id = request_id
        run.org_id = org_id
        run.session_id = session_id
        run.user_id = user_id
        run.interaction_id = interaction_id
        run.stt_provider_call_id = stt_provider_call_id
        run.llm_provider_call_id = llm_provider_call_id
        run.tts_provider_call_id = tts_provider_call_id
        run.total_latency_ms = total_latency_ms
        run.ttft_ms = ttft_ms
        run.ttfa_ms = ttfa_ms
        run.ttfc_ms = ttfc_ms
        run.tokens_in = tokens_in
        run.tokens_out = tokens_out
        run.input_audio_duration_ms = input_audio_duration_ms
        run.output_audio_duration_ms = output_audio_duration_ms
        run.tts_chunk_count = tts_chunk_count
        run.total_cost_cents = total_cost_cents
        run.tokens_per_second = tokens_per_second
        run.success = success
        run.error = error
        run.stages = _to_jsonable(stages) if stages is not None else None
        run.metadata = _to_jsonable(metadata) if metadata is not None else None

        self.db.add(run)
        return run


class PipelineEventLogger:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_run(
        self,
        *,
        pipeline_run_id: UUID,
        service: str,
        request_id: UUID | None,
        session_id: UUID | None,
        user_id: UUID | None,
        org_id: UUID | None,
    ) -> PipelineRun:
        existing = await self.db.get(PipelineRun, pipeline_run_id)
        if existing is not None:
            return existing

        run = PipelineRun(
            id=pipeline_run_id,
            service=service,
            request_id=request_id,
            org_id=org_id,
            session_id=session_id,
            user_id=user_id,
            success=True,
            error=None,
        )
        self.db.add(run)
        return run

    async def emit(
        self,
        *,
        pipeline_run_id: UUID,
        type: str,
        request_id: UUID | None,
        session_id: UUID | None,
        user_id: UUID | None,
        org_id: UUID | None,
        data: dict | None,
    ) -> PipelineEvent:
        event = PipelineEvent(
            pipeline_run_id=pipeline_run_id,
            type=type,
            data=_to_jsonable(data) if data is not None else None,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
        )
        self.db.add(event)
        return event
