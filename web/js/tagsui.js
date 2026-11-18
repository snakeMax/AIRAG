// Tags and translations of an article:
//  - the Save dialog (tags, Suggest tags, translations to keep, pictures + explainer)
//  - the row under the byline: language switcher (when the article has translations) and its tags
//  - Edit tags (for saved and unsaved articles; a saved copy's Markdown properties are updated too)
import { $, $$, h, icon, api, toast } from "./util.js";
import { t, uiLang } from "./i18n.js";

const langName = code => {
  try { return new Intl.DisplayNames([uiLang()], { type: "language" }).of(code) || code; } catch { return code; }
};
const cleanTag = s => String(s || "").trim().replace(/^#+/, "").replace(/[^\p{L}\p{N}\-_ /]+/gu, "").replace(/\s+/g, " ").toLowerCase().slice(0, 40).trim();

/** A chip editor: type and press Enter or comma; × removes. The input stays put (only the chips redraw), so
 * focus and the keyboard on phones aren't lost. Returns { get(), add(tag) }. */
function tagEditor(box, start, onChange = () => {}) {
  let tags = [...new Set((start || []).map(cleanTag).filter(x => x && x !== "airag"))];
  box.innerHTML = `<span class="tag-list"></span><input class="tag-in" aria-label="${h(t("tags.add"))}" maxlength="80">`;
  const list = $(".tag-list", box), inp = $(".tag-in", box);
  const draw = () => {
    list.innerHTML = tags.map(x => `<span class="tag-chip">${h(x)}<button type="button" data-rm="${h(x)}" aria-label="${h(t("tags.remove", { tag: x }))}">${icon("x")}</button></span>`).join("");
    inp.placeholder = tags.length ? "" : t("tags.add");
    $$("[data-rm]", list).forEach(b => (b.onclick = () => { tags = tags.filter(x => x !== b.dataset.rm); draw(); onChange(tags); }));
  };
  const add = v => {
    String(v || "").split(",").forEach(part => {
      const c = cleanTag(part);
      if (c && c !== "airag" && !tags.includes(c) && tags.length < 12) tags.push(c);
    });
    draw();
    onChange(tags);
  };
  inp.onkeydown = e => {
    if ((e.key === "Enter" || e.key === ",") && inp.value.trim()) { e.preventDefault(); add(inp.value); inp.value = ""; }
    else if (e.key === "Backspace" && !inp.value && tags.length) { tags.pop(); draw(); onChange(tags); }
  };
  inp.oninput = () => {
    if (!inp.value.includes(",")) return;
    const parts = inp.value.split(","), rest = parts.pop();
    add(parts.join(","));
    inp.value = rest;
  };
  inp.onblur = () => { if (inp.value.trim()) { add(inp.value); inp.value = ""; } };
  box.onclick = e => { if (e.target === box || e.target === list) inp.focus(); };
  draw();
  return { get: () => { if (inp.value.trim()) { add(inp.value); inp.value = ""; } return tags; }, add };
}

/** "Suggest tags": the AI proposes a few (background job); shown as dashed chips to tap. */
function suggester(row, R, editor) {
  const btn = $("[data-suggest]", row);
  btn.onclick = async () => {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner sm"></span>${h(t("tags.suggesting"))}`;
    try {
      const r = await api(`/api/tags/${encodeURIComponent(R.id)}/suggest`, { method: "POST" });
      const have = new Set(editor.get());
      const fresh = (r.tags || []).filter(x => !have.has(x));
      $$(".tag-sug", row).forEach(x => x.remove());
      if (!fresh.length) toast(t("tags.noneNew"));
      fresh.forEach(x => {
        const b = Object.assign(document.createElement("button"), { type: "button", className: "tag-sug", textContent: "+ " + x });
        b.onclick = () => { editor.add(x); b.remove(); };
        row.appendChild(b);
      });
    } catch (e) { toast(e.message, 5000); }
    btn.disabled = false;
    btn.innerHTML = `${icon("sparkle")}${h(t("tags.suggest"))}`;
  };
}

function dlg(id) {
  let d = $("#" + id);
  if (!d) { d = Object.assign(document.createElement("dialog"), { id, className: "dlg narrow tags-dlg" }); document.body.appendChild(d); }
  return d;
}

const tagBlock = id => `<div class="tags-head"><label for="${id}In">${h(t("tags.title"))}</label><span class="muted">${h(t("tags.why"))}</span></div>
  <div class="tag-box" id="${id}"></div>
  <div class="tag-sugs"><button type="button" class="chip" data-suggest>${icon("sparkle")}${h(t("tags.suggest"))}</button></div>
  <p class="help">${h(t("tags.cost"))}</p>`;

/** The Save dialog. save(rich, tags, translations) does the saving. */
export function openSaveDialog(R, defaults, save) {
  const d = dlg("saveDlg");
  const langs = Object.keys(R.translations || {});
  const hasInter = !!(R.interactiveHtml || R.interactive?.html);
  d.innerHTML = `<form method="dialog" class="save-form">
    <div class="dlg-head"><h2>${h(t("save.title"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain save-body">
      ${tagBlock("saveTags")}
      ${langs.length ? `<fieldset class="save-langs"><legend>${h(t("save.keepTr"))}</legend>
        ${langs.map(c => `<label class="check"><input type="checkbox" data-lang="${h(c)}" checked> ${h(langName(c))}</label>`).join("")}</fieldset>` : ""}
      <label class="check save-rich"><input type="checkbox" id="saveRich" ${defaults.rich ? "checked" : ""}>
        <span>${h(t("save.rich"))}<small>${h(t(hasInter ? "save.richHelp" : "save.richHelpNoInter"))}</small></span></label>
    </div>
    <div class="dlg-foot"><span class="muted save-where">${h(R.savedPath ? t("save.updates") : t("save.where"))}</span>
      <button class="btn sm ghost" value="close">${h(t("common.cancel"))}</button>
      <button type="button" class="btn sm primary" id="saveGo">${icon("download")}${h(t("save.button"))}</button></div></form>`;
  const editor = tagEditor($("#saveTags", d), R.tags);
  $("#saveTags .tag-in", d).id = "saveTagsIn";
  suggester($(".tag-sugs", d), R, editor);
  $("#saveGo", d).onclick = () => {
    const tags = editor.get();
    const keep = langs.length ? $$("[data-lang]", d).filter(x => x.checked).map(x => x.dataset.lang) : null;
    d.close();
    save($("#saveRich", d).checked, tags, keep);
  };
  d.showModal();
}

/** Edit tags of any article (saved or not). */
export function openTagEditor(R, after) {
  const d = dlg("tagsDlg");
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${h(t("tags.edit"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain save-body">${tagBlock("editTags")}
      ${R.savedPath ? `<p class="help">${h(t("tags.savedToo"))}</p>` : ""}</div>
    <div class="dlg-foot"><span></span><button class="btn sm ghost" value="close">${h(t("common.cancel"))}</button>
      <button type="button" class="btn sm primary" id="tagsGo">${h(t("tags.saveBtn"))}</button></div></form>`;
  const editor = tagEditor($("#editTags", d), R.tags);
  $("#editTags .tag-in", d).id = "editTagsIn";
  suggester($(".tag-sugs", d), R, editor);
  $("#tagsGo", d).onclick = async () => {
    try {
      const r = await api(`/api/tags/${encodeURIComponent(R.id)}`, { method: "POST", body: { tags: editor.get() } });
      R.tags = r.tags;
      d.close();
      after?.();
    } catch (e) { toast(e.message, 5000); }
  };
  d.showModal();
  setTimeout(() => $(".tag-in", d)?.focus(), 30);
}

/** The row under the byline: language switcher + tags. lang(code|null) switches the shown language. */
export function metaRow(R, { onLang, onTag }) {
  const el = $("#aMeta");
  if (!el) return;
  const langs = Object.keys(R.translations || {});
  const cur = R.translation?.article || null;
  const showTags = R.id && R.finished && R.outcome === "article";
  if (!langs.length && !showTags) { el.innerHTML = ""; return; }
  const saved = R.savedPath || R.savedFile;
  el.innerHTML = `${langs.length ? `<div class="seg a-langs" role="group" aria-label="${h(t("tr.languages"))}">
      <button type="button" data-lang="" aria-pressed="${!cur}" class="${cur ? "" : "on"}">${h(t("tr.originalShort"))}</button>
      ${langs.map(c => `<button type="button" data-lang="${h(c)}" aria-pressed="${cur === c}" class="${cur === c ? "on" : ""}">${h(langName(c))}</button>`).join("")}</div>` : ""}
    <span class="a-meta-gap"></span>
    ${saved ? `<span class="a-saved" title="${h(R.savedPath || R.savedFile)}">${icon("check")}${h(t("save.savedChip"))}</span>` : ""}
    ${showTags ? `<div class="a-tags">${icon("tag")}${(R.tags || []).map(x => `<button type="button" class="tag-chip link" data-tag="${h(x)}" title="${h(t("tags.find"))}">${h(x)}</button>`).join("")}
      <button type="button" class="btn sm ghost" data-edit-tags>${h(t((R.tags || []).length ? "tags.edit" : "tags.addBtn"))}</button></div>` : ""}`;
  $$("[data-lang]", el).forEach(b => (b.onclick = () => onLang(b.dataset.lang || null)));
  $$("[data-tag]", el).forEach(b => (b.onclick = () => onTag(b.dataset.tag)));
  $("[data-edit-tags]", el)?.addEventListener("click", () => openTagEditor(R, () => metaRow(R, { onLang, onTag })));
}
