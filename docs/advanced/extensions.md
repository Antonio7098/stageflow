# Extensions

This page documents the current extension model in stageflow.

## Current model

Stageflow uses typed extension bundles via `ExtensionBundle` and `ContextSnapshot[T]`.

```python
from dataclasses import dataclass
from stageflow.context import ContextSnapshot, ExtensionBundle, RunIdentity
from uuid import uuid4

@dataclass(frozen=True)
class SkillsExtension(ExtensionBundle):
    active_skill_ids: list[str]
    current_level: str | None = None

snapshot = ContextSnapshot[SkillsExtension](
    run_id=RunIdentity(pipeline_run_id=uuid4()),
    extensions=SkillsExtension(active_skill_ids=["python"], current_level="intermediate"),
)
```

## Access pattern

```python
async def execute(self, ctx):
    ext = ctx.snapshot.extensions
    if ext and "python" in ext.active_skill_ids:
        ...
```

## Registry utilities

`stageflow.extensions` exposes a global `ExtensionRegistry` and helpers for optional, app-level registries.
Use:
- `ExtensionRegistry.register(name, type)`
- `ExtensionRegistry.get(name)`

Do not rely on non-existent methods such as `is_registered()` or `get_type()`.

## Notes

- Prefer typed extension bundles over raw dict payloads.
- `ContextSnapshot` is initialized with `run_id=RunIdentity(...)`, not flat `pipeline_run_id=...` kwargs.
