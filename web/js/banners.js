// Disclaimer and update banners at the top of the window.
import { $, h, icon, api, pollJob, toast } from "./util.js";
import { t } from "./i18n.js";

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
export async function checkUpdates(settings) {
  if (!settings.app.check_updates) return;
  info = await api("/api/update/check").catch(() => null);
  if (!info?.newer || localStorage.getItem("airag.skipVersion") === info.latest) return;
  const el = $("#updateBanner");
  el.innerHTML = `${icon("download")}<span class="grow">${h(t("banner.update", { v: info.latest }))}</span>
    ${info.url ? `<a class="btn sm ghost" href="${h(info.url)}" target="_blank" rel="noopener">${h(t("banner.whatsNew"))}</a>` : ""}
    ${info.can_self_update && info.asset ? `<button class="btn sm primary" id="updNow">${h(t("banner.updateNow"))}</button>`
      : `<a class="btn sm primary" href="${h(info.url || "#")}" target="_blank" rel="noopener">${h(t("banner.download"))}</a>`}
    <button class="icon-btn" id="updLater" title="${h(t("banner.later"))}">${icon("x")}</button>`;
  el.hidden = false;
  $("#updLater").onclick = () => { el.hidden = true; localStorage.setItem("airag.skipVersion", info.latest); };
  $("#updNow")?.addEventListener("click", installUpdate);
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
  } catch (e) {
    toast(e.message, 6000);
    el.hidden = true;
  }
}
window.addEventListener("airag:update", installUpdate);
