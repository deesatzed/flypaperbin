"""Demo / first-run seed data — wow on open."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flypaper.store import Store

SAMPLES = [
    {
        "category": "Prompt",
        "subcategory": "PR-review",
        "trigger": ";pr",
        "body": "You are a senior engineer. Review this PR for correctness, security, and clarity. List blockers first, then nits.",
        "description": None,
    },
    {
        "category": "Prompt",
        "subcategory": "Rewrite",
        "trigger": ";rewrite",
        "body": "Rewrite the following to be clearer and more concise. Keep the meaning. Prefer active voice.",
        "description": None,
    },
    {
        "category": "CLI",
        "subcategory": "git",
        "trigger": ";gs",
        "body": "git status -sb && git diff --stat",
        "description": None,
    },
    {
        "category": "CLI",
        "subcategory": "gh",
        "trigger": ";prls",
        "body": "gh pr list --limit 20 --json number,title,author,updatedAt",
        "description": None,
    },
    {
        "category": "CLI",
        "subcategory": "docker",
        "trigger": ";dps",
        "body": "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'",
        "description": None,
    },
    {
        "category": "Snippet",
        "subcategory": "python",
        "trigger": ";uuid",
        "body": "import uuid\nprint(uuid.uuid4())",
        "description": None,
    },
    {
        "category": "Snippet",
        "subcategory": "sql",
        "trigger": ";topn",
        "body": "SELECT * FROM events ORDER BY created_at DESC LIMIT 50;",
        "description": None,
    },
    {
        "category": "URL",
        "subcategory": "docs",
        "trigger": ";pep8",
        "body": "https://peps.python.org/pep-0008/",
        "description": None,
    },
    {
        "category": "File",
        "subcategory": "Screenshots",
        "trigger": ";shot",
        "kind": "file",
        "body": "~/Desktop/IMG_4291.png",
        "path": "~/Desktop/IMG_4291.png",
        "filename": "IMG_4291.png",
        "description": "Landing page mock — amber sticky notes",
    },
    {
        "category": "Prompt",
        "subcategory": "PR-review",
        "body": "Focus on API contract breakage and missing tests. Ignore style nits.",
    },
    {
        "category": "Prompt",
        "subcategory": "PR-review",
        "body": "Check for secrets accidentally committed and suggest redaction.",
    },
    {
        "category": "Prompt",
        "subcategory": "PR-review",
        "body": "Summarize the change in three bullets for the release notes.",
    },
    {
        "category": "Prompt",
        "subcategory": "PR-review",
        "body": "Are there race conditions or missing locks around shared state?",
    },
]


def seed_demo(store: "Store", *, force: bool = False) -> dict:
    """Seed sample items. Skips if store already has items unless force."""
    if store.count() > 0 and not force:
        return {"seeded": 0, "skipped": True, "count": store.count()}
    n = 0
    for sample in SAMPLES:
        kwargs = {
            "category": sample["category"],
            "body": sample["body"],
            "kind": sample.get("kind", "text"),
            "subcategory": sample.get("subcategory"),
            "trigger": sample.get("trigger"),
            "description": sample.get("description"),
            "path": sample.get("path"),
            "filename": sample.get("filename"),
        }
        # skip if trigger already taken
        if kwargs.get("trigger") and store.find_by_trigger(kwargs["trigger"]):
            kwargs["trigger"] = None
        store.insert_item(**{k: v for k, v in kwargs.items() if v is not None or k in ("body", "category")})
        n += 1
    return {"seeded": n, "skipped": False, "count": store.count()}
