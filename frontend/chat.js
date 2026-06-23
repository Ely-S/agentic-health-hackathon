/*
 * chat.js — self-contained data-grounded chatbot widget.
 * Drop `<script src="/chat.js"></script>` into any page; it injects a floating
 * "Ask about your results" button + a DOCKED, non-modal corner panel with a
 * scrollable thread that calls POST /api/chat. The bot answers grounded in the
 * on-screen profile + predictions, cites the numbers, and refuses safety/dosing
 * questions. No dependencies.
 *
 * The panel does NOT dim or blur the page — you keep reading + clicking the
 * dashboard while you chat about it. (litsearch.js is a separate, intentionally
 * modal widget; it is not currently loaded on the dashboard pages.)
 */
(function () {
  if (window.__dashChatLoaded) return;
  window.__dashChatLoaded = true;

  // One conversation id per page load, reused on every POST → multi-turn memory.
  var CONV_ID = (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : "conv-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);

  var CSS = `
  .dch-fab{position:fixed;right:22px;bottom:22px;z-index:9998;display:inline-flex;align-items:center;
    gap:8px;padding:12px 18px;border:0;border-radius:999px;background:#2f4a7a;color:#fff;font-weight:700;
    font-size:14px;cursor:pointer;box-shadow:0 10px 30px rgba(20,30,60,.28);font-family:inherit}
  .dch-fab:hover{background:#27406b}
  .dch-overlay{position:fixed;right:22px;bottom:22px;z-index:9999;display:none}
  .dch-overlay.open{display:block}
  .dch-modal{width:min(420px,calc(100vw - 44px));height:min(620px,calc(100vh - 110px));display:flex;flex-direction:column;
    background:#fbfaf6;color:#1f2422;border-radius:18px;box-shadow:0 30px 80px rgba(20,24,30,.4);
    font-family:inherit;overflow:hidden}
  .dch-head{display:flex;align-items:center;gap:10px;padding:15px 18px;border-bottom:1px solid rgba(0,0,0,.08);
    background:#2f4a7a;color:#fff}
  .dch-head h2{margin:0;font-size:16px;font-weight:700;flex:1}
  .dch-x{border:0;background:transparent;font-size:22px;line-height:1;cursor:pointer;color:#dfe6f2;padding:2px}
  .dch-thread{flex:1;overflow:auto;padding:16px 16px 6px;display:flex;flex-direction:column;gap:10px}
  .dch-msg{max-width:88%;padding:10px 13px;border-radius:14px;font-size:13.5px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
  .dch-user{align-self:flex-end;background:#2f4a7a;color:#fff;border-bottom-right-radius:4px}
  .dch-bot{align-self:flex-start;background:#eef1f6;color:#1f2734;border-bottom-left-radius:4px}
  .dch-bot.dch-blocked{background:#f6ecd9;border:1px solid #e2cfa0;color:#6b531f}
  .dch-bot p,.dch-bot ul{margin:0 0 8px}
  .dch-bot p:last-child,.dch-bot ul:last-child{margin-bottom:0}
  .dch-md-ul{padding-left:18px}
  .dch-md-h{display:block;font-weight:700;font-size:14px;margin:4px 0 2px}
  .dch-bot code{background:rgba(0,0,0,.06);padding:1px 4px;border-radius:4px;font-size:12.5px}
  .dch-disc{align-self:flex-start;max-width:88%;color:#8a938d;font-size:11px;line-height:1.45;padding:0 4px 4px}
  .dch-typing{align-self:flex-start;color:#8a938d;font-size:13px;font-style:italic;padding:4px 6px}
  .dch-err{align-self:flex-start;color:#8a5a2a;font-size:12.5px}
  .dch-inrow{display:flex;gap:8px;padding:12px 14px;border-top:1px solid rgba(0,0,0,.08);background:#fff}
  .dch-input{flex:1;padding:11px 13px;border:1px solid rgba(0,0,0,.16);border-radius:12px;font-size:14px;
    font-family:inherit;resize:none;max-height:90px;background:#fff;color:#1f2422}
  .dch-send{padding:11px 16px;border:0;border-radius:12px;background:#2f4a7a;color:#fff;font-weight:700;
    font-size:14px;cursor:pointer;font-family:inherit}
  .dch-send:disabled{opacity:.55;cursor:default}
  .dch-hint{padding:0 16px 10px;color:#8a938d;font-size:11px;line-height:1.4}
  @media(max-width:560px){.dch-fab span{display:none}.dch-fab{padding:14px}.dch-overlay{right:0;bottom:0;left:0;top:0}.dch-modal{height:100vh;width:100vw;border-radius:0}}
  `;

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
  // Minimal, XSS-safe markdown for bot replies: escape FIRST, then format a tiny
  // whitelist (**bold**, `code`, # headings, - / * bullets, blank-line paragraphs).
  // Cited stats like "90% (95% CI 77-96%, n=198)" carry no tokens → pass verbatim.
  function mdLite(raw) {
    var s = esc(raw), lines = s.split(/\r?\n/), html = "", list = null;
    function inline(t) {
      return t
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
    }
    function flush() { if (list) { html += '<ul class="dch-md-ul">' + list + "</ul>"; list = null; } }
    lines.forEach(function (ln) {
      var t = ln.trim();
      if (!t) { flush(); return; }
      var h = t.match(/^#{1,6}\s+(.*)$/);
      if (h) { flush(); html += '<span class="dch-md-h">' + inline(h[1]) + "</span>"; return; }
      var li = t.match(/^[-*]\s+(.*)$/);
      if (li) { list = (list || "") + "<li>" + inline(li[1]) + "</li>"; return; }
      flush(); html += "<p>" + inline(t) + "</p>";
    });
    flush();
    return html || "<p></p>";
  }

  // Read whatever the page says we're currently looking at.
  // 1) treatment_predictor stashes window.__lastPredict = {profile, predictions}.
  // 2) a page may expose window.dashboardChatContext() returning {profile, predictions}.
  // 3) fall back to window.litSearchContext() (a string of terms) → profile-less.
  // 4) else empty.
  function readContext() {
    try {
      var lp = window.__lastPredict;
      if (lp && lp.profile) {
        return {
          profile: { conditions: lp.profile || [], severity: lp.severity || null },
          predictions: lp.predictions || [],
        };
      }
    } catch (e) {}
    try {
      if (typeof window.dashboardChatContext === "function") {
        var c = window.dashboardChatContext() || {};
        return {
          profile: c.profile || { conditions: [], severity: null },
          predictions: c.predictions || [],
        };
      }
    } catch (e) {}
    // No structured profile on this page — still useful for lit/keyword questions.
    return { profile: { conditions: [], severity: null }, predictions: [] };
  }

  var style = document.createElement("style");
  style.textContent = CSS;
  document.head.appendChild(style);

  var fab = el('<button class="dch-fab" title="Ask about your results">💬 <span>Ask about your results</span></button>');
  var overlay = el(
    '<div class="dch-overlay" role="region" aria-label="Ask about your results">' +
      '<div class="dch-modal">' +
        '<div class="dch-head"><h2>Ask about your results</h2><button class="dch-x" aria-label="Close">×</button></div>' +
        '<div class="dch-thread"></div>' +
        '<div class="dch-hint">Grounded in the data on your screen. Shows what patients reported — not medical advice, and it won\'t prescribe or give dosing.</div>' +
        '<div class="dch-inrow">' +
          '<textarea class="dch-input" rows="1" placeholder="e.g. Why is autonomic so high for me?"></textarea>' +
          '<button class="dch-send">Send</button>' +
        '</div>' +
      '</div>' +
    '</div>'
  );
  document.body.appendChild(fab);
  document.body.appendChild(overlay);

  var thread = overlay.querySelector(".dch-thread");
  var input = overlay.querySelector(".dch-input");
  var sendBtn = overlay.querySelector(".dch-send");

  var greeted = false;
  function open() {
    overlay.classList.add("open");
    fab.style.display = "none";
    if (!greeted) {
      greeted = true;
      addBot(
        "Hi — I can explain the numbers on your screen: the per-class predictions, what similar " +
          "patients reported, and the literature. I cite every figure and I won't tell you what to " +
          "take or whether something is safe (that's for your doctor). What would you like to know?",
        false,
        []
      );
    }
    setTimeout(function () { input.focus(); }, 30);
  }
  function close() { overlay.classList.remove("open"); fab.style.display = ""; fab.focus(); }

  fab.addEventListener("click", open);
  overlay.querySelector(".dch-x").addEventListener("click", close);
  // Non-modal panel: clicking the dashboard must NOT close it (the whole point is to
  // talk about the data you're looking at). Escape only acts while the panel is open.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && overlay.classList.contains("open")) close();
  });
  window.openDashboardChat = open;

  function scrollDown() { thread.scrollTop = thread.scrollHeight; }

  function addUser(text) {
    thread.appendChild(el('<div class="dch-msg dch-user">' + esc(text) + "</div>"));
    scrollDown();
  }
  function addBot(text, blocked, disclaimers) {
    thread.appendChild(
      el('<div class="dch-msg dch-bot' + (blocked ? " dch-blocked" : "") + '">' + mdLite(text) + "</div>")
    );
    (disclaimers || []).forEach(function (d) {
      thread.appendChild(el('<div class="dch-disc">' + esc(d) + "</div>"));
    });
    scrollDown();
  }

  var busy = false;
  function send() {
    var q = input.value.trim();
    if (!q || busy) return;
    busy = true;
    sendBtn.disabled = true;
    addUser(q);
    input.value = "";
    input.style.height = "auto";

    var typing = el('<div class="dch-typing">thinking…</div>');
    thread.appendChild(typing);
    scrollDown();

    var ctx = readContext();
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: q,
        conversation_id: CONV_ID,
        profile: ctx.profile,
        current_predictions: ctx.predictions,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        typing.remove();
        addBot(d.assistant_message || "(no response)", !!d.blocked, d.disclaimers || []);
      })
      .catch(function (e) {
        typing.remove();
        thread.appendChild(el('<div class="dch-err">Chat failed: ' + esc(e) + "</div>"));
        scrollDown();
      })
      .finally(function () {
        busy = false;
        sendBtn.disabled = false;
        input.focus();
      });
  }

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = Math.min(90, input.scrollHeight) + "px";
  });
})();
