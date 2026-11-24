// Where the Notes folder is: a card in Settings -> Library & storage, and a line in the first-start setup.
// Default: Documents/AIRAG Notes on the system drive (C: on Windows); Change… picks another folder,
// Default goes back. Vaults already made stay where they are.
import { $, h, icon, api, toast } from "./util.js";
import { t } from "./i18n.js";

export function notesFolderCard() {
  return `<h4>${h(t("nf.title"))}</h4><p class="muted" style="font-size:13px">${h(t("nf.intro"))}</p>
    <div class="status-card" id="notesFolderCard"><div class="grow">${h(t("common.loading"))}</div></div>`;
}

export async function refreshNotesFolder(scope = document) {
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
