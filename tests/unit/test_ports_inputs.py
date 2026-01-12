"""Comprehensive tests for stageflow.stages.ports and stageflow.stages.inputs.

Tests:
- CorePorts dataclass
- LLMPorts dataclass
- AudioPorts dataclass
- create_core_ports factory function
- create_llm_ports factory function
- create_audio_ports factory function
- StageInputs dataclass
- create_stage_inputs factory function
"""

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.core import (
    StageOutput,
)
from stageflow.stages.inputs import (
    StageInputs,
    create_stage_inputs,
)
from stageflow.stages.ports import (
    AudioPorts,
    CorePorts,
    LLMPorts,
    create_audio_ports,
    create_core_ports,
    create_llm_ports,
)


def _make_snapshot() -> ContextSnapshot:
    """Create a minimal ContextSnapshot for testing."""
    return ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        ),
        topology="test",
        execution_mode="test",
    )


# === Test CorePorts ===

class TestCorePorts:
    """Tests for CorePorts dataclass."""

    def test_default_values(self):
        """Test CorePorts default values."""
        ports = CorePorts()
        assert ports.db is None
        assert ports.db_lock is None
        assert ports.call_logger_db is None
        assert ports.send_status is None
        assert ports.call_logger is None
        assert ports.retry_fn is None

    def test_with_values(self):
        """Test CorePorts with values."""
        db_mock = object()

        def status_cb(_stage, _state, _data):
            return None

        ports = CorePorts(
            db=db_mock,
            send_status=status_cb,
        )
        assert ports.db is db_mock
        assert ports.send_status is status_cb

    def test_frozen_immutable(self):
        """Test CorePorts is frozen/immutable."""
        ports = CorePorts()
        with pytest.raises(FrozenInstanceError):
            ports.db = object()

    def test_slots_optimization(self):
        """Test CorePorts uses __slots__ for memory efficiency."""
        ports = CorePorts()
        assert hasattr(ports, '__slots__')
        # Frozen dataclasses with slots prevent attribute addition
        try:
            ports.new_attribute = "test"
            raise AssertionError("Should have raised an exception")
        except (AttributeError, FrozenInstanceError, TypeError):
            pass  # Expected for frozen dataclass with slots


# === Test LLMPorts ===

class TestLLMPorts:
    """Tests for LLMPorts dataclass."""

    def test_default_values(self):
        """Test LLMPorts default values."""
        ports = LLMPorts()
        assert ports.llm_provider is None
        assert ports.chat_service is None
        assert ports.llm_chunk_queue is None
        assert ports.send_token is None

    def test_with_values(self):
        """Test LLMPorts with values."""
        llm_mock = object()

        def token_cb(_token):
            return None

        ports = LLMPorts(
            llm_provider=llm_mock,
            send_token=token_cb,
        )
        assert ports.llm_provider is llm_mock
        assert ports.send_token is token_cb

    def test_frozen_immutable(self):
        """Test LLMPorts is frozen/immutable."""
        ports = LLMPorts()
        with pytest.raises(FrozenInstanceError):
            ports.llm_provider = object()


# === Test AudioPorts ===

class TestAudioPorts:
    """Tests for AudioPorts dataclass."""

    def test_default_values(self):
        """Test AudioPorts default values."""
        ports = AudioPorts()
        assert ports.tts_provider is None
        assert ports.stt_provider is None
        assert ports.send_audio_chunk is None
        assert ports.send_transcript is None
        assert ports.audio_data is None
        assert ports.audio_format is None
        assert ports.tts_text_queue is None
        assert ports.recording is None

    def test_with_values(self):
        """Test AudioPorts with values."""
        tts_mock = object()

        def audio_cb(_chunk, _fmt, _idx, _last):
            return None

        ports = AudioPorts(
            tts_provider=tts_mock,
            send_audio_chunk=audio_cb,
        )
        assert ports.tts_provider is tts_mock
        assert ports.send_audio_chunk is audio_cb

    def test_with_audio_data(self):
        """Test AudioPorts with audio data."""
        audio = b"\x00\x01\x02\x03"
        ports = AudioPorts(
            audio_data=audio,
            audio_format="wav",
        )
        assert ports.audio_data == audio
        assert ports.audio_format == "wav"

    def test_frozen_immutable(self):
        """Test AudioPorts is frozen/immutable."""
        ports = AudioPorts()
        with pytest.raises(FrozenInstanceError):
            ports.tts_provider = object()


# === Test Factory Functions ===

class TestPortFactories:
    """Tests for port factory functions."""

    def test_create_core_ports(self):
        """Test create_core_ports factory."""
        db_mock = object()

        def status_cb(_stage, _state, _data):
            return None

        ports = create_core_ports(
            db=db_mock,
            send_status=status_cb,
        )
        assert isinstance(ports, CorePorts)
        assert ports.db is db_mock
        assert ports.send_status is status_cb

    def test_create_llm_ports(self):
        """Test create_llm_ports factory."""
        llm_mock = object()

        def token_cb(_token):
            return None

        ports = create_llm_ports(
            llm_provider=llm_mock,
            send_token=token_cb,
        )
        assert isinstance(ports, LLMPorts)
        assert ports.llm_provider is llm_mock
        assert ports.send_token is token_cb

    def test_create_audio_ports(self):
        """Test create_audio_ports factory."""
        tts_mock = object()

        def audio_cb(_chunk, _fmt, _idx, _last):
            return None

        audio = b"test audio"

        ports = create_audio_ports(
            tts_provider=tts_mock,
            send_audio_chunk=audio_cb,
            audio_data=audio,
        )
        assert isinstance(ports, AudioPorts)
        assert ports.tts_provider is tts_mock
        assert ports.send_audio_chunk is audio_cb
        assert ports.audio_data == audio


# === Test StageInputs ===

class TestStageInputs:
    """Tests for StageInputs dataclass."""

    def test_default_values(self):
        """Test StageInputs default values."""
        snapshot = _make_snapshot()
        inputs = StageInputs(snapshot=snapshot)
        assert inputs.snapshot is snapshot
        assert inputs.prior_outputs == {}
        assert inputs.ports is None

    def test_with_values(self):
        """Test StageInputs with values."""
        snapshot = _make_snapshot()
        prior_outputs = {
            "stage_a": StageOutput.ok(data={"value": 42}),
            "stage_b": StageOutput.ok(data={"text": "hello"}),
        }
        ports = CorePorts(db=object())

        inputs = StageInputs(
            snapshot=snapshot,
            prior_outputs=prior_outputs,
            ports=ports,
        )
        assert inputs.snapshot is snapshot
        assert inputs.prior_outputs == prior_outputs
        assert inputs.ports is ports

    def test_frozen_immutable(self):
        """Test StageInputs is frozen/immutable."""
        snapshot = _make_snapshot()
        inputs = StageInputs(snapshot=snapshot)
        with pytest.raises(FrozenInstanceError):
            inputs.snapshot = object()

    def test_slots_optimization(self):
        """Test StageInputs uses __slots__ for memory efficiency."""
        snapshot = _make_snapshot()
        inputs = StageInputs(snapshot=snapshot)
        assert hasattr(inputs, '__slots__')
        # Frozen dataclasses with slots prevent attribute addition
        try:
            inputs.new_attribute = "test"
            raise AssertionError("Should have raised an exception")
        except (AttributeError, FrozenInstanceError, TypeError):
            pass  # Expected for frozen dataclass with slots

    def test_get(self):
        """Test StageInputs.get method."""
        snapshot = _make_snapshot()
        prior_outputs = {
            "stage_a": StageOutput.ok(data={"value": 42, "shared": "from_a"}),
            "stage_b": StageOutput.ok(data={"text": "hello", "shared": "from_b"}),
        }

        inputs = StageInputs(
            snapshot=snapshot,
            prior_outputs=prior_outputs,
        )

        # Test getting specific values
        assert inputs.get("value") == 42
        assert inputs.get("text") == "hello"
        assert inputs.get("missing", "default") == "default"

        # Test that it returns first match (insertion order)
        assert inputs.get("shared") == "from_a"

    def test_get_from(self):
        """Test StageInputs.get_from method."""
        snapshot = _make_snapshot()
        prior_outputs = {
            "stage_a": StageOutput.ok(data={"value": 42}),
            "stage_b": StageOutput.ok(data={"text": "hello"}),
        }

        inputs = StageInputs(
            snapshot=snapshot,
            prior_outputs=prior_outputs,
        )

        # Test getting from specific stage
        assert inputs.get_from("stage_a", "value") == 42
        assert inputs.get_from("stage_b", "text") == "hello"

        # Test missing stage
        assert inputs.get_from("missing", "key") is None
        assert inputs.get_from("missing", "key", "default") == "default"

        # Test missing key
        assert inputs.get_from("stage_a", "missing") is None
        assert inputs.get_from("stage_a", "missing", "default") == "default"

    def test_get_output(self):
        """Test StageInputs.get_output method."""
        snapshot = _make_snapshot()
        output = StageOutput.ok(data={"value": 42})
        prior_outputs = {"stage_a": output}

        inputs = StageInputs(
            snapshot=snapshot,
            prior_outputs=prior_outputs,
        )

        # Test getting output
        assert inputs.get_output("stage_a") is output
        assert inputs.get_output("missing") is None


# === Test StageInputs Factory ===

class TestStageInputsFactory:
    """Tests for create_stage_inputs factory function."""

    def test_create_stage_inputs_minimal(self):
        """Test create_stage_inputs with minimal arguments."""
        snapshot = _make_snapshot()
        inputs = create_stage_inputs(snapshot=snapshot)
        assert isinstance(inputs, StageInputs)
        assert inputs.snapshot is snapshot
        assert inputs.prior_outputs == {}
        assert inputs.ports is None

    def test_create_stage_inputs_with_all(self):
        """Test create_stage_inputs with all arguments."""
        snapshot = _make_snapshot()
        prior_outputs = {"stage_a": StageOutput.ok(data={"value": 42})}
        ports = LLMPorts(llm_provider=object())

        inputs = create_stage_inputs(
            snapshot=snapshot,
            prior_outputs=prior_outputs,
            ports=ports,
        )
        assert isinstance(inputs, StageInputs)
        assert inputs.snapshot is snapshot
        assert inputs.prior_outputs == prior_outputs
        assert inputs.ports is ports

    def test_create_stage_inputs_with_core_ports(self):
        """Test create_stage_inputs with CorePorts."""
        snapshot = _make_snapshot()
        ports = CorePorts(db=object())
        inputs = create_stage_inputs(snapshot=snapshot, ports=ports)
        assert inputs.ports is ports

    def test_create_stage_inputs_with_llm_ports(self):
        """Test create_stage_inputs with LLMPorts."""
        snapshot = _make_snapshot()
        ports = LLMPorts(llm_provider=object())
        inputs = create_stage_inputs(snapshot=snapshot, ports=ports)
        assert inputs.ports is ports

    def test_create_stage_inputs_with_audio_ports(self):
        """Test create_stage_inputs with AudioPorts."""
        snapshot = _make_snapshot()
        ports = AudioPorts(tts_provider=object())
        inputs = create_stage_inputs(snapshot=snapshot, ports=ports)
        assert inputs.ports is ports
