from fastapi.testclient import TestClient

from customs.ingest.pii import scrub
from customs.observability.tracing import Tracer, mask


def test_scrub_us_identifiers():
    text = (
        "Mail jane.doe@example.com or call (415) 555-0123; SSN 123-45-6789; "
        "passport number 123456789."
    )
    out, found = scrub(text)
    assert "example.com" not in out and "555-0123" not in out and "6789" not in out
    assert "123456789" not in out
    assert set(found) == {"EMAIL", "PHONE", "SSN", "PASSPORT"}


def test_scrub_leaves_regulatory_numbers_alone():
    text = "19 CFR 148.33(a), HTSUS 9816.00.20, 26 USC 5761, $13.50 per proof gallon, 750 ml"
    assert scrub(text) == (text, scrub(text)[1])
    assert not scrub(text)[1]


def test_trace_mask_is_recursive():
    data = {"q": "my email is a@b.co", "turns": ["call 212-555-0199"]}
    out = mask(data=data)
    assert "a@b.co" not in str(out) and "555-0199" not in str(out)


def test_tracing_off_without_keys(settings):
    tracer = Tracer(settings)
    assert tracer.enabled is False
    with tracer.run("s1", "q", ["t"]) as run:
        assert run.callbacks == [] and run.url is None


def test_health_needs_no_upgrad_call():
    from customs.api.app import app

    body = TestClient(app).get("/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "planner"
