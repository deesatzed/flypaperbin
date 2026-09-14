# FlyPaper architecture

## Processes
- Single macOS app + optional menu-bar presence
- Global hotkeys → Capture palette | Retrieve palette
- SQLite + Keychain; no server in v1

## Core FlyBots (in-process modules)
1. Capture Captain
2. Text Sorter
3. Secret Sentinel
4. File Scout
5. Retrieve Concierge

## Dynamic specialists
- Records in DB: `{subcategory, parent, policy, trigger_prefix, stats}`
- Spawn / retire via Captain rules
- Not separate OS processes in v1

## Event loop
Capture hotkey → read clipboard → route by kind → palette → persist item + event  
Retrieve hotkey → score items → palette → copy + retrieve event
