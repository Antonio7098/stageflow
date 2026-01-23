# ROUTE Stage Routing Logic & Reliability Tracker

## Scope
Synthesizes ROUTE-001, ROUTE-005, ROUTE-006, ROUTE-007 findings covering confidence threshold calibration, multi-criteria routing, A/B testing integration, and routing loop detection.

---

## Evidence Summary

| Report | Core Claim | Code Evidence | Verdict |
|--------|------------|---------------|---------|
| ROUTE-001 | Social engineering bypasses escalation routing | Custom `ConfidenceRouterStage` implementation - no built-in routing. Uppercase urgency keywords not recognized. | **Confirmed gap** |
| ROUTE-001 | Recovery success rate only 33% | No built-in circuit breaker or retry patterns in ROUTE stages. | **Confirmed gap** |
| ROUTE-005 | Multi-criteria routing works correctly | 100% success rate across 68 tests. Framework provides solid foundation. | **Confirmed strength** |
| ROUTE-005 | No built-in weighted scoring | Must implement custom `WeightedScoreCalculator`. | **Confirmed gap** |
| ROUTE-006 | A/B testing achievable but lacks first-class support | No built-in `ABTestStage`. Traffic splitting requires custom implementation. | **Confirmed gap** |
| ROUTE-007 | No built-in loop detection in ROUTE stages | Must implement custom `LoopDetector`. Framework has no native loop prevention. | **Confirmed gap** |
| ROUTE-007 | False positive in semantic loop detection | Context hash similarity threshold (0.9) too low for empty contexts. | **Confirmed bug** |

---

## Consolidated Findings

### Critical Issues (P0)

**None** - All issues are reliability/DX gaps, not breaking bugs.

### High-Severity Issues (P1)

| ID | Issue | Impact | Evidence |
|----|-------|--------|----------|
| BUG-054 | False positive loop detection with similar context hashes | Incorrect loop termination | ROUTE-007: Threshold 0.9 too low |

### Medium-Severity Issues

| ID | Issue | Impact |
|----|-------|--------|
| BUG-001 | Social engineering bypasses escalation routing | Incorrect routing for urgency patterns |
| - | Recovery success rate only 33% | Limited resilience patterns |

### DX Issues

| ID | Issue | Severity |
|----|-------|----------|
| DX-056 | `create_pipeline_context` function does not exist | Medium |
| DX-058 | StageInputs user_id access pattern unclear | Medium |
| DX-059 | ContextSnapshot API complexity for newcomers | Medium |

### Strengths

| ID | Strength | Evidence |
|----|----------|----------|
| STR-072 | Multi-criteria routing core functionality works correctly | 100% success rate, 12,155 rps throughput |
| STR-073 | Hash-based consistent bucketing for A/B testing | Deterministic user assignment |
| STR-074 | Traffic split accuracy within tolerance | 50/50, 80/20, 90/10 all pass |
| STR-075 | Loop detection mechanism works for direct cycles | Custom implementation successful |
| STR-076 | State reset functionality works correctly | Between-run isolation |
| STR-077 | Max iterations enforcement prevents runaway pipelines | Configurable limits |

---

## Implementation Plan

### Phase 1: Bug Fixes (Immediate)

| # | Status | Action | Priority | Effort | Impact |
|---|--------|--------|----------|--------|--------|
| 1 | Not Started | **Fix semantic loop detection threshold** - Increase from 0.9 to 0.99 for empty context scenarios | P1 | Low | High |
| 2 | Not Started | **Expand escalation keywords** - Add uppercase detection and social engineering patterns to routing logic | P1 | Low | Medium |

### Phase 2: Documentation & DX (Short Term)

| # | Status | Action | Owner | Effort |
|---|--------|--------|-------|--------|
| 1 | Not Started | **Confidence Threshold Guide** - Add `docs/advanced/routing-confidence.md` with threshold tuning, calibration drift detection | Docs | Low |
| 2 | Not Started | **A/B Testing Patterns** - Document traffic splitting, consistent bucketing, experiment tracking in `docs/examples/ab-testing.md` | Docs | Low |
| 3 | Not Started | **Loop Detection Patterns** - Add routing loop prevention guide to `docs/advanced/routing-loops.md` | Docs | Low |
| 4 | Not Started | **Fix function name documentation** - Update docs to use `create_test_stage_context` instead of `create_pipeline_context` | Docs | Low |
| 5 | Not Started | **User ID access pattern** - Document `ctx.snapshot.run_id.user_id` access in `docs/api/context-submodules.md` | Docs | Low |

### Phase 3: Core Runtime Enhancements (Medium Term)

| # | Status | Enhancement | Priority | Design |
|---|--------|-------------|----------|--------|
| 1 | Not Started | **Built-in Loop Detection** | P1 | Add optional `loop_detection_threshold` and `max_iterations` to ROUTE stages. Emit `route.loop_detected` event. |
| 2 | Not Started | **Circuit Breaker Integration** | P1 | Add `CircuitBreakerInterceptor` for ROUTE stage resilience. Configurable failure threshold and recovery timeout. |
| 3 | Not Started | **Calibration Drift Detection** | P2 | Track confidence distribution over time. Emit `route.calibration_drift` when distribution shifts. |

### Phase 4: Stageflow Plus Components (Medium Term)

| ID | Status | Component | Type | Priority | Use Case |
|----|--------|-----------|------|----------|----------|
| IMP-001 | Not Started | `ConfidenceCalibrationStage` | Stagekind | P1 | Calibration tracking and threshold optimization |
| IMP-077 | Not Started | `WeightedRouteStage` | Stagekind | P2 | Configurable multi-criteria routing |
| IMP-078 | Not Started | `FallbackRouteStage` | Stagekind | P1 | Automatic failover routing with circuit breaker |
| IMP-079 | Not Started | `ABTestStage` | Stagekind | P2 | Built-in A/B testing with traffic splitting |
| IMP-080 | Not Started | Built-in loop detection for ROUTE stages | Core | P1 | Native loop prevention |
| - | Not Started | `ThresholdOptimizer` | Utility | P1 | Production threshold tuning |
| - | Not Started | `CircuitBreakerMiddleware` | Integration | P1 | Resilience patterns |
| - | Not Started | `ExperimentTracker` | Utility | P2 | A/B test metrics and tracking |

---

## Design Principles

### Speed
- Loop detection adds <1ms overhead (hash comparison)
- Weighted scoring is O(n) where n = number of criteria
- A/B bucketing is O(1) via SHA-256 hash

### Safety
- **Max iterations as safeguard**: Prevent runaway routing loops
- **Fail-explicit**: Emit events on loop detection, calibration drift
- **Deterministic bucketing**: Same user always gets same variant

### Observability
- `route.loop_detected` event with loop type, iteration count
- `route.calibration_drift` event with distribution metrics
- `route.decision` event with confidence, selected route, criteria weights

### Reliability
- Circuit breaker prevents cascade failures
- Fallback routes for degraded operation
- State reset between independent runs

### SOLID Principles
- **Single Responsibility**: Each ROUTE stage handles one routing concern
- **Open/Closed**: Loop detection via optional parameters, not code changes
- **Liskov Substitution**: All ROUTE stages implement `Stage` protocol
- **Interface Segregation**: Minimal routing interface (route + confidence)
- **Dependency Inversion**: Routing logic depends on abstractions (criteria weights), not concretions

### Scalability
- Consistent bucketing scales horizontally (stateless)
- Loop detection state is per-run, not global
- Multi-criteria routing is parallelizable

---

## Proposed API: Built-in Loop Detection

```python
# Current approach (manual)
class MyRouterStage:
    name = "router"
    kind = StageKind.ROUTE
    
    def __init__(self):
        self._loop_detector = LoopDetector(threshold=3)
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        route = self._compute_route(ctx)
        if self._loop_detector.is_loop(route, ctx):
            return StageOutput.cancel(reason="Loop detected")
        return StageOutput.ok(route=route, confidence=0.9)

# Suggested approach (built-in)
class MyRouterStage:
    name = "router"
    kind = StageKind.ROUTE
    max_iterations: int = 100
    loop_detection_threshold: int = 3
    loop_detection_mode: str = "direct"  # direct, indirect, semantic, all
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        route = self._compute_route(ctx)
        return StageOutput.ok(route=route, confidence=0.9)
        # Framework handles loop detection automatically
```

---

## Test Coverage Requirements

| Component | Test Type | Coverage Target |
|-----------|-----------|-----------------|
| Loop detection threshold | Unit | No false positives for empty contexts |
| Escalation keywords | Unit | Uppercase and urgency patterns detected |
| Circuit breaker | Integration | Opens after threshold, recovers after timeout |
| A/B bucketing | Integration | Consistent assignment across sessions |
| Multi-criteria routing | E2E | Weighted scoring produces correct routes |

---

## Next Actions

1. **Immediate**: Fix semantic loop detection threshold (1 day)
2. **This Sprint**: Add escalation keyword patterns (1 day)
3. **This Sprint**: Create `docs/advanced/routing-loops.md` (1 day)
4. **Next Sprint**: Implement `FallbackRouteStage` prototype
5. **Backlog**: Design built-in loop detection API

---

## DX Score Summary

| Report | Score | Key Friction |
|--------|-------|--------------|
| ROUTE-001 | 4.0/5 | Missing threshold configuration examples |
| ROUTE-005 | 3.8/5 | Outdated function names in docs |
| ROUTE-006 | 3.5/5 | No A/B testing patterns documented |
| ROUTE-007 | 3.5/5 | ContextSnapshot API complexity |
| **Average** | **3.7/5** | Routing patterns underdocumented |

---

## Performance Benchmarks

| Pipeline | Avg Latency | Throughput | Notes |
|----------|-------------|------------|-------|
| Multi-criteria routing | 0.08ms | 12,155 rps | Excellent |
| A/B bucketing | 8.80ms P95 | 200 req/20 concurrent | Good |
| Loop detection | <1ms | N/A | Minimal overhead |

---

*Synthesized from ROUTE-001, ROUTE-005, ROUTE-006, ROUTE-007 final reports.*
