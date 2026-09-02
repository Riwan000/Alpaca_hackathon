"""Task P1-OPS-3 — the GitHub Actions workflow is well-formed and complete.

- the workflow file parses as YAML
- jobs ``backend``, ``frontend`` and ``db-fresh`` are present
- no PR-run step invokes the smoke selection (``-m smoke`` / ``-m "smoke"``)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_REQUIRED_JOBS = {"backend", "frontend", "db-fresh"}
_SMOKE_SELECTOR = re.compile(r"-m\s+[\"']?\bsmoke\b")


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    assert _WORKFLOW.is_file(), f"missing CI workflow at {_WORKFLOW}"
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _triggers(workflow: dict[str, Any]) -> Any:
    # PyYAML 1.1 parses the bare key `on:` as the boolean True.
    return workflow.get("on", workflow.get(True))


def _all_run_steps(workflow: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run")
            if isinstance(run, str):
                steps.append(run)
    return steps


def test_workflow_parses(workflow: dict[str, Any]) -> None:
    assert isinstance(workflow, dict)
    assert "jobs" in workflow and isinstance(workflow["jobs"], dict)


def test_runs_on_pull_requests(workflow: dict[str, Any]) -> None:
    triggers = _triggers(workflow)
    assert triggers, "workflow declares no `on:` triggers"
    if isinstance(triggers, dict):
        assert "pull_request" in triggers
    else:  # list or scalar form
        assert "pull_request" in (triggers if isinstance(triggers, list) else [triggers])


def test_required_jobs_present(workflow: dict[str, Any]) -> None:
    missing = sorted(_REQUIRED_JOBS - set(workflow["jobs"]))
    assert not missing, f"CI workflow is missing jobs: {missing}"


def test_backend_job_runs_pytest_and_coverage(workflow: dict[str, Any]) -> None:
    backend = workflow["jobs"]["backend"]
    runs = " ".join(
        step.get("run", "") for step in backend.get("steps", []) if isinstance(step.get("run"), str)
    )
    assert "pytest" in runs, "backend job never runs pytest"
    assert "--cov" in runs, "backend job has no coverage gate"


def test_db_fresh_job_migrates_then_seeds(workflow: dict[str, Any]) -> None:
    db_fresh = workflow["jobs"]["db-fresh"]
    runs = [s.get("run", "") for s in db_fresh.get("steps", []) if isinstance(s.get("run"), str)]
    joined = "\n".join(runs)
    assert "alembic" in joined and "upgrade head" in joined, "db-fresh never migrates"
    assert "backend.seed" in joined, "db-fresh never seeds"
    migrate_at = next(i for i, r in enumerate(runs) if "upgrade head" in r)
    seed_at = next(i for i, r in enumerate(runs) if "backend.seed" in r)
    assert migrate_at < seed_at, "db-fresh seeds before it migrates"


def test_smoke_selection_never_runs(workflow: dict[str, Any]) -> None:
    for run in _all_run_steps(workflow):
        assert not _SMOKE_SELECTOR.search(run), f"a CI step runs the smoke selection: {run!r}"


def test_smoke_is_explicitly_deselected_somewhere(workflow: dict[str, Any]) -> None:
    """At least the backend pytest step spells out `-m "not smoke"`."""
    joined = "\n".join(_all_run_steps(workflow))
    assert 'not smoke' in joined, "no step explicitly deselects smoke tests"
