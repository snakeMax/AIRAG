// "Export web page": the article (and optionally its summary, explainer and pictures) as ONE standalone
// HTML file to send to someone. Before exporting, the user picks what to include; parts that haven't
// been made yet (summary, explainer) are only made when ticked, since they cost AI tokens.
import { $, h, icon, api, apiStream, toast, stripThink } from "./util.js";
import { t, uiLang } from "./i18n.js";
import { cachedSummary, makeSummary, summaryHtml } from "./summary.js";
import { pokeJobs } from "./activity.js";

function dialog() {
  return $("#exportDlg") || document.body.appendChild(Object.assign(document.createElement("dialog"), { id: "exportDlg", className: "dlg narrow" }));
}

const sumKey = R => `a:${R.id}`;

export function exportHtml(R, articleEl) {
  if (!articleEl || !R.finished) return;
  const dlg = dialog();
  const hasSum = !!cachedSummary(sumKey(R));
  const hasX = !!R.interactiveHtml;
  const xPossible = hasX || (R.interactive?.suitable !== false && !R.savedFile);
  const hasPics = !!articleEl.querySelector("img");
  const opt = (id, on, label, note, disabled = false) => `<label class="switch exp-opt"><input type="checkbox" id="${id}" ${on ? "checked" : ""} ${disabled ? "disabled" : ""}>
      <span><b>${h(label)}</b><span class="help">${h(note)}</span></span></label>`;
  dlg.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${icon("html")} ${h(t("exp.button"))}</h2><button class="icon-btn" value="close">${icon("x")}</button></div>
    <div class="dlg-body plain"><p>${h(t("exp.intro"))}</p>
      ${opt("expSum", hasSum, t("exp.optSummary"), hasSum ? t("exp.ready") : t("exp.willMake"))}
      ${opt("expX", hasX, t("exp.optExplainer"), hasX ? t("exp.ready") : xPossible ? t("exp.willBuild") : t("exp.noneFits"), !xPossible)}
      ${hasPics ? opt("expPics", true, t("exp.optPictures"), t("exp.picturesNote")) : ""}
      <div class="status-line" id="expStatus"></div></div>
    <div class="dlg-foot"><button class="btn sm ghost" value="close">${h(t("common.cancel"))}</button>
      <button type="button" class="btn sm primary" id="expGo">${icon("html")}${h(t("exp.go"))}</button></div></form>`;
  if (!dlg.open) dlg.showModal();
  const ctrl = new AbortController();
  dlg.addEventListener("close", () => ctrl.abort(), { once: true });
  $("#expGo", dlg).onclick = () => run(R, articleEl, dlg, ctrl.signal);
}

async function buildExplainer(R, status, signal) {
  const res = await api("/api/interactive/start", { method: "POST", body: { id: R.id, force: false, ui_lang: uiLang() } });
  if (res.html) { R.interactiveHtml = res.html; return; }
  pokeJobs();
  let err = null;
  await apiStream(`/api/research/${encodeURIComponent(res.job)}/stream`, null, ev => {
    if (ev.type === "done" && ev.html) { R.interactiveHtml = ev.html; if (ev.interactive) R.interactive = ev.interactive; }
    else if (ev.type === "error") err = ev.message;
    else if (ev.type === "cancelled") err = t("inter.cancelled");
  }, signal, "GET");
  if (err) throw new Error(err);
  status(t("exp.explainerDone"));
}

async function run(R, articleEl, dlg, signal) {
  const go = $("#expGo", dlg), st = $("#expStatus", dlg);
  const status = (msg, busy = true) => { st.innerHTML = `${busy ? '<span class="spinner sm"></span>' : ""}${h(msg)}`; };
  const want = id => !!$(`#${id}`, dlg)?.checked;
  go.disabled = true;
  dlg.querySelectorAll("input").forEach(i => (i.disabled = true));
  try {
    let summary = "";
    if (want("expSum")) {
      status(t("exp.makingSummary"));
      summary = await makeSummary({ kind: "article", query: R.query, payload: { markdown: stripThink(R.md) }, key: sumKey(R) }, signal);
    }
    if (want("expX") && !R.interactiveHtml) {
      status(t("exp.buildingExplainer"));
      await buildExplainer(R, status, signal);
    }
    status(t("exp.working"));
    const clone = articleEl.cloneNode(true);
    clone.querySelectorAll(".a-actions, .cursor, #trNoteArt, button").forEach(x => x.remove());
    const r = await api("/api/export/html", { method: "POST", body: {
      id: R.id || "saved", title: $("#aTitle")?.textContent || R.query, body_html: clone.outerHTML,
      explainer: want("expX"), explainer_html: R.savedFile ? (R.interactiveHtml || "") : "",
      summary_html: summary ? summaryHtml(summary) : "", pictures: want("expPics"), lang: uiLang() } });
    showDone(dlg, r);
  } catch (e) {
    if (e.name === "AbortError") return;
    status(t("exp.failed", { e: e.message }), false);
    st.classList.add("err");
    go.disabled = false;
    dlg.querySelectorAll("input").forEach(i => (i.disabled = false));
  }
}

function showDone(dlg, r) {
  const kb = Math.max(1, Math.round(r.size / 1024));
  dlg.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${icon("html")} ${h(t("exp.doneTitle"))}</h2><button class="icon-btn" value="close">${icon("x")}</button></div>
    <div class="dlg-body plain"><p>${h(t("exp.done", { name: r.name, size: kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : kb + " KB" }))}</p>
      <p class="help">${h(t("exp.help"))}</p></div>
    <div class="dlg-foot"><button type="button" class="btn sm" id="expReveal">${icon("folder")}${h(t("exp.show"))}</button>
      <button type="button" class="btn sm primary" id="expOpen">${icon("html")}${h(t("exp.open"))}</button></div></form>`;
  const open = reveal => api("/api/export/open", { method: "POST", body: { name: r.name, reveal } }).catch(e => toast(e.message));
  $("#expOpen", dlg).onclick = () => { open(false); dlg.close(); };
  $("#expReveal", dlg).onclick = () => { open(true); dlg.close(); };
}
