// Research toolbar: follow-up questions, compare / timeline / fact-check, rewrite, cite, calculate,
// voice commands and image analysis on a finished article (or results page).
//  - computer: a compact floating dock; "Follow-up" opens an ask box in it
//  - phone: a round menu button (three lines that turn upright when open) opening a sheet
//  - selecting text shows a small popup with actions for that text
//  - answers stream into a thread panel beside the article (a bottom sheet on phones)
import { addToNotes } from "./tonotes.js";
import { registerSnap } from "./snap.js";
import { $, $$, h, icon, api, apiStream, toast, stripThink } from "./util.js";
import { render, allowLinks } from "./markdown.js";
import { t, uiLang } from "./i18n.js";
import { micButton } from "./speech.js";
import { cite, STYLES } from "./cite.js";
import { speak } from "./tts.js";

let hooks = { getRun: () => null, reload: () => {}, citeStyle: () => "apa", act: () => {} };
const phone = () => matchMedia("(max-width: 720px)").matches;
const S = { R: null, open: false, panel: false, busy: null, calc: null, ctx: null };

export function initToolbar(x) {
  hooks = { ...hooks, ...x };
  document.body.insertAdjacentHTML("beforeend", `
    <div class="rt-stack" id="rtStack">
    <aside class="rt-panel" id="rtPanel" hidden aria-label="${h(t("rt.thread"))}">
      <div class="rt-panel-head"><h3>${h(t("rt.thread"))}</h3><button type="button" class="icon-btn" id="rtPanelX" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
      <div class="rt-thread" id="rtThread"></div>
    </aside>
    <nav class="rt-dock" id="rtDock" hidden aria-label="${h(t("rt.label"))}">
      <div class="rt-ctx" id="rtCtx" hidden><span class="rt-ctx-l">${h(t("rt.about"))}</span><span class="rt-ctx-t" id="rtCtxText"></span>
        <button type="button" class="rt-ctx-x" id="rtCtxX" aria-label="${h(t("rt.clearSel"))}" title="${h(t("rt.clearSel"))}">${icon("x")}</button></div>
      <form class="rt-ask" id="rtAsk" hidden><button type="button" class="rt-hist" data-rt="thread" hidden title="${h(t("rt.threadTip"))}" aria-label="${h(t("rt.threadTip"))}">${icon("list")}<b></b></button><input type="text" id="rtAskInput" autocomplete="off" placeholder="${h(t("rt.askPh"))}" aria-label="${h(t("rt.askPh"))}">
        <span class="rt-mic"></span><button type="submit" class="rt-send" aria-label="${h(t("rt.send"))}">${icon("send")}</button></form>
      <div class="rt-row">
        <button type="button" class="rt-main" data-rt="ask">${icon("chat")}<span>${h(t("rt.followup"))}</span></button>
        <span class="rt-sep" aria-hidden="true"></span>
        ${tool("compare", "columns")}${tool("timeline", "timeline")}${tool("factcheck", "checkCircle")}${tool("rewrite", "edit")}
        ${tool("calc", "calc")}${tool("cite", "quote")}
        <button type="button" class="rt-x rt-thread-btn" data-rt="thread" title="${h(t("rt.threadTip"))}" aria-label="${h(t("rt.threadTip"))}">${icon("list")}</button>
        <button type="button" class="rt-x" data-rt="collapse" title="${h(t("rt.collapse"))}" aria-label="${h(t("rt.collapse"))}">${icon("chevDown")}</button>
      </div>
    </nav>
    </div>
    <button type="button" class="rt-fab" id="rtFab" hidden aria-label="${h(t("rt.label"))}" aria-expanded="false"><span class="rt-burger"><i></i><i></i><i></i></span></button>
    <div class="rt-sel" id="rtSel" hidden role="toolbar" aria-label="${h(t("rt.selLabel"))}"></div>
    <div class="rt-calc" id="rtCalc" hidden role="status"></div>`);
  const dock = $("#rtDock");
  // snap panels: the answers and the calculator card can be dragged, snapped and minimized
  registerSnap("answers", $("#rtPanel"), { title: () => t("rt.thread"), head: el => $(".rt-panel-head", el), slot: "right-top",
    summary: el => [...el.querySelectorAll(".rt-answer")].at(-1)?.textContent || "" });
  registerSnap("calc", $("#rtCalc"), { title: () => t("snap.calc"), head: el => $(".rt-calc-head", el), slot: null,
    summary: el => $(".rt-calc-result", el)?.textContent || "" });
  dock.addEventListener("click", onDockClick);
  $("#rtFab").onclick = () => setOpen(!S.open);
  $("#rtPanelX").onclick = () => showPanel(false);
  $("#rtAsk").onsubmit = e => { e.preventDefault(); const q = $("#rtAskInput").value.trim(); if (q) { ask("ask", q, selText()); $("#rtAskInput").value = ""; } };
  $("#rtCtxX").onclick = clearCtx;
  $("#rtAskInput").addEventListener("focus", hideSel);
  const mic = micButton($("#rtAskInput"), text => { if (text.trim()) ask("voice", text, selText()); $("#rtAskInput").value = ""; });
  if (mic) $(".rt-mic", dock).replaceWith(mic); else $(".rt-mic", dock).remove();
  document.addEventListener("selectionchange", onSelection);
  document.addEventListener("pointerdown", e => {
    if (e.target.closest("#rtSel, #rtCalc, .rt-dock, .rt-panel, .rt-fab, dialog")) return;
    // dragging a selection handle also starts with a touch: only close the menu (and forget the text) if
    // there's no selection a moment later
    const inText = e.target.closest("#aTitle, #aDek, #aBody, .results");
    setTimeout(() => {
      if (!getSelection()?.isCollapsed) return;
      hideSel();
      if (inText) clearCtx();
    }, 450);
  });
  addEventListener("resize", layout);
  hookImages();
}

const tool = (k, ic) => `<button type="button" class="rt-tool" data-rt="${k}" title="${h(t("rt." + k + "Tip"))}">${icon(ic)}<span>${h(t("rt." + k))}</span></button>`;

/** Shown for a finished article or results page; hidden everywhere else. */
export function showToolbar(R) {
  if (R !== S.R) { clearCtx(); const th = $("#rtThread"); if (th) th.dataset.for = ""; }
  S.R = R;
  const on = !!(R && R.finished && R.id && !R.cancelled && !R.error);
  $("#rtDock").hidden = !on || phone();
  $("#rtFab").hidden = !on || !phone();
  if (!on) { setOpen(false); showPanel(false); hideSel(); return; }
  if (S.panel) showPanel(true);
  $("#rtDock").querySelectorAll("[data-rt=rewrite],[data-rt=calc]").forEach(b => (b.hidden = R.outcome !== "article"));
  layout();
}
export const hideToolbar = () => showToolbar(null);

function layout() {
  if (!S.R) return;
  const p = phone();
  $("#rtDock").hidden = p;
  $("#rtFab").hidden = !p;
  document.body.classList.toggle("rt-sheet", p && S.open);
  $("#rtDock").classList.toggle("as-sheet", p);
  if (p) $("#rtDock").hidden = !S.open;
}

function setOpen(open) {
  S.open = open;
  // the selection menu stays; on phones it moves to the top edge while the menu sheet is open at the bottom
  const sel = $("#rtSel");
  if (sel && !sel.hidden && S.selRect) requestAnimationFrame(() => placeSel(sel, S.selRect));
  $("#rtFab").classList.toggle("open", open);
  $("#rtFab").setAttribute("aria-expanded", String(open));
  if (phone()) { $("#rtDock").hidden = !open; $("#rtDock").classList.add("as-sheet"); }
  if (open && phone()) openAsk(false);
  if (phone() && S.panel) requestAnimationFrame(() => { const th = $("#rtThread"); th.scrollTop = th.scrollHeight; });
}

function openAsk(focus = true) {
  const f = $("#rtAsk");
  f.hidden = false;
  $("#rtDock").classList.add("asking");
  if (focus) setTimeout(() => $("#rtAskInput").focus(), 30);
}

// ---------------------------------------------------------------- remembered selection
// Phones drop the text selection on the next tap, so the selected text is remembered (and kept visibly
// marked) until it's cleared with ✕, replaced by a new selection, or the reader taps elsewhere in the article.
function setCtx(text, range) {
  S.ctx = { text, range: range ? range.cloneRange() : null };
  try { if (S.ctx.range && window.Highlight) CSS.highlights.set("rt-ctx", new Highlight(S.ctx.range)); } catch { /* old browser */ }
  const one = text.replace(/\s+/g, " ");
  $("#rtCtxText").textContent = "“" + (one.length > 140 ? one.slice(0, 140) + "…" : one) + "”";
  $("#rtCtx").hidden = false;
  $("#rtAskInput").placeholder = t("rt.askAboutPh");
}

function clearCtx() {
  S.ctx = null;
  try { CSS.highlights?.delete("rt-ctx"); } catch { /* old browser */ }
  const c = $("#rtCtx");
  if (c) c.hidden = true;
  const i = $("#rtAskInput");
  if (i) i.placeholder = t("rt.askPh");
}

function selText() {
  const sel = getSelection();
  const node = sel?.anchorNode?.parentElement;
  const live = sel && !sel.isCollapsed && node?.closest("#aTitle, #aDek, #aBody, .results, .rt-answer") ? sel.toString().trim() : "";
  return live || S.ctx?.text || "";
}

function onDockClick(e) {
  const b = e.target.closest("[data-rt]");
  if (!b) return;
  const k = b.dataset.rt, sel = selText();
  if (k === "ask") openAsk();
  else if (k === "collapse") { $("#rtAsk").hidden = true; $("#rtDock").classList.remove("asking"); if (phone()) setOpen(false); else $("#rtDock").classList.toggle("mini"); }
  else if (k === "thread") showPanel(!S.panel);
  else if (["compare", "timeline", "factcheck"].includes(k)) ask(k, "", sel);
  else if (k === "rewrite") sel ? rewrite(sel) : toast(t("rt.selectFirst"), 3500);
  else if (k === "calc") sel ? calculate(sel) : toast(t("rt.selectMath"), 3500);
  else if (k === "cite") citeDialog();
  if (phone() && k !== "ask") setOpen(false);
}

// ---------------------------------------------------------------- selection popup
let selTimer = 0;
function onSelection() {
  clearTimeout(selTimer);
  selTimer = setTimeout(() => {
    const sel = getSelection();
    if (!S.R || !sel || sel.isCollapsed) return;
    const node = sel.anchorNode?.parentElement;
    const inCalc = node?.closest("#rtCalc");
    if (!node?.closest("#aTitle, #aDek, #aBody, .results, .rt-answer") && !inCalc) return;
    const text = sel.toString().trim();
    if (text.length < 2) return;
    const range = sel.getRangeAt(0);
    if (!inCalc) setCtx(text, range);
    showSel(range.getBoundingClientRect(), text, !!inCalc);
  }, 180);
}

const looksLikeMath = s => /[0-9a-z]\s*[=+\-*/^×÷²³√]\s*[0-9a-z(]/i.test(s) || /\b(solve|integral|derivative|sqrt|equation|formula)\b/i.test(s);

// The menu follows the selection as it's changed (handles dragged) without being rebuilt, so its buttons stay
// steady. On touch screens it docks to the top or bottom edge, away from the selection, so it never sits where
// a selection handle is dragged (dragging onto it used to select the whole page).
function showSel(rect, text, inCalc) {
  const box = $("#rtSel");
  S.selText = text;
  S.selRect = rect;
  const elaborate = !!(S.calc && (inCalc || S.calc.formula === text));
  const article = S.R.outcome === "article";
  const math = !elaborate && looksLikeMath(text);
  const sig = [article, elaborate, math].join();
  if (box.hidden || box.dataset.sig !== sig) {
    const short = matchMedia("(pointer: coarse)").matches;      // docked bar on phones: short labels
    const btn = (k, ic, label) => `<button type="button" data-sel="${k}">${icon(ic)}<span>${h(label)}</span></button>`;
    box.innerHTML = btn("ask", "chat", t(short ? "rt.askShort" : "rt.askThis"))
      + btn("factcheck", "checkCircle", t("rt.factcheck"))
      + (article ? btn("rewrite", "edit", t("rt.rewrite")) : "")
      + (elaborate ? `<button type="button" data-sel="elaborate">${icon("sparkle")}<span><em>${h(t("rt.elaborate"))}</em></span></button>`
        : math ? btn("calc", "calc", t("rt.calc")) : "")
      + btn("copycite", "quote", t(short ? "rt.copyShort" : "rt.copyCite"))
      + `<span class="rt-sel-mic"></span>`;
    const voice = micButton(document.createElement("input"), said => { if (said.trim()) ask("voice", said, S.selText); });
    if (voice) {
      voice.classList.add("rt-voice");
      voice.title = t("rt.voiceTip");
      if (short) voice.insertAdjacentHTML("beforeend", `<span>${h(t("rt.voice"))}</span>`);
      $(".rt-sel-mic", box).replaceWith(voice);
    } else $(".rt-sel-mic", box).remove();
    box.dataset.sig = sig;
    const n = box.children.length;      // even rows: up to 4 in one row, otherwise two rows
    box.style.setProperty("--cols", String(n <= 4 ? n : Math.ceil(n / 2)));
  }
  box.hidden = false;
  placeSel(box, rect);
  box.onpointerdown = e => { if (e.target.closest("[data-sel]")) e.preventDefault(); };   // keeps the selection
  box.onclick = e => {
    const b = e.target.closest("[data-sel]");
    if (!b) return;
    const k = b.dataset.sel, text = S.selText || selText();
    if (k === "ask") { if (!S.ctx) setCtx(text, null); if (phone()) setOpen(true); openAsk(); }
    else if (k === "factcheck") ask("factcheck", "", text);
    else if (k === "rewrite") rewrite(text);
    else if (k === "calc") calculate(text, S.selRect);
    else if (k === "elaborate") elaborate();
    else if (k === "copycite") copyWithSource(text);
    hideSel();
  };
}

function placeSel(box, rect) {
  const touch = matchMedia("(pointer: coarse)").matches;
  box.classList.toggle("docked", touch);
  if (touch) {
    // the half of the screen the selection isn't in; above the round menu button at the bottom. While the
    // menu sheet is open (it fills the bottom), always the top edge
    const below = !S.open && (rect.top + rect.bottom) / 2 < innerHeight * 0.55;
    box.style.left = box.style.right = "";
    box.style.top = below ? "" : "64px";
    box.style.bottom = below ? "calc(88px + env(safe-area-inset-bottom))" : "";
    return;
  }
  box.style.bottom = "";
  const w = box.offsetWidth, hgt = box.offsetHeight;
  const x = Math.min(Math.max(8, rect.left + rect.width / 2 - w / 2), innerWidth - w - 8);
  let y = rect.top - hgt - 10;
  if (y < 60) y = rect.bottom + 10;
  if (y + hgt > innerHeight - 8) y = Math.max(60, rect.top - hgt - 10);
  box.style.left = x + "px";
  box.style.top = y + "px";
}
function hideSel() { const b = $("#rtSel"); if (b) b.hidden = true; }

// ---------------------------------------------------------------- thread panel
function showPanel(on) {
  S.panel = on;
  if (on && phone() && S.open) setOpen(false);   // phones: the answer gets the room, the menu folds away
  $("#rtPanel").hidden = !on;
  document.body.classList.toggle("rt-panel-open", on && !phone());
  if (on && S.R && $("#rtThread").dataset.for !== S.R.id) loadThread();
}

let loading = null;
function loadThread() {
  const el = $("#rtThread");
  if (el.dataset.for === S.R.id && loading) return loading;
  el.dataset.for = S.R.id;
  return (loading = drawThread(el, S.R.id));
}

async function drawThread(el, id) {
  const { items } = await api(`/api/followup/${encodeURIComponent(id)}`).catch(() => ({ items: [] }));
  if (el.dataset.for !== id) return;
  S.answers = items.map(it => ({ q: it.q, a: it.a }));
  el.innerHTML = items.length ? items.map((it, i) => entryHtml(it, i)).join("") : `<p class="muted rt-empty">${h(t("rt.empty"))}</p>`;
  el.querySelectorAll(".rt-answer").forEach((a, i) => fill(a, items[i].a));
  countAnswers(items.length);
  wireEntries();
  el.scrollTop = el.scrollHeight;
}

const MODE_LABEL = m => t(m === "ask" || m === "voice" ? "rt.followup" : m === "explain" ? "rt.explain" : "rt." + m);

function countAnswers(n) {
  const b = $(".rt-hist");
  if (!b) return;
  b.hidden = !n;
  $("b", b).textContent = n ? String(n) : "";
}

function entryHtml(it, i) {
  return `<div class="rt-entry" data-i="${i}"><div class="rt-q"><span class="rt-mode">${h(MODE_LABEL(it.mode))}</span>${h(it.q)}</div>
    ${it.selection ? `<blockquote class="rt-quote">${h(it.selection.slice(0, 220))}</blockquote>` : ""}
    <div class="rt-tools">${(Array.isArray(it.tools) ? it.tools : []).map(x => `<span class="rt-chip">${icon("tool")}${h(x.label || x.name || x)}</span>`).join("")}</div><div class="rt-answer prose"></div>
    <div class="rt-entry-foot">${footHtml(it, i)}</div></div>`;
}

const footHtml = (it, i) => (S.R?.outcome === "article" && !it.added && it.a
  ? `<button type="button" class="link-btn" data-add="${i}">${icon("plus")}${h(t("rt.addToArticle"))}</button>` : "")
  + (it.a ? `<button type="button" class="link-btn" data-explain><em>${h(t("rt.elaborate"))}</em></button>` : "")
  + (it.a ? `<button type="button" class="link-btn" data-speak>${icon("speak")}${h(t("tts.listen"))}</button>` : "")
  + (it.a ? `<button type="button" class="link-btn" data-tonotes="${i}" title="${h(t("tn.descAnswer"))}">${icon("file")}${h(t("tn.button"))}</button>` : "");

function fill(el, md) {
  const urls = (S.R?.articleSources || []).map(s => s.url);
  allowLinks(urls);
  try { el.innerHTML = render(stripThink(md || "")); } finally { allowLinks(null); }
}

function wireEntries() {
  $$("#rtThread [data-add]").forEach(b => (b.onclick = async () => {
    b.disabled = true;
    try { await api(`/api/followup/${encodeURIComponent(S.R.id)}/add`, { method: "POST", body: { index: +b.dataset.add } }); toast(t("rt.added")); b.remove(); hooks.reload(S.R.id); }
    catch (e) { toast(e.message, 4000); b.disabled = false; }
  }));
  $$("#rtThread [data-tonotes]").forEach(b => (b.onclick = () => {
    const it = S.answers?.[+b.dataset.tonotes];
    if (it?.a) addToNotes({ kind: "answer", title: it.q, text: `> ${it.q}\n\n${stripThink(it.a).trim()}\n`, query: S.R?.query || "" });
  }));
  $$("#rtThread [data-speak]").forEach(b => (b.onclick = () => speak(b.closest(".rt-entry").querySelector(".rt-answer").innerText, uiLang())));
  // elaborate on an answer that's open (or a rewrite that replaced article text)
  $$("#rtThread [data-explain]").forEach(b => (b.onclick = () =>
    ask("explain", t("rt.elaborateQ2"), b.closest(".rt-entry").querySelector(".rt-answer").innerText.slice(0, 3000))));
}

let askCtrl = null;
/** Runs a follow-up (or a toolbar action) and streams the answer into the thread panel. */
export async function ask(mode, question, selection = "", extra = null) {
  if (!S.R) return;
  if (phone()) setOpen(false);      // fold the menu away so the answer is visible (the question stays in the answer)
  showPanel(true);
  const el = $("#rtThread");
  await loadThread();
  el.querySelector(".rt-empty")?.remove();
  const i = el.querySelectorAll(".rt-entry").length;
  el.insertAdjacentHTML("beforeend", entryHtml({ q: question || MODE_LABEL(mode), mode, selection, a: "" }, i));
  const entry = el.lastElementChild, out = $(".rt-answer", entry), tools = $(".rt-tools", entry);
  out.innerHTML = `<span class="spinner sm"></span>`;
  entry.scrollIntoView({ block: "end", behavior: "smooth" });
  askCtrl?.abort();
  const ctrl = new AbortController();
  askCtrl = ctrl;
  let md = "";
  try {
    await apiStream("/api/followup", { id: S.R.id, question, mode, selection, ui_lang: uiLang(), extra }, ev => {
      if (ev.type === "token") { md += ev.text; fill(out, md + " ▍"); }
      else if (ev.type === "tool") tools.insertAdjacentHTML("beforeend", `<span class="rt-chip">${icon("tool")}${h(ev.label)}</span>`);
      else if (ev.type === "tool_result") tools.lastElementChild?.setAttribute("title", ev.text);
      else if (ev.type === "action") hooks.act(ev);
      else if (ev.type === "error") throw new Error(ev.message);
      else if (ev.type === "done") { fill(out, ev.entry.a || md); md = ev.entry.a || md; }
    }, ctrl.signal);
    (S.answers ||= [])[i] = { q: question || MODE_LABEL(mode), a: md };
    $(".rt-entry-foot", entry).innerHTML = footHtml({ a: md }, i);
    countAnswers(el.querySelectorAll(".rt-entry").length);
    wireEntries();
  } catch (e) {
    if (e.name !== "AbortError") out.innerHTML = `<p class="status-line err">${h(e.message)}</p>`;
  }
}

// ---------------------------------------------------------------- calculate / elaborate
async function calculate(text, rect) {
  const card = $("#rtCalc");
  card.hidden = false;
  card.innerHTML = `<span class="spinner sm"></span>${h(t("rt.calculating"))}`;
  place(card, rect);
  try {
    const r = await api("/api/tools/calculate", { method: "POST", body: { text } });
    S.calc = { formula: text, expr: r.expr, result: r.result + (r.approx ? ` ≈ ${r.approx}` : "") };
    card.innerHTML = `<div class="rt-calc-head"><span>${h(t("rt.solution"))}</span><button type="button" class="icon-btn sm" data-x aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
      <div class="rt-calc-result">${h(S.calc.result)}</div><div class="rt-calc-expr">${h(r.expr)}</div>
      <button type="button" class="link-btn rt-elab"><em>${h(t("rt.elaborate"))}</em></button>`;
  } catch (e) {
    S.calc = null;
    card.innerHTML = `<div class="rt-calc-head"><span>${h(t("rt.calcFailed"))}</span><button type="button" class="icon-btn sm" data-x aria-label="${h(t("common.close"))}">${icon("x")}</button></div><p class="muted">${h(e.message)}</p>`;
  }
  $("[data-x]", card).onclick = () => { card.hidden = true; S.calc = null; };
  const el = $(".rt-elab", card);
  if (el) el.onclick = elaborate;
}

function elaborate() {
  if (!S.calc) return;
  ask("elaborate", t("rt.elaborateQ"), S.calc.formula, S.calc);
}

function place(el, rect) {
  const r = rect || { left: innerWidth / 2, top: innerHeight / 2, width: 0, bottom: innerHeight / 2 };
  el.style.left = Math.min(Math.max(8, r.left + (r.width || 0) / 2 - 150), innerWidth - 316) + "px";
  el.style.top = Math.min(innerHeight - 160, (r.bottom || r.top) + 12) + "px";
}

// ---------------------------------------------------------------- rewrite (preview side by side first)
function dlg(id) {
  return $("#" + id) || document.body.appendChild(Object.assign(document.createElement("dialog"), { id, className: "dlg tbx" }));
}

function rewrite(text) {
  const d = dlg("rwDlg");
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${icon("edit")} ${h(t("rw.title"))}</h2><button class="icon-btn" value="close">${icon("x")}</button></div>
    <div class="dlg-body plain"><div class="row rw-ins"><input type="text" class="input" id="rwIns" placeholder="${h(t("rw.ph"))}" style="flex:1"><span class="rw-mic"></span>
      <button type="button" class="btn sm primary" id="rwGo">${icon("sparkle")}${h(t("rw.go"))}</button></div>
      <div class="rw-cols"><div><h4>${h(t("rw.original"))}</h4><div class="rw-old prose" id="rwOld">${h(text)}</div></div>
        <div><h4>${h(t("rw.new"))}</h4><div class="rw-new prose" id="rwNew"><p class="muted">${h(t("rw.hint"))}</p></div></div></div></div>
    <div class="dlg-foot"><button class="btn sm ghost" value="close">${h(t("common.cancel"))}</button>
      <button type="button" class="btn sm" id="rwCopy" disabled>${icon("copy")}${h(t("rw.copy"))}</button>
      <button type="button" class="btn sm primary" id="rwReplace" disabled>${icon("check")}${h(t("rw.replace"))}</button></div></form>`;
  d.showModal();
  const ins = $("#rwIns", d);
  const mic = micButton(ins, said => { ins.value = said; go(); });
  if (mic) $(".rw-mic", d).replaceWith(mic); else $(".rw-mic", d).remove();
  let result = null;
  const go = async () => {
    $("#rwGo", d).disabled = true;
    $("#rwNew", d).innerHTML = `<span class="spinner sm"></span>`;
    let md = "";
    try {
      await apiStream("/api/rewrite", { id: S.R.id, selection: text, instructions: ins.value, ui_lang: uiLang() }, ev => {
        if (ev.type === "target") $("#rwOld", d).innerHTML = render(ev.old);
        else if (ev.type === "token") { md += ev.text; $("#rwNew", d).innerHTML = render(md); }
        else if (ev.type === "done") { result = ev; $("#rwNew", d).innerHTML = render(ev.new); }
        else if (ev.type === "error") throw new Error(ev.message);
      });
      $("#rwCopy", d).disabled = $("#rwReplace", d).disabled = !result;
    } catch (e) { $("#rwNew", d).innerHTML = `<p class="status-line err">${h(e.message)}</p>`; }
    $("#rwGo", d).disabled = false;
  };
  $("#rwGo", d).onclick = go;
  ins.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); go(); } };
  $("#rwCopy", d).onclick = () => copy(result.new).then(() => toast(t("art.copied")));
  $("#rwReplace", d).onclick = async () => {
    try {
      await api("/api/rewrite/apply", { method: "POST", body: { id: S.R.id, old: result.old, new: result.new, instructions: ins.value } });
      d.close();
      toast(t("rw.done"));
      clearCtx();
      S.panel = true;          // the reloaded article opens with the answers showing the rewrite (with Elaborate)
      hooks.reload(S.R.id);
    } catch (e) { toast(e.message, 4500); }
  };
  setTimeout(() => ins.focus(), 30);
}

// ---------------------------------------------------------------- citations
function sourcesOf(R) { return R.articleSources?.length ? R.articleSources : Object.values(R.sources || {}).filter(s => s.relevance >= 4); }

function citeDialog() {
  const d = dlg("citeDlg");
  let style = hooks.citeStyle() || "apa";
  const draw = () => {
    const list = sourcesOf(S.R).filter(s => /^https?:/.test(s.url || ""));
    const text = list.map((s, i) => cite(s, style, i + 1)).join(style === "bibtex" ? "\n\n" : "\n");
    d.innerHTML = `<form method="dialog">
      <div class="dlg-head"><h2>${icon("quote")} ${h(t("cite.title"))}</h2><button class="icon-btn" value="close">${icon("x")}</button></div>
      <div class="dlg-body plain"><div class="seg">${Object.keys(STYLES).map(k => `<button type="button" data-style="${k}" class="${k === style ? "on" : ""}">${h(t("cite." + k))}</button>`).join("")}</div>
        <pre class="cite-out">${h(text)}</pre></div>
      <div class="dlg-foot"><button type="button" class="btn sm" id="ciDl">${icon("download")}${h(t("cite.download"))}</button>
        <button type="button" class="btn sm primary" id="ciCopy">${icon("copy")}${h(t("cite.copyAll"))}</button></div></form>`;
    $$("[data-style]", d).forEach(b => (b.onclick = () => { style = b.dataset.style; draw(); }));
    $("#ciCopy", d).onclick = () => copy(text).then(() => toast(t("art.copied")));
    $("#ciDl", d).onclick = () => {
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text], { type: "text/plain" })),
        download: `airag-sources.${style === "bibtex" ? "bib" : "txt"}` });
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    };
  };
  draw();
  if (!d.open) d.showModal();
}

function copyWithSource(text) {
  const nums = [...new Set([...text.matchAll(/\[(\d+)\]/g)].map(m => +m[1]))];
  const src = sourcesOf(S.R).filter(s => nums.includes(s.n));
  const clean = text.replace(/\s*\[\d+(?:,\s*\d+)*\]/g, "").trim();
  const style = hooks.citeStyle() || "apa";
  const refs = (src.length ? src : sourcesOf(S.R).slice(0, 1)).map((s, i) => cite(s, style, i + 1)).join("\n");
  copy(`"${clean}"\n\n${refs}`).then(() => toast(t("rt.copiedCite")));
}

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return; } catch { /* fallback */ }
  const ta = Object.assign(document.createElement("textarea"), { value: text });
  ta.style.cssText = "position:fixed;opacity:0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); } finally { ta.remove(); }
}

// ---------------------------------------------------------------- analyze image (press and hold, or right-click)
function hookImages() {
  let timer = 0;
  const target = e => e.target.closest?.("#aBody img, .gallery img, .a-hero img, #aBody svg");
  const menu = (el, x, y) => {
    const box = $("#rtSel");
    box.innerHTML = `<button type="button" data-img>${icon("eye")}<span>${h(t("rt.analyzeImage"))}</span></button>`;
    box.dataset.sig = "image";
    box.classList.remove("docked");
    box.style.bottom = "";
    box.hidden = false;
    box.style.left = Math.min(x, innerWidth - 200) + "px";
    box.style.top = Math.max(60, y - 56) + "px";
    $("[data-img]", box).onclick = () => { hideSel(); analyze(el); };
  };
  document.addEventListener("contextmenu", e => { const el = target(e); if (el && S.R) { e.preventDefault(); menu(el, e.clientX, e.clientY); } });
  document.addEventListener("touchstart", e => {
    const el = target(e);
    if (!el || !S.R) return;
    const p = e.touches[0];
    timer = setTimeout(() => menu(el, p.clientX, p.clientY), 550);
  }, { passive: true });
  ["touchend", "touchmove", "touchcancel"].forEach(ev => document.addEventListener(ev, () => clearTimeout(timer), { passive: true }));
}

async function imageData(el) {
  if (el.tagName.toLowerCase() === "svg") {   // drawn equations / charts: turn the SVG into a picture
    const xml = new XMLSerializer().serializeToString(el);
    const img = new Image();
    img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(xml)));
    await img.decode();
    const c = Object.assign(document.createElement("canvas"), { width: img.width * 2 || 800, height: img.height * 2 || 600 });
    const g = c.getContext("2d");
    g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
    g.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/png");
  }
  return el.currentSrc || el.src;
}

async function analyze(el) {
  showPanel(true);
  const th = $("#rtThread");
  await loadThread();
  th.querySelector(".rt-empty")?.remove();
  th.insertAdjacentHTML("beforeend", `<div class="rt-entry"><div class="rt-q"><span class="rt-mode">${h(t("rt.analyzeImage"))}</span></div><div class="rt-answer prose"><span class="spinner sm"></span></div></div>`);
  const out = th.lastElementChild.querySelector(".rt-answer");
  let md = "";
  try {
    const image = await imageData(el);
    await apiStream("/api/analyze-image", { image, id: S.R.id, ui_lang: uiLang() }, ev => {
      if (ev.type === "token") { md += ev.text; fill(out, md); }
      else if (ev.type === "error") throw new Error(ev.message);
    });
  } catch (e) { out.innerHTML = `<p class="status-line err">${h(e.message)}</p>`; }
}
