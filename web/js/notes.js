// Notes Mode: vaults, a note editor (Edit / Read), every-match search, backlinks and voice notes.
// Computers: vault sidebar | note | links panel. Phones: one screen at a time with a bottom bar
// (Notes / Search / Voice note / Graph / Ask). Everything here works without the AI.
import { $, $$, h, icon, api, toast } from "./util.js";
import { t } from "./i18n.js";
import { render as renderMd, allowLinks } from "./markdown.js";
import { micButton } from "./speech.js";

const VKEY = "airag.notes.vault";
const N = { vaults: [], templates: [], vault: null, tree: [], open: new Set(), note: null, dirty: false, mode: "edit",
            screen: "list", timer: null, saving: null, query: "" };
const phone = () => matchMedia("(max-width: 720px)").matches;

// ---------------------------------------------------------------- entry
export async function showNotes() {
  const root = $("#view-notes");
  if (!root.dataset.ready) {
    root.innerHTML = shell(); wire(root); root.dataset.ready = "1";
    addEventListener("resize", fit);
    // banners above (notice, update) can appear or close at any time: refit when they change size
    const ro = new ResizeObserver(() => fit());
    ["#disclaimer", "#updateBanner", ".topbar"].forEach(s => { const el = $(s); if (el) ro.observe(el); });
  }
  fit();
  await loadVaults();
}

// the Notes screen fills the window below whatever sits above it (top bar, notice banners)
function fit() {
  const nt = $(".nt");
  if (!nt || $("#view-notes").hidden) return;
  nt.style.height = Math.max(320, innerHeight - nt.getBoundingClientRect().top) + "px";
}

function shell() {
  return `<div class="nt" data-screen="list">
    <div class="nt-top">
      <form class="searchbox sm nt-search" id="ntSearch" autocomplete="off" role="search">
        <span class="sb-icon">${icon("search")}</span>
        <input type="search" name="q" placeholder="${h(t("nt.searchPh"))}" aria-label="${h(t("nt.search"))}">
      </form>
      <button type="button" class="icon-btn nt-words-btn" data-nt="words" title="${h(t("nt.wordsTitle"))}" aria-label="${h(t("nt.wordsTitle"))}">${icon("tag")}</button>
      <button type="button" class="btn sm nt-voice-btn" data-nt="voice">${icon("mic")}<span>${h(t("nt.voice"))}</span></button>
      <button type="button" class="btn sm primary" data-nt="new">${icon("plus")}<span>${h(t("nt.new"))}</span></button>
    </div>
    <div class="nt-body">
      <nav class="nt-side" aria-label="${h(t("nt.vault"))}">
        <div class="nt-vault-row"><label class="nt-vault-pick"><span>${h(t("nt.vault"))}</span><select id="ntVault"></select></label>
          <button type="button" class="icon-btn sm" data-nt="vaults" title="${h(t("nt.vaults"))}" aria-label="${h(t("nt.vaults"))}">${icon("plus")}</button></div>
        <div class="nt-tree" id="ntTree"></div>
      </nav>
      <main class="nt-main" id="ntMain"></main>
      <aside class="nt-right" id="ntRight" aria-label="${h(t("nt.links"))}"></aside>
    </div>
    <nav class="nt-bottom" aria-label="${h(t("nt.title"))}">
      <button type="button" data-screen-to="list">${icon("list")}<span>${h(t("nt.tabNotes"))}</span></button>
      <button type="button" data-screen-to="search">${icon("search")}<span>${h(t("nt.tabSearch"))}</span></button>
      <button type="button" class="nt-bottom-voice" data-nt="voice" aria-label="${h(t("nt.voice"))}">${icon("mic")}</button>
      <button type="button" disabled title="${h(t("nt.soon"))}">${icon("graph")}<span>${h(t("nt.tabGraph"))}</span></button>
      <button type="button" disabled title="${h(t("nt.soon"))}">${icon("chat")}<span>${h(t("nt.tabAsk"))}</span></button>
    </nav>
  </div>`;
}

function setScreen(s) {
  N.screen = s;
  $(".nt").dataset.screen = s;
  $$(".nt-bottom [data-screen-to]").forEach(b => b.classList.toggle("on", b.dataset.screenTo === s || (s === "note" && b.dataset.screenTo === "list")));
  if (s === "search" && phone()) setTimeout(() => $("#ntSearch input").focus(), 30);
}

function wire(root) {
  root.addEventListener("click", e => {
    const b = e.target.closest("[data-nt]");
    if (b) {
      const a = b.dataset.nt;
      if (a === "new") newNote();
      else if (a === "voice") voiceNote();
      else if (a === "vaults") vaultDialog();
      else if (a === "words") wordsDialog();
      else if (a === "back") setScreen("list");
      return;
    }
    const s = e.target.closest("[data-screen-to]");
    if (s) setScreen(s.dataset.screenTo);
  });
  $("#ntVault").onchange = e => selectVault(e.target.value);
  const form = $("#ntSearch");
  const mic = micButton(form.q, () => runSearch(form.q.value));
  if (mic) form.appendChild(mic);
  form.onsubmit = e => { e.preventDefault(); runSearch(form.q.value); };
  addEventListener("beforeunload", e => { if (N.dirty) { saveNow(); e.preventDefault(); } });
}

// ---------------------------------------------------------------- vaults
async function loadVaults() {
  const r = await api("/api/notes/vaults").catch(e => { toast(e.message, 5000); return null; });
  if (!r) return;
  N.vaults = r.vaults.filter(v => v.exists);
  N.templates = r.templates;
  const sel = $("#ntVault");
  sel.innerHTML = N.vaults.map(v => `<option value="${h(v.id)}">${h(v.name)}${v.linked ? " · " + h(t("nt.linked")) : ""}</option>`).join("");
  if (!N.vaults.length) { emptyState(r); return; }
  let id = "";
  try { id = localStorage.getItem(VKEY) || ""; } catch { /* storage off */ }
  if (!N.vaults.some(v => v.id === id)) id = N.vaults[0].id;
  sel.value = id;
  await selectVault(id);
}

function emptyState(r) {
  N.vault = null;
  $("#ntTree").innerHTML = "";
  $("#ntRight").innerHTML = "";
  setScreen("note");
  $("#ntMain").innerHTML = `<section class="nt-empty">
      <h2>${h(t("nt.emptyTitle"))}</h2><p>${h(t("nt.emptyIntro"))}</p>
      <p class="muted nt-path">${h(t("nt.folderIs", { p: r.root }))}</p>
      <div class="row"><button type="button" class="btn primary" data-nt="vaults">${icon("plus")}${h(t("nt.createVault"))}</button></div>
    </section>`;
}

async function selectVault(id) {
  if (N.dirty) await saveNow();
  N.vault = N.vaults.find(v => v.id === id) || null;
  if (!N.vault) return;
  try { localStorage.setItem(VKEY, id); } catch { /* storage off */ }
  N.note = null;
  $("#ntMain").innerHTML = `<div class="status-line"><span class="spinner sm"></span> ${h(t("nt.indexing"))}</div>`;
  $("#ntRight").innerHTML = "";
  await api(`/api/notes/${id}/reindex`, { method: "POST" }).catch(e => toast(e.message, 5000));
  await loadTree();
  welcome();
  setScreen("list");
}

async function loadTree() {
  const r = await api(`/api/notes/${N.vault.id}/tree`).catch(() => ({ items: [] }));
  N.tree = r.items;
  drawTree();
}

// "Search words and tags": two screens. Search words = every search operator with an example (tap to add it to
// the search box); Your tags = every tag in the vault with its count (tap to list its notes).
const WORDS = [
  ["exact", '"fell by half"'], ["exclude", "-deer"], ["or", "moose OR elk"], ["tag", "tag:status/draft"], ["type", "type:claim"],
  ["path", "path:Sources/"], ["prop", "prop:year>1800"], ["propeq", "prop:status=done"], ["linksto", 'linksto:"Moose and roads"'],
  ["linkedfrom", 'linkedfrom:"Moose and roads"'], ["has", "has:image"], ["modified", "modified:>2026-11-01"],
  ["created", "created:<2026-01-01"], ["regex", "regex:NOK \\d+"], ["case", "case:yes"],
];

function useWord(q, run = false) {
  const input = $("#ntSearch input");
  input.value = run ? q : (input.value.trim() ? input.value.trim() + " " : "") + q;
  $("#ntWordsDlg")?.close();
  if (run) runSearch(q);
  else { setScreen("search"); input.focus(); }
}

async function wordsDialog(tab = "words") {
  const d = dialog("ntWordsDlg", "nt-dlg nt-words-dlg");
  const draw = async () => {
    d.innerHTML = `<form method="dialog">
      <div class="dlg-head"><h2>${h(t("nt.wordsTitle"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
      <div class="dlg-tabs-row" role="tablist">
        <button type="button" role="tab" data-wtab="words" aria-selected="${tab === "words"}" class="${tab === "words" ? "on" : ""}">${h(t("nt.wordsTab"))}</button>
        <button type="button" role="tab" data-wtab="tags" aria-selected="${tab === "tags"}" class="${tab === "tags" ? "on" : ""}">${h(t("nt.tagsTab"))}</button></div>
      <div class="dlg-body plain" id="ntWordsBody"><div class="status-line"><span class="spinner sm"></span></div></div></form>`;
    $$("[data-wtab]", d).forEach(b => (b.onclick = () => { tab = b.dataset.wtab; draw(); }));
    const body = $("#ntWordsBody");
    if (tab === "words") {
      body.innerHTML = `<p class="muted nt-words-intro">${h(t("nt.wordsIntro"))}</p><div class="nt-words">${WORDS.map(([k, ex]) =>
        `<button type="button" class="nt-word" data-word="${h(ex)}"><code>${h(ex)}</code><span>${h(t("nt.op." + k))}</span></button>`).join("")}</div>`;
      $$("[data-word]", body).forEach(b => (b.onclick = () => useWord(b.dataset.word)));
    } else {
      const r = N.vault ? await api(`/api/notes/${N.vault.id}/tags`).catch(() => ({ tags: [] })) : { tags: [] };
      body.innerHTML = r.tags.length
        ? `<p class="muted nt-words-intro">${h(t("nt.tagsIntro", { n: r.tags.length }))}</p><div class="nt-taglist">${r.tags.sort((a, b) => a.tag.localeCompare(b.tag)).map(x =>
            `<button type="button" class="nt-tag" data-tag="${h(x.tag)}" style="--d:${x.tag.split("/").length - 1}">#${h(x.tag.split("/").pop())}<small>${x.count}</small></button>`).join("")}</div>`
        : `<p class="muted">${h(t("nt.noTags"))}</p>`;
      $$("[data-tag]", body).forEach(b => (b.onclick = () => useWord(/\s/.test(b.dataset.tag) ? `tag:"${b.dataset.tag}"` : `tag:${b.dataset.tag}`, true)));
    }
  };
  await draw();
  if (!d.open) d.showModal();
}

function drawTree() {
  const box = $("#ntTree");
  const folders = N.tree.filter(x => x.kind === "folder").map(x => x.path);
  const notes = N.tree.filter(x => x.kind === "note");
  const kids = dir => ({
    dirs: folders.filter(f => f.includes("/") ? f.slice(0, f.lastIndexOf("/")) === dir : dir === ""),
    files: notes.filter(n => (n.path.includes("/") ? n.path.slice(0, n.path.lastIndexOf("/")) : "") === dir),
  });
  const draw = (dir, depth) => {
    const k = kids(dir);
    return k.dirs.map(d => {
      const open = N.open.has(d);
      const name = d.split("/").pop();
      return `<button type="button" class="nt-dir" data-dir="${h(d)}" style="--d:${depth}" aria-expanded="${open}">${icon(open ? "chevDown" : "chevRight")}<span>${h(name)}</span></button>
        ${open ? draw(d, depth + 1) : ""}`;
    }).join("") + k.files.sort((a, b) => a.path.localeCompare(b.path)).map(n =>
      `<a href="#" class="nt-file ${N.note?.path === n.path ? "on" : ""}" data-path="${h(n.path)}" style="--d:${depth}">${h(n.path.split("/").pop().replace(/\.md$/i, ""))}</a>`).join("");
  };
  const recent = [...notes].sort((a, b) => b.mtime - a.mtime).slice(0, 5);
  box.innerHTML = (recent.length ? `<div class="nt-recent"><div class="nt-label">${h(t("nt.recent"))}</div>${recent.map(n =>
      `<a href="#" class="nt-file" data-path="${h(n.path)}">${h(n.path.split("/").pop().replace(/\.md$/i, ""))}<small>${h(n.path.includes("/") ? n.path.slice(0, n.path.lastIndexOf("/")) : "")}</small></a>`).join("")}</div>` : "")
    + `<div class="nt-label">${h(t("nt.folders"))}</div>` + (draw("", 0) || `<p class="muted">${h(t("nt.noNotes"))}</p>`);
  $$(".nt-dir", box).forEach(b => (b.onclick = () => { const d = b.dataset.dir; N.open.has(d) ? N.open.delete(d) : N.open.add(d); drawTree(); }));
  $$(".nt-file", box).forEach(a => (a.onclick = e => { e.preventDefault(); openNote(a.dataset.path); }));
}

function welcome() {
  const st = N.vault;
  $("#ntMain").innerHTML = `<section class="nt-empty"><h2>${h(st.name)}</h2>
    <p>${h(st.purpose || t("nt.pickNote"))}</p>
    <div class="row"><button type="button" class="btn primary" data-nt="new">${icon("plus")}${h(t("nt.new"))}</button>
      <button type="button" class="btn" data-nt="voice">${icon("mic")}${h(t("nt.voice"))}</button></div></section>`;
}

// ---------------------------------------------------------------- vault dialog
function dialog(id, cls = "") {
  let d = $("#" + id);
  if (!d) { d = Object.assign(document.createElement("dialog"), { id, className: "dlg " + cls }); document.body.appendChild(d); }
  return d;
}

function vaultDialog() {
  const d = dialog("ntVaultDlg", "nt-dlg");
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${h(t("nt.vaults"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain">
      <h3>${h(t("nt.createVault"))}</h3>
      <div class="field"><label for="nvName">${h(t("nt.vaultName"))}</label><input id="nvName" class="input" maxlength="80" required></div>
      <div class="field"><label for="nvTpl">${h(t("nt.template"))}</label><select id="nvTpl" class="input">${N.templates.map(x =>
        `<option value="${x}">${h(t("nt.tpl." + x))}</option>`).join("")}</select><div class="help" id="nvTplHelp"></div></div>
      <div class="field"><label for="nvPurpose">${h(t("nt.purpose"))}</label><input id="nvPurpose" class="input" maxlength="300" placeholder="${h(t("nt.purposePh"))}"></div>
      <div class="row"><button type="submit" class="btn primary" value="create">${icon("plus")}${h(t("nt.create"))}</button></div>
      <h3 style="margin-top:22px">${h(t("nt.linkTitle"))}</h3>
      <p class="muted" style="font-size:13px">${h(t("nt.linkIntro"))}</p>
      <div class="row"><input id="nvLinkPath" class="input" placeholder="${h(t("nt.linkPh"))}" style="flex:1;min-width:0">
        <button type="button" class="btn sm" id="nvPick">${icon("folder")}${h(t("nt.pick"))}</button>
        <button type="button" class="btn sm" id="nvLink">${h(t("nt.link"))}</button></div>
    </div></form>`;
  const help = () => ($("#nvTplHelp").textContent = t("nt.tplHelp." + $("#nvTpl").value));
  $("#nvTpl").onchange = help; help();
  d.querySelector("form").onsubmit = async e => {
    if (e.submitter?.value !== "create") return;
    e.preventDefault();
    try {
      const v = await api("/api/notes/vaults", { method: "POST", body: { name: $("#nvName").value.trim(), template: $("#nvTpl").value, purpose: $("#nvPurpose").value.trim() } });
      try { localStorage.setItem(VKEY, v.id); } catch { /* storage off */ }
      d.close(); toast(t("nt.vaultMade", { n: v.name })); loadVaults();
    } catch (err) { toast(err.message, 5000); }
  };
  $("#nvPick").onclick = async () => {
    const r = await api("/api/library/pick-folder", { method: "POST" }).catch(e => { toast(e.message); return {}; });
    if (r.path) $("#nvLinkPath").value = r.path;
  };
  $("#nvLink").onclick = async () => {
    const folder = $("#nvLinkPath").value.trim();
    if (!folder) return $("#nvLinkPath").focus();
    try {
      const v = await api("/api/notes/vaults/link", { method: "POST", body: { folder } });
      try { localStorage.setItem(VKEY, v.id); } catch { /* storage off */ }
      d.close(); toast(t("nt.vaultLinked", { n: v.name })); loadVaults();
    } catch (err) { toast(err.message, 5000); }
  };
  d.showModal();
  setTimeout(() => $("#nvName").focus(), 30);
}

// ---------------------------------------------------------------- note
const folderOf = p => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");
const nameOf = p => p.split("/").pop().replace(/\.md$/i, "");

export async function openNote(path) {
  if (N.dirty) await saveNow();
  const r = await api(`/api/notes/${N.vault.id}/note?path=${encodeURIComponent(path)}`).catch(e => { toast(e.message, 5000); return null; });
  if (!r) return;
  N.note = r;
  N.dirty = false;
  for (let f = folderOf(path); f; f = folderOf(f)) N.open.add(f);
  drawTree();
  drawNote();
  drawLinks();
  setScreen("note");
}

function propsTable(props) {
  const rows = Object.entries(props || {}).filter(([k]) => k !== "id");
  if (!rows.length) return "";
  const val = v => Array.isArray(v) ? v.map(x => `<span class="nt-chip">${h(String(x))}</span>`).join(" ") : h(String(v ?? ""));
  return `<dl class="nt-props">${rows.map(([k, v]) => `<dt>${h(k)}</dt><dd>${val(v)}</dd>`).join("")}</dl>`;
}

function bodyOf(text) {
  const m = text.match(/^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|$)/);
  return m ? text.slice(m[0].length) : text;
}

// [[Note#Heading|alias]] and ![[file]] -> safe links (the target goes in a data attribute, escaped)
function renderNote(text) {
  const links = [];
  const src = bodyOf(text).replace(/(!?)\[\[([^\[\]\n|#]*)(?:#([^\[\]\n|]*))?(?:\|([^\[\]\n]*))?\]\]/g, (m, emb, target, head, alias) => {
    links.push({ emb: !!emb, target: target.trim(), head: (head || "").trim(), alias: (alias || "").trim() });
    return `\u0002${links.length - 1}\u0002`;
  });
  allowLinks(null);                       // the user's own notes: their web links are kept (they open outside AIRAG)
  let html = renderMd(src);
  html = html.replace(/\u0002(\d+)\u0002/g, (m, i) => {
    const l = links[+i];
    const label = l.alias || (l.head ? `${l.target} › ${l.head}` : l.target);
    return l.emb ? `<span class="nt-embed">${icon("file")}${h(label)}</span>`
      : `<a href="#" class="nt-wl" data-target="${h(l.target)}" data-head="${h(l.head)}">${h(label)}</a>`;
  });
  return html;
}

function drawNote() {
  const n = N.note;
  const linked = n.linked_vault;
  $("#ntMain").innerHTML = `<article class="nt-note">
    <div class="nt-crumbs"><button type="button" class="icon-btn sm nt-back" data-nt="back" aria-label="${h(t("nt.back"))}">${icon("chevLeft")}</button>
      <span class="muted">${h(folderOf(n.path) || N.vault.name)}</span><span class="grow"></span>
      <span class="nt-state" id="ntState">${h(t(linked ? "nt.readOnly" : "nt.saved"))}</span>
      <div class="seg nt-modes" role="tablist">
        <button type="button" role="tab" data-mode="edit" aria-selected="${N.mode === "edit"}" class="${N.mode === "edit" ? "on" : ""}" ${linked ? "disabled" : ""}>${h(t("nt.edit"))}</button>
        <button type="button" role="tab" data-mode="read" aria-selected="${N.mode === "read" || linked}" class="${N.mode === "read" || linked ? "on" : ""}">${h(t("nt.read"))}</button></div></div>
    <h1 class="nt-title">${h(nameOf(n.path))}</h1>
    ${N.mode === "read" || linked ? `${propsTable(n.props)}<div class="prose nt-prose">${renderNote(n.text)}</div>`
      : `<textarea class="nt-editor" id="ntEditor" spellcheck="true" aria-label="${h(t("nt.editorLabel"))}">${h(n.text)}</textarea>
         <p class="muted nt-hint">${h(t("nt.editHint"))}</p>`}
  </article>`;
  $$(".nt-modes [data-mode]").forEach(b => (b.onclick = async () => { if (N.dirty) await saveNow(); N.mode = b.dataset.mode; drawNote(); }));
  const ed = $("#ntEditor");
  if (ed) {
    ed.oninput = () => { N.dirty = true; setState("nt.unsaved"); clearTimeout(N.timer); N.timer = setTimeout(saveNow, 1500); };
    ed.onkeydown = e => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveNow(); } };
    ed.onblur = () => N.dirty && saveNow();
  }
  $$(".nt-wl").forEach(a => (a.onclick = e => { e.preventDefault(); followLink(a.dataset.target); }));
}

function setState(key) { const s = $("#ntState"); if (s) s.textContent = t(key); }

async function saveNow() {
  clearTimeout(N.timer);
  if (!N.dirty || !N.note) return;
  if (N.saving) return N.saving;
  const ed = $("#ntEditor");
  const text = ed ? ed.value : N.note.text;
  setState("nt.saving");
  N.saving = api(`/api/notes/${N.vault.id}/note`, { method: "PUT", body: { path: N.note.path, text, hash: N.note.hash } })
    .then(async r => {
      N.note.text = text; N.note.hash = r.hash; N.dirty = false; setState("nt.saved");
      const fresh = await api(`/api/notes/${N.vault.id}/note?path=${encodeURIComponent(N.note.path)}`).catch(() => null);
      if (fresh && N.note && fresh.path === N.note.path && !N.dirty) Object.assign(N.note, { props: fresh.props, outline: fresh.outline, tags: fresh.tags });
      drawLinks();
    })
    .catch(e => { setState("nt.notSaved"); toast(e.message, 7000); })
    .finally(() => { N.saving = null; });
  return N.saving;
}

async function followLink(target) {
  const want = target.toLowerCase().replace(/\.md$/, "");
  const hit = N.tree.find(x => x.kind === "note" && (x.path.toLowerCase().replace(/\.md$/, "") === want || nameOf(x.path).toLowerCase() === want.split("/").pop()));
  if (hit) return openNote(hit.path);
  if (!confirm(t("nt.createMissing", { n: target }))) return;
  const r = await api(`/api/notes/${N.vault.id}/new`, { method: "POST", body: { folder: folderOf(N.note?.path || ""), title: target.split("/").pop() } })
    .catch(e => { toast(e.message, 5000); return null; });
  if (r) { N.mode = "edit"; await loadTree(); openNote(r.path); }      // a new note opens ready to write
}

async function drawLinks() {
  const box = $("#ntRight");
  if (!N.note) { box.innerHTML = ""; return; }
  const r = await api(`/api/notes/${N.vault.id}/links?path=${encodeURIComponent(N.note.path)}`).catch(() => null);
  if (!r || N.note === null) return;
  const out = r.outgoing.filter(x => x.kind !== "url");
  const item = x => `<a href="#" class="nt-link" data-path="${h(x.path)}">${h(x.title)}</a>`;
  box.innerHTML = `
    ${N.note.outline?.length ? `<section><h2>${h(t("nt.outline"))}</h2>${N.note.outline.map(o => `<div class="nt-out" style="--d:${o.level - 1}">${h(o.heading)}</div>`).join("")}</section>` : ""}
    <section><h2>${h(t("nt.linkedFrom", { n: r.backlinks.linked.length }))}</h2>${r.backlinks.linked.map(item).join("") || `<p class="muted">${h(t("nt.none"))}</p>`}</section>
    <section><h2>${h(t("nt.mentions", { n: r.backlinks.unlinked.length }))}</h2>${r.backlinks.unlinked.map(x =>
      `<div class="nt-mention">${item(x)}<button type="button" class="btn sm" data-linkfrom="${h(x.path)}">${h(t("nt.linkIt"))}</button></div>`).join("") || `<p class="muted">${h(t("nt.none"))}</p>`}</section>
    ${out.some(x => !x.exists) ? `<section><h2>${h(t("nt.missing"))}</h2>${out.filter(x => !x.exists).map(x =>
      `<a href="#" class="nt-link nt-ghost" data-make="${h(x.target)}">${h(x.target)}</a>`).join("")}</section>` : ""}`;
  $$(".nt-link[data-path]", box).forEach(a => (a.onclick = e => { e.preventDefault(); openNote(a.dataset.path); }));
  $$("[data-make]", box).forEach(a => (a.onclick = e => { e.preventDefault(); followLink(a.dataset.make); }));
  $$("[data-linkfrom]", box).forEach(b => (b.onclick = () => linkMention(b.dataset.linkfrom)));
}

// "Link it": in the other note, the first plain mention of this note's name becomes [[name]]
async function linkMention(otherPath) {
  const v = N.vault.id, name = nameOf(N.note.path);
  const o = await api(`/api/notes/${v}/note?path=${encodeURIComponent(otherPath)}`).catch(e => { toast(e.message); return null; });
  if (!o) return;
  const body = bodyOf(o.text), head = o.text.slice(0, o.text.length - body.length);
  const re = new RegExp(`(?<!\\[\\[)(?<![\\w])(${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})(?![\\w])(?!\\]\\])`, "i");
  if (!re.test(body)) { toast(t("nt.mentionGone")); return; }
  const next = head + body.replace(re, (m, w) => (w === name ? `[[${name}]]` : `[[${name}|${w}]]`));
  try {
    await api(`/api/notes/${v}/note`, { method: "PUT", body: { path: otherPath, text: next, hash: o.hash, approved: false } });
    toast(t("nt.linked2", { n: nameOf(otherPath) }));
    drawLinks();
  } catch (e) { toast(e.message, 6000); }
}

async function newNote(title = "", body = "", folder = null) {
  if (!N.vault) return vaultDialog();
  if (N.vault.linked) return toast(t("nt.linkedNoWrite"), 6000);
  title = title || prompt(t("nt.newTitle"), "")?.trim();
  if (!title) return;
  const inbox = N.tree.some(x => x.kind === "folder" && x.path === "Inbox") ? "Inbox" : "";
  const f = folder ?? (N.note ? folderOf(N.note.path) : inbox);
  const r = await api(`/api/notes/${N.vault.id}/new`, { method: "POST", body: { folder: f, title, body } }).catch(e => { toast(e.message, 5000); return null; });
  if (!r) return;
  N.mode = "edit";
  await loadTree();
  await openNote(r.path);
  setTimeout(() => { const ed = $("#ntEditor"); if (ed) { ed.focus(); ed.setSelectionRange(ed.value.length, ed.value.length); } }, 30);
}

// ---------------------------------------------------------------- voice note (manual: your words into the Inbox)
function voiceNote() {
  if (!N.vault) return vaultDialog();
  if (N.vault.linked) return toast(t("nt.linkedNoWrite"), 6000);
  const d = dialog("ntVoiceDlg", "nt-dlg");
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${h(t("nt.voice"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain">
      <p class="muted" style="font-size:13px">${h(t("nt.voiceIntro"))}</p>
      <div class="nt-voice"><textarea id="nvText" class="input" rows="6" placeholder="${h(t("nt.voicePh"))}"></textarea><span id="nvMic"></span></div>
    </div>
    <div class="dlg-foot"><span class="grow muted" style="font-size:12.5px">${h(t("nt.voiceWhere"))}</span>
      <button class="btn ghost" value="close">${h(t("common.cancel"))}</button>
      <button type="submit" class="btn primary" value="save">${h(t("nt.toInbox"))}</button></div></form>`;
  const ta = $("#nvText");
  const mic = micButton(ta);
  if (mic) { $("#nvMic").appendChild(mic); setTimeout(() => mic.click(), 60); }
  d.querySelector("form").onsubmit = async e => {
    if (e.submitter?.value !== "save") return;
    e.preventDefault();
    const text = ta.value.trim();
    if (!text) return ta.focus();
    d.close();
    const now = new Date();
    const title = `${t("nt.voiceNoteTitle")} ${now.toISOString().slice(0, 10)} ${String(now.getHours()).padStart(2, "0")}.${String(now.getMinutes()).padStart(2, "0")}`;
    const inbox = N.tree.some(x => x.kind === "folder" && x.path === "Inbox") ? "Inbox" : "";
    await newNote(title, text + "\n", inbox);
  };
  d.showModal();
  if (!mic) setTimeout(() => ta.focus(), 30);
}

// ---------------------------------------------------------------- search (every match)
function marked(text, marks) {
  let out = "", at = 0;
  for (const [s, e] of marks || []) {
    if (s < at || s >= text.length) continue;
    out += h(text.slice(at, s)) + "<mark>" + h(text.slice(s, e)) + "</mark>";
    at = e;
  }
  return out + h(text.slice(at));
}

async function runSearch(q) {
  if (!N.vault) return;
  q = (q || "").trim();
  N.query = q;
  setScreen("search");
  const main = $("#ntMain");
  if (!q) { welcome(); return; }
  main.innerHTML = `<div class="status-line"><span class="spinner sm"></span></div>`;
  let r;
  try { r = await api(`/api/notes/${N.vault.id}/search?q=${encodeURIComponent(q)}`); }
  catch (e) { main.innerHTML = `<p class="status-line err">${h(e.message)}</p>`; return; }
  main.innerHTML = `<section class="nt-results">
    <div class="nt-res-head"><button type="button" class="icon-btn sm nt-back" data-nt="back" aria-label="${h(t("nt.back"))}">${icon("chevLeft")}</button>
      <h2>${h(t("nt.everyMatch"))}</h2><span class="muted">${h(t("nt.resultCount", { s: r.sections, n: r.notes }))}</span></div>
    ${r.groups.map(g => `<article class="nt-hit"><a href="#" class="nt-hit-t" data-path="${h(g.path)}">${h(g.title)}</a>
        <span class="muted"> · ${h(folderOf(g.path) || N.vault.name)}${g.type ? " · " + h(g.type) : ""}</span>
        ${g.sections.map(s => `<p class="nt-snip">${s.heading ? `<b>${h(s.heading)}</b> ` : ""}${marked(s.text, s.marks)}</p>`).join("")}</article>`).join("")
      || `<p class="muted">${h(t("nt.noMatches"))}</p>`}
    <p class="muted nt-ops">${h(t("nt.operators"))} <a href="#" data-nt="words">${h(t("nt.wordsAll"))}</a></p></section>`;
  $$(".nt-hit-t", main).forEach(a => (a.onclick = e => { e.preventDefault(); openNote(a.dataset.path); }));
}

export function notesDirty() { return N.dirty; }
export function saveNotes() { return saveNow(); }
