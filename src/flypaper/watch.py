"""Awareness profiles, ephemeral buffer ingest, and nag-learning."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

from flypaper.classify import classify_for_storage, guess_category
from flypaper.rank import public_item

PROFILES = ("Manual", "Coach", "Autopilot", "Vault")

DEFAULT_CONFIG = {
    "profile": "Manual",
    "buffer_ttl_hours": "48",
    "buffer_max": "40",
    "min_chars": "12",
    "prompt_cooldown_sec": "90",
}

# Confidence thresholds
HIGH_CONF = 0.72
RICH_CATEGORIES = frozenset({"Prompt", "CLI", "Snippet", "URL", "File"})
AUTOPILOT_AUTO = frozenset({"Prompt", "CLI"})
# Nag: after this many shown, require decent accept rate
NAG_MIN_SHOWN = 4
NAG_MIN_ACCEPT_RATE = 0.25


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:40]


def _preview_for(text: str, guess: dict[str, Any]) -> str:
    if guess.get("category") == "Secret" and guess.get("secret"):
        return guess["secret"]["redacted"]
    t = (text or "").strip().replace("\n", " ")
    return t[:160] + ("…" if len(t) > 160 else "")


def _raw_len(text: str) -> int:
    return len((text or "").strip())


def get_config(store) -> dict[str, Any]:
    raw = store.get_all_config()
    out = dict(DEFAULT_CONFIG)
    out.update(raw)
    # typed views
    return {
        "profile": _norm_profile(out.get("profile", "Manual")),
        "buffer_ttl_hours": int(float(out.get("buffer_ttl_hours", 48))),
        "buffer_max": int(float(out.get("buffer_max", 40))),
        "min_chars": int(float(out.get("min_chars", 12))),
        "prompt_cooldown_sec": int(float(out.get("prompt_cooldown_sec", 90))),
    }


def set_profile(store, profile: str) -> dict[str, Any]:
    p = _norm_profile(profile)
    store.set_config("profile", p)
    return get_config(store)


def set_config_fields(store, fields: dict[str, Any]) -> dict[str, Any]:
    allowed = set(DEFAULT_CONFIG.keys())
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "profile":
            store.set_config(k, _norm_profile(str(v)))
        else:
            store.set_config(k, str(v))
    return get_config(store)


def _norm_profile(p: str) -> str:
    if not p:
        return "Manual"
    for name in PROFILES:
        if name.lower() == str(p).strip().lower():
            return name
    return "Manual"


def should_nudge(store, category: str, cooldown_sec: int) -> bool:
    """Soft prompt only if accept_rate not terrible and cooldown elapsed."""
    stats = store.get_nudge_stats(category)
    shown = int(stats.get("shown") or 0)
    accepted = int(stats.get("accepted") or 0)
    dismissed = int(stats.get("dismissed") or 0)
    if shown >= NAG_MIN_SHOWN:
        rate = accepted / max(shown, 1)
        if rate < NAG_MIN_ACCEPT_RATE:
            return False
    # cooldown: last prompt time stored in nudge_stats.last_shown_at via meta — use events or nudge table
    last = stats.get("last_shown_at")
    if last and cooldown_sec > 0:
        if time.time() - float(last) < cooldown_sec:
            return False
    # heavy dismiss without accept → quiet
    if dismissed >= 3 and accepted == 0:
        return False
    return True


def record_nudge_shown(store, category: str) -> None:
    store.bump_nudge(category, shown=1)


def record_nudge_accepted(store, category: str) -> None:
    store.bump_nudge(category, accepted=1)


def record_nudge_dismissed(store, category: str) -> None:
    store.bump_nudge(category, dismissed=1)


def ingest(store, text: str, *, source: str = "watch") -> dict[str, Any]:
    """
    Profile-aware ingest into ephemeral buffer (+ optional auto-file).

    Manual: no buffer, no sticky — returns skipped.
    Coach/Autopilot/Vault: buffer (+ profile actions).
    """
    cfg = get_config(store)
    profile = cfg["profile"]
    store.purge_expired_buffer()

    result: dict[str, Any] = {
        "ok": True,
        "profile": profile,
        "buffered": False,
        "auto_filed": False,
        "pending_prompt": None,
        "item": None,
        "buffer_event": None,
        "skipped": False,
        "reason": None,
    }

    if profile == "Manual":
        result["skipped"] = True
        result["reason"] = "manual_profile"
        return result

    raw = (text or "").strip()
    if not raw:
        result["skipped"] = True
        result["reason"] = "empty"
        return result

    if _raw_len(raw) < cfg["min_chars"]:
        result["skipped"] = True
        result["reason"] = "too_short"
        return result

    guess = guess_category(raw)
    cat = guess.get("category") or "Snippet"
    conf = float(guess.get("confidence") or 0)

    # Dedup: same hash still active in buffer → refresh / skip duplicate
    th = text_hash(raw)
    existing = store.find_buffer_by_hash(th)
    if existing and not existing.get("dismissed") and not existing.get("promoted_item_id"):
        result["buffer_event"] = _public_buffer(existing)
        result["buffered"] = True
        result["reason"] = "duplicate_buffer"
        # still may set pending for Coach if rich
        if profile == "Coach" and cat in RICH_CATEGORIES and conf >= 0.55:
            if should_nudge(store, cat, cfg["prompt_cooldown_sec"]):
                record_nudge_shown(store, cat)
                result["pending_prompt"] = _pending(existing, guess, raw)
        return result

    # Build buffer row — secrets: redacted + fingerprint only
    is_secret = cat == "Secret"
    preview = _preview_for(raw, guess)
    payload = "" if is_secret else raw
    fingerprint = None
    last4 = None
    if is_secret and guess.get("secret"):
        fingerprint = guess["secret"]["fingerprint"]
        last4 = guess["secret"]["last4"]
        payload = ""  # never store full secret body in buffer

    expires = time.time() + cfg["buffer_ttl_hours"] * 3600
    ev = store.insert_buffer_event(
        text_hash=th,
        preview=preview,
        payload=payload,
        category_guess=cat,
        confidence=conf,
        fingerprint=fingerprint,
        last4=last4,
        expires_at=expires,
        meta={"source": source, "reasons": guess.get("reasons", [])},
    )
    store.trim_buffer(cfg["buffer_max"])
    result["buffered"] = True
    result["buffer_event"] = _public_buffer(ev)

    # --- Profile actions ---
    if profile == "Coach":
        # never auto-file; soft Stick? for rich clips
        if cat in RICH_CATEGORIES and conf >= 0.55 and not is_secret:
            if should_nudge(store, cat, cfg["prompt_cooldown_sec"]):
                record_nudge_shown(store, cat)
                result["pending_prompt"] = _pending(ev, guess, raw)
        elif is_secret:
            # secrets always confirm in Coach
            if should_nudge(store, "Secret", cfg["prompt_cooldown_sec"]):
                record_nudge_shown(store, "Secret")
                result["pending_prompt"] = _pending(ev, guess, raw, secret=True)

    elif profile == "Autopilot":
        if is_secret:
            # secrets still confirm — never auto full body
            if should_nudge(store, "Secret", cfg["prompt_cooldown_sec"]):
                record_nudge_shown(store, "Secret")
                result["pending_prompt"] = _pending(ev, guess, raw, secret=True)
        elif cat in AUTOPILOT_AUTO and conf >= HIGH_CONF and cat != "Noise":
            item = _auto_capture(store, raw, guess)
            store.mark_buffer_promoted(ev["id"], item["id"])
            result["auto_filed"] = True
            result["item"] = public_item(item)
            ev = store.get_buffer_event(ev["id"])
            result["buffer_event"] = _public_buffer(ev)
        elif cat in RICH_CATEGORIES and conf >= 0.55:
            # lower confidence → soft prompt
            if should_nudge(store, cat, cfg["prompt_cooldown_sec"]):
                record_nudge_shown(store, cat)
                result["pending_prompt"] = _pending(ev, guess, raw)

    elif profile == "Vault":
        if is_secret:
            # fingerprint-only auto stick (no full body — classify_for_storage already redacts)
            fields = classify_for_storage(raw, as_secret=True)
            item = store.insert_item(
                category="Secret",
                body=fields["body"],
                body_redacted=fields["body_redacted"],
                kind="secret",
                fingerprint=fields["fingerprint"],
                last4=fields["last4"],
                secret_status="active",
                meta={**(fields.get("meta") or {}), "vault_fingerprint_only": True},
            )
            store.mark_buffer_promoted(ev["id"], item["id"])
            result["auto_filed"] = True
            result["item"] = public_item(item)
            ev = store.get_buffer_event(ev["id"])
            result["buffer_event"] = _public_buffer(ev)
        else:
            # always ask before persisting full body of prompts/snippets
            if cat != "Noise" and should_nudge(store, cat, cfg["prompt_cooldown_sec"]):
                record_nudge_shown(store, cat)
                result["pending_prompt"] = _pending(ev, guess, raw)

    return result


def stick_buffer(store, buffer_id: int, *, extra: Optional[dict] = None) -> dict[str, Any]:
    """Promote a buffer event through the capture flow."""
    store.purge_expired_buffer()
    ev = store.get_buffer_event(buffer_id)
    if not ev:
        return {"error": "not found", "ok": False}
    if ev.get("dismissed"):
        return {"error": "dismissed", "ok": False}
    if ev.get("promoted_item_id"):
        item = store.get_item(int(ev["promoted_item_id"]))
        return {"ok": True, "action": "already_promoted", "item": public_item(item) if item else None}

    extra = extra or {}
    cat = extra.get("category") or ev.get("category_guess") or "Snippet"
    is_secret = cat == "Secret" or bool(ev.get("fingerprint"))

    if is_secret:
        # Stick secret: fingerprint sticky only (no full body available from buffer)
        fields = {
            "body": ev.get("preview") or f"••••{ev.get('last4') or ''}",
            "body_redacted": ev.get("preview"),
            "fingerprint": ev.get("fingerprint"),
            "last4": ev.get("last4"),
            "secret_status": "active",
            "kind": "secret",
            "meta": {"from_buffer": True, "fingerprint_only": True},
        }
        item = store.insert_item(
            category="Secret",
            body=fields["body"],
            body_redacted=fields["body_redacted"],
            kind="secret",
            fingerprint=fields["fingerprint"],
            last4=fields["last4"],
            secret_status="active",
            trigger=extra.get("trigger"),
            subcategory=extra.get("subcategory"),
            meta=fields["meta"],
        )
    else:
        text = ev.get("payload") or ev.get("preview") or ""
        if not text.strip():
            return {"error": "empty payload", "ok": False}
        fields = classify_for_storage(text, as_secret=bool(extra.get("as_secret")))
        category = extra.get("category") or fields["category"]
        item = store.insert_item(
            category=category,
            subcategory=extra.get("subcategory") if "subcategory" in extra else fields.get("subcategory"),
            body=fields["body"],
            kind=fields.get("kind") or "text",
            body_redacted=fields.get("body_redacted"),
            path=fields.get("path"),
            filename=fields.get("filename"),
            description=extra.get("description") or fields.get("description"),
            fingerprint=fields.get("fingerprint"),
            last4=fields.get("last4"),
            secret_status=fields.get("secret_status"),
            trigger=_norm_trigger(extra.get("trigger")),
            meta={**(fields.get("meta") or {}), "from_buffer": True},
        )

    store.mark_buffer_promoted(buffer_id, item["id"])
    record_nudge_accepted(store, cat)
    return {"ok": True, "action": "stuck", "item": public_item(item)}


def dismiss_buffer(store, buffer_id: int) -> dict[str, Any]:
    ev = store.get_buffer_event(buffer_id)
    if not ev:
        return {"error": "not found", "ok": False}
    store.dismiss_buffer_event(buffer_id)
    cat = ev.get("category_guess") or "Snippet"
    record_nudge_dismissed(store, cat)
    return {"ok": True, "action": "dismissed", "id": buffer_id}


def list_buffer(store, *, include_expired: bool = False) -> list[dict]:
    store.purge_expired_buffer()
    rows = store.list_buffer_events(include_expired=include_expired)
    return [_public_buffer(r) for r in rows]


def _auto_capture(store, text: str, guess: dict[str, Any]) -> dict:
    fields = classify_for_storage(text)
    return store.insert_item(
        category=fields["category"],
        subcategory=fields.get("subcategory"),
        body=fields["body"],
        kind=fields.get("kind") or "text",
        body_redacted=fields.get("body_redacted"),
        path=fields.get("path"),
        filename=fields.get("filename"),
        description=fields.get("description"),
        fingerprint=fields.get("fingerprint"),
        last4=fields.get("last4"),
        secret_status=fields.get("secret_status"),
        meta={**(fields.get("meta") or {}), "autopilot": True},
    )


def _pending(ev: dict, guess: dict, raw: str, *, secret: bool = False) -> dict[str, Any]:
    return {
        "buffer_id": ev["id"],
        "preview": ev.get("preview") or _preview_for(raw, guess),
        "category": guess.get("category"),
        "confidence": guess.get("confidence"),
        "secret": secret or guess.get("category") == "Secret",
        "message": "Stick that?",
    }


def _public_buffer(ev: Optional[dict]) -> Optional[dict]:
    if not ev:
        return None
    return {
        "id": ev["id"],
        "text_hash": ev.get("text_hash"),
        "preview": ev.get("preview"),
        "category_guess": ev.get("category_guess"),
        "confidence": ev.get("confidence"),
        "fingerprint": ev.get("fingerprint"),
        "last4": ev.get("last4"),
        "created_at": ev.get("created_at"),
        "expires_at": ev.get("expires_at"),
        "promoted_item_id": ev.get("promoted_item_id"),
        "dismissed": bool(ev.get("dismissed")),
        # never expose full payload for secrets; for non-secrets omit full payload from list by default
        "has_payload": bool(ev.get("payload")),
    }


def _norm_trigger(trigger: Optional[str]) -> Optional[str]:
    if not trigger:
        return None
    t = str(trigger)
    return t if t.startswith(";") else f";{t}"
