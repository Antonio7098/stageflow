# Contract Hardening Tracker

Branch: `chore/contract-tracker`
Last updated: 2026-01-22

## Scope
Summarize CONTRACT-001/002/004 findings, capture current evidence from the repository, and outline an implementation plan covering schema validation, evolution, and error messaging.

## Evidence Summary

| Contract | Recommendation | Repo Evidence | Status |
|----------|----------------|---------------|--------|
| CONTRACT-001 | Typed StageOutput validation + docs | `StageOutput` is a frozen dataclass with an untyped `data: dict[str, Any]` and no validation hooks @stageflow/core/stage_output.py#35-115. Grepping repo for "Pydantic" shows no stage/docs integration outside projector docs (search result limited to `docs/api/projector.md`). | Confirmed gap |
| CONTRACT-002 | Schema versioning/registry/compatibility | Same `StageOutput` has no `version` field or schema metadata. No schema registry modules found. | Confirmed gap |
| CONTRACT-004 | Structured, actionable contract violation errors | `PipelineValidationError` only stores `message` and `stages`; `CycleDetectedError` is the only structured child. Other errors (e.g., empty pipeline) surface terse strings via raising site in `pipeline.Pipeline.build()`. No doc links or suggestions exist. | Confirmed gap |

## Implementation Plan

### Phase 1 – Immediate DX Wins
1. **Typed Output Helper + Docs**
   - Add `stageflow.contracts.TypedStageOutput` that wraps a Pydantic `BaseModel` (optional dependency) and validates `StageOutput.ok(...)` payloads.
   - Provide synchronous + async helper for validation and serialization.
   - Document patterns in `docs/guides/stages.md` + `docs/advanced/testing.md` with migration examples and strict/coerce guidance.
2. **Structured Error Metadata**
   - Introduce `ContractErrorInfo` dataclass (code, summary, fix_hint, doc_url, context dict) and update `PipelineValidationError`, `DependencyIssue`, etc., to populate it.
   - Add doc links pointing to the new troubleshooting guide.
   - Ensure `CycleDetectedError` adds fix hints (e.g., "Remove dependency {edge}" ).

### Phase 2 – Schema Management Foundations
1. **StageOutput Version Tagging**
   - Add optional `version: str | None` to `StageOutput` plus helper on `TypedStageOutput` to auto-populate semantic version/UTC timestamp.
   - Enforce version presence via lint check (raise warning when omitted for contract stages).
2. **Schema Registry Module**
   - Create `stageflow.contracts.registry` that registers Pydantic model metadata per stage name + version.
   - Provide CLI (`scripts/contracts.py diff <stage> --from v1 --to v2`) for compatibility reports.
3. **Compatibility Validator**
   - Build utility that compares two models (leveraging `pydantic.schema_json()` + jsonschema compatibility rules) to detect backward/forward breakage.
   - Integrate optional CI gate invoked by users (documented in PR playbook).

### Phase 3 – Error Messaging + Automation
1. **Error Style Guide + Enforcement**
   - Add `docs/advanced/error-messages.md` capturing format guidelines (Problem, Context, Fix, Docs, Code).
   - Add linters/tests ensuring contract violation errors expose doc links + fix hints (use golden snapshots).
2. **Runtime Suggestions**
   - Provide `stageflow.contracts.suggestions` module that maps error codes to remediation steps (e.g., missing stage -> run `.with_stage(...)`).
   - For empty pipeline error, include builder guidance + link.
3. **Schema Change Runbooks**
   - Extend registry CLI with `plan-upgrade` that outputs migration steps, default injection helpers, and recommended interceptors for compatibility bridging.

### Deliverables
- New helpers (`TypedStageOutput`, registry, compatibility APIs).
- Updated docs & PR playbook (release discipline, schema docs standard).
- Enhanced error classes with structured metadata + doc links.
- Tracking tests for typed outputs, registry diffing, and error formatting.

## Implementation Status

### Phase 1 – Immediate DX Wins ✅
- **Typed Output Helper + Docs**
  - Implemented `stageflow.contracts.TypedStageOutput` with sync/async validation, version factories, and registry registration.
  - Updated `docs/guides/stages.md` with usage examples and versioning guidance.
- **Structured Error Metadata**
  - Added `ContractErrorInfo` dataclass and integrated into `PipelineValidationError`, `CycleDetectedError`, and `PipelineBuilder` validation.
  - Populated default suggestions in `stageflow.contracts.suggestions` with fix steps and doc URLs.

### Phase 2 – Schema Management Foundations ✅
- **StageOutput Version Tagging**
  - Added optional `version` field to `StageOutput` and all factory methods; added `with_version` helper.
  - Tests cover version propagation and immutability.
- **Schema Registry Module**
  - Implemented `stageflow.contracts.registry` with registration, retrieval, listing, and compatibility diffing.
  - Added `clear()` helper for test isolation.
- **CLI Tooling**
  - Created `scripts/contracts.py` with `list`, `diff`, and `plan-upgrade` subcommands.
  - Integrated `contracts` subcommand into `stageflow.cli` that forwards to the script.
  - Updated `docs/advanced/testing.md` with CLI workflows and lint integration notes.

### Phase 3 – Error Messaging + Automation ✅
- **Error Style Guide + Enforcement**
  - Added `docs/advanced/error-messages.md` defining problem/context/fix/docs/code template.
  - Created unit tests for `ContractErrorInfo`, `ContractSuggestion`, and `ContractRegistry`.
- **Runtime Suggestions**
  - `ContractSuggestion` registry maps error codes to remediation steps and doc URLs.
  - `PipelineValidationError` and `DependencyIssue` now surface structured metadata.
- **Schema Change Runbooks**
  - `plan-upgrade` CLI emits markdown runbooks enriched with suggestion steps.

## Deliverables Completed
- ✅ New helpers (`TypedStageOutput`, registry, compatibility APIs).
- ✅ Updated docs (`stages.md`, `testing.md`, `error-messages.md`).
- ✅ Enhanced error classes with structured metadata + doc links.
- ✅ Tracking tests for typed outputs, registry diffing, and error formatting.
- ✅ CLI commands (`list`, `diff`, `plan-upgrade`) and lint integration.

## Next Steps
- All tracker deliverables are complete. Optional follow-ups:
  1. Add pre-commit hook template for `stageflow cli lint --strict`.
  2. Wire `DependencyIssue` lint messages to `ContractSuggestion` registry for richer suggestions.
  3. Add CI job example that runs `contracts diff` and fails on breaking changes.
