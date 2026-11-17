// A research run: live progress, then results / article / suggestions. Also re-opens saved runs.
import { $, $$, h, safeUrl, favicon, shortUrl, stripThink, rafThrottle, icon, toast, api, apiStream, fmtDate } from "./util.js";
import { render, allowLinks } from "./markdown.js";
import { chipHtml, openDatePicker, emptyRange } from "./dates.js";
import { t, has, uiLang } from "./i18n.js";
import { openSummary } from "./summary.js";
import { openInteractive } from "./interactive.js";

export const RUN = { current: null, ctrl: null };
let hooks = { go: () => {}, openSettings: () => {}, showView: () => {}, refreshRecent: () => {} };
export function setRunHooks(x) { hooks = { ...hooks, ...x }; }

function newRun(query, mode, library, dates = emptyRange()) {
  return {
    query, mode, library, dates, id: null, model: "", search: "", created: new Date().toISOString(), steps: [], sources: {},
    plan: null, outcome: null, images: [], md: "", articleSources: [], related: [], results: null, suggestions: null,
    interactive: null, finished: false, error: null, t0: Date.now(), elapsed: null,
  };
}

// live run
export async function startResearch(query, mode, library, fromId = null, dates = emptyRange(), mergeId = null) {
  RUN.ctrl?.abort();
  const ctrl = new AbortController();
  RUN.ctrl = ctrl;
  const R = newRun(query, mode, library, dates);
  RUN.current = R;
  hooks.showView("run");
  scrollTo(0, 0);
  $("#topSearch input").value = query;
  document.title = `${query} - AIRAG`;
  renderShell(R);
  try {
    await apiStream("/api/research", { query, mode, include_library: !!library, ui_lang: uiLang(), from_id: fromId,
      date_from: dates?.from || "", date_to: dates?.to || "", merge_id: mergeId }, ev => {
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
    case "start":
      Object.assign(R, { id: ev.id, model: ev.model, search: ev.search, created: ev.created || R.created });
      setSub(`${ev.model} · ${ev.search}`);
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
  const rich = localStorage.getItem("airag.saveRich") === "1";
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
    localStorage.setItem("airag.saveRich", on ? "1" : "0");
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
  $(".again-chip")?.removeAttribute("hidden");
  updateSaveButton(R);
  const ph = $("#phIcon");
  if (ph) { ph.className = "ph-icon " + (R.error ? "err" : "ok"); ph.innerHTML = icon(R.error ? "warn" : "check"); }
  const pt = $(".ph-title");
  if (pt) pt.textContent = t("run.researchFor", { q: R.query });
  if (!R.error) {
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
      <button type="button" class="check-chip again-chip" data-act="again" ${done ? "" : "hidden"} title="${h(t("run.againTip"))}">${icon("refresh")}<span>${h(t("run.again"))}</span></button></div>
    <div id="output">${done ? "" : `<div class="skel" style="padding:8px 4px"><div style="width:70%"></div><div style="width:92%"></div><div style="width:84%"></div><div style="width:60%"></div></div>`}</div>`;
  $("#runSide").innerHTML = `<div class="sticky"><div class="side-card"><div class="side-title">${h(t("src.title"))} <span class="count" id="srcCount">0</span></div>
    <div class="src-list" id="srcList"><div class="muted" style="font-size:13px">${h(t("src.waiting"))}</div></div></div></div>`;
  $("#progressToggle").onclick = () => $("#progress").classList.toggle("collapsed");
  $("#runDates").onclick = e => openDatePicker(e.currentTarget, R.dates,
    d => hooks.go(R.query, R.mode || "auto", R.library, null, d), t("date.searchAgain"));
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
  return `<button class="link-btn" data-act="sum-source" data-sid="${s.id}">${icon("sparkle")}${h(t("sum.button"))}</button>${save}${lib}`;
}

// clicks inside the output area
$("#runMain").addEventListener("click", e => {
  const b = e.target.closest("[data-act]");
  const R = RUN.current;
  if (!b || !R) return;
  const act = b.dataset.act;
  if (act === "article") hooks.go(R.query, "article", R.library, R.id);   // reuse this search's sources
  else if (act === "results") hooks.go(R.query, "results", R.library);
  else if (act === "retry" || act === "again") hooks.go(R.query, R.mode || "auto", R.library, null, R.dates, R.id);
  else if (act === "search") hooks.go(b.dataset.q, "auto", R.library);
  else if (act === "settings") hooks.openSettings(b.dataset.tab);
  else if (act === "copy") navigator.clipboard.writeText(articleMarkdown(R)).then(() => toast(t("art.copied")));
  else if (act === "save") openSavePop(b, R);
  else if (act === "sum-article") openSummary({ kind: "article", query: R.query, payload: { markdown: stripThink(R.md) }, label: $("#aTitle")?.textContent || R.query, key: `a:${R.id}` });
  else if (act === "sum-results") {
    const items = (R.results?.items || []).filter(s => s.relevance != null).slice(0, 12);
    openSummary({ kind: "results", query: R.query, payload: { items }, label: t("res.title"), key: `r:${R.id}` });
  } else if (act === "sum-source") {
    const s = R.sources[b.dataset.sid] || R.articleSources.find(x => String(x.id) === b.dataset.sid);
    if (s) openSummary({ kind: "source", query: R.query, payload: { url: s.url }, label: s.title || s.url, key: `s:${s.url}` });
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
        </div>
      </div>
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
      <div class="a-byline"><span class="avatar">A</span><div><div class="by-name">${h(t("art.by"))}</div><div class="muted">${h(fmtDate(R.created, uiLang()))} · ${h(R.model)}</div></div>
        <div class="a-actions">
          <button class="btn sm" data-act="sum-article">${icon("sparkle")}${h(t("sum.button"))}</button>
          <button class="btn sm has-tip" data-act="interactive" id="interBtn" aria-disabled="true"><span class="lbl row" style="gap:7px">${icon("play")}${h(t("inter.button"))}</span><span class="tip-text" id="interTip">${h(t("inter.checking"))}</span></button>
          <button class="btn sm ghost" data-act="results">${icon("list")}${h(t("art.results"))}</button>
          <button class="btn sm" data-act="save" id="saveBtn" disabled title="${h(t("save.tip"))}">${icon("download")}${h(t("save.button"))}</button>
          <button class="btn sm ghost" data-act="copy">${icon("copy")}${h(t("art.copy"))}</button>
        </div></div>
      ${hero ? `<figure class="a-hero" data-img><img src="${h(hero.src)}" alt="${h(hero.title)}" referrerpolicy="no-referrer" ${imgOnErr}>
        <figcaption>${h(hero.title)}${hero.title ? " · " : ""}<a href="${h(safeUrl(hero.page_url))}" target="_blank" rel="noopener noreferrer">${h(hero.credit)}</a></figcaption></figure>` : ""}
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

function updateInteractiveButton(R) {
  const b = $("#interBtn"), tip = $("#interTip");
  if (!b) return;
  const info = R.interactive;
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

function sourceEntry(s) {
  return `<li class="src-entry" id="src-${s.n}"><span class="se-n">${s.n}</span><div style="min-width:0">
    <div class="se-head">${s.local ? `<span class="fav-lib">${icon("folder")}</span>` : `<img class="fav" src="${favicon(s.domain)}" alt="">`}<a href="${h(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${h(s.title || s.url)}</a></div>
    <div class="se-meta"><span>${h(s.local ? s.path : s.site_name || s.domain)}</span>${s.source_type ? `<span class="tag">${h(s.source_type)}</span>` : ""}${trustBadge(s)}${(s.date || s.published) ? `<span>${h(String(s.date || s.published).slice(0, 10))}</span>` : ""}</div>
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

function articleMarkdown(R) {
  const refs = R.articleSources.map(s => `${s.n}. [${s.title || s.url}](${s.local ? s.path : s.url}) - ${s.local ? "local file" : s.domain}${s.source_type ? ", " + s.source_type : ""}`).join("\n");
  return `${stripThink(R.md).trim()}\n\n## ${t("art.sources")}\n\n${refs}\n`;
}

// citation tooltips
const tip = $("#tip");
document.addEventListener("mouseover", e => {
  const c = e.target.closest(".cite");
  if (!c || !RUN.current) return;
  const s = RUN.current.articleSources.find(x => x.n === +c.dataset.n);
  if (!s) return;
  tip.innerHTML = `<div class="tt-head">${s.local ? icon("folder") : `<img class="fav" src="${favicon(s.domain)}" alt="">`}<span>${h(s.title || s.url)}</span></div>
    <div class="tt-meta"><span>${h(srcDomain(s))}</span>${s.source_type ? `<span>${h(s.source_type)}</span>` : ""}${trustBadge(s)}</div>
    ${s.summary ? `<p>${h(s.summary)}</p>` : ""}`;
  tip.hidden = false;
  const r = c.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
  const x = Math.min(Math.max(8, r.left + r.width / 2 - tw / 2), innerWidth - tw - 8);
  let y = r.top - th - 10;
  if (y < 70) y = r.bottom + 10;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
});
document.addEventListener("mouseout", e => { if (e.target.closest(".cite")) tip.hidden = true; });
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

// saved runs
export async function openRecord(id) {
  RUN.ctrl?.abort();
  if (RUN.current && RUN.current.id === id && RUN.current.finished && !RUN.current.savedFile) { hooks.showView("run"); return; }
  let rec;
  try {
    rec = await api(`/api/history/${encodeURIComponent(id)}`);
  } catch (e) {
    return showNotFound(e);
  }
  showRecord(rec);
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
}

function showNotFound(e) {
  hooks.showView("run");
  $("#runMain").innerHTML = `<div class="empty"><h2>${h(t("err.notFound"))}</h2><p>${h(e.message)}</p></div>`;
  $("#runSide").innerHTML = "";
}

function showRecord(rec) {
  const R = newRun(rec.query, rec.mode, rec.library, rec.dates ? { from: rec.dates[0], to: rec.dates[1] } : emptyRange());
  Object.assign(R, {
    id: rec.id, model: rec.model, search: rec.search, created: rec.created, plan: rec.plan, outcome: rec.outcome,
    images: rec.images || [], md: rec.article || "", articleSources: rec.article_sources || [], related: rec.related || [],
    results: rec.results || null, suggestions: rec.suggestions || null, elapsed: rec.elapsed, interactive: rec.interactive || null,
    savedPath: rec.saved_path || null, savedFile: rec.saved_file || null, interactiveHtml: rec.interactive_html || "",
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
  setSub(`${fmtDate(rec.created, uiLang())} · ${rec.model} · ${t("run.found", { n: Object.keys(R.sources).length })} · ${rec.elapsed ?? "?"}s`);
}
