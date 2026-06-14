/*
 * litsearch.js — self-contained literature-search popup.
 * Drop `<script src="/litsearch.js"></script>` into any page; it injects a floating
 * "Literature search" button + a modal that calls POST /api/lit-search and renders the
 * deterministic evidence summary (PubMed / Europe PMC / OpenAlex). No dependencies.
 */
(function () {
  if (window.__litSearchLoaded) return;
  window.__litSearchLoaded = true;

  var CSS = `
  .lit-fab{position:fixed;right:22px;bottom:22px;z-index:9998;display:inline-flex;align-items:center;
    gap:8px;padding:12px 18px;border:0;border-radius:999px;background:#1f5f4f;color:#fff;font-weight:700;
    font-size:14px;cursor:pointer;box-shadow:0 10px 30px rgba(20,50,40,.28);font-family:inherit}
  .lit-fab:hover{background:#19503f}
  .lit-overlay{position:fixed;inset:0;z-index:9999;display:none;align-items:flex-start;justify-content:center;
    padding:40px 16px;background:rgba(20,24,22,.5);backdrop-filter:blur(3px);overflow:auto}
  .lit-overlay.open{display:flex}
  .lit-modal{width:min(820px,100%);background:#fbfaf6;color:#1f2422;border-radius:18px;
    box-shadow:0 30px 80px rgba(20,24,22,.35);font-family:inherit;overflow:hidden}
  .lit-head{display:flex;align-items:center;gap:12px;padding:18px 22px;border-bottom:1px solid rgba(0,0,0,.08)}
  .lit-head h2{margin:0;font-size:20px;font-weight:700;flex:1}
  .lit-x{border:0;background:transparent;font-size:22px;line-height:1;cursor:pointer;color:#66706a;padding:4px}
  .lit-body{padding:18px 22px;max-height:70vh;overflow:auto}
  .lit-searchrow{display:flex;gap:8px;margin-bottom:10px}
  .lit-input{flex:1;padding:12px 14px;border:1px solid rgba(0,0,0,.16);border-radius:12px;font-size:15px;
    font-family:inherit;background:#fff;color:#1f2422}
  .lit-go{padding:12px 18px;border:0;border-radius:12px;background:#1f5f4f;color:#fff;font-weight:700;
    font-size:14px;cursor:pointer;font-family:inherit}
  .lit-go:disabled{opacity:.6;cursor:default}
  .lit-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
  .lit-chip{padding:6px 11px;border:1px solid rgba(31,95,79,.3);border-radius:999px;background:#fff;
    color:#1f5f4f;font-size:12px;cursor:pointer}
  .lit-chip:hover{background:#eaf2ee}
  .lit-note{color:#66706a;font-size:12px;margin:2px 0 14px}
  .lit-status{padding:24px 4px;color:#66706a;font-size:14px;text-align:center}
  .lit-err{padding:14px;background:#f6e0da;border:1px solid #e2b4a8;border-radius:10px;color:#7a3a2c;font-size:13.5px}
  .lit-sum{margin:0 0 16px;padding:14px 16px;background:#eef3ef;border:1px solid #cdddd2;border-radius:12px}
  .lit-sum-label{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#3f6654;margin-bottom:7px}
  .lit-sum p{margin:0 0 7px;font-size:13.5px;line-height:1.6;color:#28302b}.lit-sum p:last-child{margin-bottom:0}
  .lit-sec{margin:0 0 16px}
  .lit-sec h3{margin:0 0 8px;font-size:15px;font-weight:700}
  .lit-claim{margin:0 0 7px;padding-left:14px;position:relative;font-size:13.5px;line-height:1.55;color:#2b322e}
  .lit-claim:before{content:"–";position:absolute;left:0;color:#9aa39d}
  .lit-cite{color:#8a938d;font-size:11px}
  .lit-arts{margin-top:8px;display:grid;gap:10px}
  .lit-art{padding:12px 14px;border:1px solid rgba(0,0,0,.1);border-radius:12px;background:#fff}
  .lit-art a{color:#1f5f4f;text-decoration:none;font-weight:700;font-size:14px}
  .lit-art a:hover{text-decoration:underline}
  .lit-meta{margin:5px 0 0;color:#66706a;font-size:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  .lit-badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700}
  .lit-pos{background:#dce9e0;color:#2f5641}.lit-neg{background:#f1e0d2;color:#8a5a2a}
  .lit-neu{background:#e8e8e0;color:#5b605a}
  .lit-abs{margin:7px 0 0;color:#454b47;font-size:12.5px;line-height:1.5}
  .lit-disc{margin:14px 0 0;padding-top:10px;border-top:1px solid rgba(0,0,0,.08);color:#8a938d;font-size:11.5px;line-height:1.5}
  @media(max-width:560px){.lit-fab span{display:none}.lit-fab{padding:14px}}
  `;

  var QUICK = ["LDN long COVID", "POTS treatment", "MCAS antihistamine", "ME/CFS pacing", "small fiber neuropathy IVIG"];

  function el(html) {
    var t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstChild;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var style = document.createElement("style");
  style.textContent = CSS;
  document.head.appendChild(style);

  var fab = el('<button class="lit-fab" title="Search the scientific literature">🔬 <span>Literature search</span></button>');
  var overlay = el(
    '<div class="lit-overlay" role="dialog" aria-modal="true">' +
      '<div class="lit-modal">' +
        '<div class="lit-head"><h2>Literature search</h2><button class="lit-x" aria-label="Close">×</button></div>' +
        '<div class="lit-body">' +
          '<div class="lit-searchrow">' +
            '<input class="lit-input" type="text" placeholder="e.g. low dose naltrexone long COVID" />' +
            '<button class="lit-go">Search</button>' +
          "</div>" +
          '<div class="lit-chips"></div>' +
          '<div class="lit-note">Live search of PubMed, Europe PMC &amp; OpenAlex with an auto-generated evidence summary. Not medical advice.</div>' +
          '<div class="lit-results"></div>' +
        "</div>" +
      "</div>" +
    "</div>"
  );
  document.body.appendChild(fab);
  document.body.appendChild(overlay);

  var input = overlay.querySelector(".lit-input");
  var goBtn = overlay.querySelector(".lit-go");
  var results = overlay.querySelector(".lit-results");
  var chipsBox = overlay.querySelector(".lit-chips");

  QUICK.forEach(function (q) {
    var chip = el('<button class="lit-chip">' + esc(q) + "</button>");
    chip.addEventListener("click", function () {
      input.value = q;
      userEdited = true;
      run();
    });
    chipsBox.appendChild(chip);
  });

  var userEdited = false;
  function open() {
    overlay.classList.add("open");
    // Seed from whatever the page says we're currently looking at, unless the user typed their own.
    if (!userEdited && typeof window.litSearchContext === "function") {
      var seed = "";
      try { seed = (window.litSearchContext() || "").trim(); } catch (e) {}
      if (seed && seed !== input.value.trim()) {
        input.value = seed;
        setTimeout(run, 0);
      }
    }
    setTimeout(function () { input.focus(); }, 30);
  }
  function close() { overlay.classList.remove("open"); }

  fab.addEventListener("click", open);
  overlay.querySelector(".lit-x").addEventListener("click", close);
  overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  goBtn.addEventListener("click", run);
  input.addEventListener("keydown", function (e) { if (e.key === "Enter") run(); });
  input.addEventListener("input", function () { userEdited = true; });
  // Let any page element opt in as a trigger: <a data-litsearch>…</a>
  document.querySelectorAll("[data-litsearch]").forEach(function (n) {
    n.addEventListener("click", function (e) { e.preventDefault(); open(); });
  });
  window.openLitSearch = open;

  var busy = false;
  function run() {
    var q = input.value.trim();
    if (!q || busy) return;
    busy = true;
    goBtn.disabled = true;
    results.innerHTML = '<div class="lit-status">Searching PubMed &amp; friends… (this can take a few seconds)</div>';
    fetch("/api/lit-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q, max_results: 8 }),
    })
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function (e) {
        results.innerHTML = '<div class="lit-err">Search failed: ' + esc(e) + "</div>";
      })
      .finally(function () { busy = false; goBtn.disabled = false; });
  }

  function badge(signal) {
    if (signal === "positive") return '<span class="lit-badge lit-pos">positive signal</span>';
    if (signal === "mixed_or_negative") return '<span class="lit-badge lit-neg">mixed / negative</span>';
    return '<span class="lit-badge lit-neu">' + esc(signal || "neutral") + "</span>";
  }

  function render(d) {
    if (d.error && (!d.articles || !d.articles.length)) {
      results.innerHTML = '<div class="lit-err">' + esc(d.error) + "</div>";
      return;
    }
    var html = "";
    if (d.llm_summary) {
      var paras = d.llm_summary.split(/\n{2,}|\n(?=[-•])/).map(function (p) {
        return "<p>" + esc(p.trim()).replace(/\n/g, "<br>") + "</p>";
      }).join("");
      html += '<div class="lit-sum"><div class="lit-sum-label">AI summary</div>' + paras + "</div>";
    }
    (d.sections || []).forEach(function (s) {
      if (!s.claims || !s.claims.length) return;
      html += '<div class="lit-sec"><h3>' + esc(s.title) + "</h3>";
      s.claims.forEach(function (c) {
        var cites = (c.citation_ids || []).filter(function (x) { return x && x !== "search-plan"; });
        html += '<div class="lit-claim">' + esc(c.text) +
          (cites.length ? ' <span class="lit-cite">[' + esc(cites.join(", ")) + "]</span>" : "") + "</div>";
      });
      html += "</div>";
    });
    if (d.articles && d.articles.length) {
      html += '<div class="lit-sec"><h3>Cited articles (' + d.articles.length + ")</h3><div class=\"lit-arts\">";
      d.articles.forEach(function (a) {
        var meta = [];
        if (a.evidence_type) meta.push(esc(a.evidence_type));
        if (a.journal) meta.push(esc(a.journal));
        if (a.year) meta.push(esc(a.year));
        if (a.citation_count != null) meta.push(esc(a.citation_count) + " citations");
        if (a.open_access) meta.push("open access");
        html += '<div class="lit-art"><a href="' + esc(a.url) + '" target="_blank" rel="noopener">' +
          esc(a.title) + "</a>" +
          '<div class="lit-meta">' + badge(a.signal) + (meta.length ? "<span>" + meta.join(" · ") + "</span>" : "") + "</div>" +
          (a.abstract ? '<p class="lit-abs">' + esc(a.abstract) + (a.abstract.length >= 480 ? "…" : "") + "</p>" : "") +
          "</div>";
      });
      html += "</div></div>";
    }
    if (d.disclaimer) html += '<div class="lit-disc">' + esc(d.disclaimer) + "</div>";
    results.innerHTML = html || '<div class="lit-status">No summary generated.</div>';
  }
})();
