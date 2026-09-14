"""Retrieve Concierge scoring — frequency + recency + pin − noise."""

from __future__ import annotations

import math
import time
from typing import Any, Optional


def _recency_score(ts: Optional[float], now: Optional[float] = None) -> float:
    if not ts:
        return 0.0
    now = now or time.time()
    age_hours = max((now - ts) / 3600.0, 0.0)
    # half-life ~72h
    return math.exp(-age_hours / 72.0)


def score_item(
    item: dict[str, Any],
    stats: dict[str, Any],
    query: str = "",
    now: Optional[float] = None,
) -> float:
    now = now or time.time()
    freq = float(stats.get("freq") or 0)
    last = stats.get("last_retrieve") or item.get("last_used_at") or item.get("updated_at")
    pin = 25.0 if item.get("pin") else 0.0
    noise = 15.0 if (item.get("category") or "") == "Noise" else 0.0
    # secrets that are rotated sink
    if item.get("secret_status") == "rotated":
        noise += 10.0
    if item.get("secret_status") == "missing":
        noise += 8.0

    freq_s = math.log1p(freq) * 4.0
    rec_s = _recency_score(last, now) * 12.0
    current_s = _recency_score(item.get("updated_at"), now) * 6.0

    q = (query or "").strip().lower()
    match_s = 0.0
    if q:
        hay = " ".join(
            filter(
                None,
                [
                    item.get("body_redacted") or "",
                    item.get("body") or "",
                    item.get("category") or "",
                    item.get("subcategory") or "",
                    item.get("trigger") or "",
                    item.get("filename") or "",
                    item.get("description") or "",
                    item.get("path") or "",
                    item.get("last4") or "",
                ],
            )
        ).lower()
        if q.startswith(";") and (item.get("trigger") or "").lower() == q:
            match_s = 40.0
        elif q in hay:
            match_s = 18.0 + min(len(q), 20) * 0.3
        else:
            # token overlap
            tokens = [t for t in q.split() if t]
            hits = sum(1 for t in tokens if t in hay)
            if tokens and hits:
                match_s = 8.0 * (hits / len(tokens))
            else:
                match_s = -5.0  # weak penalty; filter layer drops non-matches

    return freq_s + rec_s + current_s + pin + match_s - noise


def matches_query(item: dict[str, Any], query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    if q.startswith(";"):
        return (item.get("trigger") or "").lower() == q
    hay = " ".join(
        filter(
            None,
            [
                item.get("body_redacted") or "",
                item.get("body") or "",
                item.get("category") or "",
                item.get("subcategory") or "",
                item.get("trigger") or "",
                item.get("filename") or "",
                item.get("description") or "",
                item.get("path") or "",
                item.get("last4") or "",
            ],
        )
    ).lower()
    return all(tok in hay for tok in q.split())


def rank_items(
    items: list[dict[str, Any]],
    event_stats: dict[int, dict[str, Any]],
    query: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    now = time.time()
    scored: list[dict[str, Any]] = []
    for item in items:
        if not matches_query(item, query):
            continue
        stats = event_stats.get(int(item["id"]), {"freq": 1})
        s = score_item(item, stats, query=query, now=now)
        row = dict(item)
        row["score"] = round(s, 3)
        row["heat"] = _heat(s)
        row["freq"] = int(stats.get("freq") or 0)
        scored.append(row)
    scored.sort(key=lambda r: (-r["score"], -(r.get("updated_at") or 0)))
    return scored[:limit]


def _heat(score: float) -> float:
    """Normalize roughly to 0..1 for UI heat bars."""
    return max(0.0, min(1.0, score / 40.0))


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    """Strip full secrets from API list bodies."""
    out = {
        "id": item["id"],
        "kind": item.get("kind"),
        "category": item.get("category"),
        "subcategory": item.get("subcategory"),
        "trigger": item.get("trigger"),
        "pin": bool(item.get("pin")),
        "path": item.get("path"),
        "filename": item.get("filename"),
        "description": item.get("description"),
        "fingerprint": item.get("fingerprint"),
        "last4": item.get("last4"),
        "secret_status": item.get("secret_status"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "last_used_at": item.get("last_used_at"),
        "score": item.get("score"),
        "heat": item.get("heat"),
        "freq": item.get("freq"),
    }
    if (item.get("category") or "") == "Secret" or item.get("kind") == "secret":
        out["body"] = item.get("body_redacted") or item.get("body") or f"••••{item.get('last4') or ''}"
        out["meta"] = {
            "fingerprint": item.get("fingerprint"),
            "last4": item.get("last4"),
            "secret_status": item.get("secret_status"),
        }
    else:
        out["body"] = item.get("body_redacted") or item.get("body")
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        out["meta"] = {k: v for k, v in meta.items() if k != "_full_secret" and not str(k).startswith("full_")}
    return out
