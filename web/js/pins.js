// Pinned sources: keep a web page until you unpin it. Pinned pages are listed on the home page and open
// as the saved copy ("fetched") or as a short AI-written version ("generated"), per Settings -> Defaults.
import { $, h, icon, api, apiStream, toast, safeUrl, favicon, fmtAgo, stripThink } from "./util.js";
import { render, allowLinks } from "./markdown.js";
import { t, uiLang } from "./i18n.js";

export const PINS = { items: [], urls: new Set() };
let hooks = { showView: () => {}, defaultView: () => "fetched" };
export function setPinHooks(x) { hooks = { ...hooks, ...x }; }

export async function loadPins() {
  try {
    PINS.items = (await api("/api/pins/sources")).items || [];
  } catch { PINS.items = []; }
  PINS.urls = new Set(PINS.items.map(x => x.url));
  window.dispatchEvent(new Event("airag:pins"));
  return PINS.items;
}

export const isPinned = url => PINS.urls.has(url);
export const pinButton = s => s.local || !/^https?:/.test(s.url || "") ? "" :
  `<button class="link-btn" data-act="pin-source" data-sid="${s.id}">${icon("pin")}${h(t(isPinned(s.url) ? "pinsrc.unpin" : "pinsrc.pin"))}</button>`;

/** Pins (fetches and saves the page) or unpins a source; updates the button it was clicked from. */
export async function togglePinSource(s, query, btn) {
  if (btn) btn.disabled = true;
  try {
    if (isPinned(s.url)) {
      const item = PINS.items.find(x => x.url === s.url);
      await api(`/api/pins/source/${encodeURIComponent(item?.id || s.url)}`, { method: "DELETE" });
      toast(t("pinsrc.unpinned"));
    } else {
      await api("/api/pins/source", { method: "POST", body: { url: s.url, title: s.title || "", query, domain: s.domain || "",
        summary: s.summary || s.snippet || "", trust: s.trust ?? null, published: s.published || s.date || null, site_name: s.site_name || null } });
      toast(t("pinsrc.pinned"), 3500);
    }
    await loadPins();
    if (btn) btn.innerHTML = `${icon("pin")}${h(t(isPinned(s.url) ? "pinsrc.unpin" : "pinsrc.pin"))}`;
  } catch (e) { toast(e.message, 4500); }
  finally { if (btn) btn.disabled = false; }
}

export function pinnedCards() {
  if (!PINS.items.length) return "";
  return `<div class="recent-head"><h3>${h(t("pinsrc.title"))}</h3></div><div class="recent-grid" style="margin-bottom:14px">${PINS.items.map(x => `
    <button class="recent-item pinned" data-pinned="${h(x.id)}"><img class="fav" src="${favicon(x.domain)}" alt="">
      <div><div class="ri-t">${h(x.title)}</div><div class="ri-k">${h(x.domain)} · ${h(t("pinsrc.since", { when: fmtAgo(x.pinned_at, uiLang()) }))}</div></div></button>`).join("")}</div>`;
}

let ctrl = null;

/** The pinned-source page (#/pinned/<id>). */
export async function openPinned(id, view) {
  ctrl?.abort();
  hooks.showView("run");
  scrollTo(0, 0);
  let item;
  try { item = await api(`/api/pins/source/${encodeURIComponent(id)}`); }
  catch (e) {
    $("#runMain").innerHTML = `<div class="empty"><h2>${h(t("err.notFound"))}</h2><p>${h(e.message)}</p></div>`;
    $("#runSide").innerHTML = "";
    return;
  }
  view = view || hooks.defaultView() || "fetched";
  document.title = `${item.title} - AIRAG`;
  $("#runSide").innerHTML = "";
  $("#runMain").innerHTML = `<article class="article pinned-page">
    <div class="a-kicker"><span class="pill">${h(t("pinsrc.kicker"))}</span><span>${h(item.domain)}</span></div>
    <h1 class="a-title">${h(item.title)}</h1>
    <div class="a-byline"><img class="fav" src="${favicon(item.domain)}" alt=""><div class="muted">${h(t("pinsrc.since", { when: fmtAgo(item.pinned_at, uiLang()) }))}${item.query ? " · " + h(t("pinsrc.from", { q: item.query })) : ""}</div>
      <div class="a-actions">
        <div class="seg"><button type="button" data-pv="fetched" class="${view === "fetched" ? "on" : ""}">${h(t("pinsrc.fetched"))}</button>
          <button type="button" data-pv="generated" class="${view === "generated" ? "on" : ""}">${h(t("pinsrc.generated"))}</button></div>
        <a class="btn sm ghost" href="${h(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">${icon("ext")}${h(t("pinsrc.original"))}</a>
        <button type="button" class="btn sm ghost" id="pinUnpin">${icon("pin")}${h(t("pinsrc.unpin"))}</button>
      </div></div>
    <div class="a-body prose" id="pinBody"></div></article>`;
  $("#runMain").querySelectorAll("[data-pv]").forEach(b => (b.onclick = () => openPinned(id, b.dataset.pv)));
  $("#pinUnpin").onclick = async () => {
    if (!confirm(t("pinsrc.unpinConfirm"))) return;
    await api(`/api/pins/source/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(e => toast(e.message));
    await loadPins();
    location.hash = "#/";
  };
  const body = $("#pinBody");
  if (view === "fetched") {
    allowLinks([item.url]);
    try { body.innerHTML = render(item.text || ""); } finally { allowLinks(null); }
    return;
  }
  body.innerHTML = `<div class="row muted"><span class="spinner sm"></span>${h(t("sum.working"))}</div>`;
  const c = new AbortController();
  ctrl = c;
  let text = "";
  try {
    await apiStream("/api/summarize", { kind: "pinned", query: item.query || item.title, payload: { id }, ui_lang: uiLang() }, ev => {
      if (ev.type === "token") { text += ev.text; body.innerHTML = render(stripThink(text)) + '<span class="cursor"></span>'; }
      else if (ev.type === "error") throw new Error(ev.message);
    }, c.signal);
    body.innerHTML = render(stripThink(text));
  } catch (e) {
    if (e.name !== "AbortError") body.innerHTML = `<p class="status-line err">${h(e.message)}</p>`;
  }
}
