#!/usr/bin/env python3
"""
Refresh data/publications-cache.json from INSPIRE-HEP.

The website already queries INSPIRE live in the browser; this script keeps a
committed snapshot alongside it so the page paints instantly and still works
if INSPIRE is slow or unreachable.

Run it by hand:

    python3 scripts/fetch_publications.py

or let .github/workflows/refresh-publications.yml run it on a schedule.
Only the standard library is used, so there is nothing to install.
"""

import json
import pathlib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# INSPIRE author record ID for Jonas Karthein.
# Careful: a different physicist, Jamie M. Karthein (recid 1844379), is also
# credited to Texas A&M in INSPIRE, so never match on the name alone.
AUTHOR_RECID = 1819057

API = "https://inspirehep.net/api/literature"
FIELDS = ",".join([
    "titles", "authors.full_name", "authors.recid", "publication_info",
    "arxiv_eprints", "dois", "earliest_date", "citation_count",
    "document_type", "texkeys", "control_number", "collaborations",
])

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "publications-cache.json"

CERT_HELP = """
Python cannot verify the HTTPS certificate for inspirehep.net.

This usually means Python was installed from python.org and carries its own
certificate store, separate from your operating system's. Fix it with:

    python3 -m pip install --upgrade certifi

or, on macOS, run the bundled fixer (substitute your version number):

    open "/Applications/Python 3.12/Install Certificates.command"
"""


def ssl_context() -> ssl.SSLContext:
    """Prefer certifi's CA bundle, fall back to whatever Python was built with."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_page(page: int, size: int = 250) -> dict:
    query = urllib.parse.urlencode({
        "q": f"authors.recid:{AUTHOR_RECID}",
        "sort": "mostrecent",
        "size": size,
        "page": page,
        "fields": FIELDS,
    })
    request = urllib.request.Request(
        f"{API}?{query}",
        headers={
            "Accept": "application/json",
            # INSPIRE asks that automated clients identify themselves.
            "User-Agent": "karthein-lab-website/1.0 (+https://lab.karthein.com)",
        },
    )
    with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
        return json.load(response)


def normalise(hit: dict) -> dict:
    """Shape one INSPIRE record the way assets/js/publications.js expects."""
    meta = hit.get("metadata", {})
    infos = meta.get("publication_info") or []
    info = next((i for i in infos if i.get("journal_title")), infos[0] if infos else {})

    eprint = (meta.get("arxiv_eprints") or [{}])[0]
    doi = (meta.get("dois") or [{}])[0]

    year = info.get("year")
    if not year and meta.get("earliest_date"):
        try:
            year = int(str(meta["earliest_date"])[:4])
        except ValueError:
            year = None

    if info.get("artid"):
        pages = info["artid"]
    elif info.get("page_start"):
        pages = info["page_start"]
        if info.get("page_end"):
            pages += f"-{info['page_end']}"
    else:
        pages = ""

    types = meta.get("document_type") or []
    if "thesis" in types:
        kind = "thesis"
    elif "conference paper" in types:
        kind = "proceedings"
    elif "book chapter" in types:
        kind = "chapter"
    elif not info.get("journal_title"):
        kind = "preprint"
    else:
        kind = "article"

    recid = meta.get("control_number") or hit.get("id")

    return {
        "id": str(recid),
        "title": (meta.get("titles") or [{}])[0].get("title", "Untitled"),
        "authors": [
            {"full_name": a.get("full_name", ""), "recid": a.get("recid")}
            for a in meta.get("authors", [])
        ],
        "collaboration": (meta.get("collaborations") or [{}])[0].get("value", ""),
        "journal": info.get("journal_title", ""),
        "volume": info.get("journal_volume", ""),
        "issue": info.get("journal_issue", ""),
        "pages": pages,
        "year": year,
        "doi": doi.get("value", ""),
        "arxiv": eprint.get("value", ""),
        "arxivCategory": (eprint.get("categories") or [""])[0],
        "citations": meta.get("citation_count", 0),
        "kind": kind,
        "texkey": (meta.get("texkeys") or [""])[0],
        "inspire": f"https://inspirehep.net/literature/{recid}",
    }


def main() -> int:
    papers, page = [], 1
    while True:
        try:
            payload = fetch_page(page)
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as err:
            reason = getattr(err, "reason", err)
            if isinstance(reason, ssl.SSLCertVerificationError):
                print(CERT_HELP, file=sys.stderr)
                return 2
            print(f"Could not reach INSPIRE-HEP: {err}", file=sys.stderr)
            return 1

        hits = payload.get("hits", {}).get("hits", [])
        papers.extend(normalise(h) for h in hits)

        total = payload.get("hits", {}).get("total", len(papers))
        if len(papers) >= total or not hits:
            break
        page += 1

    if not papers:
        print("INSPIRE returned no records — check AUTHOR_RECID.", file=sys.stderr)
        return 1

    papers.sort(key=lambda p: (-(p["year"] or 0), p["title"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": f"https://inspirehep.net/authors/{AUTHOR_RECID}",
                "papers": papers,
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(papers)} publications to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
