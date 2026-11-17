// Summary side sheet: short, query-focused summaries of articles, result lists and single sources.
import { $, h, icon, apiStream, toast, stripThink } from "./util.js";
import { render } from "./markdown.js";
import { t, uiLang } from "./i18n.js";

const cache = new Map();
let ctrl = null;

export function closeSummary() {
  ctrl?.abort();
  $("#sheet").hidden = true;
  if ($("#drawer").hidden) $("#scrim").hidden = true;
}

export async function openSummary({ kind, query, payload, label, key }) {
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
      <button class="btn sm ghost" data-redo>${icon("refresh")}${h(t("sum.again"))}</button></div>`;
  sheet.querySelector("[data-close]").onclick = closeSummary;
  let text = cache.get(key) || "";
  const out = () => $("#sumText");
  sheet.querySelector("[data-copy]").onclick = () => navigator.clipboard.writeText(stripThink(text)).then(() => toast(t("art.copied")));
  sheet.querySelector("[data-redo]").onclick = () => { cache.delete(key); openSummary({ kind, query, payload, label, key }); };
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
    cache.set(key, text);
  } catch (e) {
    if (e.name !== "AbortError") out().innerHTML = `<p class="status-line err">${h(e.message)}</p>`;
  }
}
