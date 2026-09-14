import time

from flypaper.rank import rank_items, score_item


def test_rank_prefers_frequent_and_recent():
    now = time.time()
    items = [
        {"id": 1, "category": "CLI", "body": "rare", "pin": 0, "updated_at": now - 86400 * 10, "last_used_at": now - 86400 * 10},
        {"id": 2, "category": "CLI", "body": "hot", "pin": 0, "updated_at": now - 60, "last_used_at": now - 60},
        {"id": 3, "category": "Noise", "body": "zzz", "pin": 0, "updated_at": now, "last_used_at": now},
        {"id": 4, "category": "Prompt", "body": "pinned", "pin": 1, "updated_at": now - 3600, "last_used_at": now - 3600},
    ]
    stats = {
        1: {"freq": 1, "last_retrieve": now - 86400 * 10},
        2: {"freq": 12, "last_retrieve": now - 60},
        3: {"freq": 20, "last_retrieve": now},
        4: {"freq": 2, "last_retrieve": now - 3600},
    }
    ranked = rank_items(items, stats, query="")
    ids = [r["id"] for r in ranked]
    # pin should beat noise; hot frequent should beat rare
    assert ids[0] == 4  # pin
    assert 2 in ids[:3]
    assert ids.index(2) < ids.index(1)
    # noise sinks despite high freq
    assert ids.index(3) > ids.index(2)


def test_score_query_trigger():
    item = {"id": 1, "category": "CLI", "body": "git status", "trigger": ";gs", "pin": 0, "updated_at": time.time()}
    s = score_item(item, {"freq": 1}, query=";gs")
    s2 = score_item(item, {"freq": 1}, query="nope")
    assert s > s2
