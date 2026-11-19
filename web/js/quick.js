// Quick search: the "Add to this" box under a quick answer, and the Quick search dialog in an article's
// Sources menu (a short question; by default the answer is added to the article as a new section).
import { $, h, icon } from "./util.js";
import { t } from "./i18n.js";
import { micButton } from "./speech.js";

export function quickBox() {
  return `<section class="quick-more" id="quickMore">
    <label for="quickAdd" class="quick-more-label">${h(t("quick.addTo"))}</label>
    <div class="quick-more-row">
      <input id="quickAdd" type="text" autocomplete="off" placeholder="${h(t("quick.addPh"))}">
      <button type="button" class="btn sm primary" data-act="quick-more">${icon("bolt")}<span>${h(t("quick.button"))}</span></button>
    </div>
    <p class="hint">${h(t("quick.addHint"))}</p>
    <div class="quick-full"><button type="button" class="btn sm ghost" data-act="quick-full">${icon("search")}<span>${h(t("quick.full"))}</span></button>
      <span class="hint">${h(t("quick.fullHint"))}</span></div>
  </section>`;
}

document.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.isComposing && e.target?.id === "quickAdd") {
    e.preventDefault();
    e.target.closest(".quick-more")?.querySelector('[data-act="quick-more"]')?.click();
  }
});

export function openQuickDialog(R, run) {
  let d = $("#quickDlg");
  if (!d) { d = Object.assign(document.createElement("dialog"), { id: "quickDlg", className: "dlg quick-dlg" }); document.body.appendChild(d); }
  d.innerHTML = `<form method="dialog" id="quickForm">
    <div class="dlg-head"><h2>${h(t("quick.title"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain">
      <label for="quickQ" class="field-label">${h(t("quick.ask"))}</label>
      <div class="quick-q"><input id="quickQ" type="text" autocomplete="off" required placeholder="${h(t("quick.askPh"))}"></div>
      <label class="check quick-update"><input type="checkbox" id="quickUpdate" checked>
        <span>${h(t("quick.update"))}<small>${h(t("quick.updateHint"))}</small></span></label>
    </div>
    <div class="dlg-foot"><span class="hint grow">${h(t("quick.cost"))}</span>
      <button class="btn sm ghost" value="close">${h(t("common.cancel"))}</button>
      <button type="submit" class="btn sm primary" value="go">${icon("bolt")}<span>${h(t("quick.button"))}</span></button></div></form>`;
  const f = d.querySelector("form");
  f.onsubmit = e => {
    if (e.submitter?.value === "close") return;
    e.preventDefault();
    const q = $("#quickQ").value.trim();
    if (!q) { $("#quickQ").focus(); return; }
    const update = $("#quickUpdate").checked;
    d.close();
    run(q, update);
  };
  const mic = micButton($("#quickQ"), () => {});      // speaking fills the box; Quick search starts it
  if (mic) d.querySelector(".quick-q").appendChild(mic);
  d.showModal();
  setTimeout(() => $("#quickQ").focus(), 30);
}
