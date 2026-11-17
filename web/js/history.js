// History drawer and the "Recent" list on the home page.
import { $, $$, h, icon, api, fmtAgo } from "./util.js";
import { t, uiLang } from "./i18n.js";

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
    if (!items.length) { el.innerHTML = `<div class="h-empty">${h(t("saved.empty"))}</div>`; return; }
    el.innerHTML = items.map(it => `
      <a class="h-item" href="#/saved/${encodeURIComponent(it.file)}">${icon(it.rich ? "palette" : "doc")}
        <div style="min-width:0"><div class="h-q">${h(it.title || it.query)}</div>
        <div class="h-d">${h(fmtAgo(it.created, uiLang()))}${it.rich ? ` · ${h(t("saved.rich"))}` : ""}${it.title !== it.query ? ` · "${h(it.query)}"` : ""}</div></div></a>`).join("");
    $$(".h-item", el).forEach(a => a.addEventListener("click", closeDrawer));
  } catch (e) { el.innerHTML = `<div class="h-empty">${h(e.message)}</div>`; }
}
export function closeDrawer() { $("#drawer").hidden = true; if ($("#sheet").hidden) $("#scrim").hidden = true; }

export async function loadHistory() {
  const el = $("#historyList");
  try {
    const { items } = await api("/api/history");
    if (!items.length) { el.innerHTML = `<div class="h-empty">${h(t("history.empty"))}</div>`; return; }
    el.innerHTML = items.map(it => `
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
    $$(".h-item", el).forEach(a => a.addEventListener("click", closeDrawer));
  } catch (e) { el.innerHTML = `<div class="h-empty">${h(e.message)}</div>`; }
}

export async function refreshRecent() {
  const el = $("#recent");
  try {
    const { items } = await api("/api/history");
    const saved = `<button type="button" class="link-btn" id="openSaved">${icon("book")}${h(t("saved.title"))}</button>`;
    if (!items.length) { el.innerHTML = `<div class="recent-head">${saved}</div>`; $("#openSaved").onclick = () => openDrawer("saved"); return; }
    el.innerHTML = `<div class="recent-head"><h3>${h(t("home.recent"))}</h3>${saved}</div><div class="recent-grid">${items.slice(0, 6).map(it => `
      <button class="recent-item" data-id="${h(it.id)}">${icon(outcomeIcon(it.outcome))}
        <div><div class="ri-t">${h(it.title || it.query)}</div><div class="ri-k">${h(outcomeLabel(it.outcome))} · ${h(fmtAgo(it.created, uiLang()))}</div></div></button>`).join("")}</div>`;
    $$(".recent-item", el).forEach(b => (b.onclick = () => (location.hash = `#/view/${encodeURIComponent(b.dataset.id)}`)));
    $("#openSaved").onclick = () => openDrawer("saved");
  } catch { /* server not ready */ }
}

window.addEventListener("airag:history", () => { refreshRecent(); });
