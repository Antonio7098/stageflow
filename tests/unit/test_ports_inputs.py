"""Comprehensive tests for stageflow.stages.ports and stageflow.stages.inputs.

Tests:
- StagePorts dataclass
- create_stage_ports factory function
- create_stage_ports_from_data_dict
- StageInputs dataclass
- create_stage_inputs factory function
"""

import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, UTC
from typing import Any
from uuid import uuid4
import pytest

from stageflow.context.snapshot import ContextSnapshot
from stageflow.core.stages import (
    StageContext,
    StageOutput,
    StageStatus,
)
from stageflow.stages.inputs import (
    create_stage_inputs,
    StageInputs,
)
from stageflow.stages.ports import (
    create_stage_ports,
    create_stage_ports_from_data_dict,
    StagePorts,
)


# === Test StagePorts ===

class TestStagePorts:
    """Tests for StagePorts dataclass."""

    def test_default_values(self):
        """Test StagePorts default values."""
        ports = StagePorts()
        assert ports.db is None
        assert ports.db_lock is None
        assert ports.call_logger_db is None
        assert ports.send_status is None
        assert ports.send_token is None
        assert ports.send_audio_chunk is None
        assert ports.send_transcript is None
        assert ports.llm_chunk_queue is None
        assert ports.chat_service is None
        assert ports.llm_provider is None
        assert ports.tts_provider is None
        assert ports.recording is None
        assert ports.audio_data is None
        assert ports.audio_format is None
        assert ports.tts_text_queue is None
        assert ports.stt_provider is None
        assert ports.call_logger is None
        assert ports.retry_fn is None

    def test_with_db(self):
        """Test StagePorts with db."""
        db = {"connection": "test"}
        ports = StagePorts(db=db)
        assert ports.db == db

    def test_with_callbacks(self):
        """Test StagePorts with callback functions."""

        async def send_status(stage, status, data):
            pass

        async def send_token(token):
            pass

        ports = StagePorts(
            send_status=send_status,
            send_token=send_token,
        )
        assert ports.send_status == send_status
        assert ports.send_token == send_token

    def test_with_providers(self):
        """Test StagePorts with providers."""
        llm = {"generate": lambda x: "response"}
        tts = {"synthesize": lambda x: b"audio"}
        stt = {"transcribe": lambda x: "text"}

        ports = StagePorts(
            llm_provider=llm,
            tts_provider=tts,
            stt_provider=stt,
        )
        assert ports.llm_provider == llm
        assert ports.tts_provider == tts
        assert ports.stt_provider == stt

    def test_with_audio_data(self):
        """Test StagePorts with audio data."""
        audio = b"\x00\x01\x02\x03"
        ports = StagePorts(
            audio_data=audio,
            audio_format="wav",
        )
        assert ports.audio_data == audio
        assert ports.audio_format == "wav"

    def test_is_frozen(self):
        """Test StagePorts is frozen."""
        ports = StagePorts()
        with pytest.raises(FrozenInstanceError):
            ports.db = "modified"

    def test_has_slots(self):
        """Test StagePorts uses slots."""
        assert hasattr(StagePorts, "__slots__")

    def test_with_all_fields(self):
        """Test StagePorts with all fields set."""
        db = {"conn": "test"}
        lock = asyncio.Lock()
        cl_db = {"log": "test"}

        async def status_cb(stage, status, data):
            pass

        async def token_cb(token):
            pass

        async def audio_cb(chunk, format, index, final):
            pass

        async def transcript_cb(msg_id, transcript, confidence, duration):
            pass

        llm_queue = asyncio.Queue()
        chat_svc = {"chat": "service"}
        llm = {"generate": lambda: "text"}
        tts = {"synthesize": lambda: b"audio"}
        rec = {"recording": "meta"}
        audio = b"data"
        tts_queue = asyncio.Queue()
        stt = {"transcribe": lambda x: "text"}
        call_log = {"log": "call"}
        retry = lambda: "retry"

        ports = StagePorts(
            db=db,
            db_lock=lock,
            call_logger_db=cl_db,
            send_status=status_cb,
            send_token=token_cb,
            send_audio_chunk=audio_cb,
            send_transcript=transcript_cb,
            llm_chunk_queue=llm_queue,
            chat_service=chat_svc,
            llm_provider=llm,
            tts_provider=tts,
            recording=rec,
            audio_data=audio,
            audio_format="mp3",
            tts_text_queue=tts_queue,
            stt_provider=stt,
            call_logger=call_log,
            retry_fn=retry,
        )

        assert ports.db == db
        assert ports.db_lock is lock
        assert ports.call_logger_db == cl_db
        assert ports.send_status is status_cb
        assert ports.send_token is token_cb
        assert ports.send_audio_chunk is audio_cb
        assert ports.send_transcript is transcript_cb
        assert ports.llm_chunk_queue is llm_queue
        assert ports.chat_service == chat_svc
        assert ports.llm_provider == llm
        assert ports.tts_provider == tts
        assert ports.recording == rec
        assert ports.audio_data == audio
        assert ports.audio_format == "mp3"
        assert ports.tts_text_queue is tts_queue
        assert ports.stt_provider == stt
        assert ports.call_logger == call_log
        assert ports.retry_fn is retry


# === Test create_stage_ports ===

class TestCreateStagePorts:
    """Tests for create_stage_ports factory function."""

    def test_empty_creation(self):
        """Test creating empty StagePorts."""
        ports = create_stage_ports()
        assert isinstance(ports, StagePorts)
        assert ports.db is None

    def test_with_db(self):
        """Test creating with db."""
        db = {"connection": "test"}
        ports = create_stage_ports(db=db)
        assert ports.db == db

    def test_with_callbacks(self):
        """Test creating with callbacks."""
        async def send_status(stage, status, data):
            pass

        ports = create_stage_ports(send_status=send_status)
        assert ports.send_status is send_status

    def test_with_multiple_fields(self):
        """Test creating with multiple fields."""
        db = {"conn": "test"}
        llm = {"generate": lambda: "text"}

        ports = create_stage_ports(
            db=db,
            llm_provider=llm,
            audio_format="wav",
        )
        assert ports.db == db
        assert ports.llm_provider == llm
        assert ports.audio_format == "wav"


# === Test create_stage_ports_from_data_dict ===

class TestCreateStagePortsFromDataDict:
    """Tests for create_stage_ports_from_data_dict function."""

    def test_empty_dict(self):
        """Test with empty dict."""
        ports = create_stage_ports_from_data_dict({})
        assert isinstance(ports, StagePorts)
        assert ports.db is None

    def test_extracts_db(self):
        """Test extracting db from data dict."""
        data = {"db": {"connection": "test"}}
        ports = create_stage_ports_from_data_dict(data)
        assert ports.db == {"connection": "test"}

    def test_extracts_callbacks(self):
        """Test extracting callbacks from data dict."""

        async def send_status(stage, status, data):
            pass

        data = {"send_status": send_status}
        ports = create_stage_ports_from_data_dict(data)
        assert ports.send_status is send_status

    def test_extracts_audio_data(self):
        """Test extracting audio data."""
        data = {
            "audio_data": b"\x00\x01\x02",
            "audio_format": "mp3",
        }
        ports = create_stage_ports_from_data_dict(data)
        assert ports.audio_data == b"\x00\x01\x02"
        assert ports.audio_format == "mp3"

    def test_extracts_multiple_fields(self):
        """Test extracting multiple fields."""
        data = {
            "db": {"conn": "test"},
            "db_lock": asyncio.Lock(),
            "send_status": lambda *args: None,
            "send_token": lambda x: None,
            "send_audio_chunk": lambda *args: None,
            "llm_chunk_queue": asyncio.Queue(),
            "chat_service": {"service": "test"},
            "recording": {"meta": "test"},
            "audio_data": b"data",
            "audio_format": "wav",
        }
        ports = create_stage_ports_from_data_dict(data)

        assert ports.db == {"conn": "test"}
        assert ports.db_lock is not None
        assert ports.send_status is not None
        assert ports.send_token is not None
        assert ports.send_audio_chunk is not None
        assert ports.llm_chunk_queue is not None
        assert ports.chat_service == {"service": "test"}
        assert ports.recording == {"meta": "test"}
        assert ports.audio_data == b"data"
        assert ports.audio_format == "wav"

    def test_missing_keys_return_none(self):
        """Test that missing keys return None."""
        data = {"only_this": "exists"}
        ports = create_stage_ports_from_data_dict(data)
        assert ports.db is None
        assert ports.send_status is None


# === Test StageInputs ===

class TestStageInputs:
    """Tests for StageInputs dataclass."""

    @pytest.fixture
    def snapshot(self):
        """Create a test ContextSnapshot."""
        return ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            channel="test",
            behavior="test",
        )

    def test_default_values(self, snapshot):
        """Test StageInputs default values."""
        inputs = StageInputs(snapshot=snapshot)
        assert inputs.snapshot == snapshot
        assert inputs.prior_outputs == {}
        assert isinstance(inputs.ports, StagePorts)

    def test_with_prior_outputs(self, snapshot):
        """Test StageInputs with prior outputs."""
        outputs = {
            "stage_a": StageOutput.ok(data={"key": "value"}),
            "stage_b": StageOutput.ok(data={"other": "data"}),
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        assert len(inputs.prior_outputs) == 2

    def test_with_custom_ports(self, snapshot):
        """Test StageInputs with custom ports."""
        ports = create_stage_ports(db={"test": "db"})
        inputs = StageInputs(snapshot=snapshot, ports=ports)
        assert inputs.ports.db == {"test": "db"}

    def test_is_frozen(self, snapshot):
        """Test StageInputs is frozen."""
        inputs = StageInputs(snapshot=snapshot)
        with pytest.raises(FrozenInstanceError):
            inputs.snapshot = "modified"

    def test_has_slots(self, snapshot):
        """Test StageInputs uses slots."""
        assert hasattr(StageInputs, "__slots__")

    def test_get_finds_value(self, snapshot):
        """Test get() finds value in prior outputs."""
        outputs = {
            "stage_a": StageOutput.ok(data={"key": "value"}),
            "stage_b": StageOutput.ok(data={"other": "data"}),
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        assert inputs.get("key") == "value"
        assert inputs.get("other") == "data"

    def test_get_returns_default(self, snapshot):
        """Test get() returns default when key not found."""
        inputs = StageInputs(snapshot=snapshot)
        assert inputs.get("missing") is None
        assert inputs.get("missing", "default") == "default"

    def test_get_searches_all_outputs(self, snapshot):
        """Test get() searches all prior outputs in order."""
        outputs = {
            "stage_a": StageOutput.ok(data={"found": "first"}),
            "stage_b": StageOutput.ok(data={"found": "second"}),
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        # First one wins
        assert inputs.get("found") == "first"

    def test_get_from_specific_stage(self, snapshot):
        """Test get_from() gets value from specific stage."""
        outputs = {
            "stage_a": StageOutput.ok(data={"key": "from_a"}),
            "stage_b": StageOutput.ok(data={"key": "from_b"}),
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        assert inputs.get_from("stage_a", "key") == "from_a"
        assert inputs.get_from("stage_b", "key") == "from_b"

    def test_get_from_missing_stage(self, snapshot):
        """Test get_from() returns default for missing stage."""
        inputs = StageInputs(snapshot=snapshot)
        assert inputs.get_from("missing", "key") is None
        assert inputs.get_from("missing", "key", "default") == "default"

    def test_get_from_missing_key(self, snapshot):
        """Test get_from() returns default for missing key."""
        outputs = {
            "stage_a": StageOutput.ok(data={"other": "value"}),
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        assert inputs.get_from("stage_a", "missing") is None
        assert inputs.get_from("stage_a", "missing", "default") == "default"

    def test_has_output_true(self, snapshot):
        """Test has_output() returns True for existing stage."""
        outputs = {
            "stage_a": StageOutput.ok(),
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        assert inputs.has_output("stage_a") is True

    def test_has_output_false(self, snapshot):
        """Test has_output() returns False for missing stage."""
        inputs = StageInputs(snapshot=snapshot)
        assert inputs.has_output("missing") is False

    def test_get_output(self, snapshot):
        """Test get_output() returns StageOutput."""
        output = StageOutput.ok(data={"key": "value"})
        outputs = {"stage_a": output}
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        result = inputs.get_output("stage_a")
        assert result is output
        assert result.data["key"] == "value"

    def test_get_output_missing(self, snapshot):
        """Test get_output() returns None for missing."""
        inputs = StageInputs(snapshot=snapshot)
        assert inputs.get_output("missing") is None


# === Test create_stage_inputs ===

class TestCreateStageInputs:
    """Tests for create_stage_inputs factory function."""

    @pytest.fixture
    def snapshot(self):
        """Create a test ContextSnapshot."""
        return ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            channel="test",
            behavior="test",
        )

    def test_creates_inputs(self, snapshot):
        """Test factory creates StageInputs."""
        inputs = create_stage_inputs(snapshot=snapshot)
        assert isinstance(inputs, StageInputs)
        assert inputs.snapshot == snapshot

    def test_with_prior_outputs(self, snapshot):
        """Test with prior outputs."""
        outputs = {"stage_a": StageOutput.ok(data={"key": "value"})}
        inputs = create_stage_inputs(snapshot=snapshot, prior_outputs=outputs)
        assert inputs.prior_outputs == outputs

    def test_with_ports(self, snapshot):
        """Test with custom ports."""
        ports = create_stage_ports(db={"test": "db"})
        inputs = create_stage_inputs(snapshot=snapshot, ports=ports)
        assert inputs.ports.db == {"test": "db"}

    def test_defaults_to_empty(self, snapshot):
        """Test defaults to empty dict and default ports."""
        inputs = create_stage_inputs(snapshot=snapshot)
        assert inputs.prior_outputs == {}
        assert isinstance(inputs.ports, StagePorts)
        assert inputs.ports.db is None


# === Edge Cases ===

class TestPortsInputsEdgeCases:
    """Edge case tests for StagePorts and StageInputs."""

    def test_stage_ports_with_none_callbacks(self):
        """Test StagePorts with None callback fields."""
        ports = StagePorts(
            send_status=None,
            send_token=None,
            send_audio_chunk=None,
        )
        assert ports.send_status is None
        assert ports.send_token is None

    def test_stage_inputs_with_empty_prior_outputs(self):
        """Test StageInputs with empty prior_outputs dict."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            channel="test",
            behavior="test",
        )
        inputs = StageInputs(snapshot=snapshot, prior_outputs={})
        assert inputs.prior_outputs == {}
        assert inputs.get("any_key") is None

    def test_stage_inputs_with_none_prior_outputs(self):
        """Test StageInputs with None prior_outputs."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            channel="test",
            behavior="test",
        )
        inputs = create_stage_inputs(snapshot=snapshot, prior_outputs=None)
        assert inputs.prior_outputs == {}

    def test_stage_inputs_get_with_nested_keys(self):
        """Test get() with nested key access."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            channel="test",
            behavior="test",
        )
        outputs = {
            "stage_a": StageOutput.ok(data={"nested": {"key": "value"}}),
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        # get() doesn't do nested access, just key lookup
        assert inputs.get("nested") is not None
        assert isinstance(inputs.get("nested"), dict)

    def test_stage_ports_with_callable_fields(self):
        """Test StagePorts with callable fields."""
        def my_retry():
            return "retry"

        ports = StagePorts(retry_fn=my_retry)
        assert ports.retry_fn is my_retry

    def test_stage_ports_with_asyncio_queue(self):
        """Test StagePorts with asyncio.Queue."""
        queue = asyncio.Queue()
        ports = StagePorts(llm_chunk_queue=queue)
        assert ports.llm_chunk_queue is queue

    def test_stage_ports_with_asyncio_lock(self):
        """Test StagePorts with asyncio.Lock."""
        lock = asyncio.Lock()
        ports = StagePorts(db_lock=lock)
        assert ports.db_lock is lock

    def test_create_stage_ports_preserves_none(self):
        """Test create_stage_ports preserves None values."""
        ports = create_stage_ports(
            db=None,
            send_status=None,
            llm_provider=None,
        )
        assert ports.db is None
        assert ports.send_status is None
        assert ports.llm_provider is None

    def test_stage_inputs_with_many_prior_outputs(self):
        """Test StageInputs with many prior outputs."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            channel="test",
            behavior="test",
        )
        outputs = {
            f"stage_{i}": StageOutput.ok(data={"n": i})
            for i in range(100)
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)

        # Should find values
        assert inputs.get("n") == 0  # First one wins
        assert inputs.has_output("stage_50") is True
        assert inputs.get_output("stage_99").data["n"] == 99

    def test_stage_inputs_get_order_preserved(self):
        """Test that get() respects output insertion order."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            channel="test",
            behavior="test",
        )
        # Create outputs dict (preserves insertion order in Python 3.7+)
        outputs = {
            "first": StageOutput.ok(data={"key": "first"}),
            "second": StageOutput.ok(data={"key": "second"}),
            "third": StageOutput.ok(data={"key": "third"}),
        }
        inputs = StageInputs(snapshot=snapshot, prior_outputs=outputs)
        # First one wins
        assert inputs.get("key") == "first"
