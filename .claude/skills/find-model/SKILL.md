---
name: find-model
description: Search for an existing printable model before designing from scratch. Auto-searches Thingiverse (license-aware, with download) and generates browser search links for Creality Cloud, MakerWorld, Printables, Cults3D, MyMiniFactory. Use when the user asks to make something that likely already exists.
argument-hint: <what to find>
---

# find-model

Before modeling from scratch, offer to check whether someone already made it. Tool: `scripts/find_model.py` (official APIs only — never scrape).

## Auto-search Thingiverse (search + download)
```
python3 scripts/find_model.py search "<query>" [--limit 6] [--all-licenses]
python3 scripts/find_model.py download <thing_id> <slug>
```
- `search` returns JSON candidates (name, creator, license, license_class, thumbnail, url). Present them with the **thumbnail** (`![](thumbnail)`), the **license**, and the **source link**, and let the user pick.
- Default search is **permissive-licensed only** (CC0 / CC-BY / CC-BY-SA / GPL / BSD). Add `--all-licenses` only if asked, and clearly flag Non-Commercial / No-Derivatives / personal-use items.
- On the user's pick, `download <thing_id> <slug>` saves the STL to `models/downloads/<slug>/<slug>.stl` + `attribution.json`. Then **render it** so it shows with the spin/slice buttons:
  ```
  scripts/render.sh models/downloads/<slug>/<slug>.stl out/preview
  ```
- Needs a free `THINGIVERSE_TOKEN` (`config/repos.env`). Without it, `search`/`download` error and you fall back to `links`.

## Browser links for the closed sites
```
python3 scripts/find_model.py links "<query>"
```
Creality Cloud, MakerWorld, Printables, Cults3D and MyMiniFactory have no usable download API (bot/login-gated), so surface these as clickable **search links** — the user browses + downloads there. **Creality Cloud is built into Creality Print**, so its library is also reachable from the "Open in Creality Print" button.

## License guardrails (always honor)
- Show **author + license + source** for anything surfaced or downloaded (the download writes them to `attribution.json`).
- **Do not AI-modify** a No-Derivatives / "non-remixable" / all-rights-reserved model — use it as-is, or build fresh instead.
- Default to permissive licenses; treat unknown/missing as personal-use-only. Never redistribute downloaded files.
