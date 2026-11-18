"""The agent is frozen (pack/agent.lock.yaml) after tuning on dev. Any change to a frozen prompt,
policy or agent file fails here, by name, until the version is bumped with a written reason."""

import pytest
import yaml

from customs.config import PROJECT_ROOT
from eval.freeze_agent import LOCK, frozen_files, sha


@pytest.fixture(scope="module")
def lock():
    if not LOCK.exists():
        pytest.skip("agent not frozen yet (plan step 10)")
    return yaml.safe_load(LOCK.read_text(encoding="utf-8"))


def test_frozen_agent_files_unchanged(lock):
    changed = [rel for rel, digest in lock["files"].items() if sha(rel) != digest]
    assert not changed, (
        f"frozen agent files changed since version {lock['version']}: {changed}. "
        "Bump the version and write the reason in docs/results/dev-runs.md."
    )


def test_no_unfrozen_agent_file(lock):
    new = sorted(set(frozen_files()) - set(lock["files"]))
    assert not new, f"agent files added after the freeze: {new}"


def test_lock_points_at_real_files(lock):
    assert all((PROJECT_ROOT / rel).exists() for rel in lock["files"])
