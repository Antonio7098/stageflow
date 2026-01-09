"""Testing utilities for stageflow.

This module provides helpers for testing stages, pipelines, and contexts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from stageflow.context import ContextSnapshot, Message
from stageflow.core import StageContext, StageOutput
from stageflow.events import NoOpEventSink
from stageflow.stages.context import PipelineContext
from stageflow.stages.inputs import StageInputs, create_stage_inputs
from stageflow.stages.ports import CorePorts, LLMPorts, AudioPorts


def create_test_snapshot(
    *,
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    topology: str | None = "test",
    execution_mode: str | None = "test",
    input_text: str | None = None,
    messages: list[Message] | None = None,
    extensions: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ContextSnapshot:
    """Create a ContextSnapshot for testing with sensible defaults.
    
    All UUID fields default to new random UUIDs if not provided.
    
    Args:
        pipeline_run_id: Pipeline run ID (default: new UUID)
        request_id: Request ID (default: new UUID)
        session_id: Session ID (default: new UUID)
        user_id: User ID (default: new UUID)
        org_id: Organization ID (default: None)
        interaction_id: Interaction ID (default: new UUID)
        topology: Pipeline topology name (default: "test")
        execution_mode: Execution mode (default: "test")
        input_text: Input text for the pipeline
        messages: Message history
        extensions: Extension data
        **kwargs: Additional ContextSnapshot fields
        
    Returns:
        ContextSnapshot configured for testing
        
    Example:
        snapshot = create_test_snapshot(
            input_text="Hello, world!",
            user_id=uuid4(),
        )
    """
    return ContextSnapshot(
        pipeline_run_id=pipeline_run_id or uuid4(),
        request_id=request_id or uuid4(),
        session_id=session_id or uuid4(),
        user_id=user_id or uuid4(),
        org_id=org_id,
        interaction_id=interaction_id or uuid4(),
        topology=topology,
        execution_mode=execution_mode,
        input_text=input_text,
        messages=messages or [],
        extensions=extensions or {},
        **kwargs,
    )


def create_test_stage_context(
    *,
    snapshot: ContextSnapshot | None = None,
    config: dict[str, Any] | None = None,
    inputs: StageInputs | None = None,
    prior_outputs: dict[str, StageOutput] | None = None,
    ports: CorePorts | LLMPorts | AudioPorts | None = None,
    event_sink: Any | None = None,
    **snapshot_kwargs: Any,
) -> StageContext:
    """Create a StageContext for testing with sensible defaults.
    
    Args:
        snapshot: ContextSnapshot to use (creates one if not provided)
        config: Stage configuration dict
        inputs: StageInputs for upstream data access
        prior_outputs: Dict of prior stage outputs (used if inputs not provided)
        ports: Modular ports for service injection (CorePorts, LLMPorts, or AudioPorts)
        event_sink: Event sink for observability (default: NoOpEventSink)
        **snapshot_kwargs: Passed to create_test_snapshot if snapshot not provided
        
    Returns:
        StageContext configured for testing
        
    Example:
        ctx = create_test_stage_context(
            input_text="Test input",
            prior_outputs={"stage_a": StageOutput.ok(value=42)},
        )
        
        # Access inputs
        value = ctx.inputs.get("value")  # Returns 42
    """
    if snapshot is None:
        snapshot = create_test_snapshot(**snapshot_kwargs)
    
    # Build config
    final_config = config.copy() if config else {}
    
    # Set up inputs if not provided
    if inputs is None and (prior_outputs or ports):
        inputs = create_stage_inputs(
            snapshot=snapshot,
            prior_outputs=prior_outputs or {},
            ports=ports,
        )
    
    if inputs is not None:
        final_config["inputs"] = inputs
    
    # Set event sink
    final_config["event_sink"] = event_sink or NoOpEventSink()
    
    return StageContext(snapshot=snapshot, config=final_config)


def create_test_pipeline_context(
    *,
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    topology: str | None = "test",
    execution_mode: str | None = "test",
    service: str = "test",
    data: dict[str, Any] | None = None,
    event_sink: Any | None = None,
    **kwargs: Any,
) -> PipelineContext:
    """Create a PipelineContext for testing with sensible defaults.
    
    Args:
        pipeline_run_id: Pipeline run ID (default: new UUID)
        request_id: Request ID (default: new UUID)
        session_id: Session ID (default: new UUID)
        user_id: User ID (default: new UUID)
        org_id: Organization ID (default: None)
        interaction_id: Interaction ID (default: new UUID)
        topology: Pipeline topology name (default: "test")
        execution_mode: Execution mode (default: "test")
        service: Service name (default: "test")
        data: Context data dict
        event_sink: Event sink (default: NoOpEventSink)
        **kwargs: Additional PipelineContext fields
        
    Returns:
        PipelineContext configured for testing
        
    Example:
        ctx = create_test_pipeline_context(
            user_id=uuid4(),
            data={"key": "value"},
        )
    """
    return PipelineContext(
        pipeline_run_id=pipeline_run_id or uuid4(),
        request_id=request_id or uuid4(),
        session_id=session_id or uuid4(),
        user_id=user_id or uuid4(),
        org_id=org_id,
        interaction_id=interaction_id or uuid4(),
        topology=topology,
        execution_mode=execution_mode,
        service=service,
        data=data or {},
        event_sink=event_sink or NoOpEventSink(),
        **kwargs,
    )


@dataclass
class SnapshotValidationError:
    """Represents a validation error in a ContextSnapshot."""
    
    field: str
    message: str
    value: Any = None


@dataclass
class SnapshotValidationResult:
    """Result of validating a ContextSnapshot."""
    
    valid: bool
    errors: list[SnapshotValidationError] = field(default_factory=list)
    warnings: list[SnapshotValidationError] = field(default_factory=list)
    
    def __bool__(self) -> bool:
        return self.valid


def validate_snapshot(
    snapshot: ContextSnapshot,
    *,
    require_user_id: bool = False,
    require_org_id: bool = False,
    require_pipeline_run_id: bool = True,
    require_request_id: bool = False,
    strict: bool = False,
) -> SnapshotValidationResult:
    """Validate a ContextSnapshot for correctness.
    
    Checks for common issues like missing required fields, invalid UUIDs,
    and inconsistent data.
    
    Args:
        snapshot: The snapshot to validate
        require_user_id: Require user_id to be set
        require_org_id: Require org_id to be set
        require_pipeline_run_id: Require pipeline_run_id to be set
        require_request_id: Require request_id to be set
        strict: If True, treat warnings as errors
        
    Returns:
        SnapshotValidationResult with validation status and any errors/warnings
        
    Example:
        result = validate_snapshot(snapshot, require_user_id=True)
        if not result:
            for error in result.errors:
                print(f"{error.field}: {error.message}")
    """
    errors: list[SnapshotValidationError] = []
    warnings: list[SnapshotValidationError] = []
    
    # Required field checks
    if require_pipeline_run_id and snapshot.pipeline_run_id is None:
        errors.append(SnapshotValidationError(
            field="pipeline_run_id",
            message="pipeline_run_id is required but not set",
        ))
    
    if require_request_id and snapshot.request_id is None:
        errors.append(SnapshotValidationError(
            field="request_id",
            message="request_id is required but not set",
        ))
    
    if require_user_id and snapshot.user_id is None:
        errors.append(SnapshotValidationError(
            field="user_id",
            message="user_id is required but not set",
        ))
    
    if require_org_id and snapshot.org_id is None:
        errors.append(SnapshotValidationError(
            field="org_id",
            message="org_id is required but not set",
        ))
    
    # Type checks for messages
    if snapshot.messages:
        for i, msg in enumerate(snapshot.messages):
            if not isinstance(msg, Message):
                errors.append(SnapshotValidationError(
                    field=f"messages[{i}]",
                    message=f"Expected Message, got {type(msg).__name__}",
                    value=msg,
                ))
            elif not msg.role:
                warnings.append(SnapshotValidationError(
                    field=f"messages[{i}].role",
                    message="Message role is empty",
                    value=msg,
                ))
    
    # Topology/execution_mode consistency warnings
    if snapshot.topology is None and snapshot.execution_mode is not None:
        warnings.append(SnapshotValidationError(
            field="topology",
            message="execution_mode is set but topology is None",
        ))
    
    # Extensions type check
    if not isinstance(snapshot.extensions, dict):
        errors.append(SnapshotValidationError(
            field="extensions",
            message=f"extensions must be a dict, got {type(snapshot.extensions).__name__}",
            value=snapshot.extensions,
        ))
    
    # In strict mode, warnings become errors
    if strict:
        errors.extend(warnings)
        warnings = []
    
    return SnapshotValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def validate_snapshot_strict(snapshot: ContextSnapshot, **kwargs: Any) -> ContextSnapshot:
    """Validate a snapshot and raise if invalid.
    
    Args:
        snapshot: The snapshot to validate
        **kwargs: Passed to validate_snapshot
        
    Returns:
        The snapshot if valid
        
    Raises:
        ValueError: If validation fails, with details about errors
        
    Example:
        # This will raise if snapshot is invalid
        snapshot = validate_snapshot_strict(snapshot, require_user_id=True)
    """
    result = validate_snapshot(snapshot, strict=True, **kwargs)
    if not result:
        error_details = "; ".join(f"{e.field}: {e.message}" for e in result.errors)
        raise ValueError(f"ContextSnapshot validation failed: {error_details}")
    return snapshot


def snapshot_from_dict_strict(data: dict[str, Any], **validation_kwargs: Any) -> ContextSnapshot:
    """Create a ContextSnapshot from dict with validation.
    
    Args:
        data: Dictionary data to create snapshot from
        **validation_kwargs: Passed to validate_snapshot
        
    Returns:
        Validated ContextSnapshot
        
    Raises:
        ValueError: If the data produces an invalid snapshot
        
    Example:
        snapshot = snapshot_from_dict_strict(
            {"pipeline_run_id": "...", ...},
            require_user_id=True,
        )
    """
    snapshot = ContextSnapshot.from_dict(data)
    return validate_snapshot_strict(snapshot, **validation_kwargs)


__all__ = [
    # Snapshot creation
    "create_test_snapshot",
    "create_test_stage_context", 
    "create_test_pipeline_context",
    # Validation
    "SnapshotValidationError",
    "SnapshotValidationResult",
    "validate_snapshot",
    "validate_snapshot_strict",
    "snapshot_from_dict_strict",
]
