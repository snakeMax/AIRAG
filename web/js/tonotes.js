// Research -> Notes: "Add to notes" on articles and quick answers, search results, and single sources.
// Two ways: "Add as raw data" saves the text exactly as it is (no AI) in the folder you pick;
// "Auto-categorize" asks the AI (a background job) for a title, folder, type, tags and related notes,
// keeps the text as it is, and shows the proposal to check before anything is saved.
import { $, h, icon, api, toast } from "./util.js";
import { t, uiLang } from "./i18n.js";
import { pokeJobs } from "./activity.js";

const VKEY = "airag.notes.vault";
const linkLine = titles => titles.length ? `\n\n## ${t("tn.related")}\n\n` + titles.map(x => `- [[${x}]]`).join("\n") + "\n" : "";
const cleanTitle = s => String(s || "").replace(/[\\/:*?"<>|#^[\]]/g, " ").replace(/\s+/g, " ").trim().slice(0, 100);

function dlg() {
  let d = $("#tnDlg");
  if (!d) { d = Object.assign(document.createElement("dialog"), { id: "tnDlg", className: "dlg nt-dlg" }); document.body.appendChild(d); }
  return d;
}

async function vaultInfo(vid) {
  const [tree, vs] = await Promise.all([api(`/api/notes/${vid}/tree`), api("/api/notes/vaults")]);
  const v = vs.vaults.find(x => x.id === vid);
  return { folders: (tree.items || tree).filter(x => x.kind === "folder").map(x => x.path), types: (vs.types || {})[v?.template || "empty"] || [] };
}

// item: { title, text, kind: "article" | "results" | "source" | "answer", query, url }
export async function addToNotes(item) {
  let vs;
  try { vs = await api("/api/notes/vaults"); } catch (e) { return toast(e.message, 6000); }
  const vaults = vs.vaults.filter(v => v.exists && !v.read_only);
  const d = dlg();
  if (!vaults.length) {
    d.innerHTML = `<form method="dialog"><div class="dlg-head"><h2>${h(t("tn.title"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
      <div class="dlg-body plain"><p>${h(t("tn.noVault"))}</p></div>
      <div class="dlg-foot"><span class="grow"></span><a class="btn primary" href="#/notes">${h(t("tn.openNotes"))}</a></div></form>`;
    d.querySelector("a").onclick = () => d.close();
    return d.showModal();
  }
  let last = ""; try { last = localStorage.getItem(VKEY) || ""; } catch { /* storage off */ }
  const pick = vaults.find(v => v.main) || vaults.find(v => v.id === last) || vaults[0];
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${h(t("tn.title"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain nt-org">
      <p class="muted nt-org-why">${h(t("tn.what." + item.kind))}: <b>${h(item.title)}</b></p>
      <label class="nt-org-f"><span>${h(t("nt.vault"))}</span><select id="tnVault" class="input">${vaults.map(v => `<option value="${h(v.id)}"${v.id === pick.id ? " selected" : ""}>${v.main ? "★ " : ""}${h(v.name)}${v.linked ? " · Obsidian" : ""}</option>`).join("")}</select></label>
      <div class="tn-ways" role="radiogroup" aria-label="${h(t("tn.how"))}">
        <label class="tn-way"><input type="radio" name="tnHow" value="auto" checked><span><b>${icon("bolt")}${h(t("tn.auto"))}</b><small>${h(t("tn.autoDesc"))}</small></span></label>
        <label class="tn-way"><input type="radio" name="tnHow" value="raw"><span><b>${icon("file")}${h(t("tn.raw"))}</b><small>${h(t("tn.rawDesc"))}</small></span></label>
      </div>
      <label class="nt-org-f" id="tnFolderRow" hidden><span>${h(t("nt.orgFolder"))}</span><select id="tnFolder" class="input"></select></label>
      <p class="nt-org-busy" id="tnBusy" hidden><span class="spinner sm"></span>${h(t("tn.working"))}</p>
    </div>
    <div class="dlg-foot"><button class="btn ghost" value="close">${h(t("common.cancel"))}</button><span class="grow"></span>
      <button type="submit" class="btn primary" value="go" id="tnGo">${h(t("tn.next"))}</button></div></form>`;
  const folderSel = $("#tnFolder"), row = $("#tnFolderRow");
  let info = null;
  const loadFolders = async () => {
    info = null;
    try { info = await vaultInfo($("#tnVault").value); } catch (e) { return toast(e.message, 5000); }
    const pref = ["Sources", "Inbox"].find(f => info.folders.includes(f)) || "";
    folderSel.innerHTML = `<option value="">${h(t("nt.orgTop"))}</option>` + info.folders.map(f => `<option value="${h(f)}"${f === pref ? " selected" : ""}>${h(f)}</option>`).join("");
  };
  const how = () => d.querySelector("input[name=tnHow]:checked").value;
  const sync = () => { row.hidden = how() !== "raw"; $("#tnGo").textContent = t(how() === "raw" ? "tn.save" : "tn.next"); };
  d.querySelectorAll("input[name=tnHow]").forEach(r => (r.onchange = sync));
  $("#tnVault").onchange = loadFolders;
  sync();
  loadFolders();
  d.querySelector("form").onsubmit = async e => {
    if (e.submitter?.value !== "go") return;
    e.preventDefault();
    const vid = $("#tnVault").value;
    try { localStorage.setItem(VKEY, vid); } catch { /* storage off */ }
    const props = { source: "research" };
    if (item.query) props.query = item.query;
    if (item.url) props.url = item.url;
    if (how() === "raw") {
      d.close();
      return save(vid, folderSel.value, cleanTitle(item.title) || t("tn.untitled"), item.text, props);
    }
    $("#tnGo").disabled = true;
    $("#tnBusy").hidden = false;
    let p;
    const job = api(`/api/notes/${vid}/categorize`, { method: "POST", body: { text: item.text, title: item.title, ui_lang: uiLang() } });
    pokeJobs();
    try { p = await job; }
    catch (err) {
      if (d.open) { $("#tnGo").disabled = false; $("#tnBusy").hidden = true; }
      return toast(t("tn.failed", { msg: err.message }), 8000);
    }
    if (!info) await loadFolders();
    preview(vid, p, item, props, info || { folders: [], types: [] });
  };
  d.showModal();
}

function preview(vid, p, item, props, info) {
  const d = dlg();
  const opt = (v, label, sel) => `<option value="${h(v)}"${v === sel ? " selected" : ""}>${h(label)}</option>`;
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${h(t("nt.orgTitle"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain nt-org">
      ${p.why ? `<p class="muted nt-org-why">${h(p.why)}</p>` : ""}
      <label class="nt-org-f"><span>${h(t("nt.orgName"))}</span><input id="tnTitle" class="input" maxlength="120" value="${h(p.title)}"></label>
      <div class="nt-org-row">
        <label class="nt-org-f"><span>${h(t("nt.orgFolder"))}</span><select id="tnF" class="input">${opt("", t("nt.orgTop"), p.folder)}${info.folders.map(f => opt(f, f, p.folder)).join("")}</select></label>
        <label class="nt-org-f"><span>${h(t("nt.orgType"))}</span><select id="tnT" class="input">${opt("", t("nt.orgNoType"), p.type)}${info.types.map(x => opt(x, x, p.type)).join("")}</select></label>
      </div>
      <label class="nt-org-f"><span>${h(t("nt.orgTags"))}</span><input id="tnTags" class="input" value="${h((p.tags || []).join(", "))}" placeholder="${h(t("nt.orgTagsPh"))}"></label>
      ${p.links?.length ? `<fieldset class="tn-rel"><legend>${h(t("tn.relatedPick"))}</legend>${p.links.map((x, i) => `<label><input type="checkbox" data-rel="${i}" checked> ${h(x)}</label>`).join("")}</fieldset>` : ""}
      <details class="tn-peek"><summary>${h(t("tn.peek", { n: item.text.length.toLocaleString() }))}</summary><pre>${h(item.text.slice(0, 1500))}${item.text.length > 1500 ? "\n…" : ""}</pre></details>
    </div>
    <div class="dlg-foot"><button class="btn ghost" value="close">${h(t("common.cancel"))}</button><span class="grow"></span>
      <button type="submit" class="btn primary" value="save">${h(t("nt.orgSave"))}</button></div></form>`;
  d.querySelector("form").onsubmit = async e => {
    if (e.submitter?.value !== "save") return;
    e.preventDefault();
    const title = cleanTitle($("#tnTitle").value);
    if (!title) return $("#tnTitle").focus();
    const rel = p.links.filter((x, i) => d.querySelector(`[data-rel="${i}"]`)?.checked);
    const tags = [...new Set($("#tnTags").value.split(/[,\s]+/).map(x => x.trim().replace(/^#/, "")).filter(Boolean))].slice(0, 12);
    const pr = { ...props };
    if ($("#tnT").value) pr.type = $("#tnT").value;
    if (tags.length) pr.tags = tags;
    d.close();
    await save(vid, $("#tnF").value, title, item.text.trimEnd() + "\n" + linkLine(rel), pr);
  };
  if (!d.open) d.showModal();
}

async function save(vid, folder, title, body, props) {
  try {
    const r = await api(`/api/notes/${vid}/new`, { method: "POST", body: { folder, title, body, props } });
    toast(t("tn.saved", { path: r.path }), 8000, { label: t("tn.open"), run: () => { location.hash = `#/notes?p=${encodeURIComponent(r.path)}`; } });
  } catch (e) { toast(e.message, 6000); }
}

// --- turning each kind of research into Markdown ---
export function resultsMarkdown(R) {
  const items = (R.results?.items || []).slice(0, 40);
  const one = s => `### [${s.title || s.url}](${s.url})\n` + [s.domain, s.source_type, s.relevance != null ? `relevance ${s.relevance}/10` : ""].filter(Boolean).join(" · ")
    + (s.summary ? `\n\n${s.summary}` : "") + (s.findings?.length ? "\n\n" + s.findings.map(f => `- ${f.claim}${f.evidence ? ` (“${f.evidence}”)` : ""}`).join("\n") : "");
  return `> ${R.query}\n\n` + items.map(one).join("\n\n") + "\n";
}

export function sourceMarkdown(s, query) {
  return (query ? `> ${query}\n\n` : "") + `[${s.title || s.url}](${s.local ? s.path : s.url})` +
    [s.domain, s.source_type].filter(Boolean).map(x => ` · ${x}`).join("") +
    (s.summary ? `\n\n${s.summary}` : "") + (s.findings?.length ? "\n\n" + s.findings.map(f => `- ${f.claim}${f.evidence ? ` (“${f.evidence}”)` : ""}`).join("\n") : "") + "\n";
}
