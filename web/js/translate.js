// Translate the article or the results page into another language with the AI model.
import { $, h, icon, api, apiStream, toast } from "./util.js";
import { t, uiLang } from "./i18n.js";

let languages = null;
async function langs() {
  if (!languages) languages = (await api("/api/app/info").catch(() => ({}))).languages || [];
  return languages;
}

function popover(anchor, html) {
  $(".tr-pop")?.remove();
  const pop = document.createElement("div");
  pop.className = "date-pop tr-pop";
  pop.innerHTML = html;
  document.body.appendChild(pop);
  const r = anchor.getBoundingClientRect(), w = Math.min(300, innerWidth - 16);
  pop.style.width = w + "px";
  pop.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + "px";
  pop.style.top = (r.bottom + scrollY + 8) + "px";
  setTimeout(() => document.addEventListener("pointerdown", function away(e) {
    if (!pop.isConnected) { document.removeEventListener("pointerdown", away); return; }
    if (pop.contains(e.target) || anchor.contains(e.target)) return;
    pop.remove();
    document.removeEventListener("pointerdown", away);
  }), 0);
  return pop;
}

/** kind: "article" or "results". hooks.render() redraws the view after a change. */
export async function openTranslate(anchor, R, kind, hooks) {
  if ($(".tr-pop")) { $(".tr-pop").remove(); return; }
  const list = await langs();
  const current = R.translation?.[kind];
  const pick = current || hooks.defaultLang || localStorage.getItem("airag.translateTo") || uiLang();
  const pop = popover(anchor, `
    <label class="tr-label">${h(t("tr.to"))}
      <select class="input" id="trLang">${list.map(l => `<option value="${l.code}" ${l.code === pick ? "selected" : ""}>${h(l.native)}${l.native !== l.name ? ` (${h(l.name)})` : ""}</option>`).join("")}</select></label>
    <div class="muted" style="font-size:12px">${h(t("tr.help"))}</div>
    <div class="dp-foot">${current ? `<button type="button" class="btn sm ghost" id="trOrig">${h(t("tr.original"))}</button>` : "<span></span>"}
      <button type="button" class="btn sm primary" id="trGo">${icon("globe")}${h(t("tr.go"))}</button></div>`);
  $("#trOrig", pop)?.addEventListener("click", () => { pop.remove(); restore(R, kind); hooks.render(); });
  $("#trGo", pop).onclick = () => {
    const lang = $("#trLang", pop).value;
    localStorage.setItem("airag.translateTo", lang);
    pop.remove();
    (kind === "article" ? translateArticle : translateResults)(R, lang, hooks);
  };
}

export function restoreTranslation(R, kind) { restore(R, kind); }

function restore(R, kind) {
  if (kind === "article" && R.origMd != null) { R.md = R.origMd; R.origMd = null; }
  if (kind === "results" && R.origItems) { R.results.items = R.origItems; R.origItems = null; }
  if (R.translation) delete R.translation[kind];
}

async function translateArticle(R, lang, hooks) {
  const source = R.origMd ?? R.md;
  R.origMd = source;
  R.translation = { ...(R.translation || {}), article: lang };
  R.md = "";
  hooks.setBusy(true);
  try {
    await apiStream("/api/translate/article", { markdown: source, lang, id: R.id, ui_lang: uiLang() }, ev => {
      if (ev.type === "token") { R.md += ev.text; hooks.render(false); }
      if (ev.type === "error") throw new Error(ev.message);
    });
  } catch (e) {
    toast(e.message, 5000);
    restore(R, "article");
  }
  if (R.translation?.article === lang && R.md) R.translations = { ...(R.translations || {}), [lang]: R.md };
  hooks.setBusy(false);
  hooks.render(true);
}

async function translateResults(R, lang, hooks) {
  const items = R.origItems || R.results.items;
  hooks.setBusy(true);
  try {
    const todo = items.filter(s => s.relevance != null);
    const r = await api("/api/translate/items", { method: "POST", body: { lang, items: todo } });
    const byId = new Map(r.items.map(x => [String(x.id), x]));
    R.origItems = items;
    R.results.items = items.map(s => {
      const tr = byId.get(String(s.id));
      if (!tr) return s;
      const findings = (s.findings || []).map((f, i) => ({ ...f, claim: tr.findings?.[i] || f.claim }));
      return { ...s, title: tr.title || s.title, summary: tr.summary || s.summary, findings };
    });
    R.translation = { ...(R.translation || {}), results: lang };
  } catch (e) { toast(e.message, 5000); }
  hooks.setBusy(false);
  hooks.render(true);
}
