// A research run: live progress, then results / article / suggestions. Also re-opens saved runs.
import { $, $$, h, safeUrl, favicon, shortUrl, stripThink, rafThrottle, icon, toast, api, apiStream, fmtDate } from "./util.js";
import { render, allowLinks } from "./markdown.js";
import { chipHtml, openDatePicker, emptyRange } from "./dates.js";
import { openTranslate, restoreTranslation } from "./translate.js";
import { t, has, uiLang } from "./i18n.js";
import { openSummary } from "./summary.js";
import { openInteractive } from "./interactive.js";
import { jobFor, pokeJobs } from "./activity.js";
import { ttsAvailable, speak, pause as ttsPause, resume as ttsResume, stop as ttsStop, paused as ttsPaused } from "./tts.js";
import { exportHtml } from "./export.js";
import { pinButton, togglePinSource } from "./pins.js";
import { showToolbar, hideToolbar } from "./toolbar.js";
import { downloadSummary } from "./summaryfile.js";
import { openRegenerate, setRegenHooks } from "./regenerate.js";

export const RUN = { current: null, ctrl: null };
let hooks = { go: () => {}, openSettings: () => {}, showView: () => {}, refreshRecent: () => {} };
export function setRunHooks(x) { hooks = { ...hooks, ...x }; }

function newRun(query, mode, library, dates = emptyRange(), extras = true) {
  return {
    query, mode, library, dates, extras, id: null, model: "", search: "", created: new Date().toISOString(), steps: [], sources: {},
    plan: null, outcome: null, images: [], md: "", articleSources: [], related: [], results: null, suggestions: null,
    interactive: null, finished: false, error: null, t0: Date.now(), elapsed: null,
  };
}

// live run
// While a search runs, the address is #/run/<id>: leaving and coming back (or reopening the app) reconnects to it.
function rememberRun(R) {
  pokeJobs();
  if (R.id && !R.finished && RUN.current === R) history.replaceState(null, "", `#/run/${encodeURIComponent(R.id)}`);
}

/** Reconnect to a search that is still running (or queued) on the server. */
export async function attachRun(id) {
  RUN.ctrl?.abort();
  if (RUN.current?.id === id && !RUN.current.finished && RUN.current.ctrl && !RUN.current.ctrl.signal.aborted) { hooks.showView("run"); return; }
  const ctrl = new AbortController();
  RUN.ctrl = ctrl;
  const R = newRun("", "auto", false);
  R.id = id;
  R.ctrl = ctrl;
  RUN.current = R;
  hooks.showView("run");
  let shell = false;
  try {
    await apiStream(`/api/research/${encodeURIComponent(id)}/stream`, null, ev => {
      if (RUN.current !== R) return false;
      if (!shell && (ev.type === "start" || ev.type === "queued" || ev.type === "accepted")) {
        const q = ev.query || (RUN.active || []).find(a => a.id === id)?.query || "";
        if (q) { R.query = q; $("#topSearch input").value = q; document.title = `${q} - AIRAG`; }
        renderShell(R);
        shell = true;
      }
      onEvent(R, ev);
    }, ctrl.signal, "GET");
    if (RUN.current === R && !R.finished) finish(R);
  } catch (e) {
    if (e.name === "AbortError" || RUN.current !== R) return;
    // not running any more: show the finished search from history
    location.hash = `#/view/${encodeURIComponent(id)}`;
  }
}

export async function cancelRun(id) {
  await api(`/api/research/${encodeURIComponent(id)}/cancel`, { method: "POST" }).catch(() => {});
}

// the explainer button follows background explainer jobs
window.addEventListener("airag:jobs", () => { if (RUN.current?.finished) updateInteractiveButton(RUN.current); });

export async function startResearch(query, mode, library, fromId = null, dates = emptyRange(), mergeId = null, extras = true, extendId = null) {
  RUN.ctrl?.abort();
  const ctrl = new AbortController();
  RUN.ctrl = ctrl;
  const R = newRun(query, mode, library, dates, extras);
  R.ctrl = ctrl;
  R.extend = extendId;
  RUN.current = R;
  hooks.showView("run");
  scrollTo(0, 0);
  $("#topSearch input").value = query;
  document.title = `${query} - AIRAG`;
  renderShell(R);
  try {
    await apiStream("/api/research", { query, mode, include_library: !!library, ui_lang: uiLang(), from_id: fromId,
      date_from: dates?.from || "", date_to: dates?.to || "", merge_id: mergeId, extras, extend_id: extendId }, ev => {
      if (RUN.current !== R) return false;
      onEvent(R, ev);
    }, ctrl.signal);
    if (RUN.current === R && !R.finished) finish(R);
  } catch (e) {
    if (e.name === "AbortError" || RUN.current !== R) return;
    onEvent(R, { type: "error", message: e.message });
  }
}

function onEvent(R, ev) {
  switch (ev.type) {
    case "accepted": R.id = ev.id; rememberRun(R); break;
    case "queued":
      R.id = ev.id;
      rememberRun(R);
      setSub(t("run.queued", { n: ev.position }));
      break;
    case "start":
      Object.assign(R, { id: ev.id, model: ev.model, search: ev.search, created: ev.created || R.created });
      rememberRun(R);
      setSub(`${ev.model} · ${ev.search}`);
      break;
    case "cancelled":
      R.error = t("run.cancelled");
      R.cancelled = true;
      renderError(R);
      finish(R);
      hooks.refreshRecent();
      break;
    case "step": upsertStep(R, ev); break;
    case "plan": R.plan = ev.plan; setSub(t("run.lookingFor", { x: ev.plan.intent })); break;
    case "sources": ev.items.forEach(s => (R.sources[s.id] = s)); renderSourceSide(R); break;
    case "source": R.sources[ev.source.id] = ev.source; renderSourceSide(R); break;
    case "outcome": R.outcome = ev.outcome; break;
    case "results": R.results = ev; R.images = ev.images || []; renderResults(R); break;
    case "article_start":
      Object.assign(R, { articleSources: ev.sources, images: ev.images || [], related: ev.related || [] });
      renderArticle(R);
      break;
    case "token": R.md += ev.text; renderArticleBodyThrottled(R); break;
    case "interactive": R.interactive = ev; updateInteractiveButton(R); break;
    case "suggestions": R.suggestions = ev; renderSuggestions(R); break;
    case "error": R.error = ev.message; renderError(R); finish(R); break;
    case "done":
      R.id = ev.id;
      R.elapsed = ev.elapsed;
      finish(R);
      if (ev.extended !== undefined) {   // "Locate more sources": show the updated article
        toast(ev.extended ? t(R.outcome === "results" ? "more.addedResults" : "more.added", { n: ev.extended }) : t("more.none"), 4500);
        history.replaceState(null, "", `#/view/${encodeURIComponent(ev.id)}`);
        RUN.current = null;
        openRecord(ev.id);
        break;
      }
      if (ev.id) history.replaceState(null, "", `#/view/${encodeURIComponent(ev.id)}`);
      hooks.refreshRecent();
      break;
  }
}

// save the article to My library (Markdown with the sources at the bottom)
function updateSaveButton(R) {
  const b = $("#saveBtn");
  if (!b) return;
  const ready = R.finished && !R.error && R.id && R.outcome === "article" && !R.savedFile;
  b.disabled = !ready;
  b.innerHTML = R.savedPath ? `${icon("check")}${h(t("save.saved"))}` : `${icon("download")}${h(t("save.button"))}`;
  if (R.savedPath) b.title = R.savedPath;
}

function openSavePop(anchor, R) {
  if ($(".save-pop")) { $(".save-pop").remove(); return; }
  const rich = !!hooks.defaults?.()?.save_rich;
  const pop = document.createElement("div");
  pop.className = "date-pop save-pop";
  pop.innerHTML = `<label class="switch"><input type="checkbox" id="saveRich" ${rich ? "checked" : ""}> ${h(t("save.rich"))}</label>
    <div class="muted" style="font-size:12px">${h(t(R.interactiveHtml || R.interactive?.html ? "save.richHelp" : "save.richHelpNoInter"))}</div>
    <div class="dp-foot"><span></span><button type="button" class="btn sm primary" id="saveGo">${icon("download")}${h(t("save.button"))}</button></div>`;
  document.body.appendChild(pop);
  const r = anchor.getBoundingClientRect(), w = Math.min(300, innerWidth - 16);
  pop.style.width = w + "px";
  pop.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + "px";
  pop.style.top = (r.bottom + scrollY + 8) + "px";
  $("#saveGo", pop).onclick = () => {
    const on = $("#saveRich", pop).checked;
    pop.remove();
    saveArticle(R, on);
  };
  setTimeout(() => document.addEventListener("pointerdown", function away(e) {
    if (!pop.isConnected) { document.removeEventListener("pointerdown", away); return; }
    if (pop.contains(e.target) || anchor.contains(e.target)) return;
    pop.remove();
    document.removeEventListener("pointerdown", away);
  }), 0);
}

async function saveArticle(R, rich = false) {
  const b = $("#saveBtn");
  if (b) b.disabled = true;
  try {
    const r = await api("/api/mylibrary/save", { method: "POST", body: { id: R.id, rich } });
    R.savedPath = r.path;
    toast(t("save.done", { path: r.path }), 5000);
  } catch (e) { toast(e.message, 5000); }
  updateSaveButton(R);
}

function finish(R) {
  if (R.finished) return;
  R.finished = true;
  pokeJobs();
  if (RUN.current === R && !R.extend) setTimeout(() => showToolbar(R), 0);
  $(".again-chip")?.removeAttribute("hidden");
  $(".cancel-chip")?.setAttribute("hidden", "");
  updateSaveButton(R);
  const ph = $("#phIcon");
  if (ph) { ph.className = "ph-icon " + (R.error ? "err" : "ok"); ph.innerHTML = icon(R.error ? "warn" : "check"); }
  const pt = $(".ph-title");
  if (pt) pt.textContent = t("run.researchFor", { q: R.query });
  if (R.openedFile) {          // opened with AIRAG from a file: no research steps to show
    if (pt) pt.textContent = t("open.from", { name: R.openedFile });
    setSub(t("open.noAI"));
    $("#progress")?.classList.add("collapsed");
  } else if (!R.error) {
    const all = Object.values(R.sources);
    setSub(t("run.summary", { steps: R.steps.length, found: all.length, read: all.filter(s => s.relevance != null).length,
      secs: R.elapsed ?? Math.round((Date.now() - R.t0) / 100) / 10 }));
    $("#progress")?.classList.add("collapsed");
  }
  if (R.outcome === "article") { renderArticleBody(R, true); renderArticleSide(R); updateInteractiveButton(R); }
}

// shell + progress
function renderShell(R, done = false) {
  $("#runMain").innerHTML = `
    <div class="progress card ${done ? "collapsed" : ""}" id="progress">
      <button class="progress-head" id="progressToggle" type="button">
        <span class="ph-icon" id="phIcon"><span class="spinner"></span></span>
        <div class="ph-text"><div class="ph-title">${h(t(done ? "run.researchFor" : "run.researching", { q: R.query }))}</div><div class="ph-sub" id="phSub">${h(t("run.starting"))}</div></div>
        <span class="chev">${icon("chev")}</span>
      </button>
      <div class="progress-body"><ol class="steps" id="steps"></ol></div>
    </div>
    <div class="run-filters">${chipHtml("runDates", R.dates)}
      <button type="button" class="check-chip cancel-chip" data-act="cancel" ${done ? "hidden" : ""} title="${h(t("run.cancelTip"))}">${icon("x")}<span>${h(t("run.cancel"))}</span></button>
      <button type="button" class="check-chip again-chip" data-act="again" ${done ? "" : "hidden"} title="${h(t("run.againTip"))}">${icon("refresh")}<span>${h(t("run.again"))}</span></button></div>
    <div id="output">${done ? "" : `<div class="skel" style="padding:8px 4px"><div style="width:70%"></div><div style="width:92%"></div><div style="width:84%"></div><div style="width:60%"></div></div>`}</div>`;
  $("#runSide").innerHTML = `<div class="sticky"><div class="side-card"><div class="side-title">${h(t("src.title"))} <span class="count" id="srcCount">0</span></div>
    <div class="src-list" id="srcList"><div class="muted" style="font-size:13px">${h(t("src.waiting"))}</div></div></div></div>`;
  $("#progressToggle").onclick = () => $("#progress").classList.toggle("collapsed");
  $("#runDates").onclick = e => openDatePicker(e.currentTarget, R.dates,
    d => hooks.go(R.query, R.mode || "auto", R.library, null, d, null, R.extras), t("date.searchAgain"));
}

function setSub(text) { const el = $("#phSub"); if (el) el.textContent = text; }

function upsertStep(R, ev) {
  const i = R.steps.findIndex(s => s.id === ev.id);
  if (i >= 0) R.steps[i] = ev; else R.steps.push(ev);
  const list = $("#steps");
  if (!list) return;
  let li = list.querySelector(`[data-step="${CSS.escape(ev.id)}"]`);
  if (!li) { li = document.createElement("li"); li.dataset.step = ev.id; list.appendChild(li); }
  li.className = ev.status;
  const ic = ev.status === "running" ? '<span class="spinner"></span>' : icon(ev.status === "warn" ? "warn" : "check");
  li.innerHTML = `<span class="st-icon">${ic}</span><div><div class="st-label">${h(stepLabel(ev))}</div>${ev.detail ? `<div class="st-detail">${h(ev.detail)}</div>` : ""}</div>`;
}

// Step labels come from the server in English; translate the known ones.
function stepLabel(ev) {
  const st = ev.status === "running" ? "run" : "done";
  const n = (ev.label.match(/\d+/) || [""])[0];
  for (const key of [`step.${ev.id}.${st}`, `step.${ev.id.replace(/\d+$/, "")}.${st}`]) {
    if (has(key)) return t(key, { n });
  }
  return ev.label;
}

const favHtml = s => (s.local ? `<span class="fav-lib">${icon("folder")}</span>` : `<img src="${favicon(s.domain)}" alt="" loading="lazy">`);
const srcDomain = s => (s.local ? `${t("src.library")} · ${s.site_name || ""}` : s.domain);

const renderSourceSide = rafThrottle(R => {
  if (RUN.current !== R || (R.outcome === "article" && R.articleSources.length)) return;
  const list = $("#srcList");
  if (!list) return;
  const all = Object.values(R.sources);
  $("#srcCount").textContent = all.length;
  all.sort((a, b) => ((b.relevance ?? -1) - (a.relevance ?? -1)) || a.id - b.id);
  list.innerHTML = all.map(s => {
    const dim = ["unreadable", "error"].includes(s.status) || (s.relevance != null && s.relevance < 3) || s.out_of_range;
    const right = s.out_of_range ? `<span class="st-chip" title="${h(s.published || s.date || "")}">${h(t("src.outOfRange"))}</span>`
      : s.relevance != null
      ? `<span class="rel" title="${h(t("rel.label"))} ${s.relevance}/10"><i style="width:${s.relevance * 10}%"></i></span>`
      : `<span class="st-chip">${h(t("src." + (s.status || "found")))}</span>`;
    return `<a class="src-row ${dim ? "dim" : ""}" href="${h(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer" title="${h(s.title)}${s.error ? " - " + h(s.error) : ""}">
      ${favHtml(s)}<div style="min-width:0"><div class="sr-t">${h(s.title || s.domain)}</div><div class="sr-d">${h(srcDomain(s))}</div></div>${right}</a>`;
  }).join("") || `<div class="muted" style="font-size:13px">${h(t("src.none"))}</div>`;
});

// shared bits
function trustBadge(s, short = false) {
  const v = s.trust ?? s.prior;
  if (v == null) return "";
  const lvl = v >= 7 ? "high" : v >= 4 ? "mid" : "low";
  const bars = Array.from({ length: 5 }, (_, i) => `<i class="${i < Math.round(v / 2) ? "on" : ""}"></i>`).join("");
  const warn = s.suspicious ? `<span class="sus" title="${h(t("src.suspicious"))}">${icon("warn")}</span>` : "";
  return `<span class="trust t-${lvl}" title="${h(s.trust_reason || s.prior_label || "")}"><span class="bars">${bars}</span>${short ? "" : h(t("trust." + lvl))}</span>${warn}`;
}
const meter = (key, v) => (v == null ? "" : `<span class="meter">${h(t(key))} <span class="rel"><i style="width:${v * 10}%"></i></span> ${v}/10</span>`);
const imgOnErr = `onerror="this.closest('[data-img]').remove()"`;

function imgStrip(images) {
  if (!images?.length) return "";
  return `<div class="img-strip">${images.map(im => `<a class="img-tile" data-img href="${h(safeUrl(im.page_url || im.src))}" target="_blank" rel="noopener noreferrer" title="${h(im.title)}">
    <img src="${h(im.thumb || im.src)}" alt="${h(im.title)}" loading="lazy" referrerpolicy="no-referrer" ${imgOnErr}><span>${h(im.credit)}</span></a>`).join("")}</div>`;
}

function sourceActions(s) {
  const lib = s.local ? `<button class="link-btn" data-act="lib-open" data-fid="${s.file_id}">${icon("ext")}${h(t("lib.open"))}</button>
    <button class="link-btn" data-act="lib-reveal" data-fid="${s.file_id}">${icon("folder")}${h(t("lib.reveal"))}</button>` : "";
  const save = s.local ? "" : `<button class="link-btn" data-act="save-source" data-sid="${s.id}" title="${h(t("save.sourceTip"))}">${icon("download")}${h(t("save.source"))}</button>`;
  return `<button class="link-btn" data-act="sum-source" data-sid="${s.id}">${icon("sparkle")}${h(t("sum.button"))}</button>${save}${pinButton(s)}${lib}`;
}

// clicks inside the output area
$("#runMain").addEventListener("click", e => {
  const b = e.target.closest("[data-act]");
  const R = RUN.current;
  if (!b || !R) return;
  const act = b.dataset.act;
  if (act === "article") hooks.go(R.query, "article", R.library, R.id);   // reuse this search's sources
  else if (act === "results") hooks.go(R.query, "results", R.library);
  else if (act === "cancel") { b.disabled = true; if (R.id) cancelRun(R.id); }
  else if (act === "retry" || act === "again") hooks.go(R.query, R.mode || "auto", R.library, null, R.dates, R.id, R.extras);
  else if (act === "search") hooks.go(b.dataset.q, "auto", R.library);
  else if (act === "settings") hooks.openSettings(b.dataset.tab);
  else if (act === "copy") copyText(articleMarkdown(R)).then(ok => toast(t(ok ? "art.copied" : "art.copyFailed")));
  else if (act === "listen") {
    if (ttsPaused()) ttsResume();
    else if ($("#ttsBtn")?.textContent.includes(t("tts.pause"))) ttsPause();
    else {
      const { title, body } = parseArticle(R.md);
      const plain = stripThink(`${title}\n\n${body}`).replace(/\[\d+(?:,\s*\d+)*\]/g, "").replace(/[#*_>`|]/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
      speak(plain, R.lang || uiLang(), setListenButton);
    }
  }
  else if (act === "listen-stop") ttsStop();
  else if (act === "pin" && R.id) togglePin(R);
  else if (act === "more-sources" && R.id && R.finished) startResearch(R.query, R.outcome === "article" ? "article" : "results", R.library, null, R.dates, null, false, R.id);
  else if (act === "export-html") exportHtml(R, $("article.article"));
  else if (act === "save") openSavePop(b, R);
  else if (act === "regenerate") openRegenerate(R);
  else if (act === "versions") openRegenerate(R, true);
  else if (act === "tr-original") {
    restoreTranslation(R, b.dataset.kind);
    if (b.dataset.kind === "article") { renderArticleBody(R, true); renderArticleSide(R); showTrNote(R); }
    else renderResults(R);
    const x = $("#trArtBtn"); if (x) x.innerHTML = `${icon("globe")}${h(t("tr.button"))}`;
  }
  else if (act === "translate-article" && R.finished) openTranslate(b, R, "article", {
    defaultLang: hooks.defaults?.()?.translate_to,
    render: (final = true) => { renderArticleBody(R, final); if (final) { renderArticleSide(R); showTrNote(R); } },
    setBusy: on => { const x = $("#trArtBtn"); if (x) { x.disabled = on; x.innerHTML = on ? `<span class="spinner sm"></span>${h(t("tr.working"))}` : `${icon("globe")}${h(t("tr.button"))}`; } },
  });
  else if (act === "translate-results") openTranslate(b, R, "results", {
    defaultLang: hooks.defaults?.()?.translate_to,
    render: () => renderResults(R),
    setBusy: on => { const x = $("#trResBtn"); if (x) { x.disabled = on; x.innerHTML = on ? `<span class="spinner sm"></span>${h(t("tr.working"))}` : `${icon("globe")}${h(t("tr.button"))}`; } },
  });
  else if (act === "sum-article") openSummary({ kind: "article", query: R.query, payload: { markdown: stripThink(R.md) }, label: $("#aTitle")?.textContent || R.query, key: `a:${R.id}`, sources: R.articleSources });
  else if (act === "sum-file") downloadSummary({ kind: "article", query: R.query, payload: { markdown: stripThink(R.md) }, label: $("#aTitle")?.textContent || R.query, key: `a:${R.id}` }, R.articleSources, b);
  else if (act === "sum-results") {
    const items = (R.results?.items || []).filter(s => s.relevance != null).slice(0, 12);
    openSummary({ kind: "results", query: R.query, payload: { items }, label: t("res.title"), key: `r:${R.id}`, sources: items });
  } else if (act === "sum-source") {
    const s = R.sources[b.dataset.sid] || R.articleSources.find(x => String(x.id) === b.dataset.sid);
    if (s) openSummary({ kind: "source", query: R.query, payload: { url: s.url }, label: s.title || s.url, key: `s:${s.url}`, sources: [s] });
  } else if (act === "pin-source") {
    const s = R.sources[b.dataset.sid] || R.articleSources.find(x => String(x.id) === b.dataset.sid);
    if (s) togglePinSource(s, R.query, b);
  } else if (act === "save-source") {
    const s = R.sources[b.dataset.sid] || R.articleSources.find(x => String(x.id) === b.dataset.sid);
    if (!s) return;
    b.disabled = true;
    api("/api/mylibrary/save-source", { method: "POST", body: { url: s.url, query: R.query } })
      .then(r => { toast(t("save.done", { path: r.path }), 5000); b.innerHTML = `${icon("check")}${h(t("save.saved"))}`; })
      .catch(err => { toast(err.message, 5000); b.disabled = false; });
  } else if (act === "lib-open" || act === "lib-reveal") {
    api("/api/library/open", { method: "POST", body: { file_id: +b.dataset.fid, reveal: act === "lib-reveal" } }).catch(err => toast(err.message));
  } else if (act === "interactive") {
    if (b.getAttribute("aria-disabled") !== "true") openInteractive(R);
  }
});

// results view
// "Translated into X with AI · Show original" bar
function trNote(R, kind) {
  const code = R.translation?.[kind];
  if (!code) return "";
  let name = code;
  try { name = new Intl.DisplayNames([uiLang()], { type: "language" }).of(code) || code; } catch { /* old browsers */ }
  return `<div class="tr-note">${icon("globe")}<span>${h(t("tr.note", { lang: name }))}</span>
    <button type="button" class="btn sm" data-act="tr-original" data-kind="${kind}">${h(t("tr.original"))}</button></div>`;
}

function showTrNote(R) {
  const el = $("#trNoteArt");
  if (el) el.innerHTML = trNote(R, "article");
}

function renderResults(R) {
  const res = R.results, best = new Set(res.best || []);
  const items = res.items || [];
  const assessed = items.filter(s => s.relevance != null), others = items.filter(s => s.relevance == null);
  const head = best.size ? t(best.size === 1 ? "res.direct1" : "res.directN", { n: best.size }) : t("res.title");
  $("#output").innerHTML = `
    <div class="results">
      <div class="results-head">
        <div><div class="rh-title">${h(head)}</div><div class="rh-sub">${h(t("res.sub"))}</div></div>
        <div class="row">
          ${assessed.length ? `<button class="btn" data-act="sum-results">${icon("sparkle")}${h(t("sum.button"))}</button>` : ""}
          <button class="btn" data-act="article">${icon("doc")}${h(t("res.toArticle"))}</button>
          ${R.id && R.finished && !R.savedFile ? `<button class="btn ghost" data-act="more-sources" title="${h(t("more.tipResults"))}">${icon("search")}${h(t("more.button"))}</button>` : ""}
          <button class="btn ghost" data-act="translate-results" id="trResBtn" title="${h(t("tr.tip"))}">${icon("globe")}${h(t("tr.button"))}</button>
        </div>
      </div>
      <div id="trNoteRes">${trNote(R, "results")}</div>
      ${imgStrip(res.images)}
      ${assessed.map(s => resultCard(s, best.has(s.id))).join("") || `<p class="muted">${h(t("res.none"))}</p>`}
      ${others.length ? `<div class="also"><div class="also-title">${h(t("res.more"))}</div>${others.map(s => `
        <a class="lite" href="${h(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer"><div class="lite-t">${h(s.title || s.url)}</div><div class="lite-s">${h(srcDomain(s))} - ${h(s.snippet || s.error || "")}</div></a>`).join("")}</div>` : ""}
    </div>`;
}

function resultCard(s, isBest) {
  const snip = s.summary && !/^nothing relevant/i.test(s.summary) ? s.summary : s.snippet;
  const n = s.findings?.length || 0;
  return `<div class="result ${isBest ? "best" : ""}">
    <div class="r-site">${favHtml(s)}<div style="min-width:0"><div class="r-domain">${h(s.local ? t("src.library") : s.site_name || s.domain)}</div><div class="r-url">${h(s.local ? s.path : shortUrl(s.url))}</div></div></div>
    <a class="r-title" href="${h(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${h(s.title || s.url)}</a>
    <p class="r-snip">${h(snip)}</p>
    <div class="r-meta">${isBest ? `<span class="tag strong">${h(t("res.best"))}</span>` : ""}${s.source_type ? `<span class="tag">${h(s.source_type)}</span>` : ""}${meter("rel.label", s.relevance)}${meter("cov.label", s.coverage)}${trustBadge(s)}</div>
    ${n ? `<details class="r-find"><summary>${h(t(n === 1 ? "res.findings1" : "res.findings", { n }))}</summary><ul>${s.findings.map(f => `<li>${h(f.claim)}${f.evidence ? `<blockquote>"${h(f.evidence)}"</blockquote>` : ""}</li>`).join("")}</ul></details>` : ""}
    <div class="r-actions">${sourceActions(s)}</div>
  </div>`;
}

// article view
function renderArticle(R) {
  const n = R.articleSources.length;
  const [hero, ...rest] = R.images || [];
  $("#output").innerHTML = `
    <article class="article">
      <div class="a-kicker"><span class="pill">${h(t("art.kicker"))}</span><span>${h(t("art.compiled", { n }))}</span></div>
      <h1 class="a-title" id="aTitle">${h(R.query)}</h1>
      <p class="a-dek" id="aDek"></p>
      <div class="a-byline"><span class="avatar">A</span><div><div class="by-name">${h(t("art.by"))}</div><div class="muted">${h(fmtDate(R.created, uiLang()))} · ${h(R.model)}<span id="aStats"></span></div></div>
        <div class="a-actions" id="aActions">${articleActions(R)}</div></div>
      ${hero ? `<figure class="a-hero" data-img><img src="${h(hero.src)}" alt="${h(hero.title)}" referrerpolicy="no-referrer" ${imgOnErr}>
        <figcaption>${h(hero.title)}${hero.title ? " · " : ""}<a href="${h(safeUrl(hero.page_url))}" target="_blank" rel="noopener noreferrer">${h(hero.credit)}</a></figcaption></figure>` : ""}
      <div id="trNoteArt"></div>
      <div class="a-body prose ${/^(zh|ja|ko)/.test(uiLang()) ? "" : "dropcap"}" id="aBody"><span class="cursor"></span></div>
      ${rest.length ? `<section class="a-gallery"><h2>${h(t("art.images"))}</h2><div class="gallery-grid">${rest.map(im => `
        <figure data-img><a href="${h(safeUrl(im.page_url || im.src))}" target="_blank" rel="noopener noreferrer"><img src="${h(im.thumb || im.src)}" alt="${h(im.title)}" loading="lazy" referrerpolicy="no-referrer" ${imgOnErr}></a>
        <figcaption>${h(im.title)} - ${h(im.credit)}</figcaption></figure>`).join("")}</div></section>` : ""}
      <section class="a-sources"><h2>${h(t("art.sources"))}</h2><ol>${R.articleSources.map(sourceEntry).join("")}</ol></section>
      ${R.related?.length ? `<section class="a-related"><h2>${h(t("art.related"))}</h2><div class="chips">${R.related.map(q => `<button class="chip" data-act="search" data-q="${h(q)}">${icon("search")}${h(q)}</button>`).join("")}</div></section>` : ""}
    </article>`;
  renderArticleSide(R);
  updateInteractiveButton(R);
}

// Article tools in fold-out groups (Explainer always on its own). Every button exists once; on phones the
// Rewrite / Sources groups and Pin sit in a "More" sheet, and each menu opens as a bottom sheet.
function articleActions(R) {
  const chev = `<svg class="a-chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;
  const item = (act, ic, label, desc = "", extra = "") =>
    `<button type="button" class="a-item" data-act="${act}" ${extra}>${icon(ic)}<span class="a-item-t">${h(label)}${desc ? `<small>${h(desc)}</small>` : ""}</span></button>`;
  const head = label => `<div class="a-menu-head"><b>${h(label)}</b><button type="button" class="icon-btn" data-group-close aria-label="${h(t("common.close"))}">${icon("x")}</button></div>`;
  const group = (key, ic, label, items) => `<div class="a-group" data-group="${key}">
      <button type="button" class="btn sm ghost a-gbtn" data-group-toggle aria-expanded="false" aria-haspopup="true">${icon(ic)}<span class="a-glong">${h(label)}</span><span class="a-gshort">${h(t("grp." + key + "Short"))}</span>${chev}</button>
      <div class="a-menu" role="menu">${head(label)}${items}</div></div>`;
  return `<button class="btn sm primary has-tip" data-act="interactive" id="interBtn" aria-disabled="true"><span class="lbl row" style="gap:7px">${icon("play")}${h(t("inter.button"))}</span><span class="tip-text" id="interTip">${h(t("inter.checking"))}</span></button>
    ${ttsAvailable() ? `<button class="btn sm ghost" data-act="listen" id="ttsBtn" title="${h(t("tts.tip"))}">${icon("speak")}${h(t("tts.listen"))}</button>
      <button class="btn sm ghost" data-act="listen-stop" id="ttsStop" hidden title="${h(t("tts.stop"))}">${icon("stop")}</button>` : ""}
    ${group("export", "download", t("grp.export"),
      item("export-html", "html", t("exp.button"), "", `title="${h(t("exp.tip"))}"`)
      + item("copy", "copy", t("art.copy"))
      + item("sum-file", "download", t("sumfile.button"), t("sumfile.desc"), `title="${h(t("sumfile.tip"))}"`)
      + item("save", "download", t("save.button"), t("save.desc"), `id="saveBtn" disabled title="${h(t("save.tip"))}"`))}
    <button type="button" class="btn sm ghost a-more-btn" data-more-toggle aria-expanded="false">${icon("more")}<span>${h(t("grp.more"))}</span></button>
    <div class="a-more">${head(t("grp.more"))}
      ${group("rewrite", "edit", t("grp.rewrite"),
        item("regenerate", "refresh", t("regen.button"), t("regen.desc"))
        + item("versions", "history", t("regen.versions"))
        + item("translate-article", "globe", t("tr.button"), "", `id="trArtBtn" title="${h(t("tr.tip"))}"`)
        + item("sum-article", "sparkle", t("sum.button")))}
      ${group("sources", "search", t("grp.sources"),
        (R.savedFile ? "" : item("more-sources", "search", t("more.button"), "", `title="${h(t("more.tip"))}"`))
        + item("results", "list", t("art.results"))
        + item("again", "refresh", t("run.again"), "", `title="${h(t("run.againTip"))}"`))}
      <button class="btn sm ghost" data-act="pin" id="pinBtn" ${R.savedFile ? "hidden" : ""} title="${h(t("pin.tip"))}">${icon("pin")}<span>${h(t(R.pinned ? "pin.unpin" : "pin.pin"))}</span></button>
    </div>
    <div class="a-scrim" data-group-close></div>`;
}

function syncGroups() {
  $$("[data-group-toggle]").forEach(b => b.setAttribute("aria-expanded", String(b.closest(".a-group").classList.contains("open"))));
  const bar = $(".a-actions");
  $$("[data-more-toggle]").forEach(b => b.setAttribute("aria-expanded", String(!!bar?.classList.contains("more-open"))));
  document.body.classList.toggle("a-sheet-open", !!$(".a-group.open, .a-actions.more-open"));
  // computers: open a menu upwards when it would run under the bottom of the window (or the toolbar there)
  const m = $(".a-group.open > .a-menu");
  if (m && matchMedia("(min-width: 721px)").matches) {
    m.classList.remove("up");
    const r = m.getBoundingClientRect();
    if (r.bottom > innerHeight - 96 && r.top - r.height - 50 > 0) m.classList.add("up");
  }
}

function closeGroups() {
  $$(".a-group.open").forEach(g => g.classList.remove("open"));
  $(".a-actions")?.classList.remove("more-open");
  syncGroups();
}

// opening and closing the groups (a click on an item runs it through the normal data-act handler first)
document.addEventListener("click", e => {
  const tog = e.target.closest("[data-group-toggle]");
  if (tog) {
    const g = tog.closest(".a-group"), was = g.classList.contains("open");
    $$(".a-group.open").forEach(x => x.classList.remove("open"));
    g.classList.toggle("open", !was);
    syncGroups();
    return;
  }
  if (e.target.closest("[data-more-toggle]")) {
    const bar = $(".a-actions"), open = !bar.classList.contains("more-open");
    closeGroups();
    bar.classList.toggle("more-open", open);
    syncGroups();
    return;
  }
  if (e.target.closest("[data-group-close], .a-menu [data-act], .a-more [data-act]") || !e.target.closest(".a-actions")) closeGroups();
});
document.addEventListener("keydown", e => { if (e.key === "Escape") closeGroups(); });

function updateInteractiveButton(R) {
  const b = $("#interBtn"), tip = $("#interTip");
  if (!b) return;
  const busy = R.id && jobFor("explainer", R.id);
  b.classList.toggle("busy", !!busy);
  b.querySelector(".lbl").innerHTML = `${busy ? '<span class="spinner sm"></span>' : icon("play")}${h(t("inter.button"))}`;
  if (busy) {
    b.setAttribute("aria-disabled", "false");
    tip.className = "tip-text";
    tip.textContent = t(busy.status === "queued" ? "inter.queuedTip" : "inter.buildingTip");
    tip.style.whiteSpace = "normal";
    tip.style.width = "240px";
    return;
  }
  const info = R.interactive;
  if (!info && R.finished && !R.error && R.extras === false && R.id && !R.savedFile) {
    // searched without the explainer check: the reader can ask for it now
    b.setAttribute("aria-disabled", "false");
    tip.className = "tip-text";
    tip.textContent = t("inter.checkNow");
    tip.style.whiteSpace = "normal";
    tip.style.width = "260px";
    return;
  }
  if (!info) {
    b.setAttribute("aria-disabled", "true");
    tip.className = "tip-text";
    tip.textContent = R.finished ? t("inter.unavailable") : t("inter.checking");
    if (R.finished) tip.classList.add("bad");
    return;
  }
  b.setAttribute("aria-disabled", info.suitable ? "false" : "true");
  tip.className = "tip-text" + (info.suitable ? "" : " bad");
  tip.textContent = info.suitable ? (info.idea || t("inter.ready")) : t("inter.unavailable");
  tip.style.whiteSpace = info.suitable ? "normal" : "nowrap";
  tip.style.width = info.suitable ? "280px" : "";
}

// YouTube sources get a preview card (thumbnail + play mark) that opens the video
function videoCard(s) {
  if (!String(s.via || "").startsWith("youtube") || !s.og_image) return "";
  return `<a class="video-card" data-img href="${h(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">
    <img src="${h(s.og_image)}" alt="" loading="lazy" referrerpolicy="no-referrer" ${imgOnErr}><span class="vc-play">${icon("play")}</span>
    ${s.via === "youtube-nocaptions" ? `<span class="vc-note">${h(t("yt.noCaptions"))}</span>` : ""}</a>`;
}

function sourceEntry(s) {
  return `<li class="src-entry" id="src-${s.n}"><span class="se-n">${s.n}</span><div style="min-width:0">
    <div class="se-head">${s.local ? `<span class="fav-lib">${icon("folder")}</span>` : `<img class="fav" src="${favicon(s.domain)}" alt="">`}<a href="${h(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${h(s.title || s.url)}</a></div>
    <div class="se-meta"><span>${h(s.local ? s.path : s.site_name || s.domain)}</span>${s.source_type ? `<span class="tag">${h(s.source_type)}</span>` : ""}${trustBadge(s)}${(s.date || s.published) ? `<span>${h(String(s.date || s.published).slice(0, 10))}</span>` : ""}</div>
    ${videoCard(s)}
    ${s.trust_reason ? `<p class="se-reason">${h(s.trust_reason)}</p>` : ""}
    <div class="r-actions" style="margin-top:4px">${sourceActions(s)}</div></div></li>`;
}

function parseArticle(md) {
  const lines = stripThink(md).split("\n");
  let i = 0, title = null, dek = null;
  while (i < lines.length && !lines[i].trim()) i++;
  if (i < lines.length && /^#\s+/.test(lines[i])) {
    title = lines[i].replace(/^#\s+/, "").trim();
    i++;
    while (i < lines.length && !lines[i].trim()) i++;
    const m = i < lines.length && lines[i].trim().match(/^[*_]([^*_].*?)[*_]$/);
    if (m) { dek = m[1]; i++; }
  }
  return { title, dek, body: lines.slice(i).join("\n") };
}

function renderArticleBody(R, final = false) {
  const body = $("#aBody");
  if (!body) return;
  const { title, dek, body: md } = parseArticle(R.md);
  if (title) { $("#aTitle").textContent = title; document.title = `${title} - AIRAG`; }
  if (dek) $("#aDek").textContent = dek;
  allowLinks([...R.articleSources, ...Object.values(R.sources)].map(x => x.url));
  body.innerHTML = render(md) + (final ? "" : '<span class="cursor"></span>');
  allowLinks(null);
  if (final) showStats(md);
  const max = R.articleSources.length;
  $$(".cite", body).forEach(c => { if (+c.dataset.n > max || +c.dataset.n < 1) c.classList.add("missing"); });
}
const renderArticleBodyThrottled = rafThrottle(R => { if (RUN.current === R && !R.finished) renderArticleBody(R, false); });

function renderArticleSide(R) {
  const heads = $$("#aBody h2");
  heads.forEach((x, i) => { if (!x.id) x.id = "sec-" + i; });
  $("#runSide").innerHTML = `<div class="sticky">
    ${heads.length ? `<div class="side-card toc"><div class="side-title">${h(t("art.contents"))}</div><nav>${heads.map(x => `<a href="#" data-to="${h(x.id)}">${h(x.textContent)}</a>`).join("")}</nav></div>` : ""}
    <div class="side-card"><div class="side-title">${h(t("art.cited"))} <span class="count">${R.articleSources.length}</span></div><div class="src-list">
      ${R.articleSources.map(s => `<a class="src-row" href="#" data-src="${s.n}" title="${h(s.title)}"><span class="src-n">${s.n}</span><div style="min-width:0"><div class="sr-t">${h(s.title || s.domain)}</div><div class="sr-d">${h(srcDomain(s))}</div></div>${trustBadge(s, true)}</a>`).join("")}
    </div></div></div>`;
  $$("[data-to]").forEach(a => (a.onclick = e => { e.preventDefault(); document.getElementById(a.dataset.to)?.scrollIntoView({ behavior: "smooth", block: "start" }); }));
  $$("[data-src]", $("#runSide")).forEach(a => (a.onclick = e => { e.preventDefault(); flashSource(a.dataset.src); }));
  if (heads.length) {
    const obs = new IntersectionObserver(entries => {
      entries.forEach(en => { if (en.isIntersecting) $$(".toc a").forEach(a => a.classList.toggle("on", a.dataset.to === en.target.id)); });
    }, { rootMargin: "-80px 0px -70% 0px" });
    heads.forEach(x => obs.observe(x));
  }
}

function flashSource(n) {
  const el = document.getElementById("src-" + n);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1400);
}

// reading time and word count under the title
function showStats(md) {
  const el = $("#aStats");
  if (!el) return;
  const text = stripThink(md).replace(/\[\d+(?:,\s*\d+)*\]/g, " ").replace(/[#*_>`\-|[\]()]/g, " ");
  const cjk = (text.match(/[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/g) || []).length;
  const words = cjk > 200 ? cjk : (text.match(/\S+/g) || []).length;
  const minutes = Math.max(1, Math.round(words / (cjk > 200 ? 450 : 230)));
  el.textContent = " · " + t("art.stats", { min: minutes, words: words.toLocaleString(uiLang()) });
}

function setListenButton(state) {
  const b = $("#ttsBtn"), st = $("#ttsStop");
  if (!b) return;
  const playing = state === "playing", paused = state === "paused";
  b.innerHTML = `${icon(playing ? "pause" : "speak")}${h(t(playing ? "tts.pause" : paused ? "tts.resume" : "tts.listen"))}`;
  st.hidden = !(playing || paused);
}

async function togglePin(R) {
  const r = await api(`/api/history/${encodeURIComponent(R.id)}/pin`, { method: "POST", body: { pinned: !R.pinned } }).catch(e => { toast(e.message, 3500); return null; });
  if (!r) return;
  R.pinned = r.pinned;
  const b = $("#pinBtn span");
  if (b) b.textContent = t(R.pinned ? "pin.unpin" : "pin.pin");
  toast(t(R.pinned ? "pin.pinned" : "pin.unpinned"));
  hooks.refreshRecent();
}

function articleMarkdown(R) {
  const refs = R.articleSources.map(s => `${s.n}. [${s.title || s.url}](${s.local ? s.path : s.url}) - ${s.local ? "local file" : s.domain}${s.source_type ? ", " + s.source_type : ""}`).join("\n");
  return `${stripThink(R.md).trim()}\n\n## ${t("art.sources")}\n\n${refs}\n`;
}

// citation tooltips
const tip = $("#tip");
// Hover previews (desktop): [n] citations, and links to pages AIRAG read (title, site, trust, summary)
const hoverable = matchMedia("(hover: hover) and (pointer: fine)").matches;
function sourceForLink(url) {
  const R = RUN.current;
  if (!R || !url) return null;
  const clean = u => String(u).replace(/#.*$/, "").replace(/\/$/, "");
  const all = [...(R.articleSources || []), ...Object.values(R.sources || {})];
  return all.find(x => x.url && clean(x.url) === clean(url)) || null;
}
document.addEventListener("mouseover", e => {
  const c = e.target.closest(".cite");
  const a = !c && hoverable ? e.target.closest("#aBody a[href^='http'], .a-sources a[href^='http'], .result a.r-title") : null;
  if ((!c && !a) || !RUN.current) return;
  let s = c ? RUN.current.articleSources.find(x => x.n === +c.dataset.n) : sourceForLink(a.href);
  if (!s && a) {   // a link to a page AIRAG didn't read: just say where it goes
    let host = "";
    try { host = new URL(a.href).hostname.replace(/^www\./, ""); } catch { return; }
    s = { title: a.textContent.trim() || a.href, domain: host, url: a.href };
  }
  if (!s) return;
  const el = c || a;
  tip.innerHTML = `<div class="tt-head">${s.local ? icon("folder") : `<img class="fav" src="${favicon(s.domain)}" alt="">`}<span>${h(s.title || s.url)}</span></div>
    <div class="tt-meta"><span>${h(srcDomain(s))}</span>${s.source_type ? `<span>${h(s.source_type)}</span>` : ""}${s.trust != null || s.prior_label ? trustBadge(s) : ""}</div>
    ${s.summary ? `<p>${h(s.summary)}</p>` : ""}`;
  tip.hidden = false;
  const r = el.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
  const x = Math.min(Math.max(8, r.left + r.width / 2 - tw / 2), innerWidth - tw - 8);
  let y = r.top - th - 10;
  if (y < 70) y = r.bottom + 10;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
});
document.addEventListener("mouseout", e => { if (e.target.closest(".cite, #aBody a, .a-sources a, .result a.r-title")) tip.hidden = true; });
addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });
document.addEventListener("click", e => {
  const c = e.target.closest(".cite");
  if (c && !c.classList.contains("missing")) flashSource(c.dataset.n);
});

// suggestions + errors
function renderSuggestions(R) {
  const sg = R.suggestions;
  $("#output").innerHTML = `
    <div class="empty">
      <div class="empty-icon">${icon("searchOff")}</div>
      <h2>${h(t("sug.title"))}</h2>
      <p>${h(sg.message)}</p>
      ${sg.items?.length ? `<div class="sugg-title">${h(t("sug.try"))}</div><div class="sugg-grid">${sg.items.map(x => `
        <button class="sugg" data-act="search" data-q="${h(x.query)}"><span class="sq">${icon("search")}${h(x.query)}</span>${x.why ? `<span class="sw">${h(x.why)}</span>` : ""}</button>`).join("")}</div>` : ""}
      ${sg.sources?.length ? `<div class="also"><div class="also-title">${h(t("sug.partial"))}</div>${sg.sources.map(s => `
        <a class="lite" href="${h(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer"><div class="lite-t">${h(s.title || s.url)}</div><div class="lite-s">${h(srcDomain(s))} - ${h(s.summary || s.snippet || "")}</div></a>`).join("")}</div>` : ""}
      <details class="tried"><summary>${h(t("sug.tried", { n: (sg.tried || []).length }))}</summary><ul>${(sg.tried || []).map(q => `<li>${h(q)}</li>`).join("")}</ul></details>
      <div class="row" style="margin-top:20px"><button class="btn" data-act="article">${icon("doc")}${h(t("sug.anyway"))}</button></div>
    </div>`;
}

function renderError(R) {
  // nothing runs any more: stop every step spinner (it starts again with Try again)
  (R.steps || []).filter(st => st.status === "running").forEach(st => upsertStep(R, { ...st, status: "warn" }));
  if (R.cancelled) {
    $("#output").innerHTML = `<div class="empty"><div class="empty-icon">${icon("x")}</div><h2>${h(t("run.cancelled"))}</h2>
      <div class="row"><button class="btn primary" data-act="again">${icon("refresh")}${h(t("run.again"))}</button></div></div>`;
    const ph = $("#phIcon");
    if (ph) { ph.className = "ph-icon err"; ph.innerHTML = icon("x"); }
    setSub(t("run.cancelled"));
    return;
  }
  const msg = R.error || "Unknown error";
  const cfg = /api key|model|ollama|reach|provider|401|403|404|settings/i.test(msg);
  $("#output").innerHTML = `
    <div class="empty err-box">
      <div class="empty-icon">${icon("warn")}</div>
      <h2>${h(t("err.title"))}</h2>
      <p>${h(t(cfg ? "err.config" : "err.generic"))}</p>
      <div class="err-msg">${h(msg)}</div>
      <div class="row"><button class="btn primary" data-act="retry">${icon("refresh")}${h(t("err.retry"))}</button><button class="btn" data-act="settings" data-tab="model">${icon("gear")}${h(t("err.settings"))}</button></div>
    </div>`;
  const ph = $("#phIcon");
  if (ph) { ph.className = "ph-icon err"; ph.innerHTML = icon("warn"); }
  setSub(t("run.stopped"));
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { /* not allowed here */ }
  const ta = Object.assign(document.createElement("textarea"), { value: text });
  ta.style.cssText = "position:fixed;opacity:0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { /* */ }
  ta.remove();
  return ok;
}

// stop reading aloud and hide the research toolbar when leaving the article
window.addEventListener("hashchange", () => {
  ttsStop();
  if (!/^#\/(view|run)\//.test(location.hash)) hideToolbar();
});

/** Things the research toolbar's agent asked the app to do (read aloud, more sources, copy, pin). */
export function toolbarAction(ev) {
  const R = RUN.current;
  if (!R) return;
  if (ev.action === "listen" && ev.text) speak(ev.text, uiLang(), setListenButton);
  else if (ev.action === "more-sources" && R.id) startResearch(R.query, R.outcome === "article" ? "article" : "results", R.library, null, R.dates, null, false, R.id);
  else if (ev.action === "copy" && ev.text) copyText(ev.text).then(() => toast(t("art.copied")));
  else if (ev.action === "pin" && R.id && !R.pinned) togglePin(R);
}

setRegenHooks({ reload: id => reloadRecord(id), current: () => RUN.current });

/** Reloads an article after the toolbar changed it (rewrite, answer added). */
export function reloadRecord(id) {
  RUN.current = null;
  openRecord(id);
}

// saved runs
export async function openRecord(id, explainer = false) {
  RUN.ctrl?.abort();
  if (RUN.current && RUN.current.id === id && RUN.current.finished && !RUN.current.savedFile) {
    hooks.showView("run");
    if (explainer) openInteractive(RUN.current);
    return;
  }
  let rec;
  try {
    rec = await api(`/api/history/${encodeURIComponent(id)}`);
  } catch (e) {
    return showNotFound(e);
  }
  showRecord(rec);
  if (explainer && RUN.current) openInteractive(RUN.current);
}

/** An article saved in My library: shown from the saved copy, no AI or network needed. */
export async function openSaved(file) {
  RUN.ctrl?.abort();
  let rec;
  try {
    rec = await api(`/api/mylibrary/saved/${encodeURIComponent(file)}`);
  } catch (e) {
    return showNotFound(e);
  }
  showRecord(rec);
  if (rec.edited_outside) toast(t("open.reread"), 5000);   // the .md was edited after saving (e.g. in Obsidian)
}

function showNotFound(e) {
  hooks.showView("run");
  $("#runMain").innerHTML = `<div class="empty"><h2>${h(t("err.notFound"))}</h2><p>${h(e.message)}</p></div>`;
  $("#runSide").innerHTML = "";
}

function showRecord(rec) {
  const R = newRun(rec.query, rec.mode, rec.library, rec.dates ? { from: rec.dates[0], to: rec.dates[1] } : emptyRange(),
                   rec.extras !== false);
  Object.assign(R, {
    id: rec.id, model: rec.model, search: rec.search, created: rec.created, plan: rec.plan, outcome: rec.outcome,
    images: rec.images || [], md: rec.article || "", articleSources: rec.article_sources || [], related: rec.related || [],
    results: rec.results || null, suggestions: rec.suggestions || null, elapsed: rec.elapsed, interactive: rec.interactive || null,
    savedPath: rec.saved_path || null, savedFile: rec.saved_file || null, interactiveHtml: rec.interactive_html || "",
    openedFile: rec.opened_file || null,
    pinned: !!rec.pinned,
  });
  (rec.sources || []).forEach(s => (R.sources[s.id] = s));
  RUN.current = R;
  hooks.showView("run");
  scrollTo(0, 0);
  $("#topSearch input").value = rec.query;
  document.title = `${rec.title || rec.query} - AIRAG`;
  renderShell(R, true);
  (rec.steps || []).forEach(st => upsertStep(R, st));
  renderSourceSide(R);
  if (rec.outcome === "results" && R.results) renderResults(R);
  else if (rec.outcome === "article") renderArticle(R);
  else if (rec.outcome === "suggestions" && R.suggestions) renderSuggestions(R);
  else if (rec.outcome === "error") { R.error = rec.error || "?"; renderError(R); }
  finish(R);
  setSub(R.openedFile ? `${fmtDate(rec.created, uiLang())} · ${t("open.noAI")}`
    : `${fmtDate(rec.created, uiLang())} · ${rec.model} · ${t("run.found", { n: Object.keys(R.sources).length })} · ${rec.elapsed ?? "?"}s`);
}
