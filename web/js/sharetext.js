// "Search with AIRAG" on Android: text or a link shared from another app starts a search.
// Short text (a question, a few words, a link) starts the search straight away; long text is put in
// the search box so it can be shortened first. Links in the question are read first by the search.
import { $, toast } from "./util.js";
import { t } from "./i18n.js";

const AUTO_MAX = 400;      // longer shared text waits in the box instead of starting a search
const BOX_MAX = 2000;

export function initShareText({ go }) {
  const take = () => {
    let text = "";
    try { text = window.AIRAGShare?.takeText?.((window.__airagKey || "")) || ""; } catch { return; }   // not on Android
    text = clean(text);
    if (!text) return;
    if (text.length <= AUTO_MAX) { go(text); return; }
    location.hash = "#/";
    const inp = $("#homeSearch input");
    if (inp) { inp.value = text.slice(0, BOX_MAX); inp.focus(); }
    toast(t("share.long"), 6000);
  };
  addEventListener("airag-share", take);
  setTimeout(take, 600);
}

/** One line, no control characters (shared text can be anything). */
export function clean(text) {
  return String(text || "").replace(/[\u0000-\u001f\u007f​-‏‪-‮⁦-⁩]+/g, " ")
    .replace(/\s+/g, " ").trim();
}
