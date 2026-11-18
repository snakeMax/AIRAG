// Saved articles: list them, unsave one or several (they leave My library but stay in History), and bring back
// ones unsaved by accident from "Recently removed" (kept 30 days). Opens from the home page, the Saved tab in
// History and an article's Export menu.
import { $, $$, h, icon, api, toast, fmtAgo } from "./util.js";
import { t, uiLang } from "./i18n.js";

const changed = () => window.dispatchEvent(new CustomEvent("airag:saved"));

/** Unsave with an Undo in the message. what: { files } or { id, path }. */
export async function unsaveArticles(what, after) {
  const r = await api("/api/mylibrary/unsave", { method: "POST", body: what });
  const gone = r.removed || [];
  changed();
  after?.(gone);
  toast(t(gone.length > 1 ? "saved.unsavedMany" : "saved.unsaved", { n: gone.length }), 6000, {
    label: t("saved.undo"),
    run: async () => {
      for (const g of gone) await api("/api/mylibrary/restore", { method: "POST", body: { rid: g.rid } }).catch(() => {});
      changed();
      after?.([], true);
      toast(t("saved.restored"));
    },
  });
  return gone;
}

function dlg() {
  let d = $("#savedDlg");
  if (!d) { d = Object.assign(document.createElement("dialog"), { id: "savedDlg", className: "dlg saved-dlg" }); document.body.appendChild(d); }
  return d;
}

export async function openSavedManager() {
  const d = dlg();
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${h(t("saved.manageTitle"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain saved-body"><div class="status-line"><span class="spinner sm"></span></div></div>
    <div class="dlg-foot"><label class="check saved-all"><input type="checkbox" id="savedAll"> ${h(t("saved.selectAll"))}</label>
      <button class="btn sm ghost" value="close">${h(t("common.close"))}</button>
      <button type="button" class="btn sm danger" id="savedUnsave" disabled>${icon("trash")}<span>${h(t("saved.unsaveSel"))}</span></button></div></form>`;
  if (!d.open) d.showModal();
  await draw(d);
}

async function draw(d) {
  const body = $(".saved-body", d);
  let saved = [], removed = [], days = 30;
  try {
    [{ items: saved }, { items: removed, days }] = await Promise.all([api("/api/mylibrary/saved"), api("/api/mylibrary/removed")]);
  } catch (e) { body.innerHTML = `<p class="status-line err">${h(e.message)}</p>`; return; }
  body.innerHTML = `<p class="help saved-intro">${h(t("saved.manageIntro"))}</p>
    ${saved.length ? `<ul class="saved-list">${saved.map(it => `<li>
        <label class="check"><input type="checkbox" data-file="${h(it.file)}" aria-label="${h(t("saved.select", { title: it.title || it.query }))}"></label>
        <a class="saved-t" href="#/saved/${encodeURIComponent(it.file)}">${h(it.title || it.query)}
          <small>${h(fmtAgo(it.created, uiLang()))}${(it.tags || []).length ? " · " + h(it.tags.join(", ")) : ""}</small></a>
        <button type="button" class="icon-btn" data-one="${h(it.file)}" aria-label="${h(t("saved.unsaveOne", { title: it.title || it.query }))}" title="${h(t("save.unsave"))}">${icon("trash")}</button></li>`).join("")}</ul>`
      : `<p class="h-empty">${h(t("saved.empty"))}</p>`}
    <details class="saved-removed" ${removed.length ? "" : "hidden"}><summary>${h(t("saved.removedTitle", { n: removed.length }))}</summary>
      <p class="help">${h(t("saved.removedHelp", { days }))}</p>
      <ul class="saved-list">${removed.map(it => `<li>
        <span class="saved-t">${h(it.title)}<small>${h(t("saved.removedAgo", { when: fmtAgo(it.removed, uiLang()) }))}</small></span>
        <button type="button" class="btn sm" data-restore="${h(it.rid)}">${icon("undo")}${h(t("saved.restore"))}</button>
        <button type="button" class="icon-btn" data-forget="${h(it.rid)}" aria-label="${h(t("saved.forget", { title: it.title }))}" title="${h(t("saved.forgetShort"))}">${icon("x")}</button></li>`).join("")}</ul>
    </details>`;
  const boxes = $$("[data-file]", body), go = $("#savedUnsave", d), all = $("#savedAll", d);
  const sync = () => {
    const n = boxes.filter(b => b.checked).length;
    go.disabled = !n;
    $("span", go).textContent = n ? t("saved.unsaveN", { n }) : t("saved.unsaveSel");
    all.checked = n && n === boxes.length;
    all.indeterminate = n > 0 && n < boxes.length;
  };
  all.disabled = !boxes.length;
  all.onchange = () => { boxes.forEach(b => (b.checked = all.checked)); sync(); };
  boxes.forEach(b => (b.onchange = sync));
  sync();
  const redraw = () => draw(d);
  go.onclick = async () => {
    const files = boxes.filter(b => b.checked).map(b => b.dataset.file);
    try { await unsaveArticles({ files }, redraw); } catch (e) { toast(e.message, 5000); }
  };
  $$("[data-one]", body).forEach(b => (b.onclick = async () => {
    try { await unsaveArticles({ files: [b.dataset.one] }, redraw); } catch (e) { toast(e.message, 5000); }
  }));
  $$("[data-restore]", body).forEach(b => (b.onclick = async () => {
    try { await api("/api/mylibrary/restore", { method: "POST", body: { rid: b.dataset.restore } }); toast(t("saved.restored")); changed(); redraw(); }
    catch (e) { toast(e.message, 5000); }
  }));
  $$("[data-forget]", body).forEach(b => (b.onclick = async () => {
    if (!confirm(t("saved.forgetConfirm"))) return;
    await api(`/api/mylibrary/removed/${encodeURIComponent(b.dataset.forget)}`, { method: "DELETE" }).catch(() => {});
    redraw();
  }));
  $$(".saved-t[href]", body).forEach(a => a.addEventListener("click", () => d.close()));
}
