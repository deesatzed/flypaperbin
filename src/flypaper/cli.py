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

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
