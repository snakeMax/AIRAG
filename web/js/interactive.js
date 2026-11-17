// Interactive explainer viewer. The generated page runs in a sandboxed iframe:
// scripts allowed, but no same-origin access, no network (CSP), no popups.
import { $, h, icon, api } from "./util.js";
import { t, uiLang } from "./i18n.js";

export async function openInteractive(run, force = false) {
  const dlg = $("#interDlg");
  dlg.innerHTML = `
    <form method="dialog">
      <div class="dlg-head"><h2>${icon("play")} ${h(t("inter.title"))}</h2><button class="icon-btn" value="close">${icon("x")}</button></div>
      <div class="inter-body" id="interBody"><div class="inter-wait"><span class="spinner"></span><div>${h(t("inter.building"))}</div>
        <div class="muted">${h(run.interactive?.idea || "")}</div></div></div>
      <div class="dlg-foot"><span class="muted">${h(t("inter.note"))}</span>
        <button type="button" class="btn sm" id="interRedo">${icon("refresh")}${h(t("inter.again"))}</button>
        <button class="btn sm primary" value="close">${h(t("common.close"))}</button></div>
    </form>`;
  dlg.showModal();
  $("#interRedo").onclick = () => openInteractive(run, true);
  if (run.savedFile) $("#interRedo").hidden = true;   // opened from My library: use the saved copy
  try {
    const res = run.savedFile && run.interactiveHtml && !force
      ? { html: run.interactiveHtml }
      : await api("/api/interactive", { method: "POST", body: { id: run.id, force, ui_lang: uiLang() } });
    run.interactiveHtml = res.html;
    const frame = document.createElement("iframe");
    frame.setAttribute("sandbox", "allow-scripts");
    frame.setAttribute("referrerpolicy", "no-referrer");
    frame.className = "inter-frame";
    frame.srcdoc = res.html;
    // some browsers leave a freshly loaded sandboxed frame blank until it repaints
    frame.addEventListener("load", () => { frame.style.display = "none"; void frame.offsetHeight; frame.style.display = ""; }, { once: true });
    $("#interBody").replaceChildren(frame);
  } catch (e) {
    $("#interBody").innerHTML = `<div class="inter-wait"><div class="status-line err">${h(e.message)}</div></div>`;
  }
}
