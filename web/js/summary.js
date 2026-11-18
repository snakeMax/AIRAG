// Summary side sheet: short, query-focused summaries of articles, result lists and single sources.
import { $, h, icon, apiStream, toast, stripThink } from "./util.js";
import { render as renderAll, allowLinks } from "./markdown.js";
import { t, uiLang } from "./i18n.js";

// summaries never need links of their own
const render = md => { allowLinks([]); try { return renderAll(md); } finally { allowLinks(null); } };

const cache = new Map();
const CACHE_MAX = 40;        // recent summaries kept in memory; older ones are made again if needed
const remember = (key, text) => {
  cache.delete(key);
  cache.set(key, text);
  while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);
};
let ctrl = null;

/** A summary already made in this session, if any (used by Export web page). */
export const cachedSummary = key => cache.get(key) || "";

/** Makes a summary without showing the sheet; returns the Markdown text. */
export async function makeSummary({ kind, query, payload, key }, signal) {
  if (cache.get(key)) return cache.get(key);
  let text = "";
  await apiStream("/api/summarize", { kind, query, payload, ui_lang: uiLang() }, ev => {
    if (ev.type === "token") text += ev.text;
    else if (ev.type === "error") throw new Error(ev.message);
  }, signal);
  text = stripThink(text);
  remember(key, text);
  return text;
}

/** Summary Markdown as HTML (no links). */
export const summaryHtml = md => render(stripThink(md));

export function closeSummary() {
  ctrl?.abort();
  $("#sheet").hidden = true;
  if ($("#drawer").hidden) $("#scrim").hidden = true;
}

export async function openSummary({ kind, query, payload, label, key, sources }) {
  ctrl?.abort();
  const sheet = $("#sheet");
  sheet.hidden = false;
  $("#scrim").hidden = false;
  sheet.innerHTML = `
    <div class="drawer-head"><h2>${h(t("sum.title"))}</h2><button class="icon-btn" data-close>${icon("x")}</button></div>
    <div class="drawer-body"><div class="sum-body">
      <div class="sum-for">${h(t("sum.forSearch", { q: query }))}</div>
      <div class="sum-what">${h(label)}</div>
      <div class="prose" id="sumText"><div class="row muted"><span class="spinner sm"></span>${h(t("sum.working"))}</div></div>
    </div></div>
    <div class="drawer-foot"><button class="btn sm" data-copy>${icon("copy")}${h(t("art.copy"))}</button>
      <button class="btn sm ghost" data-redo>${icon("refresh")}${h(t("sum.again"))}</button>
      <button class="btn sm ghost" data-file title="${h(t("sumfile.tip"))}">${icon("download")}${h(t("sumfile.button"))}</button></div>`;
  sheet.querySelector("[data-close]").onclick = closeSummary;
  let text = cache.get(key) || "";
  const out = () => $("#sumText");
  sheet.querySelector("[data-copy]").onclick = () => navigator.clipboard.writeText(stripThink(text)).then(() => toast(t("art.copied")));
  sheet.querySelector("[data-redo]").onclick = () => { cache.delete(key); openSummary({ kind, query, payload, label, key, sources }); };
  sheet.querySelector("[data-file]").onclick = e => import("./summaryfile.js")
    .then(m => m.downloadSummary({ kind, query, payload, label, key }, sources || [], e.currentTarget));
  if (text) { out().innerHTML = render(stripThink(text)); return; }
  const c = new AbortController();
  ctrl = c;
  try {
    await apiStream("/api/summarize", { kind, query, payload, ui_lang: uiLang() }, ev => {
      if (ev.type === "token") {
        text += ev.text;
        out().innerHTML = render(stripThink(text)) + '<span class="cursor"></span>';
      } else if (ev.type === "error") throw new Error(ev.message);
    }, c.signal);
    out().innerHTML = render(stripThink(text));
    remember(key, text);
  } catch (e) {
    if (e.name !== "AbortError") out().innerHTML = `<p class="status-line err">${h(e.message)}</p>`;
  }
}
