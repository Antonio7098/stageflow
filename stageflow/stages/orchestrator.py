"""Pipeline orchestrator for managing pipeline execution lifecycle.

This module provides the PipelineOrchestrator class for running pipelines
with full observability, cancellation support, and dead letter queue integration.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.ai.framework.events import DbPipelineEventSink, clear_event_sink, set_event_sink
from app.ai.framework.stages.graph import UnifiedPipelineCancelled
from app.database import get_session_context
from app.models.observability import PipelineRun

if TYPE_CHECKING:
    pass

logger = logging.getLogger("orchestrator")


def _get_pipeline_event_logger(db):
    """Lazy import of PipelineEventLogger to avoid circular import."""
    from app.ai.framework.observability import PipelineEventLogger

    return PipelineEventLogger(db)


_cancel_events: dict[uuid.UUID, asyncio.Event] = {}
_active_tasks: dict[uuid.UUID, asyncio.Task[Any]] = {}


def request_cancel(pipeline_run_id: uuid.UUID) -> bool:
    cancel_event = _cancel_events.get(pipeline_run_id)
    if cancel_event is None:
        return False

    cancel_event.set()
    task = _active_tasks.get(pipeline_run_id)
    if task is not None:
        task.cancel()
    return True


def is_cancel_requested(pipeline_run_id: uuid.UUID) -> bool:
    cancel_event = _cancel_events.get(pipeline_run_id)
    return bool(cancel_event and cancel_event.is_set())


SendStatus = Callable[[str, str, dict[str, Any] | None], Awaitable[None]]
# Accept arbitrary parameters so callers can optionally pass flags like is_complete
SendToken = Callable[..., Awaitable[None]]


class PipelineOrchestrator:
    async def run(
        self,
        *,
        pipeline_run_id: uuid.UUID,
        service: str,
        topology: str,
        behavior: str,
        trigger: str,
        request_id: uuid.UUID,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        send_status: SendStatus,
        send_token: SendToken,
        runner: Callable[[SendStatus, SendToken], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        started_at = time.time()

        first_token_event_emitted = False

        cancel_event = asyncio.Event()
        _cancel_events[pipeline_run_id] = cancel_event

        current = asyncio.current_task()
        if current is not None:
            _active_tasks[pipeline_run_id] = current

        await self._ensure_run_row(
            pipeline_run_id=pipeline_run_id,
            service=service,
            topology=topology,
            behavior=behavior,
            status="created",
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            trigger=trigger,
        )

        await self._transition(
            pipeline_run_id=pipeline_run_id,
            status="running",
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            send_status=send_status,
            status_payload={"topology": topology, "behavior": behavior},
        )

        streaming_started = False

        async def _wrapped_send_status(
            stage: str,
            stage_status: str,
            metadata: dict[str, Any] | None,
        ) -> None:
            nonlocal streaming_started
            if cancel_event.is_set():
                raise asyncio.CancelledError
            if stage == "llm" and stage_status == "streaming" and not streaming_started:
                streaming_started = True
                await self._transition(
                    pipeline_run_id=pipeline_run_id,
                    status="streaming",
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    send_status=send_status,
                    status_payload={"topology": topology, "behavior": behavior},
                )

            async with get_session_context() as db:
                event_logger = _get_pipeline_event_logger(db)
                await event_logger.emit(
                    pipeline_run_id=pipeline_run_id,
                    type=f"stage.{stage}.{stage_status}",
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    data=metadata,
                )

            await send_status(stage, stage_status, metadata)

        async def _wrapped_send_token(token: str, **kwargs: Any) -> None:
            nonlocal streaming_started
            nonlocal first_token_event_emitted
            if cancel_event.is_set():
                raise asyncio.CancelledError
            if not streaming_started:
                streaming_started = True
                await self._transition(
                    pipeline_run_id=pipeline_run_id,
                    status="streaming",
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    send_status=send_status,
                    status_payload={"topology": topology, "behavior": behavior},
                )

            if not first_token_event_emitted:
                first_token_event_emitted = True
                async with get_session_context() as db:
                    event_logger = _get_pipeline_event_logger(db)
                    await event_logger.emit(
                        pipeline_run_id=pipeline_run_id,
                        type="llm.first_token",
                        request_id=request_id,
                        session_id=session_id,
                        user_id=user_id,
                        org_id=org_id,
                        data={"service": service, "behavior": behavior},
                    )

            # Forward token to the underlying callback, allowing extra flags like is_complete
            await send_token(token, **kwargs)

        _wrapped_send_token._emits_llm_first_token = True

        set_event_sink(DbPipelineEventSink(run_service=service))

        try:
            result = await runner(_wrapped_send_status, _wrapped_send_token)
        except asyncio.CancelledError:
            try:
                await self._mark_canceled(
                    pipeline_run_id=pipeline_run_id,
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    send_status=send_status,
                    status_payload={"topology": topology, "behavior": behavior},
                )
            except Exception:
                # Observability updates should never mask the original cancellation.
                logger.exception(
                    "Failed to mark pipeline as canceled",
                    extra={"pipeline_run_id": str(pipeline_run_id)},
                )
            return {}
        except UnifiedPipelineCancelled as exc:
            # Graceful pipeline cancellation (e.g., no speech detected)
            # This is NOT an error - it's an intentional early termination
            try:
                await self._mark_cancelled_gracefully(
                    pipeline_run_id=pipeline_run_id,
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    send_status=send_status,
                    status_payload={"topology": topology, "behavior": behavior},
                    reason=exc.reason,
                    cancelled_by_stage=exc.stage,
                    partial_results=exc.results,
                )
            except Exception:
                logger.exception(
                    "Failed to mark pipeline as gracefully cancelled",
                    extra={"pipeline_run_id": str(pipeline_run_id)},
                )
            # Re-raise so the caller can handle it appropriately
            raise
        except Exception as exc:
            try:
                await self._mark_failed(
                    pipeline_run_id=pipeline_run_id,
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    error=str(exc),
                    send_status=send_status,
                    status_payload={"topology": topology, "behavior": behavior},
                )
            except Exception:
                # If marking the run as failed itself fails (e.g. DB/loop issues),
                # log and re-raise the original error so callers still see it.
                logger.exception(
                    "Failed to mark pipeline as failed",
                    extra={"pipeline_run_id": str(pipeline_run_id)},
                )
            raise
        finally:
            _cancel_events.pop(pipeline_run_id, None)
            _active_tasks.pop(pipeline_run_id, None)
            clear_event_sink()

        duration_ms = int((time.time() - started_at) * 1000)
        await self._mark_completed(
            pipeline_run_id=pipeline_run_id,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            duration_ms=duration_ms,
            data=result,
            send_status=send_status,
            status_payload={"topology": topology, "behavior": behavior},
        )
        return result

    async def _ensure_run_row(
        self,
        *,
        pipeline_run_id: uuid.UUID,
        service: str,
        topology: str,
        behavior: str,
        status: str,
        request_id: uuid.UUID,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        trigger: str,
    ) -> None:
        async with get_session_context() as db:
            event_logger = _get_pipeline_event_logger(db)
            run = await event_logger.create_run(
                pipeline_run_id=pipeline_run_id,
                service=service,
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
            )

            run.status = status
            run.topology = topology
            run.behavior = behavior

            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="pipeline.created",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data={"trigger": trigger, "topology": topology},
            )

        logger.info(
            "Pipeline run created",
            extra={
                "service": "orchestrator",
                "pipeline_run_id": str(pipeline_run_id),
                "status": status,
                "metadata": {"topology": topology, "behavior": behavior, "trigger": trigger},
            },
        )

    async def _transition(
        self,
        *,
        pipeline_run_id: uuid.UUID,
        status: str,
        request_id: uuid.UUID,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        send_status: SendStatus,
        status_payload: dict[str, Any] | None,
    ) -> None:
        async with get_session_context() as db:
            run = await db.get(PipelineRun, pipeline_run_id)
            if run is not None:
                run.status = status
                db.add(run)

            event_logger = _get_pipeline_event_logger(db)
            if status == "running":
                await event_logger.emit(
                    pipeline_run_id=pipeline_run_id,
                    type="pipeline.started",
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    data=None,
                )

            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type=f"stage.pipeline.{status}",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data=status_payload,
            )

        await send_status("pipeline", status, status_payload)

        logger.info(
            "Pipeline transition",
            extra={
                "service": "orchestrator",
                "pipeline_run_id": str(pipeline_run_id),
                "status": status,
                "metadata": status_payload,
            },
        )

    async def _mark_completed(
        self,
        *,
        pipeline_run_id: uuid.UUID,
        request_id: uuid.UUID,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        duration_ms: int,
        data: dict[str, Any],
        send_status: SendStatus,
        status_payload: dict[str, Any] | None,
    ) -> None:
        async with get_session_context() as db:
            event_logger = _get_pipeline_event_logger(db)
            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="pipeline.completed",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data=data,
            )

            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="stage.pipeline.completed",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data={**(status_payload or {}), "duration_ms": duration_ms},
            )

            run = await db.get(PipelineRun, pipeline_run_id)
            if run is not None:
                run.status = "completed"
                data_success = data.get("success")
                if isinstance(data_success, bool):
                    run.success = data_success
                    if not data_success:
                        run.error = str(data.get("error") or "unsuccessful")
                    else:
                        run.error = None
                else:
                    run.success = True
                    run.error = None
                interaction_id_raw = data.get("interaction_id")
                if interaction_id_raw:
                    try:
                        run.interaction_id = uuid.UUID(str(interaction_id_raw))
                    except Exception:
                        run.interaction_id = None

        payload = dict(status_payload or {})
        payload["duration_ms"] = duration_ms
        await send_status("pipeline", "completed", payload)

    async def _mark_failed(
        self,
        *,
        pipeline_run_id: uuid.UUID,
        request_id: uuid.UUID,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        error: str,
        send_status: SendStatus,
        status_payload: dict[str, Any] | None,
    ) -> None:
        async with get_session_context() as db:
            event_logger = _get_pipeline_event_logger(db)
            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="pipeline.failed",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data={"error": error},
            )

            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="stage.pipeline.failed",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data={**(status_payload or {}), "error": error},
            )

            run = await db.get(PipelineRun, pipeline_run_id)
            if run is not None:
                run.status = "failed"
                run.success = False
                run.error = error

                # Enqueue to Dead Letter Queue for later inspection
                try:
                    from app.infrastructure.dead_letter_queue import DeadLetterQueueService

                    dlq_service = DeadLetterQueueService(db)

                    # Determine failed stage from error message if available
                    failed_stage = None
                    if "Stage" in error:
                        # Try to extract stage name from error
                        import re

                        match = re.search(r"Stage (\w+) failed", error)
                        if match:
                            failed_stage = match.group(1)

                    # Create PipelineContext-like object for DLQ entry
                    class MinimalContext:
                        def __init__(self):
                            self.pipeline_run_id = pipeline_run_id
                            self.request_id = request_id
                            self.session_id = session_id
                            self.user_id = user_id
                            self.org_id = org_id
                            self.topology = "unknown"
                            self.behavior = (
                                status_payload.get("behavior", "unknown")
                                if status_payload
                                else "unknown"
                            )
                            self.data = {}

                    ctx = MinimalContext()
                    await dlq_service.enqueue(
                        ctx=ctx,
                        error=Exception(error),
                        failed_stage=failed_stage,
                    )
                except Exception as dlq_error:
                    # DLQ enqueue failure should not mask the original error
                    logger.exception(
                        f"Failed to enqueue to DLQ: {dlq_error}",
                        extra={"pipeline_run_id": str(pipeline_run_id)},
                    )

        payload = dict(status_payload or {})
        payload["error"] = error
        await send_status("pipeline", "failed", payload)

    async def _mark_canceled(
        self,
        *,
        pipeline_run_id: uuid.UUID,
        request_id: uuid.UUID,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        send_status: SendStatus,
        status_payload: dict[str, Any] | None,
    ) -> None:
        async with get_session_context() as db:
            event_logger = _get_pipeline_event_logger(db)
            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="pipeline.canceled",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data=None,
            )

            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="stage.pipeline.canceled",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data=status_payload,
            )

            run = await db.get(PipelineRun, pipeline_run_id)
            if run is not None:
                run.status = "canceled"
                run.success = False
                run.error = "canceled"

        await send_status("pipeline", "canceled", dict(status_payload or {}))

    async def _mark_cancelled_gracefully(
        self,
        *,
        pipeline_run_id: uuid.UUID,
        request_id: uuid.UUID,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        send_status: SendStatus,
        status_payload: dict[str, Any] | None,
        reason: str,
        cancelled_by_stage: str,
        partial_results: dict[str, Any] | None,
    ) -> None:
        """Mark pipeline as gracefully cancelled (not an error).

        This is used when a stage intentionally cancels the pipeline,
        e.g., when STT returns no speech. This is different from _mark_canceled
        which is for asyncio.CancelledError (user/system cancellation).
        """
        async with get_session_context() as db:
            event_logger = _get_pipeline_event_logger(db)
            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="pipeline.cancelled_gracefully",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data={
                    "reason": reason,
                    "cancelled_by_stage": cancelled_by_stage,
                    "stages_completed": list(partial_results.keys()) if partial_results else [],
                },
            )

            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="stage.pipeline.cancelled",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data={
                    **(status_payload or {}),
                    "reason": reason,
                    "cancelled_by_stage": cancelled_by_stage,
                },
            )

            run = await db.get(PipelineRun, pipeline_run_id)
            if run is not None:
                # Graceful cancellation is successful - no error occurred
                run.status = "cancelled"
                run.success = True  # No error, just no work to do
                run.error = None

        # Send cancelled status (not failed) to client
        payload = dict(status_payload or {})
        payload["reason"] = reason
        payload["cancelled_by_stage"] = cancelled_by_stage
        await send_status("pipeline", "cancelled", payload)

        logger.info(
            "Pipeline gracefully cancelled",
            extra={
                "service": "orchestrator",
                "pipeline_run_id": str(pipeline_run_id),
                "reason": reason,
                "cancelled_by_stage": cancelled_by_stage,
            },
        )


__all__ = [
    "PipelineOrchestrator",
    "SendStatus",
    "SendToken",
    "request_cancel",
    "is_cancel_requested",
]
