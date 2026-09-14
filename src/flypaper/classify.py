"""Text Sorter + Secret Sentinel + File Scout heuristics."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Optional
from urllib.parse import unquote, urlparse

SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "openai_sk"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "github_pat"),
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "aws_akia"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), "slack_token"),
    (re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}\b"), "google_api"),
]

URL_RE = re.compile(r"^https?://\S+$", re.I)
FILE_URL_RE = re.compile(r"^file://", re.I)
PATH_HINT_RE = re.compile(
    r"(^[/~][\w./\- ]+\.\w{1,8}$)|(^[A-Za-z]:\\[\w.\\\- ]+\.\w{1,8}$)|(^[\w.\-]+/[\w./\- ]+\.\w{1,8}$)"
)
OPAQUE_NAME_RE = re.compile(
    r"^(IMG_|DSC_|Untitled|Scan|screenshot|Screen Shot|Copy of |image\d*)",
    re.I,
)
CLI_HINTS = re.compile(
    r"^(\$ |sudo |cd |ls |git |npm |pip |python |curl |wget |ssh |docker |kubectl |brew |cargo |make |apt |yum )"
    r"|(^#!/)|( \|\s*\w+)|( && )|( --\w+)",
    re.M,
)
PROMPT_HINTS = re.compile(
    r"(you are |act as |system:|user:|assistant:|please (write|explain|summarize|refactor)|as a (senior|helpful))",
    re.I,
)
SNIPPET_HINTS = re.compile(
    r"(^(def |class |function |const |let |var |import |from |SELECT |INSERT |CREATE |\{[\s\S]*\}))",
    re.M,
)


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def fingerprint_secret(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:32]


def last4(text: str) -> str:
    t = re.sub(r"\s+", "", text.strip())
    return t[-4:] if len(t) >= 4 else t


def redact_secret(text: str, keep: int = 4) -> str:
    t = text.strip()
    if len(t) <= keep + 4:
        return "•" * max(len(t) - keep, 4) + t[-keep:]
    return t[:4] + "…" + ("•" * 8) + t[-keep:]


def detect_secret(text: str) -> Optional[dict[str, Any]]:
    raw = text.strip()
    if not raw:
        return None
    for pat, kind in SECRET_PATTERNS:
        m = pat.search(raw)
        if m:
            token = m.group(0)
            return {
                "matched": token,
                "kind": kind,
                "fingerprint": fingerprint_secret(token),
                "last4": last4(token),
                "redacted": redact_secret(token),
            }
    # high-entropy single token (API-key shaped)
    token = raw.split()[0] if raw.split() else raw
    if 24 <= len(token) <= 128 and re.fullmatch(r"[A-Za-z0-9_\-/=+]+", token):
        ent = shannon_entropy(token)
        if ent >= 4.2:
            return {
                "matched": token,
                "kind": "high_entropy",
                "fingerprint": fingerprint_secret(token),
                "last4": last4(token),
                "redacted": redact_secret(token),
                "entropy": round(ent, 2),
            }
    return None


def looks_like_path(text: str) -> bool:
    t = text.strip().strip('"').strip("'")
    if not t or "\n" in t:
        return False
    if FILE_URL_RE.match(t):
        return True
    if PATH_HINT_RE.match(t):
        return True
    # existing-looking absolute/home paths without requiring extension for dirs
    if t.startswith(("/", "~/", "./")) and " " not in t[:3]:
        # prefer those with an extension or trailing slash-ish path segments
        if "." in PurePosixPath(t).name or t.endswith("/"):
            return True
    return False


def parse_file_meta(text: str) -> dict[str, Any]:
    t = text.strip().strip('"').strip("'")
    path = t
    if FILE_URL_RE.match(t):
        parsed = urlparse(t)
        path = unquote(parsed.path)
        # file:///C:/... on Windows-ish
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
    # pick path class
    if re.match(r"^[A-Za-z]:\\", path):
        name = PureWindowsPath(path).name
    else:
        name = PurePosixPath(path).name
    opaque = bool(OPAQUE_NAME_RE.match(name))
    return {
        "kind": "file",
        "path": path,
        "filename": name,
        "needs_description": opaque,
        "opaque": opaque,
    }


def guess_category(text: str) -> dict[str, Any]:
    """Return classification guess used by Capture Captain / Text Sorter."""
    raw = (text or "").strip()
    result: dict[str, Any] = {
        "category": "Snippet",
        "subcategory": None,
        "kind": "text",
        "confidence": 0.4,
        "secret": None,
        "file": None,
        "needs_description": False,
        "reasons": [],
    }
    if not raw:
        result["category"] = "Noise"
        result["confidence"] = 0.9
        result["reasons"].append("empty")
        return result

    secret = detect_secret(raw)
    if secret:
        result.update(
            {
                "category": "Secret",
                "kind": "secret",
                "confidence": 0.95,
                "secret": secret,
                "reasons": [f"secret:{secret['kind']}"],
            }
        )
        return result

    if URL_RE.match(raw):
        result.update(
            {
                "category": "URL",
                "kind": "url",
                "confidence": 0.92,
                "reasons": ["url_scheme"],
            }
        )
        return result

    if looks_like_path(raw):
        meta = parse_file_meta(raw)
        result.update(
            {
                "category": "File",
                "kind": "file",
                "confidence": 0.9,
                "file": meta,
                "needs_description": meta["needs_description"],
                "reasons": ["path_or_file_url"],
            }
        )
        return result

    if CLI_HINTS.search(raw) and len(raw) < 2000:
        result.update(
            {
                "category": "CLI",
                "kind": "text",
                "confidence": 0.8,
                "subcategory": _cli_subcat(raw),
                "reasons": ["cli_hints"],
            }
        )
        return result

    if PROMPT_HINTS.search(raw) or (len(raw) > 120 and raw.count("\n") >= 1 and not SNIPPET_HINTS.search(raw[:80])):
        result.update(
            {
                "category": "Prompt",
                "kind": "text",
                "confidence": 0.75,
                "reasons": ["prompt_hints"],
            }
        )
        return result

    if SNIPPET_HINTS.search(raw):
        result.update(
            {
                "category": "Snippet",
                "kind": "text",
                "confidence": 0.7,
                "reasons": ["snippet_hints"],
            }
        )
        return result

    # short noise-ish
    if len(raw) < 8 and not raw.isalnum():
        result.update({"category": "Noise", "confidence": 0.6, "reasons": ["short_noise"]})
        return result

    result["reasons"].append("default_snippet")
    return result


def _cli_subcat(raw: str) -> Optional[str]:
    first = raw.lstrip("$ ").split()[0] if raw.split() else None
    if not first:
        return None
    first = first.split("/")[-1]
    known = {
        "git": "git",
        "gh": "gh",
        "docker": "docker",
        "kubectl": "k8s",
        "npm": "npm",
        "pip": "pip",
        "curl": "curl",
        "ssh": "ssh",
    }
    return known.get(first)


def classify_for_storage(text: str, *, as_secret: bool = False, description: Optional[str] = None) -> dict[str, Any]:
    """Produce fields ready for Store.insert_item."""
    guess = guess_category(text)
    if as_secret and not guess.get("secret"):
        token = text.strip()
        guess["secret"] = {
            "matched": token,
            "kind": "manual",
            "fingerprint": fingerprint_secret(token),
            "last4": last4(token),
            "redacted": redact_secret(token),
        }
        guess["category"] = "Secret"
        guess["kind"] = "secret"

    out: dict[str, Any] = {
        "kind": guess["kind"],
        "category": guess["category"],
        "subcategory": guess.get("subcategory"),
        "body": text,
        "body_redacted": None,
        "path": None,
        "filename": None,
        "description": description,
        "fingerprint": None,
        "last4": None,
        "secret_status": None,
        "meta": {"guess_reasons": guess.get("reasons", []), "confidence": guess.get("confidence")},
    }

    if guess.get("secret"):
        sec = guess["secret"]
        out["body"] = sec["redacted"]  # NEVER store full secret as list body by default
        out["body_redacted"] = sec["redacted"]
        out["fingerprint"] = sec["fingerprint"]
        out["last4"] = sec["last4"]
        out["secret_status"] = "active"
        out["meta"]["secret_kind"] = sec["kind"]
        out["meta"]["fingerprint"] = sec["fingerprint"]
        # keep full only in meta under explicit key for local keychain bridge later — NOT returned in list API
        out["_full_secret"] = sec["matched"]

    if guess.get("file"):
        fm = guess["file"]
        out["path"] = fm["path"]
        out["filename"] = fm["filename"]
        out["kind"] = "file"
        out["meta"]["opaque"] = fm.get("opaque", False)
        if description:
            out["description"] = description

    return out
