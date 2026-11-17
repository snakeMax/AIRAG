// Disclaimer banner, update popup and the update progress bar.
import { $, h, icon, api, pollJob, toast } from "./util.js";
import { t } from "./i18n.js";
import { render } from "./markdown.js";

export function showDisclaimer(settings) {
  const el = $("#disclaimer");
  if (settings.app.disclaimer_dismissed) { el.hidden = true; return; }
  el.innerHTML = `${icon("info")}<span class="grow">${h(t("banner.disclaimer"))}</span>
    <button class="icon-btn" title="${h(t("banner.close"))}">${icon("x")}</button>`;
  el.hidden = false;
  el.querySelector("button").onclick = () => {
    el.hidden = true;
    api("/api/settings", { method: "POST", body: { app: { disclaimer_dismissed: true } } }).catch(() => {});
  };
}

let info = null;
/** On launch: a popup when a newer version is out (unless the user skipped that version). */
export async function checkUpdates(settings) {
  if (!settings.app.check_updates) return;
  info = await api("/api/update/check").catch(() => null);
  if (!info?.newer || localStorage.getItem("airag.skipVersion") === info.latest) return;
  showUpdatePopup(info);
}

/** Also used by Settings -> Check now. */
export function showUpdatePopup(u) {
  info = u;
  const dlg = $("#updateDlg");
  if ($("#settingsDlg")?.open) $("#settingsDlg").close();
  const canInstall = u.can_self_update && u.asset;
  dlg.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${icon("download")} ${h(t("upd.title", { v: u.latest }))}</h2><button class="icon-btn" value="later">${icon("x")}</button></div>
    <div class="dlg-body plain">
      <p>${h(t("upd.youHave", { v: u.current }))}</p>
      ${u.notes ? `<div class="upd-notes prose">${render(u.notes.split("\n---")[0])}</div>` : ""}
      ${u.asset?.size ? `<p class="muted" style="font-size:12.5px">${h(t("upd.size", { mb: (u.asset.size / 1048576).toFixed(0) }))}</p>` : ""}
    </div>
    <div class="dlg-foot">
      <button class="btn ghost" value="skip" title="${h(t("upd.skipTip"))}">${h(t("upd.skip"))}</button>
      <button class="btn ghost" value="later">${h(t("banner.later"))}</button>
      ${canInstall ? `<button class="btn primary" value="install">${icon("download")}${h(t("banner.updateNow"))}</button>`
        : `<a class="btn primary" href="${h(u.url || "#")}" target="_blank" rel="noopener">${h(t("banner.download"))}</a>`}
    </div></form>`;
  dlg.onclose = () => {
    if (dlg.returnValue === "skip") localStorage.setItem("airag.skipVersion", u.latest);
    if (dlg.returnValue === "install") installUpdate();
  };
  dlg.returnValue = "";
  dlg.showModal();
}

export async function installUpdate() {
  const el = $("#updateBanner");
  el.hidden = false;
  el.innerHTML = `<span class="spinner sm"></span><span class="grow" id="updMsg">${h(t("banner.updating", { p: 0 }))}</span><div class="bar" id="updBar"><i style="width:0"></i></div>`;
  try {
    const job = await api("/api/update/install", { method: "POST" });
    const fin = await pollJob(job, j => {
      $("#updMsg").textContent = j.progress != null && j.progress < 1 ? t("banner.updating", { p: Math.round(j.progress * 100) }) : t("banner.restarting");
      $("#updBar i").style.width = `${Math.round((j.progress || 0) * 100)}%`;
    });
    if (fin.status === "error") throw new Error(fin.error);
    if (fin.result?.needs_permission) { toast(t("upd.permission"), 8000); el.hidden = true; }
    else if (fin.result && !fin.result.restarting) el.hidden = true;   // Android: the system installer takes over
  } catch (e) {
    toast(e.message, 6000);
    el.hidden = true;
  }
}
window.addEventListener("airag:update", installUpdate);
