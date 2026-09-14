# FlyPaper

**Sticky clipboard memory for prompts, CLI, snippets, secrets, and files — driven by hotkeys, not surveillance.**

You copy something useful → hit **Capture** → FlyPaper files it (category / subcategory / shorthand).  
Later hit **Retrieve** → ranked by **how often + how current** → Enter puts it back on the clipboard.

> Assists local recall and key hygiene. Not a password manager replacement. Not cloud sync (v1). Not a whole-disk indexer.


## Simple use (3 steps)

1. **Start** — `flypaper serve --port 8787` → open http://127.0.0.1:8787  
2. **Capture** — paste something useful → press **1** to file as guessed (or 2–5 to categorize / shorthand / secret). **Esc** dismisses.  
3. **Retrieve** — open the Retrieve tab → leave search empty for hot+current → **Enter** copies it back.

Meme mascot lives at `site/assets/flypaper-file-meme.png` (also on the first-run welcome).

Optional: ⚙ → set profile to **Coach** → paste into **Live watch** → answer **Stick that?** when asked. Manual = Capture only (no watcher).

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

# P5 awareness profiles + buffer
flypaper profile get
flypaper profile set coach
flypaper watch-ingest 'git status -sb && git diff --stat'
flypaper buffer list
```

Tests:

```bash
pytest -q
```

Data lives in `~/.flypaper/flypaper.db` (override with `FLYPAPER_DB`).

## Name note

**FlyPaper** stays the product name (sticky memory). **FileFly** is the mascot — the clerk fly who stamps DECISION then files. Repo/app id remains `flypaperbin` / `flypaper` unless we deliberately rename later.

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


## Awareness modes & user profiles

People realize a clip mattered at different times:

| When they know | Need |
|---|---|
| **Before** copy | Intentional Capture |
| **Right after** use | Soft voluntary prompt (“Stick that?”) |
| **Much later** | Ephemeral buffer + “Recent (unstuck)” recovery (within TTL) |

**Design:** autonomous local observer + **voluntary** prompts + **per-user config** — sticky paper stays sacred (explicit or confirmed).

### Profiles (config dial)

| Profile | Watcher | Auto-file | Prompts | Buffer |
|---|---|---|---|---|
| **Manual** | off | never | none | none — Capture only (current default behavior) |
| **Coach** *(recommended)* | on | never | soft after rich clips | yes, short TTL |
| **Autopilot** | on | high-confidence Prompt/CLI (Noise filtered) | confirm secrets only | yes |
| **Vault** | on | secrets → fingerprint only | always ask before body store | yes, tighter retention |

Advanced toggles under each profile: buffer TTL/size, min length, secret policy, ignore-apps list.

**Learning:** ignore a prompt type often → fewer nudges; stick often → that type can become Autopilot-eligible *for that user* (anti-mean, anti-nag).

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
| GET/POST | `/api/config` | profile + buffer TTL/max/min_chars/cooldown |
| GET | `/api/buffer?include_expired=0` | Recent (unstuck) shelf |
| POST | `/api/buffer/ingest` | classify → buffer (+ profile actions) |
| POST | `/api/buffer/{id}/stick` | promote buffer → sticky item |
| POST | `/api/buffer/{id}/dismiss` | dismiss buffer event |
| POST | `/api/watch/tick` | watcher simulation (clipboard / paste) |
| GET | `/api/watch/status` | profile + pending_prompt |
| POST | `/api/nudge/ack` | nag-learning accept/dismiss |

## Roadmap

### Done in this tree (local web + CLI)
- Capture + Retrieve palettes, SQLite store, ranking, secrets hygiene, file metadata, shorthand, FlyBots + specialists, demo seed
- **P5 Awareness profiles & autonomous buffer** (Manual / Coach / Autopilot / Vault)

### P5 — Awareness profiles & autonomous buffer
- [x] Profile config: **Manual / Coach / Autopilot / Vault** (persisted locally)
- [x] Ephemeral clipboard ring (classify only; TTL/size capped; not sticky until confirmed)
- [x] Voluntary toasts after rich clips (Coach); secrets always confirm
- [x] Retrieve shelf: **Recent (unstuck)** from buffer
- [x] Nag-learning: downweight prompts the user ignores; boost types they stick
- [x] Autopilot rules: auto-stick high-confidence Prompt/CLI only; never auto-stick raw secrets
- [x] Vault: fingerprint-first; ask before any body persistence

### Try Coach mode
```bash
flypaper profile set coach
flypaper serve --port 8787
# In the UI: ⚙ → Coach → Save
# Paste into “Live watch” (or allow clipboard) → soft “Stick that?” toast
# Retrieve → Recent (unstuck) shelf · Stick / dismiss
# CLI: flypaper watch-ingest 'git status -sb' && flypaper buffer list
```

### Later
- [ ] Global OS hotkeys (macOS / others)
- [ ] Keychain bridge for secret plaintext
- [ ] Cross-device sync

## Non-goals

- Whole-disk salvage · Replacing 1Password · Cloud sync in v1 · Silent **permanent** archive without consent · One FlyBot per paste
- (Ephemeral buffer under Coach/Autopilot/Vault is opt-in via profile — not silent forever-storage)

## License / claim

Local-first assistant for recall and hygiene. You own the data on your machine.

---

*Name: FlyPaper. Catch what matters. Leave the rest.*
