# ENRICH Stage Reliability & Knowledge Integrity Tracker

## Scope
Synthesizes ENRICH-001, ENRICH-003, ENRICH-004, ENRICH-005 findings covering multi-hop retrieval, citation hallucination, document versioning, and context window degradation.

---

## Evidence Summary

| Report | Core Claim | Code Evidence | Verdict |
|--------|------------|---------------|---------|
| ENRICH-001 | Silent failure in multi-hop retrieval when bridging entities missing | No native multi-hop stage exists; ENRICH is a `StageKind` enum value only (`@stageflow/core/stage_enums.py:14`). Builders implement custom retrieval logic. | **Confirmed gap** |
| ENRICH-003 | No native citation hallucination detection | `GuardrailStage` (`@stageflow/helpers/guardrails.py:439-537`) handles content filtering but has no citation verification. `InjectionDetector` exists but not `CitationVerifier`. | **Confirmed gap** |
| ENRICH-004 | ENRICH stages lack version awareness for documents | No version field in stage contracts. `StageOutput.ok()` accepts arbitrary kwargs but no version metadata enforcement. | **Confirmed gap** |
| ENRICH-005 | Context window boundary degradation not handled | No token tracking or truncation events in stage context. `StageContext` has no `context_utilization` property. | **Confirmed gap** |

---

## Consolidated Findings

### Critical Issues (P0)

**None** - All issues are reliability/DX gaps, not breaking bugs.

### High-Severity Issues (P1)

| ID | Issue | Impact | Evidence |
|----|-------|--------|----------|
| BUG-040 | Silent failure in AnswerValidationStage - high confidence wrong answers pass validation | Production systems may serve incorrect answers | ENRICH-001: Weak similarity detection |
| BUG-042 | No native citation hallucination detection | Legal/medical RAG pipelines at risk | ENRICH-003: Real-world attorney sanctions cited |
| BUG-043 | ENRICH stages lack version awareness | LLMs receive conflicting document versions | ENRICH-004: 3 versions returned without filtering |
| BUG-045 | Context boundary degradation unhandled | Retrieval accuracy degrades unpredictably | ENRICH-005: 25% confidence drop with 10 distractors |
| BUG-046 | Silent truncation when context exceeds limits | Pipeline succeeds with incomplete context | ENRICH-005: No truncation event emission |

### DX Issues

| ID | Issue | Severity |
|----|-------|----------|
| DX-044 | No guidance on document versioning patterns | Medium |
| - | Missing multi-hop retrieval templates | Medium |
| - | No citation verification examples | Medium |
| - | Context boundary guidance absent | Medium |

---

## Implementation Plan

### Phase 1: Documentation & Patterns (Short Term)

| # | Status | Action | Owner | Effort | Impact |
|---|--------|--------|-------|--------|--------|
| 1 | Complete | **Multi-hop Retrieval Guide** - Added `docs/examples/multi-hop-rag.md` with entity chain patterns, bridging entity detection, and hop-count degradation mitigation | Docs | Low | High |
| 2 | Complete | **Citation Verification Patterns** - Documented Entity Grounding (EG) and Relation Preservation (RP) patterns in `docs/advanced/knowledge-verification.md` | Docs | Low | High |
| 3 | Complete | **Version-Aware Retrieval Guide** - Added temporal filtering patterns to `docs/guides/enrich.md` with resolution strategies (LATEST_DATE, LATEST_VERSION, ALL_VERSIONS) | Docs | Low | Medium |
| 4 | Complete | **Context Boundary Best Practices** - Documented token tracking, truncation transparency, and distractor detection in `docs/advanced/context-management.md` | Docs | Low | Medium |

### Phase 2: Core Runtime Enhancements (Medium Term)

| # | Status | Enhancement | Priority | Design Considerations |
|---|--------|-------------|----------|----------------------|
| 1 | Not Started | **Truncation Event Emission** | P1 | Add `ctx.emit_event("context.truncated", {...})` when content dropped. Include: bytes_dropped, reason, affected_keys. **Safety**: Event-only, no behavior change. |
| 2 | Not Started | **Context Utilization Property** | P1 | Add `ctx.context_utilization` returning `{tokens_used, tokens_limit, utilization_pct}`. **Observability**: Enables monitoring dashboards. |
| 3 | Not Started | **Version Metadata in StageOutput** | P1 | Already exists via `StageOutput.ok(version=...)` from contracts module. Document and promote usage. |
| 4 | Not Started | **Conflict Detection Event** | P2 | Emit `enrich.version_conflict` when multiple document versions retrieved. **Reliability**: Explicit over silent. |

### Phase 3: Stageflow Plus Components (Medium Term)

| ID | Status | Component | Type | Priority | Use Case |
|----|--------|-----------|------|----------|----------|
| IMP-056 | Not Started | `MultiHopRetrievalStage` | Stagekind | P0 | Pre-built stage for entity chain traversal with hop-count limits |
| IMP-057 | Not Started | `EntityGroundingGuard` | Guard | P0 | Verify entity accuracy against source documents |
| IMP-059 | Not Started | `CitationVerifierGuard` | Guard | P0 | Detect fabricated, misattributed, distorted citations |
| IMP-060 | Not Started | `HalluGraphIntegration` | Integration | P1 | Knowledge graph alignment for structural verification |
| IMP-062 | Not Started | `VersionAwareDocumentRetrievalStage` | Stagekind | P1 | Temporal filtering with configurable resolution strategies |
| IMP-063 | Not Started | `PositionAwareEnrichStage` | Stagekind | P1 | Context-aware retrieval prioritization |
| IMP-064 | Not Started | `DistractorDetectionStage` | Stagekind | P1 | High-similarity content filtering |
| IMP-065 | Not Started | `ContextBoundaryTracker` | Utility | P1 | Track cumulative token usage across stages |
| IMP-066 | Not Started | `TruncationTransparencyReporter` | Observability | P2 | Report what content was dropped and why |

---

## Design Principles

### Speed
- Truncation events add <1ms overhead (async emit)
- Context utilization is O(1) property access
- Version filtering adds <10ms per retrieval (confirmed in ENRICH-004)

### Safety
- **Fail-explicit over fail-silent**: Emit events for version conflicts, truncation
- **No behavior changes in core**: All enhancements are additive (events, properties)
- **Opt-in complexity**: Advanced features in Plus package

### Observability
- All new events follow `{domain}.{action}` naming: `enrich.version_conflict`, `context.truncated`
- Structured event payloads with consistent schema
- Integration with existing `ctx.event_sink.try_emit()` pattern

### Reliability
- Version-aware retrieval prevents silent data corruption
- Citation verification catches hallucinations before production
- Context tracking prevents unpredictable degradation

### SOLID Principles
- **Single Responsibility**: Each Plus component handles one concern
- **Open/Closed**: Core ENRICH stages unchanged; extensions via composition
- **Liskov Substitution**: All Plus stages implement `Stage` protocol
- **Interface Segregation**: `GuardrailCheck` protocol for custom checks
- **Dependency Inversion**: Stages depend on abstractions (protocols), not concretions

### Scalability
- Multi-hop retrieval with configurable hop limits prevents runaway queries
- Distractor detection reduces context size, improving throughput
- Version filtering reduces LLM token consumption

---

## Test Coverage Requirements

| Component | Test Type | Coverage Target |
|-----------|-----------|-----------------|
| Truncation events | Unit | Event emission with correct payload |
| Context utilization | Unit | Accurate token counting |
| Version filtering | Integration | Temporal queries return correct version |
| Citation verification | Integration | Detect fabricated/misattributed citations |
| Multi-hop retrieval | E2E | Entity chain traversal with hop limits |

---

## Next Actions

1. **Immediate**: Add truncation event emission to `UnifiedStageGraph` (1-2 days)
2. **This Sprint**: Create `docs/advanced/knowledge-verification.md` with citation patterns
3. **Next Sprint**: Implement `VersionAwareDocumentRetrievalStage` prototype
4. **Backlog**: Design `MultiHopRetrievalStage` API with entity chain configuration

---

## DX Score Summary

| Report | Score | Key Friction |
|--------|-------|--------------|
| ENRICH-001 | 3.8/5 | Missing multi-hop templates |
| ENRICH-003 | 3.0/5 | No citation verification examples |
| ENRICH-004 | 3.6/5 | Missing versioning patterns |
| ENRICH-005 | 3.8/5 | No context boundary guidance |
| **Average** | **3.55/5** | Documentation gaps |

---

*Synthesized from ENRICH-001, ENRICH-003, ENRICH-004, ENRICH-005 final reports.*
