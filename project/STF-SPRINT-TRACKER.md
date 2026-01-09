# Stageflow Sprint Tracker (STF)

**Stream:** Substrate hardening, pipeline composition, interceptors, tool execution  
**Goal:** Realize stageflow2.md vision as extractable module

---

## Sprints (in order)

- [ ] [STF-SPR-001: Pipeline Composition + ContextBag](./STF-SPR-001-pipeline-composition.md)
- [ ] [STF-SPR-002: Auth + Tenancy Interceptors](./STF-SPR-002-auth-tenancy-interceptors.md)
- [x] [STF-SPR-003: Advanced ToolExecutor](./STF-SPR-003-advanced-tool-executor.md) ✅
- [x] [STF-SPR-004: Subpipeline Runs](./STF-SPR-004-subpipeline-runs.md) ✅
- [x] [STF-SPR-005: Testing Harness + Benchmarking](./STF-SPR-005-testing-benchmarking.md) ✅

---

## Gates Produced

| Gate | Sprint | Status |
|------|--------|--------|
| G1: Substrate Foundation | STF-001 | 🔴 Not Started |
| G2: Tenancy Enforcement | STF-002 | 🔴 Not Started |
| G7: Advanced ToolExecutor | STF-003 | 🟢 Complete |
| G8: Subpipeline Runs | STF-004 | 🟢 Complete |
| G9: Testing Harness | STF-005 | 🟢 Complete |

---

## Dependencies on UCM Stream

| STF Sprint | UCM Dependency | Notes |
|------------|----------------|-------|
| STF-003 | UCM-003 | EditOrchestrator uses advanced ToolExecutor |

---

## Related Documents

- [stageflow.md](./stageflow.md) — Authoritative spec
