// "?" in the top bar: a short guide to what isn't obvious. In Notes it explains Notes; everywhere else,
// Research. Each item is one heading and one or two sentences (strings help.r.* and help.n.*).
import { $, h, icon } from "./util.js";
import { t } from "./i18n.js";

const RESEARCH = ["modes", "quick", "chips", "select", "toolbar", "sources", "panels", "save", "image", "share"];
const NOTES = ["vaults", "links", "props", "tags", "search", "backlinks", "saving", "voice"];

export function initHelp() {
  const b = $("#helpBtn");
  if (b) b.onclick = openHelp;
}

export function openHelp() {
  const notes = document.body.classList.contains("notes-mode");
  const items = notes ? NOTES : RESEARCH, p = notes ? "help.n." : "help.r.";
  let d = $("#helpDlg");
  if (!d) { d = Object.assign(document.createElement("dialog"), { id: "helpDlg", className: "dlg help-dlg" }); document.body.appendChild(d); }
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${h(t(notes ? "help.notesTitle" : "help.researchTitle"))}</h2>
      <button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain"><dl class="help-list">${items.map(k =>
      `<dt>${h(t(p + k))}</dt><dd>${h(t(p + k + ".t"))}</dd>`).join("")}</dl>
      <p class="muted help-more">${h(t("help.more"))}</p></div></form>`;
  d.showModal();
}
