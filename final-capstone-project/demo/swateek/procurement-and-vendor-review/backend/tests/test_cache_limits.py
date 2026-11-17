from fastapi.testclient import TestClient

from copilot.cache import MemoryStore, cache_key, normalize_query


def test_memory_store_ttl_and_windows():
    s = MemoryStore()
    s.set("k", [1, 2], ttl_s=60)
    assert s.get("k") == [1, 2]
    s.set("gone", 1, ttl_s=-1)
    assert s.get("gone") is None
    assert [s.hit("w", 60)[0] for _ in range(3)] == [1, 2, 3]


def test_cache_key_depends_on_normalized_query_and_corpus():
    a = cache_key("d", "by_rule", "hash1", normalize_query("  What is the LIMIT?  "))
    b = cache_key("d", "by_rule", "hash1", normalize_query("what is the limit"))
    c = cache_key("d", "by_rule", "hash2", normalize_query("what is the limit"))
    assert a == b and a != c


def test_rate_limit_returns_429_with_retry_after():
    from copilot.api import app as api

    with TestClient(api.app):
        assert api._limited("rl:test:unit", 2) is None
        assert api._limited("rl:test:unit", 2) is None
        blocked = api._limited("rl:test:unit", 2)
        assert blocked is not None and blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1


def test_trace_mask_scrubs_pii_recursively():
    from copilot.observability.tracing import _mask

    data = {"input": "mail ravi.k@example.com or call 9876543210", "nested": ["PAN ABCDE1234F", 3]}
    out = _mask(data=data)
    assert "example.com" not in out["input"] and "9876543210" not in out["input"]
    assert out["nested"] == ["PAN [REDACTED-PAN]", 3]
