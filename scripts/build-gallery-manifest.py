#!/usr/bin/env python3
"""Build gallery.json from a freshly-synced Lightroom album.

Run by .github/workflows/sync-gallery.yml after the lightroom-album-import
action has downloaded renditions into images/. Order comes from the action's
`sorted_image_paths` output (album sort order); captions come from the
per-image JSON sidecars written by `save_json: true`, falling back to a name
derived from the filename.

Also repoints og:image / JSON-LD image at the first album image so they don't
404 after the image set is replaced.

Env:
  SORTED_PATHS  space-delimited image paths in album order (action output)
  ALBUM_ID      Lightroom album id (action output)
  BUILD_STAMP   optional ISO8601 timestamp; defaults to now (UTC)
"""
import datetime
import glob
import json
import os
import re

IMAGES_DIR = "images"


def _dig(node, keys):
    """Shallow-recursive search for the first non-empty string under any of `keys`."""
    if isinstance(node, dict):
        for k in keys:
            v = node.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in node.values():
            r = _dig(v, keys)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _dig(v, keys)
            if r:
                return r
    return None


def caption_for(path):
    base = os.path.splitext(path)[0]
    for cand in (path + ".json", base + ".json"):
        if os.path.exists(cand):
            try:
                with open(cand) as fh:
                    data = json.load(fh)
                cap = _dig(data, ("caption", "title", "headline"))
                if cap:
                    return cap
            except Exception:
                pass
    name = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"[-_]+", " ", name).strip() or "Photograph"


def main():
    sorted_paths = [p for p in os.environ.get("SORTED_PATHS", "").split() if p]
    paths = [p for p in sorted_paths if os.path.exists(p)]
    if not paths:
        # Defensive fallback: action output missing/empty -> use whatever is on disk.
        paths = sorted(glob.glob(os.path.join(IMAGES_DIR, "*.jpg")) +
                       glob.glob(os.path.join(IMAGES_DIR, "*.jpeg")))

    stamp = os.environ.get("BUILD_STAMP") or \
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    items = [{"file": p, "alt": caption_for(p)} for p in paths]

    # Honor a manual published override (gallery-order.json): listed files lead in that
    # order; unlisted album photos keep album order after them. Stable sort preserves it.
    override = []
    if os.path.exists("gallery-order.json"):
        try:
            with open("gallery-order.json") as fh:
                data = json.load(fh)
            override = data if isinstance(data, list) else data.get("order", [])
        except Exception:
            override = []
    if override:
        idx = {f: i for i, f in enumerate(override)}
        items.sort(key=lambda it: (0, idx[it["file"]]) if it["file"] in idx else (1, 0))

    manifest = {
        "source": "lightroom",
        "album": os.environ.get("ALBUM_ID", ""),
        "generated": stamp,
        "count": len(items),
        "items": items,
    }
    with open("gallery.json", "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"gallery.json: {len(items)} items")

    # Keep social/SEO image references valid after the image set changes.
    if items:
        first = items[0]["file"]
        try:
            with open("index.html") as fh:
                html = fh.read()
            html = re.sub(
                r'(<meta property="og:image" content="https://aaronbisla\.com/)[^"]+(")',
                lambda m: m.group(1) + first + m.group(2), html)
            html = re.sub(
                r'("image":\s*"https://aaronbisla\.com/)[^"]+(")',
                lambda m: m.group(1) + first + m.group(2), html)
            with open("index.html", "w") as fh:
                fh.write(html)
            print(f"og:image / JSON-LD repointed -> {first}")
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
