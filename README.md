# FlyPaper

**Sticky clipboard memory for prompts, CLI, snippets, secrets, and files — driven by hotkeys, not surveillance.**

You copy something useful → hit **Capture** → FlyPaper files it (category / subcategory / shorthand).  
Later hit **Retrieve** → ranked by **how often + how current** → Enter puts it back on the clipboard.

> Assists local recall and key hygiene. Not a password manager replacement. Not cloud sync (v1). Not a whole-disk indexer.

## Why “FlyPaper”

Everything you *choose* to Capture sticks. Noise you never hotkey never pollutes the ranking. Named flies (not one mega-bot) sort streams the way a fruit-fly connectome keeps modular pathways — with extra bristles (specialists) only when a subcategory gets busy.

## Job to be done

Stop losing repeat prompts, CLI one-liners, strings, API-key context, and file/image references to scrollback — without leaving the app you’re in.

## UX (driver)

### Capture (manual hotkey only in v1)

Overlay on current clipboard contents:

1. **File as guessed**
2. **Category…**
3. **Subcategory…** (type-ahead create)
4. **Save shorthand** (`;name`)
5. **Secret / key log**
6. Esc = forget / dismiss

No always-on silent archive in v1 (optional watcher is a later, explicit opt-in).

### Retrieve (second hotkey)

- Empty query → **hot + current** list (frequency × recency, pins win, noise loses)
- Type to filter; Enter → copy to clipboard
- Secrets show **name + last4** only; value from Keychain only if you saved it

### Files / images / docs

Only when Capture is pressed and the clipboard holds a file URL / image / document:

- Store **metadata** (path, filename, type, size, mtime, cheap hash) — not a full file copy by default
- If the name is opaque (`IMG_4291.png`), prompt for an optional **one-line description**
- Retrieve by description or filename; Enter restores path/URL to the clipboard

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
| File / Image / Doc | Paths + metadata + description |
| Noise | Fade; don’t train on it |

Subcategories are **yours** (`Prompt/PR-review`, `CLI/gh`, `Image/Screenshots`).

## FlyBot architecture

### Fixed core (5)

| FlyBot | Role |
|---|---|
| **Capture Captain** | Hotkeys, overlay, store I/O |
| **Text Sorter** | Prompt / CLI / Snippet / URL / Noise |
| **Secret Sentinel** | Key-shaped → fingerprint + Keychain gate |
| **File Scout** | File/image/doc metadata + description |
| **Retrieve Concierge** | Frequency × recency palette + triggers |

### Dynamic specialists

Spawn when a subcategory needs its own policy — not one bot per paste.

**Mint when:** subcat has enough items *and* parent keeps mis-filing it; or you hit “Promote subcat to specialist.”

**Each specialist:** thin policy + teach chips + optional `;prefix`; reports up to Captain.

**Hygiene:** soft cap (~12–20); merge/retire when cold. In-process first; sidebar teammates only if you want them visible later.

```
Retrieve Concierge ←→ Store
        ↑
Capture Captain
   ├── Text Sorter ──► [dynamic Prompt/*, CLI/*, …]
   ├── Secret Sentinel
   └── File Scout ──► [dynamic Image/*, Doc/*, …]
```

## Secrets / API keys

- Detect key-shaped clipboard → Secret habitat
- Persist fingerprint, last4, first/last seen, status `active|rotated|missing`
- Plaintext → **Keychain only on explicit confirm**
- New key same service → old `rotated`; Retrieve ranks active first
- Never commit the DB with secrets; never dump full keys in the retrieve list

## Roadmap

### P0 — Skeleton (first real win)
- [ ] macOS Capture + Retrieve global hotkeys
- [ ] Text capture → guess → file / recategorize / dismiss
- [ ] SQLite store (items, events, triggers)
- [ ] Retrieve palette: empty = hot+current; Enter copies
- [ ] Real forget/delete

### P1 — Filing depth
- [ ] Subcategories + type-ahead
- [ ] Shorthand triggers + Update vs Fork on near-dup
- [ ] File/image/doc metadata + optional description
- [ ] Pin / unpin
- [ ] Dynamic specialist spawn rules (basic)

### P2 — Secrets hygiene
- [ ] Secret detector + fingerprint log
- [ ] Optional Keychain save / retrieve
- [ ] Rotation handling

### P3 — Smart ranking
- [ ] Weight tuning; optional frontmost-app boost
- [ ] “Like this” similar prompts
- [ ] Explain-why-ranked (tiny)

### P4 — Optional (explicit yes)
- [ ] Always-on clipboard watcher (off by default)
- [ ] Paste-to-frontmost-app
- [ ] Full file ingest / thumbnails
- [ ] Cross-device sync
- [ ] Tie-in to redakt-flies when a prompt embeds a key

## Build plan (engineering)

**Stack (proposed):** macOS first; small overlay app (SwiftUI or Tauri) for global hotkeys + clipboard APIs; SQLite in Application Support; Keychain for secret values.

**Classifier v0:** rules + heuristics + user teach chips. LLM naming of clusters is optional later — not on the Capture critical path.

**Minimal schema:**
- `items` — kind, category, subcategory, body/path/description, fingerprint, trigger, pin, versions, timestamps
- `events` — file | retrieve | update | dismiss
- Scores derived from events (freq, recency)

**Definition of done:**
- P0: Capture + Retrieve twice a day without opening Settings
- P1: File a screenshot with a description; find it by that text
- P2: Rotate a key; old one is not offered as current

## Non-goals

- Whole-disk / dup-iteration salvage (two-volume disk salvage is a different product)
- Replacing 1Password/Bitwarden
- Cloud sync in v1
- Silent clipboard surveillance in v1
- One FlyBot per clipboard event

## License / claim

Local-first assistant for recall and hygiene. You own the data on your machine.

---

*Name: FlyPaper. Catch what matters. Leave the rest.*
