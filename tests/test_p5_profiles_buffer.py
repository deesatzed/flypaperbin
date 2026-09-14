"""P5 — Awareness profiles & ephemeral buffer."""

from __future__ import annotations

import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from flypaper.serve import AppState, make_handler
from flypaper.store import Store
from flypaper import watch as watchmod


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "p5.db")
    yield s
    s.close()


def _set(store, profile, **kw):
    fields = {"profile": profile, **kw}
    return watchmod.set_config_fields(store, fields)


def test_manual_ingest_no_sticky_no_buffer(store):
    _set(store, "Manual")
    before = store.count()
    r = watchmod.ingest(store, "git status -sb && echo hello world")
    assert r["skipped"] is True
    assert r["reason"] == "manual_profile"
    assert r["buffered"] is False
    assert r["auto_filed"] is False
    assert store.count() == before
    assert watchmod.list_buffer(store) == []


def test_coach_ingest_buffer_only_then_stick(store):
    _set(store, "Coach", prompt_cooldown_sec=0)
    text = "git status -sb && git diff --stat HEAD"
    r = watchmod.ingest(store, text)
    assert r["buffered"] is True
    assert r["auto_filed"] is False
    assert store.count() == 0
    ev = r["buffer_event"]
    assert ev["category_guess"] == "CLI"
    assert r.get("pending_prompt") is not None

    stuck = watchmod.stick_buffer(store, ev["id"])
    assert stuck["ok"] is True
    assert stuck["item"]["category"] == "CLI"
    assert store.count() == 1
    # promoted — no longer on active shelf
    shelf = watchmod.list_buffer(store)
    assert all(e["id"] != ev["id"] for e in shelf)


def test_autopilot_rich_cli_auto_files(store):
    _set(store, "Autopilot", prompt_cooldown_sec=0)
    text = "git status -sb && git log --oneline -5"
    r = watchmod.ingest(store, text)
    assert r["buffered"] is True
    assert r["auto_filed"] is True
    assert r["item"]["category"] == "CLI"
    assert store.count() == 1
    # full body persisted
    item = store.get_item(r["item"]["id"])
    assert "git status" in item["body"]


def test_autopilot_secret_does_not_auto_full_body(store):
    _set(store, "Autopilot", prompt_cooldown_sec=0)
    raw = "sk-abcdefghijklmnopqrstuvwxyz0123456789WXYZ"
    r = watchmod.ingest(store, raw)
    assert r["buffered"] is True
    assert r["auto_filed"] is False
    assert r.get("pending_prompt") is not None
    assert store.count() == 0
    ev = r["buffer_event"]
    assert ev["fingerprint"]
    assert raw not in (ev.get("preview") or "")
    # buffer payload must not hold full secret
    full = store.get_buffer_event(ev["id"])
    assert not full.get("payload")
    assert raw not in json.dumps(full)


def test_vault_secret_fingerprint_sticky(store):
    _set(store, "Vault", prompt_cooldown_sec=0)
    raw = "ghp_abcdefghijklmnopqrstuvwx1234567890AB"
    r = watchmod.ingest(store, raw)
    assert r["auto_filed"] is True
    assert r["item"]["category"] == "Secret"
    assert r["item"]["fingerprint"]
    blob = json.dumps(r)
    assert raw not in blob
    item = store.get_item(r["item"]["id"])
    assert raw not in (item.get("body") or "")
    assert item.get("fingerprint")


def test_vault_prompt_stays_buffer_until_stick(store):
    _set(store, "Vault", prompt_cooldown_sec=0)
    text = "You are a senior engineer. Please review this PR for security issues and summarize blockers."
    r = watchmod.ingest(store, text)
    assert r["buffered"] is True
    assert r["auto_filed"] is False
    assert store.count() == 0
    assert r.get("pending_prompt") is not None
    stuck = watchmod.stick_buffer(store, r["buffer_event"]["id"])
    assert stuck["ok"]
    assert store.count() == 1
    assert stuck["item"]["category"] == "Prompt"


def test_buffer_ttl_purge(store):
    _set(store, "Coach", buffer_ttl_hours=48, prompt_cooldown_sec=0)
    r = watchmod.ingest(store, "docker ps --format '{{.Names}}' extra padding")
    assert r["buffered"]
    bid = r["buffer_event"]["id"]
    # force expire
    store._conn.execute(
        "UPDATE buffer_events SET expires_at = ? WHERE id = ?",
        (time.time() - 10, bid),
    )
    store._conn.commit()
    store.purge_expired_buffer()
    assert store.get_buffer_event(bid) is None
    assert watchmod.list_buffer(store) == []


def test_retrieve_buffer_shelf_api(tmp_path):
    store = Store(tmp_path / "http-p5.db")
    _set(store, "Coach", prompt_cooldown_sec=0)
    watchmod.ingest(store, "npm run build && npm test -- --watchAll=false")

    state = AppState(store)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/buffer?include_expired=0") as resp:
            data = json.loads(resp.read())
        assert data["events"]
        assert data["profile"] == "Coach"
        assert data["events"][0]["preview"]

        # config get/set
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/config",
            data=json.dumps({"profile": "Autopilot"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            cfg = json.loads(resp.read())
        assert cfg["config"]["profile"] == "Autopilot"

        # watch tick
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/watch/tick",
            data=json.dumps({"text": "curl -I https://example.com/healthz"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            tick = json.loads(resp.read())
        assert tick["buffered"] or tick.get("auto_filed")
    finally:
        httpd.shutdown()
        store.close()


def test_nag_learning_downweights(store):
    _set(store, "Coach", prompt_cooldown_sec=0)
    # dismiss many times without accept
    for i in range(5):
        watchmod.record_nudge_shown(store, "CLI")
        watchmod.record_nudge_dismissed(store, "CLI")
    assert watchmod.should_nudge(store, "CLI", 0) is False


def test_profile_cli_roundtrip(store, monkeypatch, tmp_path):
    # ensure Store uses our db via env
    monkeypatch.setenv("FLYPAPER_DB", str(tmp_path / "cli.db"))
    from flypaper.cli import main
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert main(["--db", str(tmp_path / "cli.db"), "profile", "set", "coach"]) == 0
    assert "Coach" in buf.getvalue()

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert main(["--db", str(tmp_path / "cli.db"), "profile", "get"]) == 0
    assert "Coach" in buf.getvalue()

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert main(["--db", str(tmp_path / "cli.db"), "watch-ingest", "git diff --stat HEAD~3"]) == 0
    out = buf.getvalue()
    assert "buffered" in out

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert main(["--db", str(tmp_path / "cli.db"), "buffer", "list"]) == 0
    assert "CLI" in buf.getvalue() or "git" in buf.getvalue().lower()
