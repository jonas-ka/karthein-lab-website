# Karthein Lab website

Plain HTML, CSS and JavaScript. **No build step, no framework, nothing to install.**
Cloudflare Pages just serves the folder as-is. That is deliberate: it means the site
cannot break because a dependency changed, and it will still work in five years.

- **Content lives in `data/*.json`**, so adding news or a new student never means
  touching HTML.
- **Publications pull themselves from INSPIRE-HEP**, so that page maintains itself.

---

## 1. Put it on GitHub

Install [GitHub Desktop](https://desktop.github.com/) if you don't already use git
on the command line — it is the least painful route.

1. On GitHub, create a new **private or public** repository called `karthein-lab-website`.
   Do not add a README or `.gitignore`; this folder already has them.
2. Copy everything in this folder into your local clone of that repo.
3. Commit and push.

Command line equivalent, from inside this folder:

```bash
git init
git add .
git commit -m "New lab website"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/karthein-lab-website.git
git push -u origin main
```

## 2. Connect Cloudflare Pages

1. Sign in at [dash.cloudflare.com](https://dash.cloudflare.com) → **Workers & Pages**
   → **Create** → **Pages** → **Connect to Git**.
2. Authorise GitHub and pick your repository.
3. Build settings — this is the part people get wrong, so:
   - **Framework preset:** `None`
   - **Build command:** *leave completely empty*
   - **Build output directory:** `/`
4. **Save and Deploy.** About thirty seconds later you get a live URL ending in
   `.pages.dev`. Check it looks right.

Every `git push` from now on redeploys automatically.

## 3. Point lab.karthein.com at it

Since `karthein.com` is your domain, this is the whole reason for the move.

1. In your new Pages project → **Custom domains** → **Set up a custom domain**.
2. Enter `lab.karthein.com`.
3. If `karthein.com` is already on Cloudflare DNS, Cloudflare adds the record itself —
   accept it and you're done.
   If your DNS is elsewhere, Cloudflare shows you a `CNAME` record to add at your
   registrar: `lab` → `your-project.pages.dev`.
4. HTTPS is issued automatically. Give it a few minutes.

**Do this last**, once you're happy with how the site looks, so the old Google Sites
version stays up until the replacement is ready.

---

## Adding news

Open `data/news.json` and add an entry at the top:

```json
{
  "date": "2026-09",
  "title": "Short, plain headline",
  "image": "assets/img/news/2026-09-something.jpg",
  "body": "<p>A sentence or two. <a href=\"https://example.org\">Links work</a>.</p>"
}
```

- `date` is `YYYY-MM`. Order in the file doesn't matter — the page sorts newest first.
- `image` can be `""` if you don't have a photo yet. A coloured placeholder appears
  instead; nothing looks broken.
- `body` takes simple HTML: `<p>`, `<a>`, `<ul>`/`<li>`, `<em>`, `<strong>`.

The home page shows the eight most recent items and a button that opens the rest.

**Watch the commas.** JSON is strict: every entry except the last needs a trailing
comma, and quotes must be straight (`"`) not curly (`"`). If the page shows
"Could not load the news feed", paste the file into
[jsonlint.com](https://jsonlint.com) — it will point at the line.

## Adding people

`data/people.json`. Same idea. To add a graduate student, drop this into the
`"Graduate students"` group's `members` list:

```json
{
  "name": "Firstname Lastname",
  "photo": "assets/img/people/firstname-lastname.jpg",
  "email": "netid@tamu.edu",
  "project": "MRTOF-LS"
}
```

When someone leaves, move them to the `alumni` list at the bottom of the file.

## Photos

**`tools/README.md`** walks through pulling every image off the old Google Site
automatically, at full original resolution — about fifteen minutes for all of them.
Start there.

**`IMAGES.md`** is the checklist of filenames the site expects, if you'd rather add
them by hand. Every one is optional: missing images render as a tidy coloured
placeholder, never a broken icon, so you can migrate gradually.

---

## Publications

The publications page needs no maintenance. It queries **INSPIRE-HEP**, the standard
literature database for nuclear and particle physics, which returns clean structured
metadata: journal, volume, DOI, arXiv ID, citation counts.

> **Why not Google Scholar?** Scholar has no public API and blocks automated access,
> so any "Scholar integration" is a scraper that breaks and can get the requester
> blocked. INSPIRE is designed to be queried and covers your field properly.

### The one setting that matters

`assets/js/publications.js`, near the top:

```js
authorRecid: 1819057,
```

That is the INSPIRE author record for **Jonas Karthein**
(<https://inspirehep.net/authors/1819057>).

⚠️ **Please confirm this ID is yours before going live.** There is a *different*
physicist, **Jamie M. Karthein** (recid `1844379`), a heavy-ion theorist also credited
to the Texas A&M Cyclotron Institute. Because of that, any name-based lookup would
blend the two of you together — which is exactly why this uses the numeric ID. Open
the link above; if it lists your papers, you're set. If not, search your name on
INSPIRE and copy the number from the end of your author-page URL.

While you're there: anything missing from your INSPIRE profile can be added with the
**claim** button, and it will then appear on the site automatically.

### Group member highlighting

Also in `publications.js`, `groupSurnames` lists the names shown in bold in author
lists. Add students as they start publishing. On large collaboration papers the list
is truncated, but lab members are never truncated away — they appear after
"et al." as "incl. …".

### Export

The **Download list** button exports **whatever the filters currently show** — so you
can, for example, filter to 2025 journal articles and export just those.

| Format | Use it for |
| --- | --- |
| BibTeX | LaTeX bibliographies, proposals |
| RIS | EndNote, Zotero, Mendeley |
| CSV | Excel, Google Sheets, annual reports |
| Plain text | Numbered list to paste into a document |

### Papers INSPIRE doesn't index

INSPIRE covers nuclear and particle physics well, but not everything — quantum
chemistry or astrochemistry work may be missing. Add those by hand to
`data/publications-extra.json`:

```json
[
  {
    "title": "Paper title",
    "authors": ["Karthein, Jonas", "Bera, Partha"],
    "journal": "J. Chem. Phys.",
    "volume": "160",
    "pages": "134301",
    "year": 2026,
    "doi": "10.1063/example",
    "arxiv": "",
    "kind": "article"
  }
]
```

Authors go in `Last, First` order. If a paper is already on INSPIRE (matched by DOI
or arXiv ID) the manual copy is skipped, so duplicates are harmless.

### The cached snapshot

`data/publications-cache.json` is a saved copy. The page paints it instantly, then
refreshes from INSPIRE in the background. If INSPIRE is ever slow or down, visitors
still see the full list.

It ships empty. Fill it either by running:

```bash
python3 scripts/fetch_publications.py
```

If that fails with `CERTIFICATE_VERIFY_FAILED`, run
`python3 -m pip install --upgrade certifi` and try again — python.org builds keep
their own certificate store and it is often empty.

You can also fill the cache by opening the **Actions** tab on GitHub → *Refresh publications* → **Run workflow**.
After that it refreshes itself every Monday and commits any changes, which triggers a
redeploy. If you'd rather not use it, delete `.github/workflows/` — the live query
still works on its own.

---

## Previewing changes on your own machine

Opening `index.html` by double-clicking **will not work** — browsers block pages
loaded from `file://` from reading the JSON files. Start a tiny local server instead:

```bash
cd karthein-lab-website
python3 -m http.server 8000
```

Then visit <http://localhost:8000>. Press `Ctrl-C` to stop.

Alternatively, just push to a branch — Cloudflare builds a preview URL for every
branch, so you can look at changes before merging to `main`.

---

## The internal section

Your intranet link still points at Google Sites, in the nav on every page. That's a
reasonable place to leave it: this site is fully public with no login, so anything
access-controlled genuinely does belong behind your TAMU Google account.

If you ever want it here instead, Cloudflare Access can put a login in front of a
single path (`/internal/*`) on the free tier, restricted to `@tamu.edu` addresses.

---

## File map

```
index.html            Home — group photo, description, news
research.html         Research overview, projects, facilities
people.html           People (rendered from data/people.json)
publications.html     Publications (INSPIRE-HEP + export)
contact.html          Contact details and the Google Form

data/news.json               ← edit to add news
data/people.json             ← edit to add people
data/publications-extra.json ← papers INSPIRE doesn't have
data/publications-cache.json ← auto-generated, don't hand-edit

assets/css/site.css          All styling
assets/js/site.js            Nav, news feed, people rendering
assets/js/publications.js    INSPIRE query, filters, export
assets/img/                  Your photos (see IMAGES.md)

tools/                            One-off: pull images off the old Google Site
scripts/fetch_publications.py     Refreshes the cache
.github/workflows/                Runs that script weekly
_headers                          Cloudflare cache + security headers
```

## Design notes

`assets/img/logo.png` does double duty: it sits at 34 px next to the wordmark in the
masthead (28 px on phones) and is also the browser-tab favicon and the iOS
home-screen icon. Supplying it larger than 34 px is deliberate — the browser
downscales, which keeps it sharp on retina screens. Nothing to generate; replacing
that one file updates all three uses.

The thin ticked rule used as a section divider is unrelated to the favicon. It is an
SVG embedded directly in `site.css` as `--spectrum-svg` and drawn through a CSS mask,
so it takes its colour from `--laser` and is unaffected by anything in `assets/img/`.

Type is Archivo (headings), Source Serif 4 (body) and IBM Plex Mono (dates, metadata),
loaded from Google Fonts. Colours are in one place — the `:root` block at the top of
`site.css`. The maroon is TAMU's `#500000`; the violet accent is a nod to the lasers.
The thin ticked rule used as a divider is an emission spectrum.

News photos are scaled to the column width rather than cropped to a fixed frame, so
nothing is cut off whatever shape they are. Very tall images are capped at 400 px
(340 px on phones) and centred against the page colour. To change that ceiling, edit
`.feed__media img { max-height: … }` in `site.css`.

Image areas use the page colour, so transparent PNGs show no box behind them. The
maroon gradient appears only where a photo is missing.

To change the accent colour site-wide, edit one line:

```css
--laser: #6e3ff3;
```
