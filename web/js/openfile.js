// Open with AIRAG: Markdown and text files, saved articles (.airag.json) and exported web pages open as an
// article, without the AI. Ways in:
//  - Windows: "Open with" -> AIRAG (the app hands the file to this page)
//  - Android: open a file in a file manager with AIRAG, or share the file to it
//  - the "Open a file" button in the Saved tab
import { api, toast } from "./util.js";
import { t } from "./i18n.js";

const ACCEPT = ".md,.markdown,.txt,.html,.htm,.json";
let show = () => {};

export function initOpenFile() {
  show = id => { location.hash = "#/view/" + encodeURIComponent(id); };
  // Windows: files handed over by the app (also when AIRAG was already running)
  const inbox = async () => {
    const r = await api("/api/app/inbox").catch(() => ({}));
    if (r.id) { show(r.id); toast(t("open.opened"), 3000); }
    else if (r.error) toast(r.error, 6000);
  };
  inbox();
  addEventListener("focus", inbox);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) inbox(); });
  setInterval(() => { if (!document.hidden) inbox(); }, 4000);
  // Android: a file opened with (or shared to) AIRAG waits in the app until the page asks for it
  const takeFile = async () => {
    let raw = "";
    try { raw = window.AIRAGShare?.takeFile?.() || ""; } catch { return; }
    if (!raw) return;
    let f;
    try { f = JSON.parse(raw); } catch { return; }
    if (f.error) { toast(t(f.error === "big" ? "open.tooBig" : "open.unreadable"), 6000); return; }
    send(f.name, f.text);
  };
  addEventListener("airag-share", takeFile);
  setTimeout(takeFile, 700);
}

async function send(name, text) {
  try {
    const { id } = await api("/api/open-file", { method: "POST", body: { name, text } });
    show(id);
    toast(t("open.opened"), 3000);
  } catch (e) {
    toast(e.message, 6000);
  }
}

/** The "Open a file" button: pick a file and open it here. */
export function pickFile() {
  const inp = Object.assign(document.createElement("input"), { type: "file", accept: ACCEPT });
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) { toast(t("open.tooBig"), 6000); return; }
    send(f.name, await f.text());
  };
  inp.click();
}
