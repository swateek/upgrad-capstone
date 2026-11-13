"""The eval set is frozen (see freeze.lock.yaml for the version). Any change to a frozen file fails here, by name."""

import hashlib

import yaml

from copilot.config import PROJECT_ROOT

PACK = PROJECT_ROOT / "domains" / "procurement"


def test_frozen_eval_files_unchanged():
    lock = yaml.safe_load((PACK / "eval" / "freeze.lock.yaml").read_text())
    changed = [
        rel
        for rel, digest in lock["files"].items()
        if hashlib.sha256((PACK / rel).read_bytes()).hexdigest() != digest
    ]
    assert not changed, (
        f"frozen eval files changed since version {lock['version']}: {changed}. "
        "Gold changes need a version bump and a written reason (docs/results/eval-freeze.md)."
    )


def test_no_new_bid_case_files_outside_the_freeze():
    lock = yaml.safe_load((PACK / "eval" / "freeze.lock.yaml").read_text())
    on_disk = {
        str(p.relative_to(PACK))
        for p in (PACK / "data" / "bid_cases").rglob("*")
        if p.is_file() and p.name != ".DS_Store"
    }
    assert on_disk <= set(lock["files"]), sorted(on_disk - set(lock["files"]))
