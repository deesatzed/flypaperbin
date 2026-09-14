"""FlyBot registry — five core bots + dynamic specialists."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flypaper.store import Store

CORE_BOTS = [
    {
        "id": "capture_captain",
        "name": "Capture Captain",
        "role": "Hotkeys, overlay, store I/O",
        "status": "active",
        "kind": "core",
    },
    {
        "id": "text_sorter",
        "name": "Text Sorter",
        "role": "Prompt / CLI / Snippet / URL / Noise",
        "status": "active",
        "kind": "core",
    },
    {
        "id": "secret_sentinel",
        "name": "Secret Sentinel",
        "role": "Key-shaped → fingerprint + hygiene",
        "status": "active",
        "kind": "core",
    },
    {
        "id": "file_scout",
        "name": "File Scout",
        "role": "File/image/doc metadata + description",
        "status": "active",
        "kind": "core",
    },
    {
        "id": "retrieve_concierge",
        "name": "Retrieve Concierge",
        "role": "Frequency × recency palette + triggers",
        "status": "active",
        "kind": "core",
    },
]


def list_bots(store: "Store") -> list[dict[str, Any]]:
    bots = [dict(b) for b in CORE_BOTS]
    for spec in store.list_specialists():
        bots.append(
            {
                "id": f"spec_{spec['id']}",
                "name": f"{spec['parent']}/{spec['subcategory']} Specialist",
                "role": f"Policy for {spec['parent']}/{spec['subcategory']} ({spec['item_count']} items)",
                "status": "active",
                "kind": "specialist",
                "subcategory": spec["subcategory"],
                "parent": spec["parent"],
                "trigger_prefix": spec.get("trigger_prefix"),
                "item_count": spec["item_count"],
            }
        )
    return bots
