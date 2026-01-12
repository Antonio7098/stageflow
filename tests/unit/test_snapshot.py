"""Comprehensive tests for stageflow.context.snapshot module.

Tests:
- ContextSnapshot class (with Generic[T] extensions)
- RunIdentity dataclass
- Enrichments composition dataclass
- Conversation composition dataclass
- Message dataclass
- RoutingDecision dataclass
- Enrichment dataclasses (ProfileEnrichment, MemoryEnrichment, DocumentEnrichment)
- to_dict and from_dict serialization
"""

from dataclasses import FrozenInstanceError, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from stageflow.context import (
    ContextSnapshot,
    Conversation,
    DocumentEnrichment,
    Enrichments,
    ExtensionBundle,
    MemoryEnrichment,
    Message,
    ProfileEnrichment,
    RoutingDecision,
    RunIdentity,
)

# === Test Message ===


class TestMessage:
    """Tests for Message dataclass."""

    def test_message_creation(self):
        """Test Message creation."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is None
        assert msg.metadata == {}

    def test_message_with_timestamp(self):
        """Test Message with timestamp."""
        ts = datetime.now(UTC)
        msg = Message(role="assistant", content="Hi", timestamp=ts)
        assert msg.timestamp == ts

    def test_message_with_metadata(self):
        """Test Message with metadata."""
        metadata = {"confidence": 0.95, "tokens": 100}
        msg = Message(role="user", content="Test", metadata=metadata)
        assert msg.metadata == metadata

    def test_message_is_frozen(self):
        """Test Message is frozen."""
        msg = Message(role="user", content="Test")
        with pytest.raises(FrozenInstanceError):
            msg.content = "Modified"

    def test_message_has_slots(self):
        """Test Message uses slots."""
        assert hasattr(Message, "__slots__")

    def test_message_default_values(self):
        """Test Message default values."""
        msg = Message(role="user", content="Test")
        assert msg.timestamp is None
        assert msg.metadata == {}


# === Test RoutingDecision ===


class TestRoutingDecision:
    """Tests for RoutingDecision dataclass."""

    def test_routing_decision_creation(self):
        """Test RoutingDecision creation."""
        decision = RoutingDecision(
            agent_id="coach",
            pipeline_name="practice",
            topology="fast_kernel",
        )
        assert decision.agent_id == "coach"
        assert decision.pipeline_name == "practice"
        assert decision.topology == "fast_kernel"
        assert decision.reason is None

    def test_routing_decision_with_reason(self):
        """Test RoutingDecision with reason."""
        decision = RoutingDecision(
            agent_id="interviewer",
            pipeline_name="interview",
            topology="accurate_kernel",
            reason="High accuracy required",
        )
        assert decision.reason == "High accuracy required"

    def test_routing_decision_is_frozen(self):
        """Test RoutingDecision is frozen."""
        decision = RoutingDecision(
            agent_id="test",
            pipeline_name="test",
            topology="test",
        )
        with pytest.raises(FrozenInstanceError):
            decision.agent_id = "modified"

    def test_routing_decision_has_slots(self):
        """Test RoutingDecision uses slots."""
        assert hasattr(RoutingDecision, "__slots__")


# === Test ProfileEnrichment ===


class TestProfileEnrichment:
    """Tests for ProfileEnrichment dataclass."""

    def test_profile_enrichment_creation(self):
        """Test ProfileEnrichment creation."""
        user_id = uuid4()
        profile = ProfileEnrichment(
            user_id=user_id,
            display_name="John Doe",
            preferences={"theme": "dark"},
            goals=["Learn Python", "Master testing"],
        )
        assert profile.user_id == user_id
        assert profile.display_name == "John Doe"
        assert profile.preferences == {"theme": "dark"}
        assert profile.goals == ["Learn Python", "Master testing"]

    def test_profile_enrichment_defaults(self):
        """Test ProfileEnrichment default values."""
        user_id = uuid4()
        profile = ProfileEnrichment(user_id=user_id)
        assert profile.display_name is None
        assert profile.preferences == {}
        assert profile.goals == []

    def test_profile_enrichment_is_frozen(self):
        """Test ProfileEnrichment is frozen."""
        user_id = uuid4()
        profile = ProfileEnrichment(user_id=user_id)
        with pytest.raises(FrozenInstanceError):
            profile.display_name = "Modified"


# === Test MemoryEnrichment ===


class TestMemoryEnrichment:
    """Tests for MemoryEnrichment dataclass."""

    def test_memory_enrichment_creation(self):
        """Test MemoryEnrichment creation."""
        memory = MemoryEnrichment(
            recent_topics=["Python", "Testing"],
            key_facts=["User prefers dark mode", "User is learning async"],
            interaction_history_summary="Session focused on async programming",
        )
        assert memory.recent_topics == ["Python", "Testing"]
        assert memory.key_facts == ["User prefers dark mode", "User is learning async"]
        assert memory.interaction_history_summary == "Session focused on async programming"

    def test_memory_enrichment_defaults(self):
        """Test MemoryEnrichment default values."""
        memory = MemoryEnrichment()
        assert memory.recent_topics == []
        assert memory.key_facts == []
        assert memory.interaction_history_summary is None

    def test_memory_enrichment_is_frozen(self):
        """Test MemoryEnrichment is frozen."""
        memory = MemoryEnrichment()
        with pytest.raises(FrozenInstanceError):
            memory.recent_topics = ["new_topic"]  # Field reassignment raises FrozenInstanceError


# === Test DocumentEnrichment ===


class TestDocumentEnrichment:
    """Tests for DocumentEnrichment dataclass."""

    def test_document_enrichment_creation(self):
        """Test DocumentEnrichment creation."""
        doc = DocumentEnrichment(
            document_id="doc123",
            document_type="pdf",
            blocks=[{"type": "text", "content": "Hello"}],
            metadata={"pages": 5},
        )
        assert doc.document_id == "doc123"
        assert doc.document_type == "pdf"
        assert len(doc.blocks) == 1
        assert doc.metadata == {"pages": 5}

    def test_document_enrichment_defaults(self):
        """Test DocumentEnrichment default values."""
        doc = DocumentEnrichment()
        assert doc.document_id is None
        assert doc.document_type is None
        assert doc.blocks == []
        assert doc.metadata == {}

    def test_document_enrichment_is_frozen(self):
        """Test DocumentEnrichment is frozen."""
        doc = DocumentEnrichment()
        with pytest.raises(FrozenInstanceError):
            doc.document_id = "modified"


# === Test RunIdentity ===


class TestRunIdentity:
    """Tests for RunIdentity dataclass."""

    def test_run_identity_creation(self):
        """Test RunIdentity creation."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        assert run_id.pipeline_run_id is not None
        assert run_id.request_id is not None

    def test_run_identity_defaults(self):
        """Test RunIdentity default values."""
        run_id = RunIdentity()
        assert run_id.pipeline_run_id is None
        assert run_id.request_id is None
        assert run_id.session_id is None
        assert run_id.user_id is None
        assert run_id.org_id is None
        assert run_id.interaction_id is None
        assert run_id.created_at is not None

    def test_run_identity_is_frozen(self):
        """Test RunIdentity is frozen."""
        run_id = RunIdentity()
        with pytest.raises(FrozenInstanceError):
            run_id.pipeline_run_id = uuid4()

    def test_run_identity_to_dict(self):
        """Test RunIdentity to_dict serialization."""
        pid = uuid4()
        run_id = RunIdentity(pipeline_run_id=pid)
        result = run_id.to_dict()
        assert result["pipeline_run_id"] == str(pid)

    def test_run_identity_from_dict(self):
        """Test RunIdentity from_dict deserialization."""
        pid = uuid4()
        data = {"pipeline_run_id": str(pid), "request_id": None}
        run_id = RunIdentity.from_dict(data)
        assert run_id.pipeline_run_id == pid


# === Test Enrichments ===


class TestEnrichments:
    """Tests for Enrichments composition class."""

    def test_enrichments_creation(self):
        """Test Enrichments creation."""
        user_id = uuid4()
        enrichments = Enrichments(
            profile=ProfileEnrichment(user_id=user_id),
            memory=MemoryEnrichment(recent_topics=["Python"]),
            documents=[DocumentEnrichment(document_id="doc1")],
            web_results=[{"title": "Test"}],
        )
        assert enrichments.profile.user_id == user_id
        assert enrichments.memory.recent_topics == ["Python"]
        assert len(enrichments.documents) == 1
        assert len(enrichments.web_results) == 1

    def test_enrichments_defaults(self):
        """Test Enrichments default values."""
        enrichments = Enrichments()
        assert enrichments.profile is None
        assert enrichments.memory is None
        assert enrichments.documents == []
        assert enrichments.web_results == []

    def test_enrichments_is_frozen(self):
        """Test Enrichments is frozen."""
        enrichments = Enrichments()
        with pytest.raises(FrozenInstanceError):
            enrichments.profile = ProfileEnrichment(user_id=uuid4())


# === Test Conversation ===


class TestConversation:
    """Tests for Conversation composition class."""

    def test_conversation_creation(self):
        """Test Conversation creation."""
        messages = [Message(role="user", content="Hello")]
        decision = RoutingDecision(
            agent_id="coach", pipeline_name="practice", topology="fast"
        )
        conversation = Conversation(messages=messages, routing_decision=decision)
        assert len(conversation.messages) == 1
        assert conversation.routing_decision.agent_id == "coach"

    def test_conversation_defaults(self):
        """Test Conversation default values."""
        conversation = Conversation()
        assert conversation.messages == []
        assert conversation.routing_decision is None

    def test_conversation_is_frozen(self):
        """Test Conversation is frozen."""
        conversation = Conversation()
        with pytest.raises(FrozenInstanceError):
            conversation.messages = [Message(role="user", content="test")]


# === Test ContextSnapshot ===


class TestContextSnapshot:
    """Tests for ContextSnapshot class."""

    @pytest.fixture
    def run_id(self):
        """Create a RunIdentity for testing."""
        return RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

    @pytest.fixture
    def required_fields(self, run_id):
        """Fields for ContextSnapshot with explicit IDs."""
        return {
            "run_id": run_id,
            "topology": "test_topology",
            "execution_mode": "test",
        }

    def test_empty_snapshot(self):
        """Test snapshot can be created with no arguments (all defaults)."""
        snapshot = ContextSnapshot()
        # Backwards compat properties
        assert snapshot.pipeline_run_id is None
        assert snapshot.request_id is None
        assert snapshot.session_id is None
        assert snapshot.user_id is None
        assert snapshot.org_id is None
        assert snapshot.interaction_id is None
        assert snapshot.topology is None
        assert snapshot.execution_mode is None
        assert snapshot.messages == []
        assert snapshot.routing_decision is None
        assert snapshot.profile is None
        assert snapshot.memory is None
        assert snapshot.documents == []
        assert snapshot.web_results == []
        assert snapshot.extensions is None  # Typed extension bundle, None by default
        assert snapshot.metadata == {}
        assert snapshot.created_at is not None

    def test_minimal_snapshot(self, required_fields, run_id):
        """Test snapshot with all fields explicitly set."""
        snapshot = ContextSnapshot(**required_fields)
        # Access via backwards compat properties
        assert snapshot.pipeline_run_id == run_id.pipeline_run_id
        assert snapshot.topology == "test_topology"
        assert snapshot.messages == []
        assert snapshot.routing_decision is None
        assert snapshot.profile is None
        assert snapshot.memory is None
        assert snapshot.documents == []
        assert snapshot.web_results == []
        assert snapshot.extensions is None

    def test_snapshot_with_messages(self, required_fields):
        """Test snapshot with messages via conversation."""
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        snapshot = ContextSnapshot(
            conversation=Conversation(messages=messages),
            **required_fields,
        )
        # Access via backwards compat property
        assert len(snapshot.messages) == 2
        assert snapshot.messages[0].role == "user"

    def test_snapshot_with_routing_decision(self, required_fields):
        """Test snapshot with routing decision via conversation."""
        decision = RoutingDecision(
            agent_id="coach",
            pipeline_name="practice",
            topology="fast_kernel",
        )
        snapshot = ContextSnapshot(
            conversation=Conversation(routing_decision=decision),
            **required_fields,
        )
        # Access via backwards compat property
        assert snapshot.routing_decision == decision

    def test_snapshot_with_profile(self, required_fields, run_id):
        """Test snapshot with profile enrichment via enrichments."""
        profile = ProfileEnrichment(user_id=run_id.user_id)
        snapshot = ContextSnapshot(
            enrichments=Enrichments(profile=profile),
            **required_fields,
        )
        # Access via backwards compat property
        assert snapshot.profile == profile

    def test_snapshot_with_memory(self, required_fields):
        """Test snapshot with memory enrichment via enrichments."""
        memory = MemoryEnrichment(recent_topics=["Python"])
        snapshot = ContextSnapshot(
            enrichments=Enrichments(memory=memory),
            **required_fields,
        )
        # Access via backwards compat property
        assert snapshot.memory == memory

    def test_snapshot_with_documents(self, required_fields):
        """Test snapshot with documents via enrichments."""
        docs = [
            DocumentEnrichment(document_id="doc1", document_type="pdf"),
            DocumentEnrichment(document_id="doc2", document_type="txt"),
        ]
        snapshot = ContextSnapshot(
            enrichments=Enrichments(documents=docs),
            **required_fields,
        )
        # Access via backwards compat property
        assert len(snapshot.documents) == 2

    def test_snapshot_with_web_results(self, required_fields):
        """Test snapshot with web results via enrichments."""
        web_results = [
            {"title": "Python Docs", "url": "https://docs.python.org"},
            {"title": "pytest", "url": "https://pytest.org"},
        ]
        snapshot = ContextSnapshot(
            enrichments=Enrichments(web_results=web_results),
            **required_fields,
        )
        # Access via backwards compat property
        assert len(snapshot.web_results) == 2

    def test_snapshot_with_input_context(self, required_fields):
        """Test snapshot with input context."""
        snapshot = ContextSnapshot(
            input_text="User's input text",
            input_audio_duration_ms=5000,
            **required_fields,
        )
        assert snapshot.input_text == "User's input text"
        assert snapshot.input_audio_duration_ms == 5000

    def test_snapshot_with_metadata(self, required_fields):
        """Test snapshot with metadata."""
        snapshot = ContextSnapshot(
            metadata={"custom_key": "custom_value"},
            **required_fields,
        )
        assert snapshot.metadata == {"custom_key": "custom_value"}

    def test_snapshot_created_at_set(self, required_fields):
        """Test created_at is set automatically."""
        before = datetime.now(UTC)
        snapshot = ContextSnapshot(**required_fields)
        after = datetime.now(UTC)

        assert snapshot.created_at is not None
        # Use replace to strip timezone for comparison if needed
        assert before <= snapshot.created_at <= after

    def test_snapshot_is_frozen(self, required_fields):
        """Test ContextSnapshot is frozen."""
        snapshot = ContextSnapshot(**required_fields)
        with pytest.raises(FrozenInstanceError):
            snapshot.topology = "modified"

    def test_snapshot_has_slots(self):
        """Test ContextSnapshot uses slots."""
        assert hasattr(ContextSnapshot, "__slots__")


# === Test Extensions ===


class TestContextSnapshotExtensions:
    """Tests for ContextSnapshot typed extensions."""

    def test_snapshot_with_typed_extension(self):
        """Test snapshot with typed extension bundle."""

        @dataclass(frozen=True)
        class MyExtensions(ExtensionBundle):
            custom_field: str = ""
            custom_list: list[str] = field(default_factory=list)

        ext = MyExtensions(custom_field="test", custom_list=["a", "b"])
        snapshot: ContextSnapshot[MyExtensions] = ContextSnapshot(extensions=ext)

        assert snapshot.extensions is not None
        assert snapshot.extensions.custom_field == "test"
        assert snapshot.extensions.custom_list == ["a", "b"]

    def test_extension_serialization(self):
        """Test extension bundle serialization."""

        @dataclass(frozen=True)
        class SalesExtensions(ExtensionBundle):
            deal_value: int = 0
            deal_stage: str = ""

        ext = SalesExtensions(deal_value=50000, deal_stage="negotiation")
        snapshot: ContextSnapshot[SalesExtensions] = ContextSnapshot(extensions=ext)

        result = snapshot.to_dict()
        assert result["extensions"]["deal_value"] == 50000
        assert result["extensions"]["deal_stage"] == "negotiation"
        assert result["extensions_type"] == "SalesExtensions"

    def test_extension_deserialization(self):
        """Test extension bundle deserialization with registry."""

        @dataclass(frozen=True)
        class TestExtensions(ExtensionBundle):
            value: int = 0

        ext = TestExtensions(value=42)
        snapshot = ContextSnapshot(extensions=ext)

        data = snapshot.to_dict()
        restored = ContextSnapshot.from_dict(
            data,
            extension_types={"TestExtensions": TestExtensions},
        )

        assert restored.extensions is not None
        assert restored.extensions.value == 42

    def test_with_extensions_method(self):
        """Test with_extensions returns new snapshot."""

        @dataclass(frozen=True)
        class MyExt(ExtensionBundle):
            x: int = 0

        snapshot = ContextSnapshot()
        new_snapshot = snapshot.with_extensions(MyExt(x=10))

        assert snapshot.extensions is None
        assert new_snapshot.extensions is not None
        assert new_snapshot.extensions.x == 10


# === Test Serialization ===


class TestContextSnapshotSerialization:
    """Tests for ContextSnapshot to_dict and from_dict."""

    @pytest.fixture
    def full_snapshot(self):
        """Create a full ContextSnapshot for testing."""
        user_id = uuid4()
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=user_id,
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        return ContextSnapshot(
            run_id=run_id,
            topology="chat_fast",
            execution_mode="practice",
            conversation=Conversation(
                messages=[
                    Message(role="user", content="Hello", timestamp=datetime.now(UTC)),
                    Message(role="assistant", content="Hi!", timestamp=datetime.now(UTC)),
                ],
                routing_decision=RoutingDecision(
                    agent_id="coach",
                    pipeline_name="practice",
                    topology="fast_kernel",
                    reason="Practice session",
                ),
            ),
            enrichments=Enrichments(
                profile=ProfileEnrichment(
                    user_id=user_id,
                    display_name="Test User",
                    preferences={"theme": "dark"},
                    goals=["Learn"],
                ),
                memory=MemoryEnrichment(
                    recent_topics=["Python"],
                    key_facts=["User is learning"],
                    interaction_history_summary="First session",
                ),
                documents=[
                    DocumentEnrichment(
                        document_id="doc1",
                        document_type="pdf",
                        blocks=[{"type": "text"}],
                        metadata={"pages": 10},
                    )
                ],
                web_results=[{"title": "Test"}],
            ),
            input_text="Test input",
            input_audio_duration_ms=3000,
            metadata={"custom": "value"},
        )

    def test_to_dict(self, full_snapshot):
        """Test to_dict converts to serializable dict."""
        result = full_snapshot.to_dict()

        assert isinstance(result, dict)
        assert result["topology"] == "chat_fast"
        assert result["execution_mode"] == "practice"

    def test_to_dict_handles_uuid(self, full_snapshot):
        """Test to_dict converts UUIDs to strings."""
        result = full_snapshot.to_dict()

        # Backwards compat flat fields
        assert isinstance(result["pipeline_run_id"], str)
        assert isinstance(result["user_id"], str)

    def test_to_dict_handles_messages(self, full_snapshot):
        """Test to_dict handles messages."""
        result = full_snapshot.to_dict()

        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert isinstance(result["messages"][0]["timestamp"], str)

    def test_to_dict_handles_routing_decision(self, full_snapshot):
        """Test to_dict handles routing decision."""
        result = full_snapshot.to_dict()

        assert result["routing_decision"]["agent_id"] == "coach"
        assert result["routing_decision"]["reason"] == "Practice session"

    def test_to_dict_handles_profile(self, full_snapshot):
        """Test to_dict handles profile enrichment."""
        result = full_snapshot.to_dict()

        assert result["profile"]["display_name"] == "Test User"

    def test_to_dict_handles_memory(self, full_snapshot):
        """Test to_dict handles memory enrichment."""
        result = full_snapshot.to_dict()

        assert result["memory"]["recent_topics"] == ["Python"]
        assert result["memory"]["interaction_history_summary"] == "First session"

    def test_to_dict_handles_documents(self, full_snapshot):
        """Test to_dict handles documents."""
        result = full_snapshot.to_dict()

        assert len(result["documents"]) == 1
        assert result["documents"][0]["document_id"] == "doc1"
        assert result["documents"][0]["blocks"] == [{"type": "text"}]

    def test_to_dict_handles_none_enrichments(self):
        """Test to_dict handles None enrichments."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
        )
        result = snapshot.to_dict()

        assert result["profile"] is None
        assert result["memory"] is None
        assert result["extensions"] is None

    def test_from_dict(self, full_snapshot):
        """Test from_dict creates ContextSnapshot from dict."""
        data = full_snapshot.to_dict()
        restored = ContextSnapshot.from_dict(data)

        assert restored.topology == full_snapshot.topology
        assert restored.execution_mode == full_snapshot.execution_mode

    def test_from_dict_handles_messages(self, full_snapshot):
        """Test from_dict handles messages."""
        data = full_snapshot.to_dict()
        restored = ContextSnapshot.from_dict(data)

        assert len(restored.messages) == 2
        assert restored.messages[0].role == "user"
        assert restored.messages[0].timestamp is not None

    def test_from_dict_handles_routing_decision(self, full_snapshot):
        """Test from_dict handles routing decision."""
        data = full_snapshot.to_dict()
        restored = ContextSnapshot.from_dict(data)

        assert restored.routing_decision.agent_id == "coach"
        assert restored.routing_decision.reason == "Practice session"

    def test_from_dict_handles_profile(self, full_snapshot):
        """Test from_dict handles profile enrichment."""
        data = full_snapshot.to_dict()
        restored = ContextSnapshot.from_dict(data)

        assert restored.profile.display_name == "Test User"

    def test_from_dict_handles_documents(self, full_snapshot):
        """Test from_dict handles documents."""
        data = full_snapshot.to_dict()
        restored = ContextSnapshot.from_dict(data)

        assert len(restored.documents) == 1
        assert restored.documents[0].document_id == "doc1"

    def test_roundtrip_preserves_data(self, full_snapshot):
        """Test roundtrip to_dict -> from_dict preserves data."""
        data = full_snapshot.to_dict()
        restored = ContextSnapshot.from_dict(data)

        # Check all fields
        assert restored.topology == full_snapshot.topology
        assert restored.execution_mode == full_snapshot.execution_mode
        assert len(restored.messages) == len(full_snapshot.messages)
        assert restored.input_text == full_snapshot.input_text

    def test_from_dict_with_minimal_data(self):
        """Test from_dict with minimal data."""
        data = {
            "topology": "test",
            "execution_mode": "test",
        }
        restored = ContextSnapshot.from_dict(data)

        assert restored.topology == "test"
        assert restored.messages == []

    def test_from_dict_handles_created_at(self, full_snapshot):
        """Test from_dict preserves created_at."""
        data = full_snapshot.to_dict()
        restored = ContextSnapshot.from_dict(data)

        assert restored.created_at == full_snapshot.created_at


# === Edge Cases ===


class TestContextSnapshotEdgeCases:
    """Edge case tests for ContextSnapshot."""

    def test_empty_messages_list(self):
        """Test with empty messages list."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
            conversation=Conversation(messages=[]),
        )
        assert snapshot.messages == []

    def test_empty_documents_list(self):
        """Test with empty documents list."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
            enrichments=Enrichments(documents=[]),
        )
        assert snapshot.documents == []

    def test_nested_metadata(self):
        """Test with deeply nested metadata."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
            metadata={"nested": {"deep": {"value": 1}}},
        )
        assert snapshot.metadata["nested"]["deep"]["value"] == 1

    def test_unicode_content(self):
        """Test with unicode content."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
            conversation=Conversation(
                messages=[
                    Message(role="user", content="日本語テスト 🎉 ñ"),
                ]
            ),
        )
        assert "日本語テスト" in snapshot.messages[0].content

    def test_none_topology_channel_execution_mode(self):
        """Test with None optional fields."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        snapshot = ContextSnapshot(
            run_id=run_id,
            topology=None,
            execution_mode=None,
        )
        assert snapshot.topology is None
        assert snapshot.execution_mode is None


# === Test with_* Methods ===


class TestContextSnapshotWithMethods:
    """Tests for ContextSnapshot with_* methods."""

    def test_with_run_id(self):
        """Test with_run_id returns new snapshot."""
        old_run_id = RunIdentity(pipeline_run_id=uuid4())
        new_run_id = RunIdentity(pipeline_run_id=uuid4())

        snapshot = ContextSnapshot(run_id=old_run_id)
        new_snapshot = snapshot.with_run_id(new_run_id)

        assert snapshot.pipeline_run_id == old_run_id.pipeline_run_id
        assert new_snapshot.pipeline_run_id == new_run_id.pipeline_run_id

    def test_with_enrichments(self):
        """Test with_enrichments returns new snapshot."""
        snapshot = ContextSnapshot()
        enrichments = Enrichments(memory=MemoryEnrichment(recent_topics=["Test"]))
        new_snapshot = snapshot.with_enrichments(enrichments)

        assert snapshot.memory is None
        assert new_snapshot.memory is not None
        assert new_snapshot.memory.recent_topics == ["Test"]

    def test_with_conversation(self):
        """Test with_conversation returns new snapshot."""
        snapshot = ContextSnapshot()
        conversation = Conversation(messages=[Message(role="user", content="Hi")])
        new_snapshot = snapshot.with_conversation(conversation)

        assert snapshot.messages == []
        assert len(new_snapshot.messages) == 1
        assert new_snapshot.messages[0].content == "Hi"
