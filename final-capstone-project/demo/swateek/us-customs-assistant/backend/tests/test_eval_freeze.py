"""The eval set is frozen (pack/eval/freeze.lock.yaml gives the version). Any change to a frozen
file, its gold, or a signed-off rule table fails here, by name."""

import hashlib

import pytest
import yaml

from customs.config import PROJECT_ROOT

EVAL = PROJECT_ROOT / "pack" / "eval"
LOCK = EVAL / "freeze.lock.yaml"


@pytest.fixture(scope="module")
def lock():
    if not LOCK.exists():
        pytest.skip("eval set not frozen yet (plan step 5: freeze after the hand-check)")
    return yaml.safe_load(LOCK.read_text(encoding="utf-8"))


def test_frozen_eval_files_unchanged(lock):
    changed = [
        rel
        for rel, digest in lock["files"].items()
        if hashlib.sha256((EVAL / rel).read_bytes()).hexdigest() != digest
    ]
    assert not changed, (
        f"frozen eval files changed since version {lock['version']}: {changed}. "
        "Gold or rule changes need a version bump and a written reason (docs/results/eval-freeze.md)."
    )


def test_every_rule_table_is_covered(lock):
    tables = {f"../rules/{p.name}" for p in (PROJECT_ROOT / "pack" / "rules").glob("*.yaml")}
    assert tables <= set(lock["files"]), sorted(tables - set(lock["files"]))


def test_frozen_counts(lock):
    assert lock["queries"] == 80 and lock["corrections"] == 6
