# FlyPaper

**Sticky clipboard memory for prompts, CLI, snippets, secrets, and files — driven by hotkeys, not surveillance.**

You copy something useful → hit **Capture** → FlyPaper files it (category / subcategory / shorthand).  
Later hit **Retrieve** → ranked by **how often + how current** → Enter puts it back on the clipboard.

> Assists local recall and key hygiene. Not a password manager replacement. Not cloud sync (v1). Not a whole-disk indexer.

## Quick start

```bash
cd flypaperbin
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Seed sample prompts/CLI so the UI isn’t empty
flypaper demo-seed

# Local web UI + JSON API (opens sticky palettes)
flypaper serve --port 8787
# → http://127.0.0.1:8787
```

CLI without the browser:

```bash
flypaper capture 'git status -sb'
flypaper capture --trigger pr 'You are a senior engineer. Review this PR…'
flypaper retrieve
flypaper retrieve ';pr'
flypaper guess 'sk-abcdefghijklmnopqrstuvwxyz012345'
```

Tests:

```bash
pytest -q
```

Data lives in `~/.flypaper/flypaper.db` (override with `FLYPAPER_DB`).

## Why “FlyPaper”

Everything you *choose* to Capture sticks. Noise you never hotkey never pollutes the ranking. Named flies (not one mega-bot) sort streams the way a fruit-fly connectome keeps modular pathways — with extra bristles (specialists) only when a subcategory gets busy.

## Job to be done

Stop losing repeat prompts, CLI one-liners, strings, API-key context, and file/image references to scrollback — without leaving the app you’re in.

## UX (driver)

### Capture palette (`/` or Capture tab)

Paste or **Read clipboard**, then number-key actions:

1. **File as guessed**
2. **Category…**
3. **Subcategory…** (type-ahead create)
4. **Shorthand trigger** (`;name`)
5. **Secret / key log**
6. **Esc** = forget / dismiss

Near-duplicates offer **Update** (make current) vs **Fork**.

### Retrieve palette

- Empty query → **hot + current** list (frequency + recency + pin − noise) with heat bars
- Type to filter; `;trigger` exact shorthand; **Enter** copies via `navigator.clipboard`
- Secrets show **name + last4** only — full key never in the retrieve list body

### Files / images / docs

If the payload looks like a path or `file://` URL:

- Store **metadata** (path, filename, description) — not a full file copy
- Opaque names (`IMG_`, `DSC_`, `Untitled`, `Scan`) prompt for a one-line description

### Ranking

```
score ≈ frequency + recency + pin + query_match − noise
```

Updating a shorthand makes the **new body current** so stale v1 loses to v3.

## Habitats (categories)

| Category | Examples |
|---|---|
| Prompt | Chat/system prompts |
| CLI | Shell one-liners |
| Snippet | Code, JSON, SQL |
| Secret | API keys (fingerprint log) |
| URL | Links / tickets |
| File | Paths + metadata + description |
| Noise | Fade; don’t train on it |

## FlyBot architecture

### Fixed core (5) — shown in the UI status bar

| FlyBot | Role |
|---|---|
| **Capture Captain** | Overlay, store I/O |
| **Text Sorter** | Prompt / CLI / Snippet / URL / Noise |
| **Secret Sentinel** | Key-shaped → fingerprint + redaction |
| **File Scout** | File/image/doc metadata + description |
| **Retrieve Concierge** | Frequency × recency palette + triggers |

### Dynamic specialists

Spawn when a subcategory reaches **≥ 5 items** (simple rule). Thin policy + optional `;prefix`; reports up to Captain.

## Secrets / API keys

- Detect `sk-`, `ghp_`, `AKIA`, high-entropy tokens → Secret habitat
- Persist **fingerprint**, **last4**, status `active|rotated|missing`
- Retrieve list stores **redacted body** only — never the full secret by default
- Optional later: macOS **Keychain** (or OS secret store) for plaintext on explicit confirm — not wired in v1

Never commit the DB with secrets; never dump full keys in the retrieve list.

## HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | version + item count |
| GET/POST | `/api/clipboard/preview` | last posted text |
| POST | `/api/capture/preview` | guess, near_matches, needs_description |
| POST | `/api/capture` | file / dismiss / secret / near update |
| GET | `/api/retrieve?q=` | ranked public items |
| GET | `/api/retrieve/copy?id=` | text for clipboard + retrieve event |
| POST | `/api/items/{id}/pin` | pin |
| DELETE | `/api/items/{id}` | forget |
| POST | `/api/items/{id}/update_body` | make current |
| GET | `/api/bots` | core + specialists |
| POST | `/api/demo/seed` | sample data |

## Roadmap

### Done in this tree (local web + CLI)
- Capture + Retrieve palettes, SQLite store, ranking, secrets hygiene, file metadata, shorthand, FlyBots + specialists, demo seed

### Later
- [ ] Global OS hotkeys (macOS / others)
- [ ] Keychain bridge for secret plaintext
- [ ] Optional clipboard watcher (explicit opt-in)
- [ ] Cross-device sync

## Non-goals

- Whole-disk salvage · Replacing 1Password · Cloud sync in v1 · Silent clipboard surveillance · One FlyBot per paste

## License / claim

Local-first assistant for recall and hygiene. You own the data on your machine.

---

*Name: FlyPaper. Catch what matters. Leave the rest.*
