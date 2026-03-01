# Beta Testing Fix Report 001

## Metadata
- Date: 2026-02-28
- Branch: `fix/beta-tier3-tier4-report-001`
- Scope: Tier 3 API reference + Tier 4 advanced docs
- Source reports:
  - `24-hour-stageflow/reports/tier-3-api-reference-report.md`
  - `24-hour-stageflow/runs/tier_4_advanced/tier_4_advanced-FINAL-REPORT.md`

## Tier 3 Work
Read and processed all checklist final reports:
- `DOC-020` ... `DOC-035` under `24-hour-stageflow/runs/tier_3_api_reference/*/DOC-*-FINAL-REPORT.md`

### Fixes applied
- Replaced broken API reference pages:
  - `docs/api/context-submodules.md`
  - `docs/api/testing.md`
  - `docs/api/wide-events.md`
- Rewrote/corrected drifted API docs:
  - `docs/api/context.md`, `docs/api/core.md`, `docs/api/helpers.md`, `docs/api/pipeline.md`, `docs/api/projector.md`, `docs/api/protocols.md`, `docs/api/observability.md`
- Fixed auth examples:
  - `docs/api/auth.md` (`validator` -> `jwt_validator`)
- Framework compatibility improvements for reported helper drift:
  - `stageflow/helpers/__init__.py` now exports `ViolationType`, `GuardrailCheck`, `ContentLengthCheck`
  - `stageflow/helpers/streaming.py` adds `threshold` alias to `BackpressureMonitor`
  - `stageflow/helpers/analytics.py` adds `sink` and `flush_interval` aliases to `BufferedExporter`
  - `stageflow/__init__.py` exports `PipelineBuilder`

### Tier 3 verification reruns
Executed originating scripts/commands from tier folders:
- DOC-023: `exact_run.py`, `provider_test.py`, `streaming_test.py`, `variation_tests.py`
- DOC-028: `exact-run.py`, `variation-runs.py`
- DOC-029: `exact-run.py`, `variation-runs.py`
- DOC-030: `tests/test_doc_example.py` (legacy script still reproduces old ContextSnapshot arg usage)
- DOC-031: `exact-run.py`, `variation-runs.py`, `error-tests.py`
- DOC-032: `results/test_exact.py`
- DOC-022/024/026/033/035: equivalent direct API checks run via `python3` inline validation

## Tier 4 Work
Detected tier-level final report and repeated process:
- Read all checklist reports under `24-hour-stageflow/runs/tier_4_advanced/*/DOC-*-FINAL-REPORT.md`

### Fixes applied
- Added reference/spec disclaimers where features are documented but not runtime-built-ins:
  - `docs/advanced/checkpointing.md`
  - `docs/advanced/routing-confidence.md`
  - `docs/advanced/routing-loops.md`
  - `docs/advanced/saga-pattern.md`
  - `docs/advanced/tool-sandboxing.md`
  - `docs/advanced/chunking.md`
- Fixed concrete API mismatches:
  - `docs/advanced/subpipelines.md` (`fork_child` -> `fork`, `topology_override` -> `topology`)
  - `docs/advanced/custom-interceptors.md` (`sink` -> `exporter`)
  - `docs/advanced/hardening.md` (`compression_ratio` -> `ratio`)
  - `docs/advanced/idempotency.md` (`v0.8.1` -> `v0.9.0`)
  - `docs/advanced/guard-security.md` (`guardrail.decision` -> `guardrail.violations_detected`, imports adjusted)
  - `docs/advanced/retry-backoff.md` (`run_with_retry` references removed, `StageOutput.retry` example updated)
  - `docs/advanced/composition.md` syntax/code-block and streaming snippet fixes
  - `docs/advanced/context-management.md`, `docs/advanced/knowledge-verification.md` switched unsafe `ctx.event_sink.try_emit` patterns to `ctx.try_emit_event`
  - `docs/advanced/testing.md` CLI command path and streaming snippets corrected
  - `docs/advanced/extensions.md` rewritten to typed `ExtensionBundle` model
- Fixed broken error doc anchors used in runtime suggestions:
  - `stageflow/contracts/suggestions.py`
  - `docs/advanced/error-messages.md`

### Tier 4 verification reruns
Executed all available origin scripts:
- DOC-037: `test_assembler.py`, `test_fixed_size.py`, `test_semantic.py`, `test_stageflow_imports.py`
- DOC-039: `test_snippets.py`
- DOC-040: `results/exact-run.py`, `results/variation-runs.py`
- DOC-041: `test_errors.py` (now prints corrected anchor URLs)
- DOC-043: `results/exact-run.py`, `results/variation-runs.py` (legacy scripts intentionally validate old dict/registry API and continue to show old-fail behavior)
- DOC-044: `results/exact-run.py`, `results/variation-runs.py`
- DOC-047: `results/test_docs_examples.py`
- DOC-050: `results/exact-run.py`
- DOC-053: `results/exact-run-compression.py`, `results/exact-run-streaming.py`, `results/exact-run-testing.py`, `results/exact-run-uuid-memory.py`

## Residual notes
- Some origin scripts encode pre-fix expectations (especially DOC-030, DOC-043, DOC-053) and still print historical mismatch findings; these were rerun as requested to verify provenance.
- Primary delivery in this pass is documentation alignment and low-risk compatibility improvements in helper exports/signatures.
