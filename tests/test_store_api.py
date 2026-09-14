import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from flypaper.classify import classify_for_storage
from flypaper.demo import seed_demo
from flypaper.rank import public_item, rank_items
from flypaper.serve import AppState, make_handler
from flypaper.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def test_capture_retrieve_roundtrip(store):
    fields = classify_for_storage("git log --oneline -20")
    item = store.insert_item(
        category=fields["category"],
        body=fields["body"],
        kind=fields["kind"],
        subcategory=fields.get("subcategory"),
        trigger=";glog",
    )
    assert item["id"]
    ranked = rank_items(store.list_items(), store.event_counts(), query=";glog")
    assert ranked and ranked[0]["id"] == item["id"]
    store.touch_retrieve(item["id"])
    ranked2 = rank_items(store.list_items(), store.event_counts(), query="git")
    assert any(r["id"] == item["id"] for r in ranked2)


def test_fingerprint_not_leaking_in_list(store):
    raw = "sk-abcdefghijklmnopqrstuvwxyz0123456789WXYZ"
    fields = classify_for_storage(raw)
    item = store.insert_item(
        category="Secret",
        body=fields["body"],
        body_redacted=fields["body_redacted"],
        kind="secret",
        fingerprint=fields["fingerprint"],
        last4=fields["last4"],
        secret_status="active",
        meta=fields.get("meta"),
    )
    pub = public_item(item)
    blob = json.dumps(pub)
    assert raw not in blob
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in blob
    assert pub["fingerprint"] == fields["fingerprint"]
    assert pub["last4"] == raw[-4:]
    assert raw not in (pub.get("body") or "")


def test_specialist_spawns_at_five(store):
    for i in range(5):
        store.insert_item(category="Prompt", subcategory="PR-review", body=f"prompt body {i} unique enough")
    specs = store.list_specialists()
    assert any(s["subcategory"] == "PR-review" for s in specs)


def test_demo_seed(store):
    r = seed_demo(store)
    assert r["seeded"] > 0
    assert store.count() >= r["seeded"]


def test_http_health_and_secret_list(tmp_path):
    store = Store(tmp_path / "http.db")
    state = AppState(store)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as resp:
            data = json.loads(resp.read())
        assert data["ok"] is True

        raw = "ghp_abcdefghijklmnopqrstuvwx1234567890AB"
        payload = json.dumps({"text": raw, "action": "file", "as_secret": True}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/capture",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            cap = json.loads(resp.read())
        assert cap["item"]["category"] == "Secret"
        assert raw not in json.dumps(cap)

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/retrieve?q=") as resp:
            listing = json.loads(resp.read())
        blob = json.dumps(listing)
        assert raw not in blob
        assert listing["items"]
        assert listing["items"][0]["fingerprint"]
    finally:
        httpd.shutdown()
        store.close()
