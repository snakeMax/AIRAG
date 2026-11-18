// "Download summary": a small Markdown file with the summary and the sources' links, saved in My library/Summaries.
// An existing summary is reused; otherwise one is made first (that's the only part that uses AI tokens).
import { $, h, icon, api, toast } from "./util.js";
import { t } from "./i18n.js";
import { makeSummary } from "./summary.js";

/**
 * @param spec  same shape as for openSummary: { kind, query, payload, key, label }
 * @param sources  [{ n, title, url }] to list under the summary
 * @param button  the button pressed (shows a spinner while working)
 */
export async function downloadSummary(spec, sources, button) {
  const old = button?.innerHTML;
  if (button) { button.disabled = true; button.innerHTML = `<span class="spinner sm"></span>${h(t("sumfile.working"))}`; }
  try {
    const summary = await makeSummary(spec);
    const r = await api("/api/summary-file", { method: "POST", body: {
      title: spec.label || spec.query, query: spec.query, summary,
      sources: (sources || []).filter(s => /^https?:/.test(s.url || "")).map(s => ({ n: s.n, title: s.title || s.site_name || s.domain || "", url: s.url })),
    } });
    done(r);
  } catch (e) {
    toast(e.message, 5000);
  } finally {
    if (button) { button.disabled = false; button.innerHTML = old; }
  }
}

function done(r) {
  let d = $("#sumFileDlg");
  if (!d) d = document.body.appendChild(Object.assign(document.createElement("dialog"), { id: "sumFileDlg", className: "dlg" }));
  const kb = Math.max(1, Math.round(r.size / 1024));
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${icon("download")} ${h(t("sumfile.doneTitle"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain"><p>${h(t("sumfile.done", { name: r.name, size: kb + " KB" }))}</p></div>
    <div class="dlg-foot"><button type="button" class="btn sm" id="sfReveal">${icon("folder")}${h(t("exp.show"))}</button>
      <button type="button" class="btn sm primary" id="sfOpen">${icon("doc")}${h(t("sumfile.open"))}</button></div></form>`;
  const open = reveal => api("/api/export/open", { method: "POST", body: { name: r.name, reveal, kind: "summary" } }).catch(e => toast(e.message));
  $("#sfOpen", d).onclick = () => { open(false); d.close(); };
  $("#sfReveal", d).onclick = () => { open(true); d.close(); };
  d.showModal();
}
