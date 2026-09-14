"""stdlib HTTP API + static site for FlyPaper."""

from __future__ import annotations

import json
import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from flypaper import __version__
from flypaper.bots import list_bots
from flypaper.classify import classify_for_storage, guess_category
from flypaper.demo import seed_demo
from flypaper.rank import public_item, rank_items
from flypaper.store import CATEGORIES, Store
from flypaper import watch as watchmod

SITE_DIR = Path(__file__).resolve().parent.parent.parent / "site"


class AppState:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.last_preview: Optional[str] = None
        self.pending_prompt: Optional[dict] = None
        self.last_watch_text: Optional[str] = None
        self.lock = threading.RLock()


def _json_bytes(data: Any, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"


def make_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            # quieter default
            pass

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/api/health":
                with state.lock:
                    count = state.store.count()
                    cfg = watchmod.get_config(state.store)
                    buf_n = len(state.store.list_buffer_events())
                return self._send(*_json_bytes({
                    "ok": True,
                    "version": __version__,
                    "items": count,
                    "product": "FlyPaper",
                    "profile": cfg["profile"],
                    "buffer": buf_n,
                    "pending_prompt": state.pending_prompt,
                }))

            if path == "/api/clipboard/preview":
                return self._send(*_json_bytes({"text": state.last_preview}))

            if path == "/api/retrieve":
                q = (qs.get("q") or [""])[0]
                with state.lock:
                    items = state.store.list_items()
                    stats = state.store.event_counts()
                    ranked = rank_items(items, stats, query=q)
                    # if exact trigger hit, touch it? leave to client copy endpoint — touch on retrieve list select via update
                    payload = [public_item(r) for r in ranked]
                return self._send(*_json_bytes({"items": payload, "q": q}))

            if path == "/api/bots":
                with state.lock:
                    bots = list_bots(state.store)
                return self._send(*_json_bytes({"bots": bots}))

            if path == "/api/categories":
                with state.lock:
                    subs = state.store.subcategories()
                return self._send(*_json_bytes({"categories": list(CATEGORIES), "subcategories": subs}))

            if path == "/api/retrieve/copy":
                # optional: GET with id to mark retrieve + return body for clipboard
                try:
                    item_id = int((qs.get("id") or ["0"])[0])
                except ValueError:
                    return self._send(*_json_bytes({"error": "bad id"}, 400))
                with state.lock:
                    item = state.store.get_item(item_id)
                    if not item:
                        return self._send(*_json_bytes({"error": "not found"}, 404))
                    state.store.touch_retrieve(item_id)
                    # For secrets: return redacted unless client asks — never full key
                    body = item.get("body_redacted") or item.get("body") or ""
                    if item.get("kind") == "file" and item.get("path"):
                        body = item["path"]
                return self._send(*_json_bytes({"id": item_id, "text": body}))

            if path == "/api/config" or path == "/api/profile":
                with state.lock:
                    cfg = watchmod.get_config(state.store)
                return self._send(*_json_bytes({
                    "config": cfg,
                    "profiles": list(watchmod.PROFILES),
                    "pending_prompt": state.pending_prompt,
                }))

            if path == "/api/buffer":
                include_expired = (qs.get("include_expired") or ["0"])[0] in ("1", "true", "yes")
                with state.lock:
                    events = watchmod.list_buffer(state.store, include_expired=include_expired)
                    cfg = watchmod.get_config(state.store)
                return self._send(*_json_bytes({
                    "events": events,
                    "profile": cfg["profile"],
                    "pending_prompt": state.pending_prompt,
                }))

            if path == "/api/watch/status":
                with state.lock:
                    cfg = watchmod.get_config(state.store)
                return self._send(*_json_bytes({
                    "profile": cfg["profile"],
                    "watching": cfg["profile"] != "Manual",
                    "pending_prompt": state.pending_prompt,
                    "last_watch_text": (state.last_watch_text or "")[:80] or None,
                }))

            # static
            return self._serve_static(path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return self._send(*_json_bytes({"error": "invalid json"}, 400))

            if path == "/api/clipboard/preview":
                text = data.get("text") or ""
                state.last_preview = text
                return self._send(*_json_bytes({"ok": True, "text": text}))

            if path == "/api/capture/preview":
                text = data.get("text") or ""
                state.last_preview = text
                guess = guess_category(text)
                with state.lock:
                    near = state.store.find_near_matches(text)
                    near_pub = [public_item(n) for n in near]
                return self._send(*_json_bytes({
                    "guess": guess,
                    "near_matches": near_pub,
                    "needs_description": bool(guess.get("needs_description")),
                    "categories": list(CATEGORIES),
                }))

            if path == "/api/capture":
                return self._capture(data)

            if path == "/api/demo/seed":
                force = bool(data.get("force"))
                with state.lock:
                    result = seed_demo(state.store, force=force)
                return self._send(*_json_bytes(result))

            m = re.fullmatch(r"/api/items/(\d+)/pin", path)
            if m:
                item_id = int(m.group(1))
                with state.lock:
                    item = state.store.pin_item(item_id, pinned=bool(data.get("pin", True)))
                    if not item:
                        return self._send(*_json_bytes({"error": "not found"}, 404))
                return self._send(*_json_bytes({"item": public_item(item)}))

            m = re.fullmatch(r"/api/items/(\d+)/update_body", path)
            if m:
                item_id = int(m.group(1))
                text = data.get("text") or ""
                with state.lock:
                    item = state.store.get_item(item_id)
                    if not item:
                        return self._send(*_json_bytes({"error": "not found"}, 404))
                    # if secret category, re-redact
                    body_redacted = None
                    if item.get("category") == "Secret":
                        from flypaper.classify import classify_for_storage as cfs
                        fields = cfs(text, as_secret=True)
                        text = fields["body"]
                        body_redacted = fields["body_redacted"]
                        state.store._conn.execute(
                            "UPDATE items SET fingerprint = ?, last4 = ?, secret_status = ? WHERE id = ?",
                            (fields["fingerprint"], fields["last4"], "active", item_id),
                        )
                    updated = state.store.update_body(item_id, text, body_redacted=body_redacted)
                return self._send(*_json_bytes({"item": public_item(updated), "action": "updated"}))

            m = re.fullmatch(r"/api/items/(\d+)/fork", path)
            if m:
                # fork: new item from near-dup with new body
                item_id = int(m.group(1))
                text = data.get("text") or ""
                with state.lock:
                    src = state.store.get_item(item_id)
                    if not src:
                        return self._send(*_json_bytes({"error": "not found"}, 404))
                    fields = classify_for_storage(text)
                    item = state.store.insert_item(
                        category=data.get("category") or src["category"],
                        subcategory=data.get("subcategory") or src.get("subcategory"),
                        body=fields["body"],
                        kind=fields["kind"],
                        body_redacted=fields.get("body_redacted"),
                        path=fields.get("path"),
                        filename=fields.get("filename"),
                        description=data.get("description") or fields.get("description"),
                        fingerprint=fields.get("fingerprint"),
                        last4=fields.get("last4"),
                        secret_status=fields.get("secret_status"),
                        trigger=None,  # fork doesn't steal trigger
                        meta=fields.get("meta"),
                    )
                return self._send(*_json_bytes({"item": public_item(item), "action": "forked"}))

            if path in ("/api/config", "/api/profile"):
                with state.lock:
                    cfg = watchmod.set_config_fields(state.store, data)
                return self._send(*_json_bytes({"ok": True, "config": cfg, "profiles": list(watchmod.PROFILES)}))

            if path == "/api/buffer/ingest":
                text = data.get("text") or ""
                with state.lock:
                    result = watchmod.ingest(state.store, text, source="api")
                    if result.get("pending_prompt"):
                        state.pending_prompt = result["pending_prompt"]
                    elif result.get("auto_filed"):
                        state.pending_prompt = None
                return self._send(*_json_bytes(result))

            if path == "/api/watch/tick":
                text = data.get("text") or ""
                with state.lock:
                    cfg = watchmod.get_config(state.store)
                    if cfg["profile"] == "Manual":
                        return self._send(*_json_bytes({
                            "ok": True,
                            "skipped": True,
                            "reason": "manual_profile",
                            "profile": "Manual",
                            "pending_prompt": None,
                        }))
                    # skip identical consecutive ticks
                    if text and text == state.last_watch_text:
                        return self._send(*_json_bytes({
                            "ok": True,
                            "skipped": True,
                            "reason": "unchanged",
                            "profile": cfg["profile"],
                            "pending_prompt": state.pending_prompt,
                            "buffer_event": None,
                        }))
                    state.last_watch_text = text
                    result = watchmod.ingest(state.store, text, source="watch")
                    if result.get("pending_prompt"):
                        state.pending_prompt = result["pending_prompt"]
                    elif result.get("auto_filed"):
                        state.pending_prompt = None
                return self._send(*_json_bytes(result))

            m = re.fullmatch(r"/api/buffer/(\d+)/stick", path)
            if m:
                bid = int(m.group(1))
                with state.lock:
                    result = watchmod.stick_buffer(state.store, bid, extra=data)
                    if result.get("ok"):
                        state.pending_prompt = None
                status = 200 if result.get("ok") else (404 if result.get("error") == "not found" else 400)
                return self._send(*_json_bytes(result, status))

            m = re.fullmatch(r"/api/buffer/(\d+)/dismiss", path)
            if m:
                bid = int(m.group(1))
                with state.lock:
                    result = watchmod.dismiss_buffer(state.store, bid)
                    if state.pending_prompt and state.pending_prompt.get("buffer_id") == bid:
                        state.pending_prompt = None
                status = 200 if result.get("ok") else 404
                return self._send(*_json_bytes(result, status))

            if path == "/api/nudge/ack":
                # optional: client ack for customize / esc without stick
                action = (data.get("action") or "dismiss").lower()
                cat = data.get("category") or "Snippet"
                with state.lock:
                    if action == "accept":
                        watchmod.record_nudge_accepted(state.store, cat)
                    else:
                        watchmod.record_nudge_dismissed(state.store, cat)
                    state.pending_prompt = None
                return self._send(*_json_bytes({"ok": True}))

            return self._send(*_json_bytes({"error": "not found"}, 404))

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            m = re.fullmatch(r"/api/items/(\d+)", parsed.path)
            if not m:
                return self._send(*_json_bytes({"error": "not found"}, 404))
            item_id = int(m.group(1))
            with state.lock:
                ok = state.store.delete_item(item_id)
            if not ok:
                return self._send(*_json_bytes({"error": "not found"}, 404))
            return self._send(*_json_bytes({"ok": True, "deleted": item_id}))

        def _capture(self, data: dict) -> None:
            action = (data.get("action") or "file").lower()
            if action == "dismiss":
                with state.lock:
                    state.store.add_event("dismiss", None)
                return self._send(*_json_bytes({"ok": True, "action": "dismiss"}))

            text = data.get("text") or ""
            if not text.strip():
                return self._send(*_json_bytes({"error": "empty text"}, 400))

            as_secret = bool(data.get("as_secret"))
            fields = classify_for_storage(
                text,
                as_secret=as_secret,
                description=data.get("description"),
            )
            category = data.get("category") or fields["category"]
            subcategory = data.get("subcategory") if "subcategory" in data else fields.get("subcategory")
            trigger = data.get("trigger")
            if trigger:
                trigger = trigger if str(trigger).startswith(";") else f";{trigger}"

            # near-dup handling
            near_action = data.get("near_action")  # update | fork | None
            near_id = data.get("near_id")
            with state.lock:
                if near_action == "update" and near_id:
                    updated = state.store.update_body(
                        int(near_id),
                        fields["body"],
                        body_redacted=fields.get("body_redacted"),
                    )
                    if updated and trigger:
                        try:
                            state.store._conn.execute(
                                "UPDATE items SET trigger = ? WHERE id = ?",
                                (trigger, int(near_id)),
                            )
                            state.store._conn.commit()
                            updated = state.store.get_item(int(near_id))
                        except Exception:
                            pass
                    if category:
                        state.store._conn.execute(
                            "UPDATE items SET category = ?, subcategory = COALESCE(?, subcategory) WHERE id = ?",
                            (category, subcategory, int(near_id)),
                        )
                        state.store._conn.commit()
                        updated = state.store.get_item(int(near_id))
                    return self._send(*_json_bytes({
                        "item": public_item(updated) if updated else None,
                        "action": "updated",
                    }))

                # rotate previous secrets with same fingerprint service? simple: same last4+kind → mark rotated if different fp
                if fields.get("fingerprint"):
                    rows = state.store._conn.execute(
                        "SELECT id, fingerprint FROM items WHERE category = 'Secret' AND secret_status = 'active'"
                    ).fetchall()
                    for r in rows:
                        if r["fingerprint"] and r["fingerprint"] != fields["fingerprint"]:
                            # same last4 heuristic optional — skip auto-rotate unless meta says
                            pass

                try:
                    item = state.store.insert_item(
                        category=category,
                        subcategory=subcategory,
                        body=fields["body"],
                        kind=fields.get("kind") or "text",
                        body_redacted=fields.get("body_redacted"),
                        path=fields.get("path"),
                        filename=fields.get("filename"),
                        description=data.get("description") or fields.get("description"),
                        fingerprint=fields.get("fingerprint"),
                        last4=fields.get("last4"),
                        secret_status=fields.get("secret_status"),
                        trigger=trigger,
                        meta=fields.get("meta"),
                    )
                except Exception as e:
                    # likely unique trigger collision
                    return self._send(*_json_bytes({"error": str(e)}, 409))

            return self._send(*_json_bytes({"item": public_item(item), "action": "filed"}))

        def _serve_static(self, path: str) -> None:
            if path in ("/", ""):
                path = "/index.html"
            # security: only site dir
            rel = path.lstrip("/")
            if ".." in rel or rel.startswith("/"):
                return self._send(*_json_bytes({"error": "bad path"}, 400))
            fp = (SITE_DIR / rel).resolve()
            if not str(fp).startswith(str(SITE_DIR.resolve())) or not fp.is_file():
                return self._send(*_json_bytes({"error": "not found"}, 404))
            ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
            if fp.suffix == ".js":
                ctype = "application/javascript; charset=utf-8"
            elif fp.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif fp.suffix == ".html":
                ctype = "text/html; charset=utf-8"
            data = fp.read_bytes()
            return self._send(200, data, ctype)

    return Handler


def create_app(store: Optional[Store] = None, db_path: Optional[str] = None) -> tuple[AppState, Any]:
    st = Store(db_path) if db_path or store is None else store
    if store is not None:
        st = store
    state = AppState(st)
    return state, make_handler(state)


def serve(host: str = "127.0.0.1", port: int = 8787, db_path: Optional[str] = None) -> None:
    store = Store(db_path)
    # first-run seed
    if store.count() == 0:
        seed_demo(store)
    state = AppState(store)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"FlyPaper sticky on http://{host}:{port}  (Ctrl+C to peel off)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nFlyPaper dismissed.")
    finally:
        httpd.server_close()
        store.close()
