"""FlyPaper CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from flypaper import __version__
from flypaper.classify import classify_for_storage, guess_category
from flypaper.demo import seed_demo
from flypaper.rank import public_item, rank_items
from flypaper.store import Store


def _db_path(args: argparse.Namespace) -> str | None:
    return getattr(args, "db", None) or os.environ.get("FLYPAPER_DB")


def cmd_serve(args: argparse.Namespace) -> int:
    from flypaper.serve import serve

    serve(host=args.host, port=args.port, db_path=_db_path(args))
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    text = args.text
    if text is None:
        text = sys.stdin.read()
    store = Store(_db_path(args))
    fields = classify_for_storage(text, as_secret=bool(args.secret))
    category = args.category or fields["category"]
    trigger = args.trigger
    if trigger and not trigger.startswith(";"):
        trigger = f";{trigger}"
    item = store.insert_item(
        category=category,
        subcategory=args.subcategory or fields.get("subcategory"),
        body=fields["body"],
        kind=fields.get("kind") or "text",
        body_redacted=fields.get("body_redacted"),
        path=fields.get("path"),
        filename=fields.get("filename"),
        description=args.description or fields.get("description"),
        fingerprint=fields.get("fingerprint"),
        last4=fields.get("last4"),
        secret_status=fields.get("secret_status"),
        trigger=trigger,
        meta=fields.get("meta"),
    )
    print(json.dumps(public_item(item), indent=2))
    store.close()
    return 0


def cmd_retrieve(args: argparse.Namespace) -> int:
    store = Store(_db_path(args))
    q = args.query or ""
    ranked = rank_items(store.list_items(), store.event_counts(), query=q, limit=args.limit)
    out = [public_item(r) for r in ranked]
    if args.json:
        print(json.dumps({"items": out, "q": q}, indent=2))
    else:
        if not out:
            print("(no matches — try flypaper demo-seed)")
        for i, it in enumerate(out, 1):
            heat = "█" * int((it.get("heat") or 0) * 8) + "░" * (8 - int((it.get("heat") or 0) * 8))
            trig = f" {it['trigger']}" if it.get("trigger") else ""
            pin = "📌 " if it.get("pin") else ""
            body = (it.get("body") or "")[:72].replace("\n", " ")
            print(f"{i:2}. [{heat}] {pin}{it.get('category')}{trig}  {body}")
    store.close()
    return 0


def cmd_demo_seed(args: argparse.Namespace) -> int:
    store = Store(_db_path(args))
    result = seed_demo(store, force=bool(args.force))
    print(json.dumps(result, indent=2))
    store.close()
    return 0


def cmd_guess(args: argparse.Namespace) -> int:
    print(json.dumps(guess_category(args.text), indent=2))
    return 0



def cmd_profile_get(args: argparse.Namespace) -> int:
    from flypaper import watch as watchmod

    store = Store(_db_path(args))
    cfg = watchmod.get_config(store)
    print(json.dumps({"config": cfg, "profiles": list(watchmod.PROFILES)}, indent=2))
    store.close()
    return 0


def cmd_profile_set(args: argparse.Namespace) -> int:
    from flypaper import watch as watchmod

    store = Store(_db_path(args))
    fields = {"profile": args.name}
    if args.ttl is not None:
        fields["buffer_ttl_hours"] = args.ttl
    if getattr(args, "buffer_max", None) is not None:
        fields["buffer_max"] = args.buffer_max
    if getattr(args, "min_chars", None) is not None:
        fields["min_chars"] = args.min_chars
    if getattr(args, "cooldown", None) is not None:
        fields["prompt_cooldown_sec"] = args.cooldown
    cfg = watchmod.set_config_fields(store, fields)
    print(json.dumps({"ok": True, "config": cfg}, indent=2))
    store.close()
    return 0


def cmd_watch_ingest(args: argparse.Namespace) -> int:
    from flypaper import watch as watchmod

    store = Store(_db_path(args))
    result = watchmod.ingest(store, args.text, source="cli")
    print(json.dumps(result, indent=2, default=str))
    store.close()
    return 0


def cmd_buffer_list(args: argparse.Namespace) -> int:
    from flypaper import watch as watchmod

    store = Store(_db_path(args))
    events = watchmod.list_buffer(store, include_expired=bool(args.include_expired))
    if args.json:
        print(json.dumps({"events": events}, indent=2))
    else:
        if not events:
            print("(buffer empty)")
        for i, ev in enumerate(events, 1):
            prev = (ev.get("preview") or "")[:72]
            print(f"{i:2}. [{ev.get('category_guess')}] {prev}")
    store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="flypaper",
        description="FlyPaper — sticky clipboard memory. Catch what matters.",
    )
    p.add_argument("--version", action="version", version=f"flypaper {__version__}")
    p.add_argument("--db", help="SQLite path (default: ~/.flypaper/flypaper.db or FLYPAPER_DB)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Local web UI + API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.set_defaults(func=cmd_serve)

    c = sub.add_parser("capture", help="File text into the sticky store")
    c.add_argument("text", nargs="?", help="Text to capture (or stdin)")
    c.add_argument("--category")
    c.add_argument("--subcategory")
    c.add_argument("--trigger")
    c.add_argument("--description")
    c.add_argument("--secret", action="store_true")
    c.set_defaults(func=cmd_capture)

    r = sub.add_parser("retrieve", help="Ranked retrieve list")
    r.add_argument("query", nargs="?", default="")
    r.add_argument("--limit", type=int, default=20)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_retrieve)

    d = sub.add_parser("demo-seed", help="Seed sample prompts/CLI for wow-on-open")
    d.add_argument("--force", action="store_true")
    d.set_defaults(func=cmd_demo_seed)

    # alias
    d2 = sub.add_parser("demo", help="Alias for demo-seed + hint to serve")
    d2.add_argument("--force", action="store_true")
    d2.set_defaults(func=cmd_demo_seed)

    g = sub.add_parser("guess", help="Classify text without storing")
    g.add_argument("text")
    g.set_defaults(func=cmd_guess)

    pr = sub.add_parser("profile", help="Get or set awareness profile")
    pr_sub = pr.add_subparsers(dest="profile_cmd", required=True)
    pr_get = pr_sub.add_parser("get", help="Show current profile + config")
    pr_get.set_defaults(func=cmd_profile_get)
    pr_set = pr_sub.add_parser("set", help="Set profile (manual|coach|autopilot|vault)")
    pr_set.add_argument("name", help="Profile name")
    pr_set.add_argument("--ttl", type=int, help="buffer_ttl_hours")
    pr_set.add_argument("--max", dest="buffer_max", type=int, help="buffer_max")
    pr_set.add_argument("--min-chars", type=int, help="min_chars")
    pr_set.add_argument("--cooldown", type=int, help="prompt_cooldown_sec")
    pr_set.set_defaults(func=cmd_profile_set)

    wi = sub.add_parser("watch-ingest", help="Simulate watcher ingest (for testing)")
    wi.add_argument("text", help="Clipboard text to ingest")
    wi.set_defaults(func=cmd_watch_ingest)

    bl = sub.add_parser("buffer", help="Ephemeral buffer commands")
    bl_sub = bl.add_subparsers(dest="buffer_cmd", required=True)
    bl_list = bl_sub.add_parser("list", help="List recent unstuck buffer events")
    bl_list.add_argument("--json", action="store_true")
    bl_list.add_argument("--include-expired", action="store_true")
    bl_list.set_defaults(func=cmd_buffer_list)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
