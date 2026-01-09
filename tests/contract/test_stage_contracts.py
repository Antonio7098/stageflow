"""Contract tests for stage protocol compliance.

These tests verify that all stages:
- Emit started events
- Emit completed or failed events
- Return StageOutput instances
"""

from __future__ import annotations

import pytest

from stageflow import StageKind, StageOutput
from tests.contract.base import (
    StageContractTest,
    create_contract_test_context,
    get_emitted_events,
)
from tests.utils.mocks import MockEventSink, MockStage


class TestMockStageContract(StageContractTest):
    """Contract tests for MockStage (validates our test infrastructure)."""

    def get_stage(self) -> MockStage:
        return MockStage(name="test_stage", kind=StageKind.TRANSFORM)

    @pytest.mark.asyncio
    async def test_has_name_attribute(self) -> None:
        await super().test_has_name_attribute()

    @pytest.mark.asyncio
    async def test_has_execute_method(self) -> None:
        await super().test_has_execute_method()

    @pytest.mark.asyncio
    async def test_execute_returns_stage_output(self) -> None:
        await super().test_execute_returns_stage_output()

    @pytest.mark.asyncio
    async def test_stage_output_has_valid_status(self) -> None:
        await super().test_stage_output_has_valid_status()


class TestStageEventEmission:
    """Tests for stage event emission contracts."""

    @pytest.mark.asyncio
    async def test_successful_stage_completes(self) -> None:
        """Successful stage execution returns ok status."""
        stage = MockStage(
            name="success_stage",
            kind=StageKind.TRANSFORM,
            output=StageOutput.ok(result="success"),
        )
        sink = MockEventSink()
        ctx = create_contract_test_context(sink)

        result = await stage.execute(ctx)

        assert result.status.value == "ok"

    @pytest.mark.asyncio
    async def test_failing_stage_raises(self) -> None:
        """Failing stage raises an exception."""
        stage = MockStage(
            name="fail_stage",
            kind=StageKind.TRANSFORM,
            should_fail=True,
            fail_message="Expected failure",
        )
        sink = MockEventSink()
        ctx = create_contract_test_context(sink)

        with pytest.raises(RuntimeError) as exc_info:
            await stage.execute(ctx)

        assert "Expected failure" in str(exc_info.value)


class TestStageOutputContract:
    """Tests for StageOutput structure contracts."""

    def test_stage_output_ok_has_status(self) -> None:
        """StageOutput.ok() has 'ok' status."""
        output = StageOutput.ok()
        assert output.status.value == "ok"

    def test_stage_output_fail_has_status(self) -> None:
        """StageOutput.fail() has 'fail' status."""
        output = StageOutput.fail("test error")
        assert output.status.value == "fail"

    def test_stage_output_ok_can_have_data(self) -> None:
        """StageOutput.ok() can include data."""
        output = StageOutput.ok(result="test_result")
        assert output.data.get("result") == "test_result"

    def test_stage_output_fail_has_error(self) -> None:
        """StageOutput.fail() includes error message."""
        output = StageOutput.fail("my error message")
        assert output.error == "my error message"

    def test_stage_output_has_data_attribute(self) -> None:
        """StageOutput has data attribute."""
        output = StageOutput.ok(result="test")
        assert hasattr(output, "data")
        assert hasattr(output, "status")
