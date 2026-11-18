// Interactive explainer viewer. The generated page runs in a sandboxed iframe:
// scripts allowed, but no same-origin access, no network (CSP), no popups.
// Building one is a background job: closing this dialog doesn't stop it, and opening it
// again while it's being built reconnects to the same job.
import { $, h, icon, api, apiStream } from "./util.js";
import { t, uiLang } from "./i18n.js";
import { pokeJobs } from "./activity.js";

let follow = null;   // AbortController of the job stream this dialog is following

function show(html) {
  const frame = document.createElement("iframe");
  frame.setAttribute("sandbox", "allow-scripts");
  frame.setAttribute("referrerpolicy", "no-referrer");
  frame.className = "inter-frame";
  frame.srcdoc = html;
  // some browsers leave a freshly loaded sandboxed frame blank until it repaints
  frame.addEventListener("load", () => { frame.style.display = "none"; void frame.offsetHeight; frame.style.display = ""; }, { once: true });
  $("#interBody")?.replaceChildren(frame);
}

function fail(run, msg) {
  if (run.interactive == null && /wouldn't help/.test(msg)) run.interactive = { suitable: false };
  const body = $("#interBody");
  if (body) body.innerHTML = `<div class="inter-wait"><div class="status-line err">${h(msg)}</div></div>`;
}

export async function openInteractive(run, force = false) {
  const dlg = $("#interDlg");
  follow?.abort();
  dlg.innerHTML = `
    <form method="dialog">
      <div class="dlg-head"><h2>${icon("play")} ${h(t("inter.title"))}</h2><button class="icon-btn" value="close">${icon("x")}</button></div>
      <div class="inter-body" id="interBody"><div class="inter-wait"><span class="spinner"></span><div>${h(t("inter.building"))}</div>
        <div class="muted">${h(run.interactive?.idea || "")}</div><div class="muted sm">${h(t("inter.background"))}</div></div></div>
      <div class="dlg-foot"><span class="muted">${h(t("inter.note"))}</span>
        <button type="button" class="btn sm ghost" id="interCancel" hidden>${icon("x")}${h(t("inter.cancel"))}</button>
        <button type="button" class="btn sm" id="interRedo">${icon("refresh")}${h(t("inter.again"))}</button>
        <button class="btn sm primary" value="close">${h(t("common.close"))}</button></div>
    </form>`;
  if (!dlg.open) dlg.showModal();
  dlg.addEventListener("close", () => follow?.abort(), { once: true });   // stop watching; the job keeps going
  $("#interRedo").onclick = () => openInteractive(run, true);
  if (run.savedFile) {   // opened from My library: use the saved copy
    $("#interRedo").hidden = true;
    if (run.interactiveHtml && !force) return show(run.interactiveHtml);
  }
  let res;
  try {
    res = await api("/api/interactive/start", { method: "POST", body: { id: run.id, force, ui_lang: uiLang() } });
  } catch (e) { return fail(run, e.message); }
  if (res.html) {
    run.interactiveHtml = res.html;
    if (res.interactive) run.interactive = res.interactive;
    return show(res.html);
  }
  pokeJobs();
  const job = res.job, ctrl = new AbortController();
  follow = ctrl;
  const cancel = $("#interCancel");
  cancel.hidden = false;
  $("#interRedo").hidden = true;
  cancel.onclick = async () => {
    cancel.disabled = true;
    await api(`/api/research/${encodeURIComponent(job)}/cancel`, { method: "POST" }).catch(() => {});
    pokeJobs();
  };
  let ended = false;
  try {
    await apiStream(`/api/research/${encodeURIComponent(job)}/stream`, null, ev => {
      if (ev.type === "queued") $(".inter-wait .muted.sm") && ($(".inter-wait .muted.sm").textContent = t("inter.queuedTip"));
      if (ev.type === "done" && ev.html) {
        ended = true;
        run.interactiveHtml = ev.html;
        if (ev.interactive) run.interactive = ev.interactive;
        show(ev.html);
      } else if (ev.type === "error") { ended = true; fail(run, ev.message); }
      else if (ev.type === "cancelled") { ended = true; fail(run, t("inter.cancelled")); }
    }, ctrl.signal, "GET");
  } catch (e) {
    if (e.name === "AbortError") return;
    if (!ended) fail(run, e.message);
  }
  if (follow === ctrl) {
    cancel.hidden = true;
    $("#interRedo").hidden = !!run.savedFile;
    pokeJobs();
  }
}
