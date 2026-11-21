"""The safety suite's offline checks (plan §7): guard refusals and look-alikes, PII masking,
planted claims blocked by the verifier, and (with the corpus) the planted-line structure."""

import pytest

from customs.config import PROJECT_ROOT
from eval import safety

HAS_CORPUS = (PROJECT_ROOT / "data" / "chunks" / "documents.jsonl").exists()


@pytest.mark.parametrize("check", safety.check_guard(), ids=lambda c: c.name[:60])
def test_guard(check):
    assert check.passed, check.detail


@pytest.mark.parametrize(
    "check", [*safety.check_pii(), *safety.check_banned()], ids=lambda c: c.name[:60]
)
def test_pii_and_banned(check):
    assert check.passed, check.detail


@pytest.mark.skipif(not HAS_CORPUS, reason="corpus not built (CI)")
def test_planted_lines_never_become_sources():
    for check in safety.check_planted():
        assert check.passed, f"{check.name}: {check.detail}"
