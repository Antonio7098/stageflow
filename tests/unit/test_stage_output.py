"""Unit tests for StageOutput."""

import pytest

from stageflow import StageOutput, StageStatus


class TestStageOutput:
    """Tests for StageOutput factory methods and behavior."""

    def test_ok_creates_success_output(self):
        """StageOutput.ok() creates output with OK status."""
        output = StageOutput.ok(result="test")
        
        assert output.status == StageStatus.OK
        assert output.data == {"result": "test"}
        assert output.error is None

    def test_ok_with_dict_data(self):
        """StageOutput.ok() accepts dict data."""
        output = StageOutput.ok(data={"key": "value"})
        
        assert output.status == StageStatus.OK
        assert output.data == {"key": "value"}

    def test_skip_creates_skipped_output(self):
        """StageOutput.skip() creates output with SKIP status."""
        output = StageOutput.skip(reason="not needed")
        
        assert output.status == StageStatus.SKIP
        assert output.data["reason"] == "not needed"

    def test_cancel_creates_cancelled_output(self):
        """StageOutput.cancel() creates output with CANCEL status."""
        output = StageOutput.cancel(reason="user requested")
        
        assert output.status == StageStatus.CANCEL
        assert output.data["cancel_reason"] == "user requested"

    def test_fail_creates_failed_output(self):
        """StageOutput.fail() creates output with FAIL status."""
        output = StageOutput.fail(error="something went wrong")
        
        assert output.status == StageStatus.FAIL
        assert output.error == "something went wrong"

    def test_retry_creates_retry_output(self):
        """StageOutput.retry() creates output with RETRY status."""
        output = StageOutput.retry(error="temporary failure")
        
        assert output.status == StageStatus.RETRY
        assert output.error == "temporary failure"

    def test_output_is_frozen(self):
        """StageOutput is immutable (frozen dataclass)."""
        output = StageOutput.ok(result="test")
        
        with pytest.raises(AttributeError):
            output.status = StageStatus.FAIL
