"""Tests for OpenTelemetry integration and correlation ID propagation."""

import asyncio
from uuid import uuid4

import pytest

from stageflow.observability.tracing import (
    NoOpSpan,
    StageflowTracer,
    TraceContext,
    clear_correlation_id,
    ensure_correlation_id,
    get_correlation_id,
    get_span_id,
    get_trace_context_dict,
    get_trace_id,
    set_correlation_id,
)


class TestTraceContext:
    """Tests for TraceContext."""

    def test_capture_empty_context(self):
        """capture() returns empty context when nothing is set."""
        clear_correlation_id()
        ctx = TraceContext.capture()

        assert ctx.trace_id is None or ctx.trace_id == get_trace_id()
        assert ctx.correlation_id is None or ctx.correlation_id == get_correlation_id()

    def test_capture_with_correlation_id(self):
        """capture() includes correlation ID when set."""
        cid = uuid4()
        set_correlation_id(cid)

        ctx = TraceContext.capture()

        assert ctx.correlation_id == cid

        # Cleanup
        clear_correlation_id()

    def test_activate_context(self):
        """activate() sets context variables within the block."""
        cid = uuid4()
        ctx = TraceContext(
            trace_id="0" * 32,
            span_id="1" * 16,
            correlation_id=cid,
        )

        # Before activation
        assert get_correlation_id() != cid

        with ctx.activate():
            # During activation
            assert get_correlation_id() == cid
            assert get_trace_id() == "0" * 32
            assert get_span_id() == "1" * 16

        # After activation - should be reset
        assert get_correlation_id() != cid

    def test_to_dict(self):
        """to_dict() returns all fields."""
        cid = uuid4()
        pipeline_run_id = uuid4()
        request_id = uuid4()
        org_id = uuid4()

        ctx = TraceContext(
            trace_id="abc123",
            span_id="def456",
            correlation_id=cid,
            pipeline_run_id=pipeline_run_id,
            request_id=request_id,
            org_id=org_id,
            baggage={"key": "value"},
        )

        result = ctx.to_dict()

        assert result["trace_id"] == "abc123"
        assert result["span_id"] == "def456"
        assert result["correlation_id"] == str(cid)
        assert result["pipeline_run_id"] == str(pipeline_run_id)
        assert result["request_id"] == str(request_id)
        assert result["org_id"] == str(org_id)
        assert result["baggage"] == {"key": "value"}
        assert "created_at" in result

    def test_to_headers(self):
        """to_headers() returns HTTP headers for propagation."""
        cid = uuid4()
        pipeline_run_id = uuid4()

        ctx = TraceContext(
            trace_id="0" * 32,
            span_id="1" * 16,
            correlation_id=cid,
            pipeline_run_id=pipeline_run_id,
            baggage={"user": "test"},
        )

        headers = ctx.to_headers()

        assert "traceparent" in headers
        assert headers["x-correlation-id"] == str(cid)
        assert headers["x-pipeline-run-id"] == str(pipeline_run_id)
        assert headers["x-baggage-user"] == "test"

    def test_from_headers(self):
        """from_headers() parses HTTP headers."""
        cid = uuid4()
        pipeline_run_id = uuid4()

        headers = {
            "traceparent": f"00-{'0' * 32}-{'1' * 16}-01",
            "x-correlation-id": str(cid),
            "x-pipeline-run-id": str(pipeline_run_id),
            "x-baggage-env": "test",
        }

        ctx = TraceContext.from_headers(headers)

        assert ctx.trace_id == "0" * 32
        assert ctx.span_id == "1" * 16
        assert ctx.correlation_id == cid
        assert ctx.pipeline_run_id == pipeline_run_id
        assert ctx.baggage.get("env") == "test"

    def test_roundtrip_headers(self):
        """Context survives roundtrip through headers."""
        cid = uuid4()
        original = TraceContext(
            trace_id="a" * 32,
            span_id="b" * 16,
            correlation_id=cid,
        )

        headers = original.to_headers()
        restored = TraceContext.from_headers(headers)

        assert restored.trace_id == original.trace_id
        assert restored.span_id == original.span_id
        assert restored.correlation_id == original.correlation_id


class TestCorrelationIdFunctions:
    """Tests for correlation ID context variable functions."""

    def test_set_and_get(self):
        """set_correlation_id and get_correlation_id work correctly."""
        cid = uuid4()
        set_correlation_id(cid)

        assert get_correlation_id() == cid

        clear_correlation_id()

    def test_clear(self):
        """clear_correlation_id removes the ID."""
        cid = uuid4()
        set_correlation_id(cid)
        clear_correlation_id()

        assert get_correlation_id() is None

    def test_ensure_creates_new(self):
        """ensure_correlation_id creates new ID if not set."""
        clear_correlation_id()

        cid = ensure_correlation_id()

        assert cid is not None
        assert get_correlation_id() == cid

        clear_correlation_id()

    def test_ensure_returns_existing(self):
        """ensure_correlation_id returns existing ID if set."""
        original = uuid4()
        set_correlation_id(original)

        result = ensure_correlation_id()

        assert result == original

        clear_correlation_id()

    def test_get_trace_context_dict(self):
        """get_trace_context_dict returns all context."""
        cid = uuid4()
        set_correlation_id(cid)

        result = get_trace_context_dict()

        assert result["correlation_id"] == str(cid)
        assert "trace_id" in result
        assert "span_id" in result

        clear_correlation_id()


class TestStageflowTracer:
    """Tests for StageflowTracer."""

    def test_tracer_creation(self):
        """Tracer can be created."""
        tracer = StageflowTracer("test_service")
        assert tracer is not None

    def test_start_span_noop(self):
        """start_span works without OpenTelemetry."""
        tracer = StageflowTracer("test_service")

        with tracer.start_span("test_operation") as span:
            assert span is not None
            span.set_attribute("key", "value")
            span.add_event("test_event", {"data": "value"})

    def test_inject_context(self):
        """inject_context adds headers to carrier."""
        tracer = StageflowTracer("test_service")
        cid = uuid4()
        set_correlation_id(cid)

        carrier: dict[str, str] = {}
        tracer.inject_context(carrier)

        assert "x-correlation-id" in carrier
        assert carrier["x-correlation-id"] == str(cid)

        clear_correlation_id()

    def test_extract_context(self):
        """extract_context parses headers."""
        tracer = StageflowTracer("test_service")
        cid = uuid4()

        carrier = {"x-correlation-id": str(cid)}
        ctx = tracer.extract_context(carrier)

        assert ctx.correlation_id == cid


class TestNoOpSpan:
    """Tests for NoOpSpan."""

    def test_set_attribute(self):
        """set_attribute stores attribute."""
        span = NoOpSpan("test")
        span.set_attribute("key", "value")

        assert span._attributes["key"] == "value"

    def test_add_event(self):
        """add_event stores event."""
        span = NoOpSpan("test")
        span.add_event("test_event", {"data": "value"})

        assert len(span._events) == 1
        assert span._events[0][0] == "test_event"

    def test_record_exception(self):
        """record_exception adds exception event."""
        span = NoOpSpan("test")
        span.record_exception(ValueError("test error"))

        assert len(span._events) == 1
        assert span._events[0][0] == "exception"

    def test_is_recording(self):
        """is_recording returns False for no-op span."""
        span = NoOpSpan("test")
        assert span.is_recording() is False


class TestAsyncContextPropagation:
    """Tests for correlation ID propagation across async boundaries."""

    @pytest.mark.asyncio
    async def test_propagation_in_task(self):
        """Correlation ID propagates to child tasks when captured."""
        cid = uuid4()
        set_correlation_id(cid)

        # Capture context
        ctx = TraceContext.capture()

        async def child_task(trace_ctx: TraceContext):
            with trace_ctx.activate():
                return get_correlation_id()

        # Run child task with captured context
        result = await child_task(ctx)

        assert result == cid

        clear_correlation_id()

    @pytest.mark.asyncio
    async def test_isolation_between_tasks(self):
        """Different tasks can have different correlation IDs."""
        results: dict[str, str | None] = {}

        async def task_with_id(name: str, cid: uuid4):
            ctx = TraceContext(correlation_id=cid)
            with ctx.activate():
                await asyncio.sleep(0.01)  # Simulate work
                results[name] = str(get_correlation_id())

        cid1 = uuid4()
        cid2 = uuid4()

        await asyncio.gather(
            task_with_id("task1", cid1),
            task_with_id("task2", cid2),
        )

        assert results["task1"] == str(cid1)
        assert results["task2"] == str(cid2)

    @pytest.mark.asyncio
    async def test_context_survives_await(self):
        """Correlation ID survives across await points."""
        cid = uuid4()
        set_correlation_id(cid)

        async def work():
            await asyncio.sleep(0.01)
            return get_correlation_id()

        result = await work()

        assert result == cid

        clear_correlation_id()

    @pytest.mark.asyncio
    async def test_nested_context_activation(self):
        """Nested context activation works correctly."""
        outer_cid = uuid4()
        inner_cid = uuid4()

        outer_ctx = TraceContext(correlation_id=outer_cid)
        inner_ctx = TraceContext(correlation_id=inner_cid)

        with outer_ctx.activate():
            assert get_correlation_id() == outer_cid

            with inner_ctx.activate():
                assert get_correlation_id() == inner_cid

            # Back to outer
            assert get_correlation_id() == outer_cid

        # Back to nothing
        assert get_correlation_id() is None
