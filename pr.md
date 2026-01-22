# Stageflow Pull Request Playbook

Use this checklist for every Stageflow pull request. Items are mandatory unless marked optional.

## 1. Prep Work
1. Ensure you are on the correct branch (`git status -sb`). Branch names follow `feat/<summary>` or `fix/<issue>`.
2. Activate the repo’s virtualenv (`source .venv/bin/activate`) and install dev deps once via `pip install -e .[dev]` (already in `pyproject.toml`).

## 2. Tests & Lint (Python-only repo)
Run from repo root:

```bash
source .venv/bin/activate
ruff check
python -m pytest
```

If you touched docs-only content, still run these quickly to catch style drift. For targeted debugging, you may run individual test modules, but a full run is required before the PR is marked ready.

## 3. Documentation Cross-Check
1. Update any impacted files under `docs/` (e.g., `docs/advanced/testing.md`, `docs/advanced/subpipelines.md`, `docs/api/context-submodules.md`).
2. Verify examples and API signatures (Pipeline, ContextSnapshot, helpers) match code.
3. Link new runtime/developer experience features in both docs and `CORE-Summary` notes when relevant.

## 4. Version & Release Notes
- Stageflow ships from `pyproject.toml`. Bump `project.version` whenever public APIs, helpers, or docs with user-visible behavior change.
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> afe8bfb (chore: bump version to v0.6.0)
- Run `python scripts/log_helper.py add` to append a changelog entry (stores data in `changelog.json`).
- Run `python scripts/check_version_sync.py` (add `--require-tag` when cutting a release) to confirm `pyproject.toml`, `changelog.json`, and docs match.
- Update `docs/RELEASE_NOTES.md` (or the current sprint summary) to describe the change set. Mention UUID/memory/compression additions when applicable.

## 5. Final Validation
1. `git status -sb` → only intentional changes staged.
2. Review `git diff` for unintended edits (especially sprint docs under `ops/24-testers`).
3. Run `python -m pytest` + `ruff check` one more time if you touched files after the last run.

## 6. Commit & PR Description
1. Use conventional commits (`feat: uuid telemetry`, `fix: docs core summary`, etc.).
2. Push branch: `git push -u origin <branch>`.
3. PR body must include:
   - Summary of changes (helpers, docs, tests).
   - Test + lint commands/output (can be summarized, e.g., “`python -m pytest` / `ruff check`”).
   - Docs/CORE summary updates.
   - Version bump rationale (if any) and release impact.

## 7. Post-Merge
1. After approval + merge, pull `main` and confirm changes.
2. Tag the repo if a release bump occurred (`git tag vX.Y.Z && git push origin vX.Y.Z`).
3. Ensure CI publish workflows succeed; update CORE summary if necessary.

## 8. Failure Handling
- If tests/lint fail locally or in CI, fix immediately and rerun commands before pushing.
- For release failures after tagging, fix the issue, bump version again if needed, and repeat tagging.

Keeping this playbook up to date ensures deterministic Stageflow releases. Update this document when the process changes.
