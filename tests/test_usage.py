"""Usage tracking: one chat_log row per tracked turn, anonymous visitor ids, token-protected admin views."""
from __future__ import annotations

import pytest

from tests.test_guided import _make_client, _new_session


@pytest.fixture()
def tracked(tmp_path_factory):
    main, client = _make_client(tmp_path_factory.mktemp("usage"), "mock")
    main.settings.admin_token = "test-token"
    return main, client


AUTH = {"Authorization": "Bearer test-token"}


def _rows(main):
    return [dict(r) for r in main.db.conn.execute("SELECT * FROM chat_log ORDER BY id")]


def test_chat_turn_is_logged_once_and_response_is_unchanged(tracked):
    main, client = tracked
    sid = _new_session(client)
    r = client.post("/api/chat", json={"session_id": sid, "message": "I love vanilla, budget 400"},
                    headers={"user-agent": "UA-1", "x-forwarded-for": "203.0.113.7:51234"})
    assert r.status_code == 200 and "reply" in r.json() and r.json()["session_id"] == sid
    rows = _rows(main)
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == sid and row["user_text"] == "I love vanilla, budget 400"
    assert len(row["visitor_id"]) == 12 and row["latency_ms"] >= 0 and row["endpoint"] == "/api/chat"
    assert "203.0.113.7" not in str(row)


def test_untracked_endpoints_log_nothing(tracked):
    main, client = tracked
    sid = _new_session(client)
    client.get("/api/health")
    client.post("/api/events", json={"session_id": sid, "name": "x", "props": {}})
    assert _rows(main) == []


def test_visitor_id_is_stable_per_browser_and_ignores_the_port(tracked):
    main, client = tracked
    sid = _new_session(client)
    for ua, xff in (("UA-1", "203.0.113.7:51234"), ("UA-1", "203.0.113.7:60001"), ("UA-2", "203.0.113.7:60001")):
        client.post("/api/chat", json={"session_id": sid, "message": "fresh"},
                    headers={"user-agent": ua, "x-forwarded-for": xff})
    ids = [r["visitor_id"] for r in _rows(main)]
    assert ids[0] == ids[1] and ids[2] != ids[0]


def test_admin_views_need_the_token_and_count_correctly(tracked):
    main, client = tracked
    assert client.get("/api/admin/usage").status_code == 401
    assert client.get("/api/admin/conversations").status_code == 401
    sid = _new_session(client)
    client.post("/api/guide/start", json={"session_id": sid}, headers={"user-agent": "UA-1"})
    client.post("/api/chat", json={"session_id": sid, "message": "I love vanilla, budget 400"},
                headers={"user-agent": "UA-1"})
    u = client.get("/api/admin/usage?days=1", headers=AUTH).json()
    assert u["visitors"] == 1 and u["sessions"] == 1 and u["messages"] == 1 and u["guided_started"] == 1
    assert u["by_day"] and u["by_day"][0]["messages"] == 1
    c = client.get("/api/admin/conversations?days=1", headers=AUTH).json()["conversations"]
    assert len(c) == 1 and c[0]["session_id"] == sid and c[0]["message_count"] == 1
    assert [t["user"] for t in c[0]["turns"]] == ["[guided: start]", "I love vanilla, budget 400"]


def test_tracking_failure_never_breaks_the_reply(tracked, monkeypatch):
    main, client = tracked
    sid = _new_session(client)

    def boom(**_):
        raise RuntimeError("disk full")

    monkeypatch.setattr(main.db, "add_chat_log", boom)
    r = client.post("/api/chat", json={"session_id": sid, "message": "fresh"})
    assert r.status_code == 200 and "reply" in r.json()
