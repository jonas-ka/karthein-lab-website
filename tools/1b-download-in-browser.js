/* =====================================================================
   PLAN B — download the images from inside the browser, as ONE zip file.

   Use this if tools/2-download.py reports "403 Forbidden". Google serves
   these pictures only to a signed-in browser session, which a script
   running outside the browser doesn't have. This runs inside the page,
   where your session already exists.

   Why a zip: Chrome allows exactly one download per user gesture. A loop
   that saves 46 files separately gets the first one and then silently
   drops the rest — no prompt, no error. So this fetches everything into
   memory, packs it into a single archive, and downloads that once.

   HOW TO RUN IT
   -------------
   1. Open a page of the old site, e.g.
        https://sites.google.com/tamu.edu/karthein-lab/about-us
   2. F12 (Mac: Cmd-Option-I) -> Console tab.
   3. If asked, type   allow pasting   and press Enter.
   4. Paste this whole file, press Enter.
   5. Wait — it prints a line per image, then saves one file such as
        karthein-lab-about-us.zip
   6. Unzip it straight into the tools/raw/ folder of the website repo.

   Repeat for each page. The filenames inside match what 2-download.py
   would have produced, so step 3 works unchanged afterwards.
   ===================================================================== */

(async () => {
  const MIN_WIDTH = 120;
  const MIN_HEIGHT = 120;

  const page = location.pathname.split("/").pop() || "home";
  const baseOf = (url) => url.replace(/=[-\w]+$/, "");

  /* ---------- zip writer (stored entries; images are already compressed) ---------- */

  const CRC_TABLE = (() => {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
    return table;
  })();

  const crc32 = (bytes) => {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };

  const makeZip = (files) => {
    const encoder = new TextEncoder();
    const parts = [];
    const central = [];
    let offset = 0;

    for (const file of files) {
      const name = encoder.encode(file.name);
      const crc = crc32(file.data);
      const size = file.data.length;

      const local = new Uint8Array(30 + name.length);
      const lv = new DataView(local.buffer);
      lv.setUint32(0, 0x04034b50, true);
      lv.setUint16(4, 20, true);
      lv.setUint16(6, 0x0800, true);      // UTF-8 filenames
      lv.setUint16(8, 0, true);           // stored
      lv.setUint16(10, 0, true);
      lv.setUint16(12, 0x0021, true);
      lv.setUint32(14, crc, true);
      lv.setUint32(18, size, true);
      lv.setUint32(22, size, true);
      lv.setUint16(26, name.length, true);
      lv.setUint16(28, 0, true);
      local.set(name, 30);
      parts.push(local, file.data);

      const dir = new Uint8Array(46 + name.length);
      const dv = new DataView(dir.buffer);
      dv.setUint32(0, 0x02014b50, true);
      dv.setUint16(4, 20, true);
      dv.setUint16(6, 20, true);
      dv.setUint16(8, 0x0800, true);
      dv.setUint16(10, 0, true);
      dv.setUint16(12, 0, true);
      dv.setUint16(14, 0x0021, true);
      dv.setUint32(16, crc, true);
      dv.setUint32(20, size, true);
      dv.setUint32(24, size, true);
      dv.setUint16(28, name.length, true);
      dv.setUint16(30, 0, true);
      dv.setUint16(32, 0, true);
      dv.setUint16(34, 0, true);
      dv.setUint16(36, 0, true);
      dv.setUint32(38, 0, true);
      dv.setUint32(42, offset, true);
      dir.set(name, 46);
      central.push(dir);

      offset += local.length + size;
    }

    const centralSize = central.reduce((n, c) => n + c.length, 0);
    const end = new Uint8Array(22);
    const ev = new DataView(end.buffer);
    ev.setUint32(0, 0x06054b50, true);
    ev.setUint16(4, 0, true);
    ev.setUint16(6, 0, true);
    ev.setUint16(8, files.length, true);
    ev.setUint16(10, files.length, true);
    ev.setUint32(12, centralSize, true);
    ev.setUint32(16, offset, true);
    ev.setUint16(20, 0, true);

    return new Blob([...parts, ...central, end], { type: "application/zip" });
  };

  /* ---------- find the images ---------- */

  console.log("Scrolling to load every image…");
  const startY = window.scrollY;
  for (let y = 0; y < document.body.scrollHeight; y += 600) {
    window.scrollTo(0, y);
    await new Promise((r) => setTimeout(r, 120));
  }
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise((r) => setTimeout(r, 1000));
  window.scrollTo(0, startY);

  const all = [...document.querySelectorAll("img")].filter((img) =>
    (img.currentSrc || img.src || "").includes("googleusercontent.com"));

  const occurrences = new Map();
  all.forEach((img) => {
    const b = baseOf(img.currentSrc || img.src);
    occurrences.set(b, (occurrences.get(b) || 0) + 1);
  });

  const seen = new Set();
  const targets = [];
  all.forEach((img) => {
    const src = img.currentSrc || img.src;
    const base = baseOf(src);
    if (seen.has(base)) return;
    seen.add(base);
    if (occurrences.get(base) > 1) return;                 // site logo, repeated per nav
    if (img.closest("header, nav, footer")) return;
    if ((img.naturalWidth || 0) < MIN_WIDTH) return;
    if ((img.naturalHeight || 0) < MIN_HEIGHT) return;
    targets.push({ index: targets.length + 1, base, original: src });
  });

  console.log(`Found ${targets.length} images on "${page}". Fetching…`);

  /* ---------- fetch everything into memory ---------- */

  const extFor = (bytes) => {
    if (bytes[0] === 0x89 && bytes[1] === 0x50) return "png";
    if (bytes[0] === 0x52 && bytes[1] === 0x49) return "webp";
    if (bytes[0] === 0x47 && bytes[1] === 0x49) return "gif";
    return "jpg";
  };

  const collected = [];
  const failed = [];
  let blockedByCors = false;

  for (const t of targets) {
    // Full resolution first, then step down to what the page itself used.
    const candidates = [t.base + "=s0", t.base + "=w2400", t.base + "=w1600", t.original];
    let done = false;

    for (const url of candidates) {
      try {
        const response = await fetch(url, { credentials: "include" });
        if (!response.ok) continue;
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (!bytes.length) continue;

        const name = `${page}-${String(t.index).padStart(2, "0")}.${extFor(bytes)}`;
        collected.push({ name, data: bytes });
        console.log(`  ${collected.length}/${targets.length}  ${name}` +
                    `  (${Math.round(bytes.length / 1024)} KB, ${url.slice(url.lastIndexOf("=") + 1)})`);
        done = true;
        break;
      } catch (err) {
        if (err instanceof TypeError) { blockedByCors = true; break; }
      }
    }

    if (blockedByCors) break;
    if (!done) failed.push(t.index);
  }

  if (blockedByCors) {
    console.error("%cThe browser blocked reading these images (CORS).",
                  "color:#7d1f2b;font-weight:bold");
    console.error(
      "Google won't let a script read the bytes, even from its own page.\n" +
      "Use Plan C instead — see tools/README.md:\n" +
      "  1. Cmd-S (Ctrl-S) on this page, choose 'Webpage, Complete'.\n" +
      '  2. python3 tools/2b-match-saved-page.py "/path/to/that_files"');
    return;
  }

  if (!collected.length) {
    console.error("Nothing could be fetched. See Plan C in tools/README.md.");
    return;
  }

  /* ---------- one download, not forty-six ---------- */

  const zip = makeZip(collected);
  const url = URL.createObjectURL(zip);
  const a = document.createElement("a");
  a.href = url;
  a.download = `karthein-lab-${page}.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);

  console.log(`%c✓ karthein-lab-${page}.zip — ${collected.length} images, ` +
              `${Math.round(zip.size / 1024 / 1024 * 10) / 10} MB`,
              "color:#6e3ff3;font-weight:bold");
  if (failed.length) console.warn(`  could not fetch image(s): ${failed.join(", ")}`);
  console.log("Unzip it into tools/raw/ then run:  python3 tools/3-rename.py");

  // If even this single download is blocked, the archive is still here:
  window.__labZipUrl = url;
  console.log("%cNo file saved? Chrome may be blocking downloads from this site.\n" +
              "Fix: click the icon at the right of the address bar and allow\n" +
              "downloads, or open chrome://settings/content/automaticDownloads.\n" +
              "Then run:  location.href = __labZipUrl",
              "color:#56535f");
})();
