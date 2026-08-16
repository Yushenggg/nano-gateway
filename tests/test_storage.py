import pytest
from pathlib import Path
from nanogateway.storage import Storage


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test.db")


def test_init_creates_db(tmp_db):
    storage = Storage(tmp_db)
    assert Path(tmp_db).exists()


def test_log_span(tmp_db):
    storage = Storage(tmp_db)
    storage.log_span(
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        latency_ms=250.5,
        status_code=200,
        user_id="user-123",
    )
    traces = storage.get_traces()
    assert len(traces) == 1
    assert traces[0]["model"] == "gpt-4"
    assert traces[0]["input_tokens"] == 100
    assert traces[0]["output_tokens"] == 50
    assert traces[0]["user_id"] == "user-123"


def test_get_traces_with_limit(tmp_db):
    storage = Storage(tmp_db)
    for i in range(5):
        storage.log_span(model=f"model-{i}")
    traces = storage.get_traces(limit=3)
    assert len(traces) == 3


def test_get_traces_filter_by_user(tmp_db):
    storage = Storage(tmp_db)
    storage.log_span(model="gpt-4", user_id="user-1")
    storage.log_span(model="gpt-4", user_id="user-2")
    storage.log_span(model="gpt-4", user_id="user-1")

    traces = storage.get_traces(user_id="user-1")
    assert len(traces) == 2
    assert all(t["user_id"] == "user-1" for t in traces)


def test_get_traces_empty(tmp_db):
    storage = Storage(tmp_db)
    traces = storage.get_traces()
    assert traces == []


def test_get_traces_pagination(tmp_db):
    storage = Storage(tmp_db)
    for i in range(7):
        storage.log_span(model=f"model-{i}")

    page0 = storage.get_traces(limit=3, offset=0)
    page1 = storage.get_traces(limit=3, offset=3)
    page2 = storage.get_traces(limit=3, offset=6)
    assert [t["id"] for t in page0 + page1 + page2] == [
        t["id"] for t in storage.get_traces(limit=20, offset=0)
    ]
    assert len(page0) == 3
    assert len(page1) == 3
    assert len(page2) == 1
    assert storage.count_traces() == 7


def test_get_trace_by_id(tmp_db):
    storage = Storage(tmp_db)
    storage.log_span(model="gpt-4", user_id="user-1")
    span_id = storage.get_traces()[0]["id"]

    trace = storage.get_trace(span_id)
    assert trace is not None
    assert trace["model"] == "gpt-4"
    assert storage.get_trace("does-not-exist") is None


def test_get_sessions_pagination(tmp_db):
    storage = Storage(tmp_db)
    for i in range(3):
        storage.log_span(model="gpt-4", session_id=f"sess-{i}")
    storage.log_span(model="gpt-4", session_id="sess-0")

    sessions = storage.get_sessions(limit=2, offset=0)
    assert len(sessions) == 2
    rest = storage.get_sessions(limit=2, offset=2)
    assert len(rest) == 1
    assert storage.count_sessions() == 3
    assert storage.count_sessions(query="sess-1") == 1
    assert storage.get_sessions(query="sess-1")[0]["trace_count"] == 1
    assert storage.get_sessions()[0]["trace_count"] == 2


def test_get_stats(tmp_db):
    storage = Storage(tmp_db)
    storage.log_span(model="gpt-4", user_id="u1", session_id="s1", latency_ms=100)
    storage.log_span(model="gpt-4", user_id="u1", session_id="s1", latency_ms=300)
    storage.log_span(model="gpt-3", user_id="u2", session_id="s2", latency_ms=200)

    stats = storage.get_stats()
    assert stats["total"] == 3
    assert stats["models"] == 2
    assert stats["users"] == 2
    assert stats["sessions"] == 2
    assert stats["avg_latency"] == 200.0
