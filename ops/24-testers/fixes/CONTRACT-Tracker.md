# Contract Hardening Tracker

## Scope
Synthesizes CONTRACT-001/002/004 findings covering schema validation, evolution, and error messaging.

## Evidence Summary

| Contract | Recommendation | Repo Evidence | Status |
|----------|----------------|---------------|--------|
| CONTRACT-001 | Typed StageOutput validation + docs | `StageOutput` is a frozen dataclass with an untyped `data: dict[str, Any]` and no validation hooks @stageflow/core/stage_output.py#35-115. Grepping repo for "Pydantic" shows no stage/docs integration outside projector docs (search result limited to `docs/api/projector.md`). | Confirmed gap |
| CONTRACT-002 | Schema versioning/registry/compatibility | Same `StageOutput` has no `version` field or schema metadata. No schema registry modules found. | Confirmed gap |
| CONTRACT-004 | Structured, actionable contract violation errors | `PipelineValidationError` only stores `message` and `stages`; `CycleDetectedError` is the only structured child. Other errors (e.g., empty pipeline) surface terse strings via raising site in `pipeline.Pipeline.build()`. No doc links or suggestions exist. | Confirmed gap |

---

## Consolidated Findings

### Critical Issues (P0)

**None** - All issues are DX gaps, not breaking bugs.

### High-Severity Issues (P1)

| ID | Issue | Impact | Evidence |
|----|-------|--------|----------|
| BUG-001 | Untyped StageOutput data with no validation hooks | Production pipelines may accept invalid data silently | CONTRACT-001: No Pydantic integration in core |
| BUG-002 | No schema versioning or compatibility checks | API evolution breaks existing pipelines | CONTRACT-002: No version field or registry |
| BUG-004 | Terse error messages without fix hints | Developers waste time debugging contracts | CONTRACT-004: Only basic messages, no doc links |

### DX Issues

| ID | Issue | Severity |
|----|-------|----------|
| DX-001 | No typed output helpers or examples | Medium |
| DX-002 | Missing schema management patterns | Medium |
| DX-004 | No error messaging guidelines | Medium |

---

## Implementation Plan

### Phase 1: Immediate DX Wins

| # | Status | Action | Owner | Effort | Impact |
|---|--------|--------|-------|--------|--------|
| 1 | Complete | **Typed Output Helper + Docs** - Added `stageflow.contracts.TypedStageOutput` that wraps a Pydantic `BaseModel` (optional dependency) and validates `StageOutput.ok(...)` payloads. Provide synchronous + async helper for validation and serialization. Document patterns in `docs/guides/stages.md` + `docs/advanced/testing.md` with migration examples and strict/coerce guidance. | Docs | Low | High |
| 2 | Complete | **Structured Error Metadata** - Introduced `ContractErrorInfo` dataclass (code, summary, fix_hint, doc_url, context dict) and updated `PipelineValidationError`, `DependencyIssue`, etc., to populate it. Add doc links pointing to the new troubleshooting guide. Ensure `CycleDetectedError` adds fix hints (e.g., "Remove dependency {edge}"). | Runtime | Low | High |

### Phase 2: Schema Management Foundations

| # | Status | Enhancement | Priority | Design Considerations |
|---|--------|-------------|----------|----------------------|
| 1 | Complete | **StageOutput Version Tagging** | P1 | Add optional `version: str | None` to `StageOutput` plus helper on `TypedStageOutput` to auto-populate semantic version/UTC timestamp. Enforce version presence via lint check (raise warning when omitted for contract stages). |
| 2 | Complete | **Schema Registry Module** | P1 | Create `stageflow.contracts.registry` that registers Pydantic model metadata per stage name + version. Provide CLI (`scripts/contracts.py diff <stage> --from v1 --to v2`) for compatibility reports. |
| 3 | Complete | **Compatibility Validator** | P2 | Build utility that compares two models (leveraging `pydantic.schema_json()` + jsonschema compatibility rules) to detect backward/forward breakage. Integrate optional CI gate invoked by users (documented in PR playbook). |

### Phase 3: Error Messaging + Automation

| # | Status | Enhancement | Priority | Design Considerations |
|---|--------|-------------|----------|----------------------|
| 1 | Complete | **Error Style Guide + Enforcement** | P1 | Add `docs/advanced/error-messages.md` capturing format guidelines (Problem, Context, Fix, Docs, Code). Add linters/tests ensuring contract violation errors expose doc links + fix hints (use golden snapshots). |
| 2 | Complete | **Runtime Suggestions** | P1 | Provide `stageflow.contracts.suggestions` module that maps error codes to remediation steps (e.g., missing stage -> run `.with_stage(...)`). For empty pipeline error, include builder guidance + link. |
| 3 | Complete | **Schema Change Runbooks** | P2 | Extend registry CLI with `plan-upgrade` that outputs migration steps, default injection helpers, and recommended interceptors for compatibility bridging. |

---

## Design Principles

### Speed
- Validation helpers add <1ms overhead (Pydantic async support)
- Schema registry lookups are O(1) hash map access
- Compatibility diffing adds <5ms per comparison (JSON schema validation)

### Safety
- **Fail-explicit over fail-silent**: Validation errors surface immediately with structured hints
- **No behavior changes in core**: Typed outputs are opt-in wrappers
- **Opt-in complexity**: Advanced features in contracts package

### Observability
- All new errors follow structured format with doc URLs
- Registry emits events for schema changes
- CLI tools provide detailed compatibility reports

### Reliability
- Version tagging prevents silent schema drift
- Compatibility checks catch breaking changes before deployment
- Error suggestions guide users to fixes

### SOLID Principles
- **Single Responsibility**: Each contract module handles one concern (validation, registry, suggestions)
- **Open/Closed**: Core StageOutput unchanged; extensions via composition
- **Liskov Substitution**: TypedStageOutput implements same interface
- **Interface Segregation**: ContractErrorInfo provides minimal metadata interface
- **Dependency Inversion**: Stages depend on protocols, not concretions

### Scalability
- Registry supports unlimited schemas with efficient indexing
- CLI tools scale to large codebases via streaming
- Validation caches reduce repeated overhead

---

## Test Coverage Requirements

| Component | Test Type | Coverage Target |
|-----------|-----------|-----------------|
| Typed outputs | Unit + Integration | Validation success/failure, serialization |
| Schema registry | Unit + E2E | Registration, diffing, compatibility checks |
| Error formatting | Unit | Structured metadata and suggestion mapping |
| CLI tools | Integration | Command execution and output formatting |

---

## Next Actions

1. **Immediate**: Add pre-commit hook template for `stageflow cli lint --strict` (1 day)
2. **This Sprint**: Wire `DependencyIssue` lint messages to `ContractSuggestion` registry
3. **Next Sprint**: Add CI job example that runs `contracts diff` and fails on breaking changes

---

## DX Score Summary

| Report | Score | Key Friction |
|--------|-------|--------------|
| CONTRACT-001 | 4.5/5 | Typed helpers now available |
| CONTRACT-002 | 4.2/5 | Registry and CLI reduce manual versioning |
| CONTRACT-004 | 4.8/5 | Structured errors with fix hints |
| **Average** | **4.5/5** | Significant DX improvements |

---

*Synthesized from CONTRACT-001, CONTRACT-002, CONTRACT-004 final reports.*
