/* Karthein Lab — shared behaviour.
   Renders the news feed and the people page from the JSON files in /data,
   so adding content never means touching HTML. */

(function () {
  "use strict";

  /* ---------- mobile navigation ---------- */

  var toggle = document.querySelector(".nav-toggle");
  var nav = document.querySelector(".nav");

  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Close" : "Menu";
    });
  }

  /* ---------- mark the current page in the nav ---------- */

  var here = document.body.dataset.page;
  if (here) {
    document.querySelectorAll(".nav a[data-nav]").forEach(function (a) {
      if (a.dataset.nav === here) a.setAttribute("aria-current", "page");
    });
  }

  /* ---------- helpers ---------- */

  function el(tag, className, html) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (html != null) node.innerHTML = html;
    return node;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // "2026-07" -> "July 2026"
  function longDate(value) {
    var parts = String(value).split("-");
    var months = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"];
    var m = months[parseInt(parts[1], 10) - 1];
    return m ? m + " " + parts[0] : value;
  }

  function initials(name) {
    return name
      // names can stack titles — "Prof. Dr. Jonas Karthein"
      .replace(/^(?:(?:Prof|Dr|Priv|Mr|Mrs|Ms)\.?\s+)+/i, "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(function (w) { return w[0]; })
      .join("")
      .toUpperCase();
  }

  /* ---------- intrinsic sizes ----------
     tools/5-optimize-images.py records each photo's dimensions. Setting
     them on the element lets the browser reserve the right space before the
     file arrives, so text doesn't jump down the page as photos load.
     Entirely optional — without the manifest everything still works. */

  var IMAGE_SIZES = {};

  function applySize(img, src) {
    var size = IMAGE_SIZES[src.replace(/^\//, "")];
    if (size) {
      img.width = size[0];
      img.height = size[1];
    }
  }

  // Show a coloured placeholder instead of a broken-image icon.
  // Photos get saved in whatever format they came in, so a path recorded as
  // .jpg may actually be a .png on disk. Rather than making that a silent
  // failure, try the other common extensions before giving up.
  var IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"];

  function candidatePaths(src) {
    var match = src.match(/^(.*)\.([^./]+)$/);
    if (!match) return [src];
    var stem = match[1];
    var declared = match[2].toLowerCase();
    var paths = [src];
    IMAGE_EXTENSIONS.forEach(function (ext) {
      if (ext !== declared) paths.push(stem + "." + ext);
    });
    return paths;
  }

  function imageInto(container, src, alt, fallbackText, fallbackAttr) {
    if (!src) {
      container.classList.add("is-missing");
      container.setAttribute(fallbackAttr, fallbackText);
      return;
    }

    var paths = candidatePaths(src);
    var attempt = 0;
    var img = new Image();
    img.alt = alt || "";
    img.loading = "lazy";
    img.decoding = "async";

    img.addEventListener("error", function () {
      attempt += 1;
      if (attempt < paths.length) {
        applySize(img, paths[attempt]);
        img.src = paths[attempt];
        return;
      }
      img.remove();
      container.classList.add("is-missing");
      container.setAttribute(fallbackAttr, fallbackText);
    });

    applySize(img, paths[0]);
    img.src = paths[0];
    container.appendChild(img);
  }

  /* ---------- images written directly into the HTML ----------
     The research cards, the hero photo and the masthead logo are in the
     markup rather than generated from JSON, so they need the same
     extension tolerance. Mark them with data-retry and they get it. */

  function wireStaticImages() {
    document.querySelectorAll("img[data-retry]").forEach(function (img) {
      var container = img.parentNode;
      var paths = candidatePaths(img.getAttribute("src") || "");
      var attempt = 0;

      function onFail() {
        attempt += 1;
        if (attempt < paths.length) {
          applySize(img, paths[attempt]);
          img.setAttribute("src", paths[attempt]);
          return;
        }
        img.remove();
        // Containers that carry a label show the placeholder; anything else
        // (the masthead logo) just disappears cleanly.
        if (container && container.hasAttribute("data-fallback")) {
          container.classList.add("is-missing");
        }
      }

      img.addEventListener("error", onFail);
      // The image may already have failed before this script ran.
      if (img.complete && img.naturalWidth === 0) onFail();
    });
  }

  function fail(node, what) {
    node.innerHTML = "";
    node.appendChild(el("p", "status status--error",
      "Could not load " + what + ". If you are previewing this from your " +
      "computer, run a local server (see README) rather than opening the file directly."));
  }

  /* ---------- start-up ---------- */

  // Fetch the size manifest first so dimensions are known before the feed
  // renders. A missing manifest is not an error — the site simply loads
  // without the layout hints.
  var ready = fetch("data/image-sizes.json")
    .then(function (r) { return r.ok ? r.json() : {}; })
    .then(function (sizes) { IMAGE_SIZES = sizes || {}; })
    .catch(function () { IMAGE_SIZES = {}; })
    .then(function () { wireStaticImages(); });

  /* ---------- news feed (home page) ---------- */

  var feedHost = document.querySelector("[data-feed]");

  if (feedHost) {
    var STEP = 8;
    var shown = 0;
    var items = [];
    var list = el("ul", "feed");
    var moreBtn = document.querySelector("[data-feed-more]");

    // First load shows a readable batch; one click then opens the whole
    // archive, rather than making people click through it 8 at a time.
    function renderNext(all) {
      var upto = all ? items.length : Math.min(shown + STEP, items.length);
      items.slice(shown, upto).forEach(function (item) {
        var li = el("li", "feed__item");

        var media = el("div", "feed__media");
        imageInto(media, item.image, item.title, item.title, "data-fallback");

        var text = el("div", "feed__text");
        text.appendChild(el("p", "feed__date", escapeHtml(longDate(item.date))));
        text.appendChild(el("h3", "feed__title", escapeHtml(item.title)));
        // body may contain simple links written by the lab; it is our own file
        text.appendChild(el("div", "feed__body", item.body || ""));

        li.appendChild(media);
        li.appendChild(text);
        list.appendChild(li);
      });
      shown = upto;
      if (moreBtn) {
        var remaining = items.length - shown;
        moreBtn.hidden = remaining <= 0;
        moreBtn.textContent = "Show " + remaining + " older news items";
      }
    }

    ready.then(function () { return fetch("data/news.json"); })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        items = data.slice().sort(function (a, b) {
          return String(b.date).localeCompare(String(a.date));
        });
        feedHost.innerHTML = "";
        feedHost.appendChild(list);
        renderNext(false);
        if (moreBtn) {
          moreBtn.addEventListener("click", function () { renderNext(true); });
        }
      })
      .catch(function () { fail(feedHost, "the news feed"); });
  }

  /* ---------- people page ---------- */

  var peopleHost = document.querySelector("[data-people]");

  if (peopleHost) {
    ready.then(function () { return fetch("data/people.json"); })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        peopleHost.innerHTML = "";

        data.groups.forEach(function (group) {
          var section = el("section", "people-group");
          section.appendChild(el("h2", null, escapeHtml(group.title)));
          section.appendChild(el("div", "spectrum"));

          if (group.layout === "pi") {
            group.members.forEach(function (p) {
              section.appendChild(renderPI(p));
            });
          } else {
            var grid = el("ul", "people-grid");
            group.members.forEach(function (p) {
              grid.appendChild(renderPerson(p));
            });
            section.appendChild(grid);
          }
          peopleHost.appendChild(section);
        });

        if (data.alumni && data.alumni.length) {
          var alumniSection = el("section", "people-group");
          alumniSection.appendChild(el("h2", null, "Former group members"));
          alumniSection.appendChild(el("div", "spectrum"));
          var ul = el("ul", "alumni");
          data.alumni.forEach(function (a) {
            var li = el("li");
            li.appendChild(el("span", "year", escapeHtml(a.year)));
            li.appendChild(el("span", null,
              "<strong>" + escapeHtml(a.name) + "</strong>" +
              (a.next ? " — " + escapeHtml(a.next) : "")));
            ul.appendChild(li);
          });
          alumniSection.appendChild(ul);
          peopleHost.appendChild(alumniSection);
        }
      })
      .catch(function () { fail(peopleHost, "the people list"); });
  }

  function metaLines(p) {
    var bits = [];
    if (p.affiliation) {
      bits.push(p.link
        ? '<a href="' + escapeHtml(p.link) + '">' + escapeHtml(p.affiliation) + "</a>"
        : escapeHtml(p.affiliation));
    }
    if (p.email) {
      bits.push('<a href="mailto:' + escapeHtml(p.email) + '">' + escapeHtml(p.email) + "</a>");
    }
    if (p.project) bits.push("Project: " + escapeHtml(p.project));
    return bits.join("<br>");
  }

  function renderPerson(p) {
    var li = el("li", "person");
    var photo = el("div", "person__photo");
    imageInto(photo, p.photo, p.name, initials(p.name), "data-initials");
    li.appendChild(photo);
    li.appendChild(el("h3", "person__name", escapeHtml(p.name)));
    if (p.role) li.appendChild(el("p", "person__role", escapeHtml(p.role)));
    var meta = metaLines(p);
    if (meta) li.appendChild(el("p", "person__meta", meta));
    return li;
  }

  function renderPI(p) {
    var wrap = el("div", "pi");
    var photo = el("div", "person__photo");
    imageInto(photo, p.photo, p.name, initials(p.name), "data-initials");
    var body = el("div");
    body.appendChild(el("h3", "person__name", escapeHtml(p.name)));
    if (p.role) body.appendChild(el("p", "person__role", escapeHtml(p.role)));
    var meta = metaLines(p);
    if (meta) body.appendChild(el("p", "person__meta", meta));
    if (p.bio) {
      var bio = el("div", "prose");
      bio.style.marginTop = "1.1rem";
      bio.innerHTML = p.bio;
      body.appendChild(bio);
    }
    wrap.appendChild(photo);
    wrap.appendChild(body);
    return wrap;
  }
})();
