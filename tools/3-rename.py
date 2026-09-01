#!/usr/bin/env python3
"""
STEP 3 — file the downloaded images into the website under the names the
pages expect.

    python3 tools/3-rename.py            # dry run: shows the plan, moves nothing
    python3 tools/3-rename.py --apply    # actually copies the files

The news and people filenames are read from data/news.json and
data/people.json, so this stays correct as you edit those.

BEFORE YOU RUN IT WITH --apply
------------------------------
Open tools/raw/contact-sheet.html and check the plan below matches the
pictures. Google Sites puts each news photo *above* its headline, so the
order should line up — but if the old site had an extra banner somewhere,
everything after it shifts by one. If that happens, edit LAYOUT below:
`None` means "leave this one in tools/raw/ and don't file it".
"""

import argparse
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "tools" / "raw"


def news_targets() -> list[str]:
    """Image paths for each news item, newest first — the order on the old site."""
    items = json.loads((ROOT / "data" / "news.json").read_text())
    items.sort(key=lambda i: i["date"], reverse=True)
    return [i["image"] for i in items]


def people_targets() -> list[str]:
    """Photo paths for everyone, in the order the old About Us page listed them."""
    data = json.loads((ROOT / "data" / "people.json").read_text())
    return [m["photo"] for g in data["groups"] for m in g["members"] if m.get("photo")]


# ---------------------------------------------------------------------
# Expected image order on each page of the old Google Site.
# Edit these lists if the contact sheet shows something different.
# ---------------------------------------------------------------------

LAYOUT = {
    # home-01 is the wide banner at the very top of the old home page.
    # home-02 is the picture sitting under the welcome paragraph.
    # Then the 21 news photos, then the funding-logos strip at the bottom.
    "home": (
        ["assets/img/group-photo.jpg", "assets/img/home-secondary.jpg"]
        + news_targets()
        + ["assets/img/funders.png"]
    ),

    # about-01 / about-02 are the two header images; the PI portrait is
    # usually the second one. Then postdocs, students, collaborators.
    "about-us": (
        [None, "assets/img/people/jonas-karthein.jpg"]
        + [p for p in people_targets() if "jonas-karthein" not in p]
    ),

    # research-01 is the page banner; the rest are the section pictures.
    "research": [
        None,
        "assets/img/research/neptune.jpg",
        "assets/img/research/isoltrap.jpg",
        "assets/img/research/becola.jpg",
        "assets/img/research/lebit.jpg",
    ],

    # The contact page has only its banner, which the new site doesn't use.
    "contact": [None],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="actually copy the files (default is a dry run)")
    args = parser.parse_args()

    if not RAW.exists():
        print("tools/raw/ not found — run tools/2-download.py first.", file=sys.stderr)
        return 1

    plan, skipped, unplaced = [], [], []

    for page, targets in LAYOUT.items():
        files = sorted(RAW.glob(f"{page}-*.*"))
        files = [f for f in files if f.suffix.lower() in {".jpg", ".png", ".webp", ".gif"}]
        if not files:
            continue

        if len(files) != len(targets):
            print(f"⚠  {page}: downloaded {len(files)} images but the layout "
                  f"expects {len(targets)}. Check the contact sheet — the "
                  f"mapping below may be shifted.\n", file=sys.stderr)

        for i, source in enumerate(files):
            target = targets[i] if i < len(targets) else None
            if target is None:
                skipped.append(source.name)
            else:
                # keep the real extension, whatever the layout says
                dest = ROOT / pathlib.Path(target).with_suffix(source.suffix)
                plan.append((source, dest))

        for source in files[len(targets):]:
            unplaced.append(source.name)

    if not plan and not skipped:
        print("Nothing to do — no downloaded images matched a page in LAYOUT.")
        return 1

    width = max((len(s.name) for s, _ in plan), default=0)
    print(f"{'DRY RUN — nothing will move' if not args.apply else 'Filing images'}\n")
    for source, dest in plan:
        print(f"  {source.name:<{width}}  →  {dest.relative_to(ROOT)}")

    if skipped:
        print(f"\n  Left in tools/raw/ (banners the new site doesn't use): "
              f"{', '.join(skipped)}")
    if unplaced:
        print(f"  Not in the layout, left in tools/raw/: {', '.join(unplaced)}")

    if not args.apply:
        print(f"\n{len(plan)} images ready. Check tools/raw/contact-sheet.html, then run:")
        print("  python3 tools/3-rename.py --apply")
        return 0

    for source, dest in plan:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)      # copy, so tools/raw/ stays as a backup

    # A photo keeps whatever format it arrived in, so a slot declared as .jpg
    # in news.json may have just been written as .png. Left alone that is a
    # silent 404 and the item shows a grey placeholder, so update the JSON to
    # match what actually landed on disk.
    renamed = {}
    for _, dest in plan:
        rel = dest.relative_to(ROOT)
        renamed[str(rel.with_suffix(".jpg"))] = str(rel)

    corrected = 0
    for name, key in (("news.json", "image"), ("people.json", "photo")):
        path = ROOT / "data" / name
        data = json.loads(path.read_text())
        records = (data if name == "news.json"
                   else [m for g in data["groups"] for m in g["members"]])
        changed = False
        for record in records:
            declared = record.get(key)
            if not declared:
                continue
            actual = renamed.get(str(pathlib.Path(declared).with_suffix(".jpg")))
            if actual and actual != declared:
                record[key] = actual
                changed = True
                corrected += 1
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    print(f"\n✓ Copied {len(plan)} images into assets/img/.")
    if corrected:
        print(f"  Updated {corrected} path(s) in data/*.json to match the file "
              f"formats that were saved.")
    print("  Originals are still in tools/raw/ — delete that folder once you're happy.")
    print("  Preview with:  python3 -m http.server 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
