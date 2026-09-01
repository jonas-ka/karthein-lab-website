#!/usr/bin/env python3
"""
PLAN C — recover the images from a browser-saved copy of the page.

Use this if both tools/2-download.py and tools/1b-download-in-browser.js
are blocked. Saving a page from the browser always works, because the
browser is simply writing out files it already has.

    1. Open a page of the old site.
    2. Scroll to the very bottom, wait a few seconds (this forces the
       lazy-loaded images to arrive), then scroll back to the top.
    3. Press Cmd-S (Ctrl-S) and choose "Webpage, Complete".
    4. Save it anywhere. You get an HTML file plus a folder ending "_files".
    5. Run this script, pointing at that folder:

         python3 tools/2b-match-saved-page.py "~/Desktop/About Us_files"

The browser names saved images after their URL, so this matches them back
against tools/urls-*.json and copies them into tools/raw/ under the same
names tools/2-download.py would have used. Step 3 then works unchanged.

Caveat: you get the resolution the page displayed, usually 1280px wide,
rather than the original upload. That is fine for the website — the
layout never shows an image wider than about 1200px.
"""

import argparse
import json
import pathlib
import shutil
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
RAW = TOOLS / "raw"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ""}
TOKEN_CHARS = 32  # a 32-char prefix of a Google asset id is already unique


def dimensions(path: pathlib.Path) -> tuple[int, int] | None:
    """Read width/height straight from the file header. Stdlib only."""
    try:
        data = path.read_bytes()
    except OSError:
        return None

    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])

    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8 ":
            return struct.unpack("<HH", data[26:30])
        if data[12:16] == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if data[12:16] == b"VP8X":
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return w, h
        return None

    if data[:2] == b"\xff\xd8":  # JPEG: walk the segments to a start-of-frame
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = int.from_bytes(data[i + 2:i + 4], "big")
            if length < 2:
                return None
            i += 2 + length
    return None


def suffix_for(path: pathlib.Path) -> str:
    """Trust the bytes, not the extension the browser guessed."""
    data = path.read_bytes()[:16]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".jpg"


def token_of(url: str) -> str:
    """The Google asset id: last path segment, minus any size directive."""
    tail = url.rstrip("/").split("/")[-1]
    return tail.split("=")[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Match a browser-saved _files folder against tools/urls-*.json")
    parser.add_argument("saved_folder",
                        help='the "..._files" folder the browser wrote')
    parser.add_argument("--apply", action="store_true",
                        help="actually copy the files (default is a dry run)")
    args = parser.parse_args()

    folder = pathlib.Path(args.saved_folder).expanduser()
    if not folder.is_dir():
        print(f"Not a folder: {folder}", file=sys.stderr)
        return 1

    candidates = [
        p for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and p.stat().st_size > 2000
    ]
    if not candidates:
        print(f"No image files found in {folder}", file=sys.stderr)
        return 1

    sizes = {p: dimensions(p) for p in candidates}
    print(f"{len(candidates)} image files in {folder.name}\n")

    sources = sorted(TOOLS.glob("urls-*.json"))
    if not sources:
        print("No tools/urls-*.json found — run tools/1-collect-urls.js first.",
              file=sys.stderr)
        return 1

    plan: list[tuple[pathlib.Path, pathlib.Path, str]] = []
    unmatched: list[str] = []
    used: set[pathlib.Path] = set()

    for source in sources:
        text = source.read_text().strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            print(f"⚠  {source.name} is not valid JSON — skipping.", file=sys.stderr)
            continue

        page = payload.get("page") or source.stem.replace("urls-", "")
        for item in payload.get("images", []):
            stem = f"{page}-{item['index']:02d}"
            token = token_of(item.get("original") or item["url"])[:TOKEN_CHARS]

            # Primary: the browser named the file after the URL.
            match = next((p for p in candidates
                          if p not in used and token and token in p.name), None)
            how = "name"

            # Secondary: intrinsic dimensions recorded in step 1, if unique.
            if not match and item.get("displayed"):
                try:
                    want = tuple(int(n) for n in item["displayed"].lower().split("x"))
                except ValueError:
                    want = None
                if want:
                    hits = [p for p in candidates if p not in used and sizes.get(p) == want]
                    if len(hits) == 1:
                        match, how = hits[0], "size"

            if match:
                used.add(match)
                plan.append((match, RAW / (stem + suffix_for(match)), how))
            else:
                unmatched.append(stem)

    by_name = sum(1 for _, _, how in plan if how == "name")
    by_size = sum(1 for _, _, how in plan if how == "size")

    print("DRY RUN — nothing copied\n" if not args.apply else "Copying\n")
    for src, dest, how in plan:
        label = src.name if len(src.name) <= 46 else src.name[:43] + "..."
        print(f"  {label:<46}  →  {dest.name}   [{how}]")

    print(f"\n  matched {len(plan)}  ({by_name} by filename, {by_size} by dimensions)")
    if unmatched:
        print(f"  unmatched: {', '.join(unmatched)}")
        print("  For these, open the saved folder and copy them into tools/raw/ by")
        print("  hand using the names above — or re-save the page after scrolling")
        print("  right to the bottom, which is usually what went wrong.")

    leftover = [p for p in candidates if p not in used]
    if leftover:
        print(f"  {len(leftover)} file(s) in the folder matched nothing "
              f"(page furniture, most likely)")

    if not args.apply:
        print("\nIf that looks right, run again with --apply")
        return 0

    RAW.mkdir(parents=True, exist_ok=True)
    for src, dest, _ in plan:
        shutil.copy2(src, dest)
    print(f"\n✓ Copied {len(plan)} images into tools/raw/")
    print("  Next:  python3 tools/2-download.py   (rebuilds the contact sheet)")
    print("  Then:  python3 tools/3-rename.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
