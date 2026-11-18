// "Analyze image": the selected AI model looks at a picture or screenshot and answers a question about it.
// Ways in: the button on Home (only shown when the model can see images), pasting or dropping a picture on
// Home, and on Android sharing a picture or screenshot to AIRAG.
import { $, h, icon, apiStream, toast, stripThink } from "./util.js";
import { render } from "./markdown.js";
import { t, uiLang } from "./i18n.js";
import { micButton } from "./speech.js";

let canSee = () => false;
const MAX_SIDE = 1600;

export function initImageAsk({ vision }) {
  canSee = vision;
  // Android: a picture shared to AIRAG waits in the app until the page asks for it
  const takeShared = () => {
    try {
      const img = window.AIRAGShare?.take?.();
      if (img) openImageAsk(img);
    } catch { /* not on Android */ }
  };
  addEventListener("airag-share", takeShared);
  setTimeout(takeShared, 600);
  // computer: paste or drop a picture on Home
  document.addEventListener("paste", e => {
    if ($("#view-home")?.hidden || e.target.closest?.("input, textarea")) return;
    const file = [...(e.clipboardData?.files || [])].find(f => f.type.startsWith("image/"));
    if (file) { e.preventDefault(); fromFile(file); }
  });
  const home = $("#view-home");
  home?.addEventListener("dragover", e => { if ([...e.dataTransfer.items].some(i => i.type.startsWith("image/"))) { e.preventDefault(); home.classList.add("drop-on"); } });
  home?.addEventListener("dragleave", () => home.classList.remove("drop-on"));
  home?.addEventListener("drop", e => {
    home.classList.remove("drop-on");
    const file = [...e.dataTransfer.files].find(f => f.type.startsWith("image/"));
    if (file) { e.preventDefault(); fromFile(file); }
  });
}

/** Shows or hides the Home button, depending on whether the selected model can see images. */
export function updateImageButton() {
  const b = $("#imgAskBtn");
  if (b) b.hidden = !canSee();
}

export function pickImage() {
  const inp = Object.assign(document.createElement("input"), { type: "file", accept: "image/*" });
  inp.onchange = () => inp.files[0] && fromFile(inp.files[0]);
  inp.click();
}

/** Shrinks big photos so they upload quickly and stay under the model's size limits. */
async function fromFile(file) {
  try {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.src = url;
    await img.decode();
    const f = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    const c = Object.assign(document.createElement("canvas"), { width: Math.round(img.naturalWidth * f), height: Math.round(img.naturalHeight * f) });
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    URL.revokeObjectURL(url);
    openImageAsk(c.toDataURL("image/jpeg", 0.88));
  } catch {
    toast(t("img.badFile"), 4000);
  }
}

export function openImageAsk(dataUrl) {
  let d = $("#imgDlg");
  if (!d) d = document.body.appendChild(Object.assign(document.createElement("dialog"), { id: "imgDlg", className: "dlg tbx" }));
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${icon("eye")} ${h(t("rt.analyzeImage"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain img-ask">
      <div class="img-ask-pic"><img alt="" src="${h(dataUrl)}"></div>
      <div class="img-ask-side">
        ${canSee() ? "" : `<div class="status-line warn">${h(t("img.noVision"))}</div>`}
        <div class="row"><input type="text" class="input" id="imgQ" style="flex:1" placeholder="${h(t("img.ph"))}"><span class="img-mic"></span></div>
        <div class="img-ask-out prose" id="imgOut"><p class="muted">${h(t("img.hint"))}</p></div>
      </div>
    </div>
    <div class="dlg-foot"><button type="button" class="btn sm ghost" id="imgOther">${icon("folder")}${h(t("img.other"))}</button>
      <button type="button" class="btn sm" id="imgCopy" disabled>${icon("copy")}${h(t("rw.copy"))}</button>
      <button type="button" class="btn sm primary" id="imgGo">${icon("sparkle")}${h(t("img.go"))}</button></div></form>`;
  if (!d.open) d.showModal();
  const q = $("#imgQ", d), out = $("#imgOut", d);
  const mic = micButton(q, said => { q.value = said; go(); });
  if (mic) $(".img-mic", d).replaceWith(mic); else $(".img-mic", d).remove();
  let md = "";
  const go = async () => {
    $("#imgGo", d).disabled = true;
    out.innerHTML = `<span class="spinner sm"></span>`;
    md = "";
    try {
      await apiStream("/api/analyze-image", { image: dataUrl, question: q.value, ui_lang: uiLang() }, ev => {
        if (ev.type === "token") { md += ev.text; out.innerHTML = render(stripThink(md)); }
        else if (ev.type === "error") throw new Error(ev.message);
      });
      $("#imgCopy", d).disabled = !md;
    } catch (e) {
      out.innerHTML = `<p class="status-line err">${h(e.message)}</p><p class="help">${h(t("img.apps"))}</p>`;
    }
    $("#imgGo", d).disabled = false;
  };
  $("#imgGo", d).onclick = go;
  q.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); go(); } };
  $("#imgCopy", d).onclick = () => navigator.clipboard?.writeText(stripThink(md)).then(() => toast(t("art.copied")));
  $("#imgOther", d).onclick = pickImage;
  setTimeout(() => q.focus(), 40);
}
