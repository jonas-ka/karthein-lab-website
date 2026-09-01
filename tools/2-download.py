#!/usr/bin/env python3
"""
STEP 2 — download every image collected in step 1.

Reads tools/urls-*.json, downloads each image at full resolution into
tools/raw/, and builds tools/raw/contact-sheet.html so you can see at a
glance which numbered file is which picture.

    python3 tools/2-download.py

Nothing to install — standard library only. Re-running skips files that
are already downloaded, so it is safe to interrupt.
"""

import argparse
import json
import pathlib
import ssl
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
RAW = TOOLS / "raw"

# Google refuses image requests that don't look like a browser tab loading a
# page. A plain urllib request gets 403, so we send what Chrome sends,
# including the Referer that marks this as coming from the site itself.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sites.google.com/",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
}

CERT_HELP = """
Python cannot verify Google's HTTPS certificate.

This is almost always because Python was installed from python.org and carries
its own certificate store, separate from the one your operating system keeps.
It is not a problem with your network or with Google.

Fix it with either of these:

  1. Install the certificate bundle Python expects (works everywhere):

         python3 -m pip install --upgrade certifi

     Then run this script again — it picks certifi up automatically.

  2. On macOS, python.org installers ship a one-click fixer. Run:

         open "/Applications/Python 3.12/Install Certificates.command"

     substituting your version number. Check which you have with:

         ls /Applications | grep Python

If neither works and you just want the images, you can skip verification for
this one-off download of public images from Google:

     python3 tools/2-download.py --insecure
"""


def ssl_context(insecure: bool = False) -> ssl.SSLContext:
    """Prefer certifi's CA bundle, fall back to whatever Python was built with."""
    if insecure:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


FORBIDDEN_HELP = """
Google returned 403 Forbidden for every image.

That is Google declining the request, not a permissions problem with your site.
Two things cause it, and this script already tries to work around both: sending
browser-like headers, and stepping down from the =s0 full-resolution request to
ordinary sizes.

If you are seeing this after those attempts, the images are almost certainly
tied to your signed-in Google session — which happens with Workspace-hosted
Sites. A script running outside the browser has no such session.

Use the in-browser downloader instead. It runs inside the page, where your
session already exists:

    tools/1b-download-in-browser.js

Open tools/README.md and follow "Plan B". It saves files with the same names
this script would have used, so step 3 works exactly the same afterwards.
"""


class CertificateProblem(Exception):
    """Raised once, to stop the run instead of failing 46 times over."""


def size_variants(url: str, original: str | None) -> list[str]:
    """Biggest first, ending with exactly what the browser loaded.

    =s0 asks for the untouched upload, but Google rejects it on some assets,
    so we walk down to progressively more ordinary requests. The last
    candidate is the URL the page itself used, which is known to work.
    """
    base = url[: -len("=s0")] if url.endswith("=s0") else url.rsplit("=", 1)[0]
    candidates = [url, base + "=w2400", base + "=w1600"]
    if original and original not in candidates:
        candidates.append(original)
    elif base + "=w1280" not in candidates:
        candidates.append(base + "=w1280")
    return candidates


def download(url: str, dest: pathlib.Path, context: ssl.SSLContext,
             original: str | None = None) -> tuple[bool, str]:
    """Fetch one image, trying progressively smaller size directives."""
    candidates = size_variants(url, original)

    last = "unknown error"
    for candidate in candidates:
        try:
            request = urllib.request.Request(candidate, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.URLError as err:
            if isinstance(getattr(err, "reason", None), ssl.SSLCertVerificationError):
                raise CertificateProblem from err
            last = str(err)
            continue
        except (TimeoutError, ssl.SSLError) as err:
            if isinstance(err, ssl.SSLCertVerificationError):
                raise CertificateProblem from err
            last = str(err)
            continue

        if not data:
            last = "empty response"
            continue

        # Give the file the extension its bytes actually deserve.
        suffix = ".jpg"
        if data[:8] == b"\x89PNG\r\n\x1a\n" or "png" in content_type:
            suffix = ".png"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            suffix = ".webp"
        elif data[:6] in (b"GIF87a", b"GIF89a"):
            suffix = ".gif"

        final = dest.with_suffix(suffix)
        final.write_bytes(data)
        size_used = candidate.rsplit("=", 1)[-1]
        return True, f"{final.name}  ({len(data) // 1024} KB, {size_used})"

    return False, last


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download images collected by tools/1-collect-urls.js")
    parser.add_argument(
        "--insecure", action="store_true",
        help="skip HTTPS certificate verification (last resort — see the note "
             "printed if verification fails)")
    args = parser.parse_args()

    context = ssl_context(args.insecure)
    if args.insecure:
        print("⚠  Certificate verification is OFF for this run.\n")

    sources = sorted(TOOLS.glob("urls-*.json"))
    if not sources:
        print(
            "No tools/urls-*.json files found.\n"
            "Run tools/1-collect-urls.js in your browser first, then save the\n"
            "JSON it prints as tools/urls-home.json (and one per other page).",
            file=sys.stderr,
        )
        return 1

    RAW.mkdir(parents=True, exist_ok=True)
    sheet: list[tuple[str, str, str]] = []
    failures = 0
    forbidden = 0
    malformed = 0

    for source in sources:
        raw_text = source.read_text().strip()
        if not raw_text:
            print(f"\n⚠  {source.name} is empty — skipping.\n"
                  f"   The clipboard copy in step 1 probably didn't land. Re-run\n"
                  f"   tools/1-collect-urls.js on that page and paste the JSON again.",
                  file=sys.stderr)
            malformed += 1
            continue

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as err:
            print(f"\n⚠  {source.name} is not valid JSON ({err.msg}, line {err.lineno})"
                  f" — skipping.\n"
                  f"   It should start with '{{' and end with '}}'. If you pasted from\n"
                  f"   the console, make sure you copied the JSON block and not the\n"
                  f"   table above it. Re-run step 1 for that page if unsure.",
                  file=sys.stderr)
            malformed += 1
            continue

        page = payload.get("page") or source.stem.replace("urls-", "")
        images = payload.get("images", [])
        if not images:
            print(f"\n⚠  {source.name} lists no images — skipping.", file=sys.stderr)
            continue

        print(f"\n{source.name} — {len(images)} images ({page})")

        for item in images:
            stem = f"{page}-{item['index']:02d}"
            existing = next(iter(RAW.glob(stem + ".*")), None)
            if existing:
                print(f"  · {existing.name} already downloaded")
                sheet.append((existing.name, item.get("alt", ""), item.get("displayed", "")))
                continue

            try:
                ok, detail = download(item["url"], RAW / stem, context,
                                      item.get("original"))
            except CertificateProblem:
                print(CERT_HELP, file=sys.stderr)
                print("Images already downloaded are kept — rerunning resumes "
                      "where this stopped.", file=sys.stderr)
                return 2

            if ok:
                print(f"  ✓ {detail}")
                sheet.append((detail.split()[0], item.get("alt", ""), item.get("displayed", "")))
            else:
                print(f"  ✗ {stem}: {detail}", file=sys.stderr)
                failures += 1
                if "403" in detail:
                    forbidden += 1

    # Contact sheet, so you can match numbers to pictures without opening 46 files.
    cards = "\n".join(
        f'''  <figure>
    <img src="{name}" alt="" loading="lazy">
    <figcaption><code>{name}</code>{f"<br><small>{alt}</small>" if alt else ""}</figcaption>
  </figure>'''
        for name, alt, _ in sheet
    )

    (RAW / "contact-sheet.html").write_text(
        f"""<!DOCTYPE html>
<meta charset="utf-8">
<title>Downloaded images</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 2rem; background: #fafafb; color: #171520; }}
  h1 {{ font-size: 1.4rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1.5rem; }}
  figure {{ margin: 0; }}
  img {{ width: 100%; aspect-ratio: 4/3; object-fit: cover; border-radius: 4px; background: #eee; }}
  figcaption {{ margin-top: .4rem; font-size: .8rem; color: #56535f; }}
  code {{ color: #500000; }}
</style>
<h1>{len(sheet)} images downloaded</h1>
<p>Check the order matches what you expect, then run
   <code>python3 tools/3-rename.py</code>.</p>
<div class="grid">
{cards}
</div>
""",
        encoding="utf-8",
    )

    print(f"\nDone. {len(sheet)} images in tools/raw/")
    print(f"Open tools/raw/contact-sheet.html to see them all at once.")
    if malformed:
        print(f"\n{malformed} urls file(s) were empty or unreadable and were skipped.",
              file=sys.stderr)

    if forbidden:
        print(FORBIDDEN_HELP, file=sys.stderr)
    elif failures:
        print(f"\n{failures} image(s) failed — see the errors above.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
