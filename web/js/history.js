// History drawer and the "Recent" list on the home page.
import { $, $$, h, icon, api, fmtAgo } from "./util.js";
import { t, uiLang } from "./i18n.js";
import { jobHref } from "./activity.js";
import { pinnedCards } from "./pins.js";
import { pickFile } from "./openfile.js";

const outcomeIcon = o => ({ article: "doc", results: "list", suggestions: "bulb" }[o] || "search");
const outcomeLabel = o => t("outcome." + (o || "search"));

let tab = "history";
export function openDrawer(which = tab) {
  tab = which;
  $("#drawer").hidden = false;
  $("#scrim").hidden = false;
  $$("#drawerTabs button").forEach(b => {
    b.classList.toggle("on", b.dataset.tab === tab);
    b.onclick = () => openDrawer(b.dataset.tab);
  });
  tab === "saved" ? loadSaved() : loadHistory();
}

/** Articles saved in My library; they open from the saved copy, without the AI. */
export async function loadSaved() {
  const el = $("#historyList");
  try {
    const { items } = await api("/api/mylibrary/saved");
    const opener = `<button type="button" class="h-item h-open" id="openFileBtn">${icon("folder")}
        <div style="min-width:0"><div class="h-q">${h(t("open.button"))}</div><div class="h-d">${h(t("open.hint"))}</div></div></button>`;
    if (!items.length) { el.innerHTML = opener + `<div class="h-empty">${h(t("saved.empty"))}</div>`; wireOpener(); return; }
    el.innerHTML = opener + items.map(it => `
      <a class="h-item" href="#/saved/${encodeURIComponent(it.file)}">${icon(it.rich ? "palette" : "doc")}
        <div style="min-width:0"><div class="h-q">${h(it.title || it.query)}</div>
        <div class="h-d">${h(fmtAgo(it.created, uiLang()))}${it.rich ? ` · ${h(t("saved.rich"))}` : ""}${it.title !== it.query ? ` · "${h(it.query)}"` : ""}</div></div></a>`).join("");
    $$(".h-item", el).forEach(a => a.addEventListener("click", closeDrawer));
    wireOpener();
  } catch (e) { el.innerHTML = `<div class="h-empty">${h(e.message)}</div>`; }
}

function wireOpener() {
  const b = $("#openFileBtn");
  if (b) b.onclick = () => { closeDrawer(); pickFile(); };
}
export function closeDrawer() { $("#drawer").hidden = true; if ($("#sheet").hidden) $("#scrim").hidden = true; }

// searches still running or waiting, shown above the finished ones
async function activeRuns() {
  return (await api("/api/research/active").catch(() => ({ items: [] }))).items || [];
}

const activeLabel = a => (a.kind === "explainer" ? t("act.explainerShort") + " · " : a.kind === "more" ? t("act.moreShort") + " · " : "")
  + (a.status === "queued" ? t("run.queuedShort", { n: a.position }) : t("run.inProgress"));

function activeHtml(list) {
  return list.map(a => `
      <a class="h-item h-active" href="${jobHref(a)}"><span class="spinner sm"></span>
        <div style="min-width:0"><div class="h-q">${h(a.query)}</div><div class="h-d">${h(activeLabel(a))}</div></div>
        <button class="icon-btn" data-cancel="${h(a.id)}" title="${h(t("run.cancel"))}">${icon("x")}</button>
        <button class="icon-btn" data-cancel="${h(a.id)}" data-remove="1" title="${h(t("history.delete"))}">${icon("trash")}</button></a>`).join("");
}

function wireCancel(el, after) {
  $$("[data-cancel]", el).forEach(b => (b.onclick = async e => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(t("run.cancelConfirm"))) return;
    await api(`/api/research/${encodeURIComponent(b.dataset.cancel)}/cancel`, { method: "POST" }).catch(() => {});
    setTimeout(after, 300);
  }));
}

export async function loadHistory() {
  const el = $("#historyList");
  try {
    const [{ items }, active] = await Promise.all([api("/api/history"), activeRuns()]);
    if (!items.length && !active.length) { el.innerHTML = `<div class="h-empty">${h(t("history.empty"))}</div>`; return; }
    el.innerHTML = activeHtml(active) + items.map(it => `
      <a class="h-item" href="#/view/${encodeURIComponent(it.id)}">${icon(outcomeIcon(it.outcome))}
        <div style="min-width:0"><div class="h-q">${h(it.title || it.query)}</div>
        <div class="h-d">${h(outcomeLabel(it.outcome))} · ${h(fmtAgo(it.created, uiLang()))}${it.title && it.title !== it.query ? ` · "${h(it.query)}"` : ""}</div></div>
        <button class="icon-btn" data-del="${h(it.id)}" title="${h(t("history.delete"))}">${icon("trash")}</button></a>`).join("");
    $$("[data-del]", el).forEach(b => (b.onclick = async e => {
      e.preventDefault();
      e.stopPropagation();
      await api(`/api/history/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" });
      loadHistory();
      refreshRecent();
    }));
    wireCancel(el, () => { loadHistory(); refreshRecent(); });
    $$(".h-item", el).forEach(a => a.addEventListener("click", closeDrawer));
  } catch (e) { el.innerHTML = `<div class="h-empty">${h(e.message)}</div>`; }
}

export async function refreshRecent() {
  const el = $("#recent");
  try {
    const [{ items }, active] = await Promise.all([api("/api/history"), activeRuns()]);
    const saved = `<button type="button" class="link-btn" id="openSaved">${icon("book")}${h(t("saved.title"))}</button>`;
    const running = active.length ? `<div class="recent-grid" style="margin-bottom:10px">${active.map(a => `
      <button class="recent-item running" data-href="${h(jobHref(a))}"><span class="spinner sm"></span>
        <div><div class="ri-t">${h(a.query)}</div><div class="ri-k">${h(activeLabel(a))}</div></div></button>`).join("")}</div>` : "";
    if (!items.length && !active.length) { el.innerHTML = `<div class="recent-head">${saved}</div>`; $("#openSaved").onclick = () => openDrawer("saved"); return; }
    const card = it => `
      <button class="recent-item${it.pinned ? " pinned" : ""}" data-id="${h(it.id)}">${icon(it.pinned ? "pin" : outcomeIcon(it.outcome))}
        <div><div class="ri-t">${h(it.title || it.query)}</div><div class="ri-k">${h(outcomeLabel(it.outcome))} · ${h(fmtAgo(it.created, uiLang()))}</div></div></button>`;
    const pinned = items.filter(it => it.pinned), recent = items.filter(it => !it.pinned).slice(0, 6);
    el.innerHTML = pinnedCards() + (pinned.length ? `<div class="recent-head"><h3>${h(t("pin.title"))}</h3></div><div class="recent-grid" style="margin-bottom:14px">${pinned.map(card).join("")}</div>` : "")
      + `<div class="recent-head"><h3>${h(t("home.recent"))}</h3>${saved}</div>${running}<div class="recent-grid">${recent.map(card).join("")}</div>`;
    $$(".recent-item[data-id]", el).forEach(b => (b.onclick = () => (location.hash = `#/view/${encodeURIComponent(b.dataset.id)}`)));
    $$(".recent-item[data-href]", el).forEach(b => (b.onclick = () => (location.hash = b.dataset.href)));
    $$(".recent-item[data-pinned]", el).forEach(b => (b.onclick = () => (location.hash = `#/pinned/${encodeURIComponent(b.dataset.pinned)}`)));
    $("#openSaved").onclick = () => openDrawer("saved");
  } catch { /* server not ready */ }
}

window.addEventListener("airag:history", () => { refreshRecent(); });
window.addEventListener("airag:pins", () => { if (!$("#view-home").hidden) refreshRecent(); });
// background jobs started, finished or moved up the queue
window.addEventListener("airag:jobs", () => {
  if (!$("#view-home").hidden) refreshRecent();
  if (!$("#drawer").hidden && !$("#historyList .h-empty, #historyList [href^='#/saved/']")) loadHistory();
});
