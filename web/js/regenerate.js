// Regenerate article: say what should be different (or Skip for a default "clearer" pass), and the article is
// written again from the same sources as a background job. Every version is kept: Undo steps back, Restore
// jumps to any version, Compare shows one next to the current text. Nothing is ever deleted.
import { $, $$, h, icon, api, apiStream, toast, fmtDate } from "./util.js";
import { render } from "./markdown.js";
import { t, uiLang } from "./i18n.js";
import { micButton } from "./speech.js";
import { pokeJobs } from "./activity.js";

let hooks = { reload: () => {} };
export function setRegenHooks(x) { hooks = { ...hooks, ...x }; }

const QUICK = ["simpler", "shorter", "detail", "formal", "clarify", "strongest"];

function dlg() {
  return $("#regenDlg") || document.body.appendChild(Object.assign(document.createElement("dialog"), { id: "regenDlg", className: "dlg tbx regen-dlg" }));
}

export async function openRegenerate(R, focusVersions = false) {
  const d = dlg();
  d.innerHTML = `<form method="dialog" class="regen">
    <div class="regen-main">
      <div class="dlg-head"><h2>${h(t("regen.title"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
      <p class="muted regen-intro">${h(t("regen.intro"))}</p>
      <label for="regenWhat" class="regen-label">${h(t("regen.what"))}</label>
      <div class="regen-ta"><textarea id="regenWhat" rows="4" placeholder="${h(t("regen.ph"))}"></textarea><span class="regen-mic"></span></div>
      <div class="chips regen-chips">${QUICK.map(k => `<button type="button" class="chip" data-quick="${k}">${h(t("regen.q." + k))}</button>`).join("")}</div>
      <details class="regen-more"><summary>${h(t("regen.moreOptions"))}</summary>
        <label class="switch"><input type="checkbox" id="regenKeep" checked> ${h(t("regen.keep"))}</label>
        <div class="help">${h(t("regen.keepHelp"))}</div>
        <div class="seg regen-len" role="radiogroup" aria-label="${h(t("regen.length"))}">${["same", "shorter", "longer"].map(l =>
          `<button type="button" data-len="${l}" class="${l === "same" ? "on" : ""}" role="radio" aria-checked="${l === "same"}">${h(t("regen.len." + l))}</button>`).join("")}</div>
      </details>
      <div class="regen-foot"><span class="muted">${h(t("regen.cost"))}</span>
        <button type="button" class="btn sm" id="regenSkip">${h(t("regen.skip"))}</button>
        <button type="button" class="btn sm primary" id="regenGo">${icon("refresh")}${h(t("regen.go"))}</button></div>
    </div>
    <aside class="regen-side" id="regenSide"><div class="status-line"><span class="spinner sm"></span></div></aside></form>`;
  d.showModal();
  const ta = $("#regenWhat", d);
  const mic = micButton(ta, said => { ta.value = (ta.value ? ta.value + " " : "") + said; });
  if (mic) $(".regen-mic", d).replaceWith(mic); else $(".regen-mic", d).remove();
  $$("[data-quick]", d).forEach(b => (b.onclick = () => {
    const txt = t("regen.q." + b.dataset.quick);
    ta.value = ta.value.trim() ? `${ta.value.trim().replace(/[.,;]$/, "")}, ${txt.toLowerCase()}` : txt;
    b.classList.add("on");
    ta.focus();
  }));
  let length = "same";
  $$("[data-len]", d).forEach(b => (b.onclick = () => {
    length = b.dataset.len;
    $$("[data-len]", d).forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", String(x === b)); });
  }));
  const go = instructions => { d.close(); run(R, instructions, $("#regenKeep", d).checked, length); };
  $("#regenGo", d).onclick = () => go(ta.value.trim());   // nothing usable typed = the default pass
  $("#regenSkip", d).onclick = () => go("");
  loadVersions(R, d);
  if (focusVersions) setTimeout(() => $("#regenSide", d)?.scrollIntoView({ block: "nearest" }), 50);
  else setTimeout(() => ta.focus(), 40);
}

const KIND = k => t("regen.kind." + (["first", "rewrite", "answer", "more", "regenerated", "edit"].includes(k) ? k : "edit"));

async function loadVersions(R, d) {
  const side = $("#regenSide", d);
  let v;
  try { v = await api(`/api/versions/${encodeURIComponent(R.id)}`); } catch (e) { side.innerHTML = `<p class="status-line err">${h(e.message)}</p>`; return; }
  const canUndo = v.items.some(x => x.n < v.pos);
  side.innerHTML = `<div class="regen-side-head"><h3>${h(t("regen.versions"))}</h3>
      <button type="button" class="btn sm" id="regenUndo" ${canUndo ? "" : "disabled"}>${icon("undo")}${h(t("regen.undo"))}</button></div>
    ${v.items.length ? `<ol class="regen-list">${v.items.map(x => `<li class="${x.n === v.pos ? "now" : ""}">
        <div class="regen-v-top"><strong>${h(t("regen.version", { n: x.n }))}${x.n === v.pos ? " · " + h(t("regen.now")) : ""}</strong><span class="muted">${h(fmtDate(x.at, uiLang()))}</span></div>
        <div class="regen-v-what">${h(KIND(x.kind))}${x.note ? `: “${h(x.note)}”` : ""}</div>
        ${x.n === v.pos ? "" : `<div class="regen-v-act"><button type="button" class="link-btn" data-cmp="${x.n}">${h(t("regen.compare"))}</button>
          <button type="button" class="link-btn" data-restore="${x.n}">${h(t("regen.restore"))}</button></div>`}</li>`).join("")}</ol>`
      : `<p class="muted">${h(t("regen.noVersions"))}</p>`}
    <p class="help">${h(t("regen.keptNote"))}</p>`;
  $("#regenUndo", d).onclick = () => change(R, d, `/api/versions/${encodeURIComponent(R.id)}/undo`, {});
  $$("[data-restore]", d).forEach(b => (b.onclick = () => change(R, d, `/api/versions/${encodeURIComponent(R.id)}/restore`, { n: +b.dataset.restore })));
  $$("[data-cmp]", d).forEach(b => (b.onclick = () => compare(R, +b.dataset.cmp)));
}

async function change(R, d, url, body) {
  try {
    await api(url, { method: "POST", body });
    toast(t("regen.changed"));
    d.close();
    hooks.reload(R.id);
  } catch (e) { toast(e.message, 4000); }
}

async function compare(R, n) {
  let v;
  try { v = await api(`/api/versions/${encodeURIComponent(R.id)}/${n}`); } catch (e) { toast(e.message, 4000); return; }
  const c = $("#regenCmp") || document.body.appendChild(Object.assign(document.createElement("dialog"), { id: "regenCmp", className: "dlg tbx" }));
  c.innerHTML = `<form method="dialog"><div class="dlg-head"><h2>${h(t("regen.compareTitle", { n }))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain"><div class="rw-cols"><div><h4>${h(t("regen.version", { n }))}</h4><div class="rw-old prose">${render(v.article)}</div></div>
      <div><h4>${h(t("regen.now"))}</h4><div class="rw-new prose">${render(R.md || "")}</div></div></div></div>
    <div class="dlg-foot"><button class="btn sm ghost" value="close">${h(t("common.close"))}</button>
      <button type="button" class="btn sm primary" id="cmpRestore">${h(t("regen.restore"))}</button></div></form>`;
  c.showModal();
  $("#cmpRestore", c).onclick = () => { c.close(); change(R, dlg(), `/api/versions/${encodeURIComponent(R.id)}/restore`, { n }); };
}

/** Runs the regeneration as a background job; the new text streams into the article while you watch. */
async function run(R, instructions, keepEdits, length) {
  const body = $("#aBody");
  let md = "", ok = false;
  body?.classList.add("regenerating");
  pokeJobs();
  try {
    await apiStream("/api/regenerate", { id: R.id, instructions, keep_edits: keepEdits, length, ui_lang: uiLang() }, ev => {
      if (ev.type === "token" && body && R === hooks.current?.()) { md += ev.text; body.innerHTML = render(md); }
      else if (ev.type === "error") throw new Error(ev.message);
      else if (ev.type === "cancelled") throw new Error(t("regen.cancelled"));
      else if (ev.type === "done") ok = true;
    });
  } catch (e) {
    toast(e.message, 6000);
  }
  body?.classList.remove("regenerating");
  if (ok) toast(t("regen.done"), 3000);
  if (R === hooks.current?.()) hooks.reload(R.id);   // the saved version (or the old text if it failed)
}
