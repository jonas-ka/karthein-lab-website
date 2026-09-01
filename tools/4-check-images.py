#!/usr/bin/env python3
"""
Check that every photo referenced in data/*.json actually exists on disk,
and fix the mismatches.

    python3 tools/4-check-images.py           # report only
    python3 tools/4-check-images.py --fix     # correct the JSON to match disk

The usual problem: a photo was saved as a .png but data/news.json still says
.jpg (or the other way round). The browser asks for the name in the JSON,
gets a 404, and shows the grey placeholder — so the picture looks "missing"
even though it is sitting right there in the folder.

--fix rewrites the extension in the JSON to match the file that is actually
present. It never renames or touches your image files.
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".gif"]


def find_actual(declared: pathlib.Path) -> pathlib.Path | None:
    """The file that is really there, whatever extension or casing it uses."""
    full = ROOT / declared
    if full.exists():
        return full

    folder = full.parent
    if not folder.is_dir():
        return None

    # same name, different extension
    for ext in EXTENSIONS:
        candidate = folder / (full.stem + ext)
        if candidate.exists():
            return candidate

    # same name, different capitalisation (matters on the live server even
    # though macOS usually hides it locally)
    for entry in folder.iterdir():
        if entry.is_file() and entry.stem.lower() == full.stem.lower():
            return entry
    return None


HTML_IMG = re.compile(r'src="(assets/img/[^"]+)"')


def html_entries():
    """Images written straight into the pages, not driven by JSON."""
    for page in sorted(ROOT.glob("*.html")):
        text = page.read_text()
        for match in HTML_IMG.finditer(text):
            yield (page, match.group(1))


def entries():
    """Every (label, json path, image path) the site references."""
    news_file = ROOT / "data" / "news.json"
    news = json.loads(news_file.read_text())
    for item in news:
        if item.get("image"):
            yield ("news", news_file, item, "image", item["title"])

    people_file = ROOT / "data" / "people.json"
    people = json.loads(people_file.read_text())
    for group in people["groups"]:
        for member in group["members"]:
            if member.get("photo"):
                yield ("people", people_file, member, "photo", member["name"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true",
                        help="rewrite the JSON so it matches the files on disk")
    args = parser.parse_args()

    ok, repairable, truly_missing = [], [], []
    html_fixes: dict[pathlib.Path, list[tuple[str, str]]] = {}

    # --- images referenced from the HTML pages ---
    seen_html = set()
    for page, declared_str in html_entries():
        declared = pathlib.Path(declared_str)
        actual = find_actual(declared)
        tag = (page.name, declared_str)
        if tag in seen_html:
            continue
        seen_html.add(tag)

        if actual is None:
            truly_missing.append(("html", declared, page.name))
        elif actual == ROOT / declared:
            ok.append(declared)
        else:
            rel = str(actual.relative_to(ROOT))
            html_fixes.setdefault(page, []).append((declared_str, rel))
            repairable.append(("html", page, None, None, declared,
                               actual.relative_to(ROOT), page.name))

    # --- images referenced from the JSON content files ---
    for kind, source, record, key, label in entries():
        declared = pathlib.Path(record[key])
        actual = find_actual(declared)

        if actual is None:
            truly_missing.append((kind, declared, label))
        elif actual == ROOT / declared:
            ok.append(declared)
        else:
            repairable.append((kind, source, record, key, declared,
                               actual.relative_to(ROOT), label))

    print(f"{len(ok)} photo(s) found exactly as referenced")

    if repairable:
        print(f"\n{len(repairable)} mismatch(es) — the file is there under another name:\n")
        for kind, _, _, _, declared, actual, label in repairable:
            where = label if kind == "html" else f"{label[:40]}  ({kind})"
            print(f"  {where}")
            print(f"    referenced: {declared}")
            print(f"    on disk   : {actual}")

    if truly_missing:
        print(f"\n{len(truly_missing)} photo(s) not on disk at all "
              f"(these show the grey placeholder):")
        for kind, declared, label in truly_missing:
            print(f"  {declared}   ({label[:40]})")

    if not repairable:
        if truly_missing:
            print("\nNothing to fix automatically — those files need adding.")
        else:
            print("\nEverything lines up.")
        return 0

    if not args.fix:
        print("\nRun again with --fix to correct the JSON:")
        print("  python3 tools/4-check-images.py --fix")
        return 0

    # Rewrite the src attributes in the HTML pages.
    for page, swaps in html_fixes.items():
        text = page.read_text()
        for old, new in swaps:
            text = text.replace(f'src="{old}"', f'src="{new}"')
        page.write_text(text, encoding="utf-8")
        print(f"\n✓ updated {page.name} ({len(swaps)} image path(s))")

    # Group the JSON edits by file so each is written once.
    by_file: dict[pathlib.Path, list] = {}
    for kind, source, record, key, _, actual, _ in repairable:
        if kind == "html":
            continue
        record[key] = str(actual)
        by_file.setdefault(source, []).append(record)

    news_file = ROOT / "data" / "news.json"
    people_file = ROOT / "data" / "people.json"

    if news_file in by_file:
        news = json.loads(news_file.read_text())
        lookup = {r["title"]: r["image"] for r in by_file[news_file] if "title" in r}
        for item in news:
            if item.get("title") in lookup:
                item["image"] = lookup[item["title"]]
        news_file.write_text(json.dumps(news, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        print(f"\n✓ updated {news_file.relative_to(ROOT)}")

    if people_file in by_file:
        people = json.loads(people_file.read_text())
        lookup = {r["name"]: r["photo"] for r in by_file[people_file] if "name" in r}
        for group in people["groups"]:
            for member in group["members"]:
                if member.get("name") in lookup:
                    member["photo"] = lookup[member["name"]]
        people_file.write_text(json.dumps(people, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
        print(f"✓ updated {people_file.relative_to(ROOT)}")

    print(f"\nFixed {len(repairable)} reference(s). Reload the page "
          f"(Cmd-Shift-R) to see them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
