/* =====================================================================
   STEP 1 — collect the image URLs from a page of the old Google Site.

   Google Sites lazy-loads images and serves them downscaled. This script
   scrolls the whole page to force everything to load, collects the images
   in the order they appear, and records both the full-resolution URL and
   the one the page actually used.

   HOW TO RUN IT
   -------------
   1. Open one page of the old site in Chrome, Edge or Firefox, e.g.
        https://sites.google.com/tamu.edu/karthein-lab/home
   2. Press F12  (Mac: Cmd-Option-I) to open developer tools.
   3. Click the "Console" tab.
   4. If the console warns you about pasting, type   allow pasting   and
      press Enter. (Chrome asks this the first time.)
   5. Paste this entire file and press Enter.
   6. Wait for it to finish scrolling. It prints a table of what it found,
      a note about anything it skipped, and copies a JSON block to your
      clipboard.
   7. Paste that JSON into a new file in the tools/ folder, named after
      the page:  tools/urls-home.json, tools/urls-about-us.json, etc.

   CHECK THE COUNT before moving on. Expected, roughly:
        home        ~24    (banner, group photo, 21 news photos, funders)
        about-us    ~19    (banner, PI, 2 postdocs, 7 students, 8 collaborators)
        research     ~5
        contact      ~1
   If a page comes back short, see "IF IMAGES ARE MISSING" at the bottom.
   ===================================================================== */

(async () => {
  const SCROLL_STEP = 600;
  const SETTLE_MS = 120;

  // Portraits on Google Sites render small — headshots are often only
  // ~200px wide. Anything at or above this is treated as content.
  const MIN_WIDTH = 120;
  const MIN_HEIGHT = 120;

  console.log("Scrolling to load every image…");

  const startY = window.scrollY;
  for (let y = 0; y < document.body.scrollHeight; y += SCROLL_STEP) {
    window.scrollTo(0, y);
    await new Promise((r) => setTimeout(r, SETTLE_MS));
  }
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise((r) => setTimeout(r, 1000));
  window.scrollTo(0, startY);

  const all = [...document.querySelectorAll("img")].filter((img) =>
    (img.currentSrc || img.src || "").includes("googleusercontent.com"));

  // The site logo is one file rendered two or three times, once per nav
  // variant. Content images appear exactly once. Counting occurrences
  // separates them without guessing at sizes.
  const baseOf = (url) => url.replace(/=[-\w]+$/, "");
  const occurrences = new Map();
  all.forEach((img) => {
    const b = baseOf(img.currentSrc || img.src);
    occurrences.set(b, (occurrences.get(b) || 0) + 1);
  });

  const seen = new Set();
  const images = [];
  const skipped = [];

  all.forEach((img) => {
    const src = img.currentSrc || img.src;
    const base = baseOf(src);
    const w = img.naturalWidth || 0;
    const h = img.naturalHeight || 0;

    if (seen.has(base)) return;
    seen.add(base);

    if (occurrences.get(base) > 1) {
      skipped.push({ reason: `repeated ${occurrences.get(base)}x (site logo)`, size: `${w}x${h}` });
      return;
    }
    if (img.closest("header, nav, footer")) {
      skipped.push({ reason: "inside header/nav/footer", size: `${w}x${h}` });
      return;
    }
    if (w < MIN_WIDTH || h < MIN_HEIGHT) {
      skipped.push({ reason: `too small (under ${MIN_WIDTH}x${MIN_HEIGHT})`, size: `${w}x${h}` });
      return;
    }

    images.push({
      index: images.length + 1,
      // "=s0" asks googleusercontent for the untouched upload rather than
      // the downscaled copy on screen.
      url: base + "=s0",
      // Keep what the page actually loaded. If Google refuses the
      // full-resolution request, the downloader falls back to this.
      original: src,
      displayed: `${w}x${h}`,
      alt: (img.alt || "").trim(),
    });
  });

  const payload = {
    page: (location.pathname.split("/").pop() || "home"),
    capturedFrom: location.href,
    images,
  };

  const json = JSON.stringify(payload, null, 2);

  console.log(`Found ${images.length} content images:`);
  console.table(images.map(({ index, displayed, alt }) => ({ index, displayed, alt })));

  if (skipped.length) {
    console.log(`Skipped ${skipped.length}:`);
    console.table(skipped);
  }

  try {
    copy(json);
    console.log("%c✓ JSON copied to your clipboard — paste it into tools/urls-<page>.json",
                "color:#6e3ff3;font-weight:bold");
  } catch (e) {
    console.log("Clipboard unavailable — select and copy the JSON printed below.");
  }
  console.log(json);

  // Retrievable if the clipboard copy silently fails.
  window.__labImages = payload;
  console.log("%cAlso saved as window.__labImages — run  copy(JSON.stringify(__labImages, null, 2))  to retry the copy.",
              "color:#56535f");

  /* IF IMAGES ARE MISSING
     ---------------------
     Lower MIN_WIDTH / MIN_HEIGHT at the top of this script and run it
     again. Decorative dividers are the only thing the threshold is meant
     to exclude, so going down to 80 is safe.

     If the count is still short, the page may not have finished
     lazy-loading. Scroll to the very bottom by hand, wait a few seconds,
     scroll back to the top, then re-run. */
})();
