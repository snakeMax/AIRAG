// Where the Notes folder is: a card in Settings -> Library & storage, and a line in the first-start setup.
// Default: Documents/AIRAG Notes on the system drive (C: on Windows); Change… picks another folder,
// Default goes back. Vaults already made stay where they are.
// Also the Notes vaults list: which vault is the main one (an AIRAG vault or an Obsidian vault), adding an
// Obsidian vault, read only on/off for added vaults, Open in Obsidian, and removing a vault from the list.
import { $, $$, h, icon, api, toast } from "./util.js";
import { t } from "./i18n.js";

export function notesFolderCard() {
  return `<h4>${h(t("nf.title"))}</h4><p class="muted" style="font-size:13px">${h(t("nf.intro"))}</p>
    <div class="status-card" id="notesFolderCard"><div class="grow">${h(t("common.loading"))}</div></div>
    <h4 style="margin-top:18px">${h(t("nv.title"))}</h4><p class="muted" style="font-size:13px">${h(t("nv.intro"))}</p>
    <div class="nv-list" id="notesVaultsCard"><div class="muted">${h(t("common.loading"))}</div></div>`;
}

// the vault list (Settings) or the main-vault line (first-start setup: compact)
export async function refreshNotesVaults(scope = document) {
  const box = $("#notesVaultsCard", scope) || $("#suNotesVault", scope);
  if (!box) return;
  const compact = box.id === "suNotesVault";
  const r = await api("/api/notes/vaults").catch(() => null);
  if (!r) return;
  const vs = r.vaults;
  const again = () => refreshNotesVaults(scope);
  const call = (url, body, method = "POST") => api(url, { method, body }).then(again).catch(e => toast(e.message, 6000));
  const addObsidian = async () => {
    const p = await api("/api/library/pick-folder", { method: "POST" }).catch(e => { toast(e.message, 6000); return {}; });
    if (p.path) call("/api/notes/vaults/link", { folder: p.path, main: true });
  };
  if (compact) {
    const main = vs.find(v => v.main);
    box.innerHTML = `${icon("book")}<div class="grow"><div class="lr-t">${h(main ? main.name + (main.linked ? " · Obsidian" : "") : t("nv.mainDefault"))}</div>
        <div class="muted mono" style="font-size:12px;word-break:break-all">${h(main ? main.dir : r.root)}</div></div>
      <button type="button" class="btn sm" data-nv="add">${icon("folder")}${h(t("nv.addObsidian"))}</button>`;
    box.querySelector('[data-nv="add"]').onclick = addObsidian;
    return;
  }
  box.innerHTML = (vs.length ? vs.map(v => `<div class="status-card nv-row" data-id="${h(v.id)}">
      <label class="nv-main" title="${h(t("nv.mainTip"))}"><input type="radio" name="nvMain" ${v.main ? "checked" : ""} ${v.exists ? "" : "disabled"} aria-label="${h(t("nv.main"))}"></label>
      <div class="grow"><div class="lr-t">${h(v.name)} ${v.main ? `<span class="badge">${h(t("nv.main"))}</span>` : ""} ${v.linked ? `<span class="badge">Obsidian</span>` : ""}${v.exists ? "" : ` <span class="badge warn">${h(t("nv.missing"))}</span>`}</div>
        <div class="muted mono" style="font-size:12px;word-break:break-all">${h(v.dir)}</div>
        ${v.linked ? `<label class="nv-ro"><input type="checkbox" data-nv="ro" ${v.read_only ? "checked" : ""}> ${h(t("nv.readOnly"))}</label>` : ""}</div>
      <button type="button" class="btn sm ghost" data-nv="obsidian" ${v.exists ? "" : "disabled"} title="${h(t("nt.openObsidian"))}">${icon("ext")}<span>Obsidian</span></button>
      <button type="button" class="icon-btn sm" data-nv="forget" title="${h(t("nv.forget"))}" aria-label="${h(t("nv.forget"))}">${icon("x")}</button></div>`).join("")
    : `<p class="muted">${h(t("nv.none"))}</p>`) +
    `<div class="row" style="margin-top:8px"><button type="button" class="btn sm" data-nv="add">${icon("folder")}${h(t("nv.addObsidian"))}</button>
      <a class="btn sm ghost" href="#/notes">${icon("plus")}${h(t("nv.newInNotes"))}</a></div>`;
  box.querySelector('[data-nv="add"]').onclick = addObsidian;
  $$(".nv-row", box).forEach(row => {
    const id = row.dataset.id, v = vs.find(x => x.id === id);
    row.querySelector("input[name=nvMain]").onchange = () => call("/api/notes/main", { vid: id });
    row.querySelector('[data-nv="ro"]')?.addEventListener("change", e => call(`/api/notes/vaults/${id}/access`, { write: !e.target.checked }));
    row.querySelector('[data-nv="obsidian"]').onclick = () => import("./notes.js").then(m => m.openInObsidian(v));
    row.querySelector('[data-nv="forget"]').onclick = () => { if (confirm(t("nv.forgetConfirm", { n: v.name }))) call(`/api/notes/vaults/${id}`, undefined, "DELETE"); };
  });
}

export async function refreshNotesFolder(scope = document) {
  refreshNotesVaults(scope);
  const card = $("#notesFolderCard", scope) || $("#suNotesFolder", scope);
  if (!card) return;
  const m = await api("/api/notes/folder").catch(() => null);
  if (!m) return;
  card.innerHTML = `${icon("folder")}<div class="grow"><div class="lr-t mono" style="word-break:break-all">${h(m.path)}</div>
      <div class="muted" style="font-size:12.5px">${h(m.exists ? t("nf.vaults", { n: m.vaults }) : t("nf.notYet"))}</div></div>
    <button type="button" class="btn sm" data-nf="pick">${icon("folder")}${h(t("nf.change"))}</button>
    ${m.custom ? `<button type="button" class="btn sm ghost" data-nf="default" title="${h(m.default)}">${h(t("nf.default"))}</button>` : ""}`;
  const set = async path => {
    const r = await api("/api/notes/folder", { method: "POST", body: { path } }).catch(e => { toast(e.message, 5000); return null; });
    if (r) refreshNotesFolder(scope);
  };
  card.querySelector('[data-nf="pick"]').onclick = () => set(null);
  card.querySelector('[data-nf="default"]')?.addEventListener("click", () => set(""));
}
