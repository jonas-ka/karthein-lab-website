# Getting your images out of Google Sites

Google Sites doesn't offer an "export images" button, and it serves pictures
**downscaled** — the versions on screen are typically 1280 px wide, not what you
originally uploaded. So it's worth pulling them properly rather than right-clicking
through 46 images.

The trick: Google image URLs end in a size directive (`=w1280`, `=w16383`). Replace
it with `=s0` and you get the **original upload, at full resolution**. The scripts
here do that for you.

Budget about fifteen minutes.

---

## Step 1 — collect the URLs (four times, once per page)

1. Open the old site in Chrome, Edge or Firefox:
   <https://sites.google.com/tamu.edu/karthein-lab/home>
2. Press **F12** (Mac: **Cmd-Option-I**) → click the **Console** tab.
3. Chrome blocks pasting into the console the first time. If it warns you, type
   `allow pasting`, press Enter, and carry on.
4. Open `tools/1-collect-urls.js`, copy the whole file, paste it into the console,
   press Enter.
5. It scrolls the page (this forces every lazy-loaded image to download), then
   prints a table of what it found and copies a JSON block to your clipboard.
6. Make a new file `tools/urls-home.json` and paste the clipboard into it.

Now repeat for the other three pages, saving each as its own file:

| Page | Save the JSON as |
| --- | --- |
| `.../karthein-lab/home` | `tools/urls-home.json` |
| `.../karthein-lab/about-us` | `tools/urls-about-us.json` |
| `.../karthein-lab/research` | `tools/urls-research.json` |
| `.../karthein-lab/contact` | `tools/urls-contact.json` |

The NEPTUNE and Stored-Ions subpages are optional — grab them too if they have
pictures you want.

### Getting the logo

Step 1 deliberately skips the logo — it appears two or three times per page (once
per nav variant), which is exactly how the script tells navigation furniture apart
from content. Grab it separately:

On any page of the old site, open the console and run:

```js
copy([...document.querySelectorAll("img")]
  .map(i => i.currentSrc)
  .find(u => u && u.includes("googleusercontent"))
  .replace(/=[-\w]+$/, "") + "=s0")
```

That copies the logo's full-resolution URL. Paste it into a new browser tab,
right-click the image, *Save image as…*, and save it as **`assets/img/logo.png`**.

This one file is used three ways: the masthead logo (34 px, 28 px on phones), the
browser-tab favicon, and the iOS home-screen icon. Square and at least 180 px is
ideal — larger is fine and downscales sharply on retina screens. A transparent PNG
looks best, since the site sits it straight on the page colour with no box around it.
If the file isn't there, the wordmark simply appears on its own.

## Step 2 — download them

```bash
python3 tools/2-download.py
```

Everything lands in `tools/raw/` as `home-01.jpg`, `home-02.jpg`, `about-us-01.jpg`
and so on, at full resolution. It also writes `tools/raw/contact-sheet.html`.

**Open that contact sheet.** It shows every downloaded image with its filename, so
you can check the order in one glance instead of opening 46 files.

### If it stops with `CERTIFICATE_VERIFY_FAILED`

Python installed from python.org keeps its own certificate store, separate from the
one your operating system maintains, and it often ships empty. Nothing is wrong with
your network or with Google.

```bash
python3 -m pip install --upgrade certifi
```

Then run step 2 again — the script picks certifi up automatically, and resumes where
it stopped, so nothing is downloaded twice.

On macOS there's also a one-click fixer bundled with Python. Find your version with
`ls /Applications | grep Python`, then:

```bash
open "/Applications/Python 3.12/Install Certificates.command"
```

As a last resort, since these are public images from Google, you can skip
verification for this one-off download:

```bash
python3 tools/2-download.py --insecure
```

The same fix applies to `scripts/fetch_publications.py`, which talks to INSPIRE over
HTTPS and would fail the same way.

### If it stops with `403 Forbidden`

Google is declining the request. This is not a permissions problem with your site.

The script already sends browser-like headers and steps down from the `=s0`
full-resolution request through `=w2400`, `=w1600` and finally the exact URL the
page itself loaded. If **all** of those come back 403, the images are tied to your
signed-in Google session — normal for Workspace-hosted Sites — and no script running
outside the browser can reach them.

Go to Plan B.

---

## Plan B — download from inside the browser, as one zip

Runs in the page, where your Google session already exists.

1. Open a page of the old site.
2. F12 → Console → paste **`tools/1b-download-in-browser.js`** → Enter.
3. It prints a line per image as it fetches, then saves a single file,
   e.g. `karthein-lab-about-us.zip`.
4. Unzip it straight into `tools/raw/`. The names inside (`about-us-01.jpg`, …)
   are the ones step 3 expects.

Repeat per page.

**Why a zip rather than separate files?** Chrome allows one download per user
gesture. A loop that saves 46 files gets the first one and then silently discards
the rest — no prompt, no error, just one file in Downloads. Packing everything into
a single archive means asking for one download, which always succeeds.

**If no file appears at all**, Chrome is blocking downloads from the site entirely.
Look for a blocked-download icon at the right-hand end of the address bar and allow
it, or visit `chrome://settings/content/automaticDownloads`. The archive is still in
memory — get it with:

```js
location.href = __labZipUrl
```

**If the console says the browser blocked reading the images (CORS)**, Google is
refusing to let any script read the bytes, even from its own page. Nothing is wrong
on your end. Go to Plan C.

---

## Plan C — save the page, then match it up

This always works, because the browser is just writing out files it already holds.

1. Open a page of the old site. **Scroll right to the bottom, wait a few seconds**
   (this forces the lazy-loaded images to arrive), then scroll back up.
2. Press **Cmd-S** / **Ctrl-S** → choose **Webpage, Complete** → save anywhere.
   You get an HTML file plus a folder ending `_files`.
3. Point the matcher at that folder:

```bash
python3 tools/2b-match-saved-page.py "~/Desktop/About Us_files"
```

It matches the saved files back against your `urls-*.json` — first on the filename,
which the browser derives from the URL, then on exact pixel dimensions for anything
the browser renamed. It prints the plan; add `--apply` to copy them into
`tools/raw/`.

Anything it can't match confidently it lists by name rather than guessing, so you can
drag those few across by hand.

The one cost: you get the resolution the page displayed, usually 1280 px wide, not
the original upload. That is fine here — the site never displays an image wider than
about 1200 px.

---

## Step 3 — file them into the site

```bash
python3 tools/3-rename.py
```

This is a **dry run**: it prints what it would do and moves nothing. Compare the plan
against the contact sheet.

Google Sites puts each news photo directly *above* its headline, so the order should
line up with `data/news.json`. If it's shifted — say the old page had a banner I
didn't account for — open `tools/3-rename.py` and edit the `LAYOUT` dictionary near
the top. `None` means "leave this one alone".

When the plan looks right:

```bash
python3 tools/3-rename.py --apply
```

It **copies** rather than moves, so `tools/raw/` stays as a backup. Delete that
folder once you're happy, and don't commit it.

Then preview:

```bash
python3 -m http.server 8000
```

---

## Two images have no source

`assets/img/research/stored-ions.jpg` and `assets/img/research/ai-digital-twin.jpg`
don't exist on the old site — the old Research page had no picture for Stored-Ions,
and the Genesis Mission work is new. Those two cards will show a maroon placeholder
until you add something. A photo of the MRTOF or the laser table would do nicely.

## If the console approach doesn't appeal

**Save the whole page.** On each page press **Ctrl-S** (Mac: **Cmd-S**) and choose
*Webpage, Complete*. You get a `_files` folder containing every image. Downside:
filenames are meaningless hashes and you only get the displayed resolution, so
you'll be matching them up by eye anyway. Scroll to the bottom of the page first,
or the lazy-loaded images won't be included.

**Google Takeout.** <https://takeout.google.com> → deselect all → select **Sites**.
This exports the whole site including images. Two caveats: it can take hours to
produce, and TAMU's Google Workspace admin may have Takeout disabled for university
accounts — check whether "Sites" even appears in your list.

**Ask for the originals.** Your footer credits the group photo to Olivia Hearne at
TAMU. She'll have the original at print resolution, which will look considerably
better in the hero slot than anything Google Sites will give you back. Worth an
email before you settle for the downscaled copy.

## A note on rights

These are your own photos, so pulling them off your own site is uncontroversial.
Two things worth checking as you go: the group photo needs its credit kept (it's in
the site footer already), and if any funding-agency or collaborator logos come across
in the batch, those are the agencies' marks — reuse them in their existing context
rather than restyling them.
