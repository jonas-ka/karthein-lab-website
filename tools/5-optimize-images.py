#!/usr/bin/env python3
"""
Shrink the photos to the largest size the site can actually display, and
convert them to WebP.

    python3 tools/5-optimize-images.py            # report what it would do
    python3 tools/5-optimize-images.py --apply    # do it

Why this matters: a news photo is shown in a 320px-wide column. Even on a
retina screen the largest useful file is 640px across. A 4000px original is
about forty times more pixels than anyone ever sees — all of it downloaded,
decoded and thrown away.

The target widths below come straight from the layout in site.css. If you
change the layout, change them here too.

Originals are copied to tools/originals/ first, so nothing is lost. The
script also updates data/*.json and the HTML pages to point at the new
filenames, and writes data/image-sizes.json so the browser can reserve the
right space before a photo arrives (which stops the page jumping about as
it loads).

Needs Pillow:   python3 -m pip install --upgrade Pillow
"""

import argparse
import json
import pathlib
import re
import shutil
import sys

try:
    from PIL import Image, ImageOps
except ImportError:
    print("This script needs Pillow:\n\n    python3 -m pip install --upgrade Pillow\n",
          file=sys.stderr)
    raise SystemExit(1)

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMG = ROOT / "assets" / "img"
BACKUP = ROOT / "tools" / "originals"
MANIFEST = ROOT / "data" / "image-sizes.json"

# Largest width each image is ever displayed at, doubled for retina screens.
TARGETS = {
    "news": 640,        # 320px column
    "people": 520,      # 260px card
    "research": 800,    # 400px card
    "_hero": 2240,      # full page width, 1120px
}

# The logo is left alone: it is already small, and it doubles as the favicon
# and iOS home-screen icon, where PNG is the safest format.
SKIP = {"logo.png", "logo.jpg", "logo.webp", "favicon.svg"}

QUALITY = 82
SOURCE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".bmp"}


LOGO_TILE = (800, 533)          # 3:2, matching .card__media in site.css

LOGO_BLOCK = re.compile(
    r'class="[^"]*card__media--logo[^"]*"[^>]*>\s*<img[^>]*src="([^"]+)"', re.S)


def logo_sources() -> set[tuple[str, str]]:
    """Images the pages mark as logo tiles, as (folder, filename-stem).

    Logos are padded onto a shared canvas so every file ends up the same
    shape. Without that, object-fit: contain renders a wide wordmark at
    full tile width and a square one much narrower — correct, but it reads
    as inconsistent when they sit side by side.

    The pages are the source of truth: add card__media--logo to a card in
    the HTML and this picks it up. No list to keep in sync.
    """
    found = set()
    for page in ROOT.glob("*.html"):
        for src in LOGO_BLOCK.findall(page.read_text()):
            p = pathlib.Path(src)
            found.add((p.parent.as_posix(), p.stem))
    return found


def pad_to_tile(im: "Image.Image", tile: tuple[int, int]) -> "Image.Image":
    """Scale to fit inside the tile, then centre it on a transparent canvas."""
    tw, th = tile
    scale = min(tw / im.width, th / im.height)
    if scale < 1:
        im = im.resize((max(1, round(im.width * scale)),
                        max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", tile, (255, 255, 255, 0))
    canvas.paste(im, ((tw - im.width) // 2, (th - im.height) // 2))
    return canvas


def target_width(path: pathlib.Path) -> int:
    parent = path.parent.name
    if parent in TARGETS:
        return TARGETS[parent]
    return TARGETS["_hero"]        # anything directly in assets/img/, e.g. the group photo


def human(n: int) -> str:
    return f"{n/1024/1024:.1f} MB" if n >= 1024 * 1024 else f"{n/1024:.0f} KB"


def gather() -> list[pathlib.Path]:
    return sorted(p for p in IMG.rglob("*")
                  if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES
                  and p.name not in SKIP)


def backup_path(path: pathlib.Path) -> pathlib.Path:
    """Mirror the folder structure under tools/originals/.

    Using just the filename would be a data-loss bug: news/lecm25.jpg and
    research/lecm25.jpg would land on the same backup and one original
    would be gone for good.
    """
    return BACKUP / path.relative_to(ROOT)


def already_optimised(path: pathlib.Path, logos: set[tuple[str, str]] | None = None) -> bool:
    """True if this file has clearly been through the script already.

    Re-encoding a WebP re-compresses lossy data, so running twice would
    quietly degrade every photo. Skipping is also what makes the script
    safe to run after adding just one new image.
    """
    if path.suffix.lower() != ".webp":
        return False
    rel = path.relative_to(ROOT)
    try:
        with Image.open(path) as im:
            if logos and (rel.parent.as_posix(), rel.stem) in logos:
                return im.size == LOGO_TILE      # logos must be exactly tile-shaped
            return im.width <= target_width(path)
    except Exception:
        return False


def convert(path: pathlib.Path, apply: bool, logos: set[tuple[str, str]] | None = None):
    """Returns (new_relative_path, width, height, old_bytes, new_bytes)."""
    old_bytes = path.stat().st_size
    rel = path.relative_to(ROOT)
    is_logo = bool(logos) and (rel.parent.as_posix(), rel.stem) in logos

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)      # honour camera rotation, then drop EXIF
        has_alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
        im = im.convert("RGBA" if has_alpha else "RGB")

        if is_logo:
            im = im.convert("RGBA")          # keep the padding transparent
            im = pad_to_tile(im, LOGO_TILE)
        else:
            width = target_width(path)
            if im.width > width:
                height = round(im.height * width / im.width)
                im = im.resize((width, height), Image.LANCZOS)

        final = path.with_suffix(".webp")
        if apply:
            backup = backup_path(path)
            backup.parent.mkdir(parents=True, exist_ok=True)
            # Never overwrite an existing backup — the first one is the true
            # original, and a later run must not replace it with a
            # already-compressed version.
            if not backup.exists():
                shutil.copy2(path, backup)
            im.save(final, "WEBP", quality=QUALITY, method=6)
            if final != path:
                path.unlink()
            new_bytes = final.stat().st_size
        else:
            import io
            buffer = io.BytesIO()
            im.save(buffer, "WEBP", quality=QUALITY, method=6)
            new_bytes = buffer.tell()

        return final.relative_to(ROOT), im.width, im.height, old_bytes, new_bytes


def update_references(renames: dict[str, str]) -> int:
    """Point data/*.json and the HTML pages at the new filenames.

    Matching is by folder + filename stem rather than the exact path, so a
    reference that already had the wrong extension (news.json saying .jpg
    for a file that was really a .png) is corrected at the same time.
    """
    by_stem = {}
    for old, new in renames.items():
        p = pathlib.Path(old)
        by_stem[(p.parent.as_posix(), p.stem)] = new

    def resolve(declared: str) -> str | None:
        p = pathlib.Path(declared)
        new = by_stem.get((p.parent.as_posix(), p.stem))
        return new if new and new != declared else None

    changed = 0

    for name, key in (("news.json", "image"), ("people.json", "photo")):
        path = ROOT / "data" / name
        data = json.loads(path.read_text())
        records = (data if name == "news.json"
                   else [m for g in data["groups"] for m in g["members"]])
        touched = False
        for record in records:
            old = record.get(key)
            new = resolve(old) if old else None
            if new:
                record[key] = new
                touched, changed = True, changed + 1
        if touched:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    for page in sorted(ROOT.glob("*.html")):
        text = original = page.read_text()
        for declared in set(re.findall(r'src="(assets/img/[^"]+)"', text)):
            new = resolve(declared)
            if new:
                text = text.replace(f'src="{declared}"', f'src="{new}"')
                changed += 1
        if text != original:
            page.write_text(text, encoding="utf-8")

    return changed


def restore() -> int:
    """Put every backed-up original back and undo the reference changes."""
    if not BACKUP.exists():
        print("Nothing to restore — tools/originals/ does not exist.", file=sys.stderr)
        return 1

    originals = [p for p in BACKUP.rglob("*") if p.is_file()]
    if not originals:
        print("Nothing to restore — tools/originals/ is empty.", file=sys.stderr)
        return 1

    renames = {}
    for backup in originals:
        target = ROOT / backup.relative_to(BACKUP)
        optimised = target.with_suffix(".webp")
        if optimised.exists() and optimised != target:
            optimised.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        renames[str(optimised.relative_to(ROOT))] = str(target.relative_to(ROOT))
        print(f"  restored {target.relative_to(ROOT)}")

    fixed = update_references(renames)
    if MANIFEST.exists():
        MANIFEST.unlink()

    print(f"\n✓ {len(originals)} original(s) restored")
    print(f"✓ {fixed} reference(s) pointed back")
    print("  tools/originals/ is left in place. Delete it yourself if you want to.")
    return 0


def main() -> int:
    global QUALITY
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="actually rewrite the images (default is a report)")
    parser.add_argument("--quality", type=int, default=QUALITY,
                        help=f"WebP quality 1-100 (default {QUALITY})")
    parser.add_argument("--restore", action="store_true",
                        help="undo everything: put the originals back from "
                             "tools/originals/ and revert the references")
    args = parser.parse_args()

    if args.restore:
        return restore()

    QUALITY = args.quality

    everything = gather()
    if not everything:
        print(f"No images found under {IMG.relative_to(ROOT)}/.")
        return 1

    logos = logo_sources()
    files = [f for f in everything if not already_optimised(f, logos)]
    skipped = len(everything) - len(files)

    if not files:
        print(f"All {skipped} image(s) are already optimised — nothing to do.")
        return 0

    print(f"{'Optimising' if args.apply else 'DRY RUN — nothing written'}   "
          f"({len(files)} image{'s' if len(files) != 1 else ''}"
          f"{f', {skipped} already done' if skipped else ''})\n")

    renames, sizes = {}, {}
    total_old = total_new = 0
    rows = []

    for path in files:
        rel_old = str(path.relative_to(ROOT))
        try:
            rel_new, w, h, old_b, new_b = convert(path, args.apply, logos)
        except Exception as err:                      # a corrupt or odd file
            print(f"  ! skipped {path.name}: {err}", file=sys.stderr)
            continue

        rel_new = str(rel_new)
        total_old += old_b
        total_new += new_b
        if rel_new != rel_old:
            renames[rel_old] = rel_new
        sizes[rel_new] = [w, h]
        rel = path.relative_to(ROOT)
        kind = "logo" if (rel.parent.as_posix(), rel.stem) in logos else ""
        rows.append((path.name, old_b, new_b, w, h, kind))

    width = max(len(r[0]) for r in rows)
    for name, old_b, new_b, w, h, kind in rows:
        cut = 100 - (new_b * 100 // max(old_b, 1))
        tag = "  logo tile" if kind else ""
        print(f"  {name:<{width}}  {human(old_b):>9} -> {human(new_b):>8}"
              f"  ({cut:>2}% smaller, {w}x{h}){tag}")

    saved = total_old - total_new
    print(f"\n  total  {human(total_old)} -> {human(total_new)}"
          f"   ({human(saved)} saved, {saved*100//max(total_old,1)}% smaller)")

    if not args.apply:
        print("\nRun again with --apply to write the changes.")
        print(f"Every original is copied to {BACKUP.relative_to(ROOT)}/ first "
              f"(folder structure preserved).")
        print("Nothing is lost: 'python3 tools/5-optimize-images.py --restore' undoes it.")
        return 0

    fixed = update_references(renames)
    MANIFEST.write_text(json.dumps(sizes, indent=2) + "\n", encoding="utf-8")

    print(f"\n✓ {len(rows)} images optimised")
    print(f"✓ {fixed} reference(s) updated in data/*.json and the HTML pages")
    print(f"✓ dimensions written to {MANIFEST.relative_to(ROOT)} "
          f"(stops the page jumping as photos load)")
    print(f"✓ originals backed up to {BACKUP.relative_to(ROOT)}/")
    print("\nOriginals are untouched in tools/originals/. To undo everything:")
    print("  python3 tools/5-optimize-images.py --restore")
    print("Delete that folder once you are happy — it is gitignored either way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
