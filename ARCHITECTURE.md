# FlyPaper architecture

## Processes
- Local **stdlib HTTP** server (`flypaper serve`) + static site (`site/index.html`)
- CLI (`flypaper capture|retrieve|demo-seed`) shares the same SQLite store
- Global OS hotkeys are a later overlay; v1 uses the browser palettes + CLI

## Core FlyBots (in-process modules)
1. Capture Captain — `serve` capture routes + UI
2. Text Sorter — `classify.guess_category`
3. Secret Sentinel — fingerprint / redact / last4
4. File Scout — path / file:// metadata + opaque-name prompt
5. Retrieve Concierge — `rank.rank_items`

## Dynamic specialists
- Records in DB: `{subcategory, parent, policy, trigger_prefix, stats}`
- Spawn when subcategory item count ≥ 5
- Not separate OS processes

## Event loop
Capture → classify → palette → persist item + `file` event  
Retrieve → score items → palette → copy + `retrieve` event  
Update shorthand → `update` event (body becomes current)

## P5 awareness loop
Config `profile` (Manual|Coach|Autopilot|Vault) in SQLite `config`  
`watch.tick` / `buffer.ingest` → classify → `buffer_events` (TTL/max)  
Coach: soft pending_prompt · Autopilot: auto-file high-conf Prompt/CLI · Vault: secret fingerprint-only  
`buffer.stick` → same capture path · `nudge_stats` downweights ignored categories

## Layout
```
src/flypaper/{cli,store,classify,rank,bots,serve,demo,watch}.py
site/index.html
tests/
```
