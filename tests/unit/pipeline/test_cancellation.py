"""Tests for structured cancellation support."""

import asyncio
from typing import Any

import pytest

from stageflow.pipeline.cancellation import (
    CancellationToken,
    CleanupRegistry,
    StructuredTaskGroup,
    cleanup_on_cancel,
    run_with_cleanup,
)


class TestCleanupRegistry:
    """Tests for CleanupRegistry."""

    @pytest.mark.asyncio
    async def test_register_and_run_cleanup(self):
        """Registered cleanup callbacks are executed."""
        cleanup_ran = False

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        registry = CleanupRegistry()
        registry.register(cleanup, name="test_cleanup")

        completed, failed = await registry.run_all()

        assert cleanup_ran
        assert "test_cleanup" in completed
        assert len(failed) == 0

    @pytest.mark.asyncio
    async def test_lifo_order(self):
        """Cleanup callbacks run in LIFO order."""
        order: list[int] = []

        async def cleanup_1():
            order.append(1)

        async def cleanup_2():
            order.append(2)

        async def cleanup_3():
            order.append(3)

        registry = CleanupRegistry()
        registry.register(cleanup_1, name="cleanup_1")
        registry.register(cleanup_2, name="cleanup_2")
        registry.register(cleanup_3, name="cleanup_3")

        await registry.run_all()

        assert order == [3, 2, 1]  # LIFO order

    @pytest.mark.asyncio
    async def test_cleanup_error_handling(self):
        """Errors in cleanup callbacks are captured but don't stop other cleanups."""
        cleanup_1_ran = False
        cleanup_3_ran = False

        async def cleanup_1():
            nonlocal cleanup_1_ran
            cleanup_1_ran = True

        async def cleanup_2():
            raise ValueError("Cleanup error")

        async def cleanup_3():
            nonlocal cleanup_3_ran
            cleanup_3_ran = True

        registry = CleanupRegistry()
        registry.register(cleanup_1, name="cleanup_1")
        registry.register(cleanup_2, name="cleanup_2")
        registry.register(cleanup_3, name="cleanup_3")

        completed, failed = await registry.run_all()

        # cleanup_3 runs first (LIFO), then cleanup_2 fails, then cleanup_1 runs
        assert cleanup_3_ran
        assert cleanup_1_ran
        assert "cleanup_2" in [name for name, _ in failed]

    @pytest.mark.asyncio
    async def test_unregister(self):
        """Unregistered callbacks are not executed."""
        cleanup_ran = False

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        registry = CleanupRegistry()
        registry.register(cleanup, name="test_cleanup")
        result = registry.unregister(cleanup)

        assert result is True
        assert registry.pending_count == 0

        await registry.run_all()
        assert cleanup_ran is False

    @pytest.mark.asyncio
    async def test_unregister_not_found(self):
        """Unregistering non-existent callback returns False."""
        async def cleanup():
            pass

        registry = CleanupRegistry()
        result = registry.unregister(cleanup)

        assert result is False

    @pytest.mark.asyncio
    async def test_pending_count(self):
        """pending_count reflects number of registered callbacks."""
        async def cleanup():
            pass

        registry = CleanupRegistry()
        assert registry.pending_count == 0

        registry.register(cleanup, name="c1")
        assert registry.pending_count == 1

        registry.register(cleanup, name="c2")
        assert registry.pending_count == 2

        await registry.run_all()
        assert registry.pending_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_timeout(self):
        """Slow cleanups are timed out."""
        async def slow_cleanup():
            await asyncio.sleep(10)

        registry = CleanupRegistry()
        registry.register(slow_cleanup, name="slow")

        completed, failed = await registry.run_all(timeout=0.1)

        assert "slow" in [name for name, _ in failed]


class TestCancellationToken:
    """Tests for CancellationToken."""

    def test_initial_state(self):
        """Token starts not cancelled."""
        token = CancellationToken()
        assert token.is_cancelled is False
        assert token.reason is None

    def test_cancel(self):
        """cancel() sets cancelled state and reason."""
        token = CancellationToken()
        token.cancel("Test reason")

        assert token.is_cancelled is True
        assert token.reason == "Test reason"

    def test_cancel_is_idempotent(self):
        """Multiple cancel() calls don't change reason."""
        token = CancellationToken()
        token.cancel("First reason")
        token.cancel("Second reason")

        assert token.reason == "First reason"

    def test_on_cancel_callback(self):
        """on_cancel callbacks are called when cancelled."""
        callback_called = False

        def callback():
            nonlocal callback_called
            callback_called = True

        token = CancellationToken()
        token.on_cancel(callback)
        token.cancel("Test")

        assert callback_called

    def test_on_cancel_after_cancelled(self):
        """on_cancel callbacks are called immediately if already cancelled."""
        callback_called = False

        def callback():
            nonlocal callback_called
            callback_called = True

        token = CancellationToken()
        token.cancel("Test")
        token.on_cancel(callback)

        assert callback_called


class TestStructuredTaskGroup:
    """Tests for StructuredTaskGroup."""

    @pytest.mark.asyncio
    async def test_basic_task_execution(self):
        """Tasks execute successfully within the group."""
        results: list[int] = []

        async def task_1():
            results.append(1)

        async def task_2():
            results.append(2)

        async with StructuredTaskGroup() as tg:
            tg.create_task(task_1())
            tg.create_task(task_2())

        assert 1 in results
        assert 2 in results

    @pytest.mark.asyncio
    async def test_cleanup_on_error(self):
        """Cleanup runs when a task raises an error."""
        cleanup_ran = False

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        async def failing_task():
            raise ValueError("Task error")

        async def slow_task():
            await asyncio.sleep(10)

        with pytest.raises(ValueError):
            async with StructuredTaskGroup() as tg:
                tg.cleanup_registry.register(cleanup, name="test_cleanup")
                tg.create_task(failing_task())
                tg.create_task(slow_task())

        assert cleanup_ran

    @pytest.mark.asyncio
    async def test_cleanup_on_success(self):
        """Cleanup runs on successful completion."""
        cleanup_ran = False

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        async def task():
            pass

        async with StructuredTaskGroup() as tg:
            tg.cleanup_registry.register(cleanup, name="test_cleanup")
            tg.create_task(task())

        assert cleanup_ran

    @pytest.mark.asyncio
    async def test_cancel_token_propagation(self):
        """Cancel token is set when task group exits with error."""
        async def failing_task():
            raise ValueError("Task error")

        tg = StructuredTaskGroup()
        with pytest.raises(ValueError):
            async with tg:
                tg.create_task(failing_task())

        assert tg.cancel_token.is_cancelled


class TestCleanupOnCancel:
    """Tests for cleanup_on_cancel context manager."""

    @pytest.mark.asyncio
    async def test_cleanup_runs_on_success(self):
        """Cleanup runs on normal exit."""
        cleanup_ran = False

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        async with cleanup_on_cancel(cleanup, name="test"):
            pass

        assert cleanup_ran

    @pytest.mark.asyncio
    async def test_cleanup_runs_on_exception(self):
        """Cleanup runs when exception is raised."""
        cleanup_ran = False

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        with pytest.raises(ValueError):
            async with cleanup_on_cancel(cleanup, name="test"):
                raise ValueError("Test error")

        assert cleanup_ran

    @pytest.mark.asyncio
    async def test_cleanup_runs_on_cancellation(self):
        """Cleanup runs when task is cancelled."""
        cleanup_ran = False

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        async def cancellable_work():
            async with cleanup_on_cancel(cleanup, name="test"):
                await asyncio.sleep(10)

        task = asyncio.create_task(cancellable_work())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert cleanup_ran


class TestRunWithCleanup:
    """Tests for run_with_cleanup function."""

    @pytest.mark.asyncio
    async def test_cleanup_runs_after_success(self):
        """Cleanup runs after successful coroutine."""
        cleanup_ran = False

        async def work():
            return "result"

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        result = await run_with_cleanup(work(), cleanup)

        assert result == "result"
        assert cleanup_ran

    @pytest.mark.asyncio
    async def test_cleanup_runs_after_error(self):
        """Cleanup runs after coroutine raises error."""
        cleanup_ran = False

        async def work():
            raise ValueError("Error")

        async def cleanup():
            nonlocal cleanup_ran
            cleanup_ran = True

        with pytest.raises(ValueError):
            await run_with_cleanup(work(), cleanup)

        assert cleanup_ran

    @pytest.mark.asyncio
    async def test_cleanup_timeout(self):
        """Slow cleanup is timed out."""
        async def work():
            return "result"

        async def slow_cleanup():
            await asyncio.sleep(10)

        # Should not hang due to timeout
        result = await run_with_cleanup(work(), slow_cleanup, cleanup_timeout=0.1)
        assert result == "result"
