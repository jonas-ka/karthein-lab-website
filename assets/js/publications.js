/* Karthein Lab — publications.
   -------------------------------------------------------------------
   Papers come from INSPIRE-HEP, which indexes nuclear and particle
   physics and hands back clean structured metadata (journal, DOI,
   arXiv, citations) — so nothing has to be typed in by hand.

   How it loads:
     1. paint the committed snapshot in data/publications-cache.json
        (instant, works even if INSPIRE is unreachable)
     2. quietly re-fetch live from INSPIRE and repaint if anything changed
     3. merge in anything listed by hand in data/publications-extra.json

   Everything on screen can be exported as BibTeX, RIS, CSV or plain text.
   ------------------------------------------------------------------- */

(function () {
  "use strict";

  /* ===================== configuration ===================== */

  var CONFIG = {
    // INSPIRE author record. Find yours at inspirehep.net → search your
    // name → the number at the end of the author-page URL.
    // NOTE: there is a *different* physicist named Jamie M. Karthein
    // (recid 1844379), also credited to Texas A&M, so matching by name
    // would mix the two profiles. Always match on this ID.
    authorRecid: 1819057,

    // Surnames highlighted in author lists (add students as they publish).
    groupSurnames: [
      "Karthein", "König", "Konig", "Rickey", "Schnoor",
      "Limarenko", "Moenter", "Daniels", "Chhabra", "Goodson", "Kulkarni"
    ],

    maxAuthorsShown: 10,
    apiBase: "https://inspirehep.net/api/literature"
  };

  /* ===================== element handles ===================== */

  var host      = document.querySelector("[data-publications]");
  if (!host) return;

  var search    = document.querySelector("#pub-search");
  var yearSel   = document.querySelector("#pub-year");
  var typeSel   = document.querySelector("#pub-type");
  var countEl   = document.querySelector("[data-pub-count]");
  var statusEl  = document.querySelector("[data-pub-status]");
  var exportBtn = document.querySelector("[data-export-toggle]");
  var exportMenu= document.querySelector("[data-export-menu]");

  var ALL = [];       // every paper we know about
  var VISIBLE = [];   // what the current filters leave

  /* ===================== small helpers ===================== */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // "Karthein, Jonas Maximilian" -> "J. M. Karthein"
  function displayName(fullName) {
    var parts = String(fullName).split(",");
    if (parts.length < 2) return fullName;
    var last = parts[0].trim();
    var given = parts[1].trim();
    var initials = given.split(/[\s.]+/).filter(Boolean)
      .map(function (w) { return w[0].toUpperCase() + "."; }).join(" ");
    return (initials ? initials + " " : "") + last;
  }

  function surnameOf(fullName) {
    return String(fullName).split(",")[0].trim();
  }

  function isGroupMember(author) {
    if (author.recid && Number(author.recid) === CONFIG.authorRecid) return true;
    var s = surnameOf(author.full_name);
    return CONFIG.groupSurnames.some(function (n) {
      return n.localeCompare(s, undefined, { sensitivity: "base" }) === 0;
    });
  }

  /* ===================== normalising INSPIRE records ===================== */

  function fromInspire(hit) {
    var m = hit.metadata || {};
    var pubInfo = (m.publication_info || []).find(function (p) { return p.journal_title; })
                  || (m.publication_info || [])[0] || {};
    var eprint = (m.arxiv_eprints || [])[0] || {};
    var doi = (m.dois || [])[0] || {};

    var year = pubInfo.year
      || (m.earliest_date ? parseInt(String(m.earliest_date).slice(0, 4), 10) : null);

    var pages = pubInfo.artid
      || (pubInfo.page_start
            ? pubInfo.page_start + (pubInfo.page_end ? "-" + pubInfo.page_end : "")
            : "");

    var docTypes = m.document_type || [];
    var kind = "article";
    if (docTypes.indexOf("thesis") > -1) kind = "thesis";
    else if (docTypes.indexOf("conference paper") > -1) kind = "proceedings";
    else if (docTypes.indexOf("book chapter") > -1) kind = "chapter";
    else if (!pubInfo.journal_title) kind = "preprint";

    return {
      id: String(m.control_number || hit.id),
      title: ((m.titles || [])[0] || {}).title || "Untitled",
      authors: (m.authors || []).map(function (a) {
        return { full_name: a.full_name, recid: a.recid };
      }),
      collaboration: ((m.collaborations || [])[0] || {}).value || "",
      journal: pubInfo.journal_title || "",
      volume: pubInfo.journal_volume || "",
      issue: pubInfo.journal_issue || "",
      pages: pages,
      year: year,
      doi: doi.value || "",
      arxiv: eprint.value || "",
      arxivCategory: (eprint.categories || [])[0] || "",
      citations: m.citation_count || 0,
      kind: kind,
      texkey: (m.texkeys || [])[0] || "",
      inspire: "https://inspirehep.net/literature/" + (m.control_number || hit.id)
    };
  }

  // A hand-written entry from publications-extra.json uses the same shape;
  // this just fills in anything left out.
  function fromManual(entry, index) {
    return Object.assign({
      id: "manual-" + index,
      authors: [],
      collaboration: "",
      journal: "", volume: "", issue: "", pages: "",
      doi: "", arxiv: "", arxivCategory: "",
      citations: 0, kind: "article", texkey: "", inspire: ""
    }, entry, {
      authors: (entry.authors || []).map(function (a) {
        return typeof a === "string" ? { full_name: a } : a;
      })
    });
  }

  /* ===================== loading ===================== */

  function inspireUrl() {
    var params = new URLSearchParams({
      q: "authors.recid:" + CONFIG.authorRecid,
      sort: "mostrecent",
      size: "250",
      fields: [
        "titles", "authors.full_name", "authors.recid", "publication_info",
        "arxiv_eprints", "dois", "earliest_date", "citation_count",
        "document_type", "texkeys", "control_number", "collaborations"
      ].join(",")
    });
    return CONFIG.apiBase + "?" + params.toString();
  }

  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
  }

  function merge(inspirePapers, manualPapers) {
    var seen = new Set();
    inspirePapers.forEach(function (p) {
      if (p.doi) seen.add(p.doi.toLowerCase());
      if (p.arxiv) seen.add("arxiv:" + p.arxiv);
    });
    // Skip a manual entry if INSPIRE already has the same paper.
    var extras = manualPapers.filter(function (p) {
      if (p.doi && seen.has(p.doi.toLowerCase())) return false;
      if (p.arxiv && seen.has("arxiv:" + p.arxiv)) return false;
      return true;
    });
    return inspirePapers.concat(extras).sort(function (a, b) {
      return (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title);
    });
  }

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.classList.toggle("status--error", !!isError);
    statusEl.hidden = !text;
  }

  function load() {
    setStatus("Loading publications…");

    var cached = getJSON("data/publications-cache.json").catch(function () { return null; });
    var manual = getJSON("data/publications-extra.json").catch(function () { return []; });

    // Step 1 + 3: paint the snapshot straight away.
    Promise.all([cached, manual]).then(function (r) {
      var snapshot = r[0], extras = r[1] || [];
      if (snapshot && snapshot.papers && snapshot.papers.length) {
        ALL = merge(snapshot.papers, extras.map(fromManual));
        buildYearOptions();
        applyFilters();
        setStatus("");
      }

      // Step 2: refresh from INSPIRE in the background.
      getJSON(inspireUrl())
        .then(function (data) {
          var hits = ((data.hits || {}).hits) || [];
          if (!hits.length) throw new Error("no records returned");
          ALL = merge(hits.map(fromInspire), extras.map(fromManual));
          buildYearOptions();
          applyFilters();
          setStatus("");
        })
        .catch(function (err) {
          if (ALL.length) {
            setStatus("Showing the most recent saved copy — live update from INSPIRE-HEP is unavailable right now.");
          } else {
            host.innerHTML = "";
            setStatus("Publications could not be loaded from INSPIRE-HEP (" + err.message +
                      "). Try again in a moment, or browse the full list on INSPIRE.", true);
          }
        });
    });
  }

  /* ===================== filtering ===================== */

  function buildYearOptions() {
    if (!yearSel) return;
    var current = yearSel.value;
    var years = Array.from(new Set(ALL.map(function (p) { return p.year; })
      .filter(Boolean))).sort(function (a, b) { return b - a; });
    yearSel.innerHTML = '<option value="">All years</option>' +
      years.map(function (y) { return '<option value="' + y + '">' + y + "</option>"; }).join("");
    if (current) yearSel.value = current;
  }

  function applyFilters() {
    var q = (search && search.value || "").trim().toLowerCase();
    var year = yearSel && yearSel.value;
    var kind = typeSel && typeSel.value;

    VISIBLE = ALL.filter(function (p) {
      if (year && String(p.year) !== year) return false;
      if (kind && p.kind !== kind) return false;
      if (!q) return true;
      var haystack = [
        p.title, p.journal, p.collaboration, p.year,
        p.authors.map(function (a) { return a.full_name; }).join(" ")
      ].join(" ").toLowerCase();
      return haystack.indexOf(q) > -1;
    });

    render();
  }

  /* ===================== rendering ===================== */

  function nameHtml(a) {
    var name = esc(displayName(a.full_name));
    return isGroupMember(a) ? '<span class="me">' + name + "</span>" : name;
  }

  function authorsHtml(p) {
    if (!p.authors.length) return "";
    var list = p.authors;
    var truncated = list.length > CONFIG.maxAuthorsShown + 2;

    if (!truncated) {
      var all = list.map(nameHtml).join(", ");
      if (p.collaboration) {
        all += ' <span class="tag">' + esc(p.collaboration) + " collaboration</span>";
      }
      return all;
    }

    // On big collaboration papers the point of the list is showing who from
    // the lab is on it — so members are never truncated away, even if they
    // are the 40th author.
    var head = list.slice(0, CONFIG.maxAuthorsShown);
    var hidden = list.slice(CONFIG.maxAuthorsShown);
    var hiddenMembers = hidden.filter(isGroupMember);

    var names = head.map(nameHtml).join(", ") + ", et al.";
    if (hiddenMembers.length) {
      names += " incl. " + hiddenMembers.map(nameHtml).join(", ");
    }
    names += ' <span class="tag">' + list.length + " authors</span>";

    if (p.collaboration) {
      names += ' <span class="tag">' + esc(p.collaboration) + " collaboration</span>";
    }
    return names;
  }

  function metaHtml(p) {
    var bits = [];

    if (p.journal) {
      var ref = esc(p.journal);
      if (p.volume) ref += " " + esc(p.volume);
      if (p.pages) ref += ", " + esc(p.pages);
      bits.push('<span class="journal">' + ref + "</span>");
    } else {
      bits.push('<span class="tag">Preprint</span>');
    }

    if (p.doi) {
      bits.push('<a href="https://doi.org/' + esc(p.doi) + '" rel="noopener">DOI</a>');
    }
    if (p.arxiv) {
      bits.push('<a href="https://arxiv.org/abs/' + esc(p.arxiv) +
                '" rel="noopener">arXiv:' + esc(p.arxiv) + "</a>");
    }
    if (p.inspire) {
      bits.push('<a href="' + esc(p.inspire) + '" rel="noopener">INSPIRE</a>');
    }
    if (p.citations > 0) {
      bits.push("cited " + p.citations + "×");
    }
    return bits.join("");
  }

  function render() {
    if (countEl) {
      countEl.textContent = VISIBLE.length +
        (VISIBLE.length === 1 ? " publication" : " publications");
    }

    if (!VISIBLE.length) {
      host.innerHTML = '<p class="status">Nothing matches those filters.</p>';
      return;
    }

    // group by year, newest first
    var byYear = new Map();
    VISIBLE.forEach(function (p) {
      var y = p.year || "Undated";
      if (!byYear.has(y)) byYear.set(y, []);
      byYear.get(y).push(p);
    });

    var html = Array.from(byYear.keys()).map(function (year) {
      var papers = byYear.get(year).map(function (p) {
        var title = p.doi
          ? '<a href="https://doi.org/' + esc(p.doi) + '" rel="noopener">' + esc(p.title) + "</a>"
          : (p.arxiv
              ? '<a href="https://arxiv.org/abs/' + esc(p.arxiv) + '" rel="noopener">' + esc(p.title) + "</a>"
              : esc(p.title));

        return '<li class="pub">' +
          '<h3 class="pub__title">' + title + "</h3>" +
          '<p class="pub__authors">' + authorsHtml(p) + "</p>" +
          '<p class="pub__meta">' + metaHtml(p) + "</p>" +
        "</li>";
      }).join("");

      return '<section class="pub-year"><h2>' + esc(year) + "</h2>" +
             '<ul class="pub-list">' + papers + "</ul></section>";
    }).join("");

    host.innerHTML = html;
  }

  /* ===================== export ===================== */

  function bibtexKey(p) {
    if (p.texkey) return p.texkey;
    var first = p.authors.length ? surnameOf(p.authors[0].full_name) : "KartheinLab";
    return first.replace(/[^A-Za-z]/g, "") + ":" + (p.year || "0000") + p.id.slice(-3);
  }

  function toBibtex(papers) {
    var typeMap = {
      article: "article", preprint: "article", proceedings: "inproceedings",
      thesis: "phdthesis", chapter: "incollection"
    };
    return papers.map(function (p) {
      var fields = [];
      if (p.authors.length) {
        fields.push(["author", p.authors.map(function (a) { return a.full_name; }).join(" and ")]);
      }
      fields.push(["title", "{" + p.title + "}"]);
      if (p.collaboration) fields.push(["collaboration", p.collaboration]);
      if (p.journal) fields.push(["journal", p.journal]);
      if (p.volume) fields.push(["volume", p.volume]);
      if (p.issue) fields.push(["number", p.issue]);
      if (p.pages) fields.push(["pages", p.pages]);
      if (p.year) fields.push(["year", String(p.year)]);
      if (p.doi) fields.push(["doi", p.doi]);
      if (p.arxiv) {
        fields.push(["eprint", p.arxiv]);
        fields.push(["archivePrefix", "arXiv"]);
        if (p.arxivCategory) fields.push(["primaryClass", p.arxivCategory]);
      }

      var body = fields.map(function (f) {
        return "    " + f[0] + " = {" + String(f[1]).replace(/^\{(.*)\}$/, "$1") + "}";
      }).join(",\n");

      return "@" + (typeMap[p.kind] || "article") + "{" + bibtexKey(p) + ",\n" + body + "\n}";
    }).join("\n\n") + "\n";
  }

  function toRis(papers) {
    var typeMap = {
      article: "JOUR", preprint: "JOUR", proceedings: "CPAPER",
      thesis: "THES", chapter: "CHAP"
    };
    return papers.map(function (p) {
      var lines = ["TY  - " + (typeMap[p.kind] || "JOUR")];
      p.authors.forEach(function (a) { lines.push("AU  - " + a.full_name); });
      lines.push("TI  - " + p.title);
      if (p.journal) lines.push("JO  - " + p.journal);
      if (p.volume) lines.push("VL  - " + p.volume);
      if (p.issue) lines.push("IS  - " + p.issue);
      if (p.pages) lines.push("SP  - " + p.pages);
      if (p.year) lines.push("PY  - " + p.year);
      if (p.doi) lines.push("DO  - " + p.doi);
      if (p.arxiv) lines.push("UR  - https://arxiv.org/abs/" + p.arxiv);
      lines.push("ER  - ");
      return lines.join("\n");
    }).join("\n\n") + "\n";
  }

  function toCsv(papers) {
    var cell = function (v) { return '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"'; };
    var header = ["Year", "Title", "Authors", "Journal", "Volume", "Pages",
                  "DOI", "arXiv", "Citations", "Type"];
    var rows = papers.map(function (p) {
      return [
        p.year, p.title,
        p.authors.map(function (a) { return a.full_name; }).join("; "),
        p.journal, p.volume, p.pages, p.doi, p.arxiv, p.citations, p.kind
      ].map(cell).join(",");
    });
    return header.map(cell).join(",") + "\n" + rows.join("\n") + "\n";
  }

  function toText(papers) {
    return papers.map(function (p, i) {
      var authors = p.authors.map(function (a) { return displayName(a.full_name); }).join(", ");
      var ref = p.journal
        ? p.journal + (p.volume ? " " + p.volume : "") + (p.pages ? ", " + p.pages : "")
        : "preprint";
      var line = (i + 1) + ". " + authors + (authors ? ", " : "") +
                 '"' + p.title + '", ' + ref + (p.year ? " (" + p.year + ")" : "") + ".";
      if (p.doi) line += " doi:" + p.doi;
      else if (p.arxiv) line += " arXiv:" + p.arxiv;
      return line;
    }).join("\n\n") + "\n";
  }

  var FORMATS = {
    bibtex: { fn: toBibtex, ext: "bib",  mime: "application/x-bibtex" },
    ris:    { fn: toRis,    ext: "ris",  mime: "application/x-research-info-systems" },
    csv:    { fn: toCsv,    ext: "csv",  mime: "text/csv" },
    text:   { fn: toText,   ext: "txt",  mime: "text/plain" }
  };

  function download(format) {
    var spec = FORMATS[format];
    if (!spec || !VISIBLE.length) return;
    var blob = new Blob([spec.fn(VISIBLE)], { type: spec.mime + ";charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "karthein-lab-publications." + spec.ext;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  /* ===================== wiring ===================== */

  [search, yearSel, typeSel].forEach(function (control) {
    if (!control) return;
    control.addEventListener("input", applyFilters);
    control.addEventListener("change", applyFilters);
  });

  if (exportBtn && exportMenu) {
    exportBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = exportMenu.hidden;
      exportMenu.hidden = !open;
      exportBtn.setAttribute("aria-expanded", String(open));
    });
    exportMenu.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-format]");
      if (!btn) return;
      download(btn.dataset.format);
      exportMenu.hidden = true;
      exportBtn.setAttribute("aria-expanded", "false");
    });
    document.addEventListener("click", function () {
      exportMenu.hidden = true;
      exportBtn.setAttribute("aria-expanded", "false");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        exportMenu.hidden = true;
        exportBtn.setAttribute("aria-expanded", "false");
      }
    });
  }

  load();
})();
