#!/usr/bin/env python3
"""find_model.py — search Thingiverse for an existing printable model before building from scratch.

Usage:
  find_model.py search "<query>" [--limit N] [--all-licenses]
  find_model.py download <thing_id> <slug> [--allow-restricted]
  find_model.py links "<query>"

Needs a FREE Thingiverse app token in THINGIVERSE_TOKEN (env or config/repos.env):
  register an app at https://www.thingiverse.com/developers/apps and copy the App Token.

License-aware: `search` defaults to permissive licenses (CC0 / CC-BY / CC-BY-SA / GPL / BSD).
Pass --all-licenses to include Non-Commercial / No-Derivatives / All-Rights-Reserved (flagged).
Every download writes an attribution.json sidecar — honor the license when reusing, and never
AI-modify a No-Derivatives / all-rights-reserved model. Uses the official API only (no scraping).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.thingiverse.com"
PROJECT = Path(__file__).resolve().parent.parent


def token() -> str:
    t = os.environ.get("THINGIVERSE_TOKEN", "").strip()
    if not t:
        env = PROJECT / "config" / "repos.env"
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line.startswith("THINGIVERSE_TOKEN=") and not line.startswith("#"):
                    t = line.split("=", 1)[1].strip().strip('"').strip("'")
    return t


def api_get(path: str, params: dict | None = None):
    tok = token()
    if not tok:
        sys.exit("No THINGIVERSE_TOKEN — register a free app at "
                 "https://www.thingiverse.com/developers/apps and put its App Token in config/repos.env")
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


PERMISSIVE = ("public domain", "creative commons - attribution", "gnu - gpl", "gnu - lgpl", "bsd")


def license_class(lic: str) -> str:
    """permissive (CC0/BY/SA/GPL/BSD) | restricted (NC/ND/all-rights) | unknown."""
    low = (lic or "").lower()
    if not low or low == "none" or "all rights" in low:
        return "restricted"
    if "non-commercial" in low or "no derivatives" in low:
        return "restricted"
    if any(low.startswith(p) or p in low for p in PERMISSIVE):
        return "permissive"
    return "unknown"


def thumb_of(thing: dict) -> str:
    img = thing.get("default_image") or {}
    for size in img.get("sizes", []):
        if size.get("type") == "preview" and size.get("size") in ("featured", "large", "medium"):
            return size.get("url", "")
    return img.get("url") or thing.get("thumbnail") or ""


def search(query: str, limit: int, all_licenses: bool) -> list:
    data = api_get(f"/search/{urllib.parse.quote(query)}", {"type": "things", "per_page": max(limit * 2, 12)})
    hits = data.get("hits") if isinstance(data, dict) else data
    out = []
    for h in (hits or []):
        tid = h.get("id")
        if not tid:
            continue
        thing = api_get(f"/things/{tid}")              # enrich: license, image, creator, url
        cls = license_class(thing.get("license") or "")
        if not all_licenses and cls != "permissive":
            continue
        out.append({
            "thing_id": tid,
            "name": thing.get("name", ""),
            "creator": (thing.get("creator") or {}).get("name", ""),
            "license": thing.get("license") or "unknown",
            "license_class": cls,
            "thumbnail": thumb_of(thing),
            "url": thing.get("public_url", f"https://www.thingiverse.com/thing:{tid}"),
        })
        if len(out) >= limit:
            break
    return out


def download(thing_id: str, slug: str, allow_restricted: bool) -> None:
    thing = api_get(f"/things/{thing_id}")
    lic = thing.get("license") or ""
    cls = license_class(lic)
    if cls != "permissive" and not allow_restricted:
        sys.exit(f"'{thing.get('name','')}' is {cls} ({lic or 'unknown'}). Personal printing may be fine, "
                 f"but pass --allow-restricted to download. Never modify/redistribute No-Derivatives or "
                 f"All-Rights-Reserved models.")
    files = api_get(f"/things/{thing_id}/files")
    stls = [f for f in (files or []) if f.get("name", "").lower().endswith(".stl")]
    if not stls:
        sys.exit("No STL on that thing (it may be a zip-only or non-STL upload — open the page to check).")
    f = max(stls, key=lambda x: x.get("size", 0))
    dl = f.get("download_url") or f.get("public_url")

    outdir = PROJECT / "models" / "downloads" / slug
    outdir.mkdir(parents=True, exist_ok=True)
    stl_path = outdir / f"{slug}.stl"
    req = urllib.request.Request(dl, headers={"Authorization": f"Bearer {token()}"})
    with urllib.request.urlopen(req, timeout=120) as r, open(stl_path, "wb") as fh:
        fh.write(r.read())

    attribution = {
        "source": "Thingiverse",
        "thing_id": thing_id,
        "title": thing.get("name", ""),
        "creator": (thing.get("creator") or {}).get("name", ""),
        "license": lic or "unknown",
        "license_class": cls,
        "url": thing.get("public_url", f"https://www.thingiverse.com/thing:{thing_id}"),
        "file": f.get("name", ""),
    }
    (outdir / "attribution.json").write_text(json.dumps(attribution, indent=2))
    print(json.dumps({"stl": str(stl_path), "attribution": attribution}, indent=2))


def links(query: str) -> None:
    q = urllib.parse.quote(query)
    print(json.dumps({
        "Thingiverse": f"https://www.thingiverse.com/search?q={q}&type=things",
        "Creality Cloud": f"https://www.crealitycloud.com/search?keyword={q}",
        "Printables": f"https://www.printables.com/search/models?q={q}",
        "MakerWorld": f"https://makerworld.com/en/search/models?keyword={q}",
        "Cults3D": f"https://cults3d.com/en/search?q={q}",
        "MyMiniFactory": f"https://www.myminifactory.com/search/?query={q}",
    }, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="Find an existing printable model before building from scratch.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=6); s.add_argument("--all-licenses", action="store_true")
    d = sub.add_parser("download"); d.add_argument("thing_id"); d.add_argument("slug"); d.add_argument("--allow-restricted", action="store_true")
    ln = sub.add_parser("links"); ln.add_argument("query")
    a = ap.parse_args()
    if a.cmd == "search":
        print(json.dumps(search(a.query, a.limit, a.all_licenses), indent=2))
    elif a.cmd == "download":
        download(a.thing_id, a.slug, a.allow_restricted)
    elif a.cmd == "links":
        links(a.query)


if __name__ == "__main__":
    main()
