// Settings dialog. Generic fields are rendered from the server's schema, so new
// providers/backends/options show up automatically; a few tabs have custom panels
// (Ollama models, library folders, headless browser, appearance, updates).
import { $, $$, h, icon, api, toast, pollJob, progressBar, fmtBytes, fmtAgo } from "./util.js";
import { t, has, uiLang, uiLanguages } from "./i18n.js";
import { PALETTES, ACCENTS, getAppearance, setAppearance } from "./theme.js";
import { showUpdatePopup } from "./banners.js";

const S = { schema: null, settings: null, info: null, dlg: null, onSaved: null };
const android = () => S.info?.platform === "android";
const DESKTOP_ONLY_PROVIDERS = ["ollama"], PHONE_ONLY_PROVIDERS = ["pc_link"];
const getPath = (o, p) => p.split(".").reduce((a, k) => a?.[k], o);
const setPath = (o, p, v) => { const ks = p.split("."); let a = o; ks.slice(0, -1).forEach(k => (a = a[k] ??= {})); a[ks.at(-1)] = v; };

export function setSettingsHooks({ onSaved }) { S.onSaved = onSaved; }

// field rendering
// provider fields can have their own text (f.pc_link.api_key) before the shared one (f.p.api_key)
const provKey = path => path.startsWith("llm.providers.") ? path.split(".")[2] : null;
const pick = (kind, sec, f, path, fallback) => {
  const pk = provKey(path);
  for (const k of [pk && `${kind}.${pk}.${f.key}`, `${kind}.${sec}.${f.key}`]) if (k && has(k)) return t(k);
  return fallback;
};
const label = (sec, f, path = "") => pick("f", sec, f, path, f.label);
const help = (sec, f, path = "") => pick("h", sec, f, path, f.help || "");
const optLabel = o => { const v = typeof o === "object" ? o.value : o; return has(`o.${v}`) ? t(`o.${v}`) : (typeof o === "object" ? o.label : o); };
const optValue = o => (typeof o === "object" ? o.value : o);

function field(f, sec, path, value) {
  if (f.type === "hidden") return "";
  const id = "f_" + path.replace(/\W/g, "_");
  const hp = help(sec, f, path), hl = hp ? `<div class="help">${h(hp)}</div>` : "";
  const v = value ?? f.default ?? "";
  const lab = h(label(sec, f, path));
  switch (f.type) {
    case "bool":
      return `<div class="field"><label class="switch"><input type="checkbox" data-path="${path}" data-type="bool" ${v ? "checked" : ""}> ${lab}</label>${hl}</div>`;
    case "select":
      return `<div class="field"><label for="${id}">${lab}</label><select id="${id}" data-path="${path}">${f.options.map(o => `<option value="${h(optValue(o))}" ${optValue(o) === v ? "selected" : ""}>${h(optLabel(o))}</option>`).join("")}</select>${hl}</div>`;
    case "number":
      return `<div class="field"><label for="${id}">${lab}</label><input id="${id}" type="number" data-path="${path}" data-type="number" value="${h(v)}" ${f.min != null ? `min="${f.min}"` : ""} ${f.max != null ? `max="${f.max}"` : ""} step="${f.step ?? "any"}">${hl}</div>`;
    case "secret":
      return `<div class="field"><label for="${id}">${lab}</label><input id="${id}" type="password" data-path="${path}" value="${h(v)}" placeholder="${f.env ? h(t("set.orEnv", { env: f.env })) : ""}" autocomplete="off" spellcheck="false">${hl}</div>`;
    case "model":
      return `<div class="field"><label for="${id}">${lab}</label><input id="${id}" type="text" data-path="${path}" value="${h(v)}" list="${id}_list" spellcheck="false"><datalist id="${id}_list"></datalist>${hl}</div>`;
    case "textarea":
      return `<div class="field"><label for="${id}">${lab}</label><textarea id="${id}" class="input ta" data-path="${path}" rows="3">${h(v)}</textarea>${hl}</div>`;
    case "prompt":
      return `<div class="field"><label for="${id}">${lab}</label><textarea id="${id}" class="input ta mono" data-path="${path}" rows="10" placeholder="${h(t("set.promptDefault"))}">${h(v)}</textarea>
        <div class="row" style="margin-top:6px"><button type="button" class="btn sm" data-prompt-load="${id}">${h(t("set.promptLoad"))}</button><button type="button" class="btn sm ghost" data-prompt-reset="${id}">${h(t("set.promptReset"))}</button></div>${hl}</div>`;
    default:
      return `<div class="field"><label for="${id}">${lab}</label><input id="${id}" type="${f.type === "url" ? "url" : "text"}" data-path="${path}" value="${h(v)}" spellcheck="false">${hl}</div>`;
  }
}
const fields = (list, sec, base, values) => list.map(f => field(f, sec, `${base}.${f.key}`, values?.[f.key])).join("");

// dialog
const TABS = [
  ["general", "home"], ["appearance", "palette"], ["model", "cpu"], ["search", "globe"], ["library", "folder"],
  ["prompts", "doc"], ["fetch", "book"], ["research", "sliders"], ["about", "info"],
];

export async function openSettings(tab = "general") {
  const dlg = $("#settingsDlg");
  if ($("#setupDlg")?.open) $("#setupDlg").close();   // never two modal dialogs on top of each other
  S.dlg = dlg;
  try {
    [S.schema, S.settings, S.info] = await Promise.all([api("/api/schema"), api("/api/settings"), api("/api/app/info")]);
  } catch (e) { toast(t("set.loadFailed", { e: e.message }), 4000); return; }
  const sc = S.schema, st = S.settings;
  dlg.innerHTML = `
    <form method="dialog" id="settingsForm">
      <div class="dlg-head"><h2>${h(t("set.title"))}</h2><button class="icon-btn" value="cancel" formnovalidate>${icon("x")}</button></div>
      <div class="dlg-main">
        <nav class="dlg-tabs">${TABS.map(([k, ic]) => `<button type="button" data-tab="${k}">${icon(ic)}${h(t("tab." + k))}</button>`).join("")}</nav>
        <div class="dlg-body">
          <section data-pane="general">${generalPane(sc, st)}</section>
          <section data-pane="appearance" hidden>${appearancePane()}</section>
          <section data-pane="model" hidden>${modelPane(sc, st)}</section>
          <section data-pane="search" hidden>${searchPane(sc, st)}</section>
          <section data-pane="library" hidden>${libraryPane(sc, st)}</section>
          <section data-pane="prompts" hidden><h3>${h(t("tab.prompts"))}</h3><p>${h(t("set.promptsIntro"))}</p>${fields(sc.prompts, "prompts", "prompts", st.prompts)}</section>
          <section data-pane="fetch" hidden>${fetchPane(sc, st)}</section>
          <section data-pane="research" hidden><h3>${h(t("tab.research"))}</h3><p>${h(t("set.researchIntro"))}</p>
            <div class="field-grid">${fields(sc.research.filter(f => f.type === "number"), "research", "research", st.research)}</div>
            ${fields(sc.research.filter(f => f.type !== "number"), "research", "research", st.research)}</section>
          <section data-pane="about" hidden>${aboutPane()}</section>
        </div>
      </div>
      <div class="dlg-foot"><span class="muted" title="${h(S.info.config_dir)}">${h(t("set.storedIn", { dir: S.info.config_dir }))}</span>
        <button class="btn ghost" value="cancel" formnovalidate>${h(t("common.cancel"))}</button>
        <button type="button" class="btn primary" id="saveSettings">${h(t("common.save"))}</button></div>
    </form>`;

  const showTab = k => {
    $$(".dlg-tabs button", dlg).forEach(b => b.classList.toggle("on", b.dataset.tab === k));
    $$("[data-pane]", dlg).forEach(p => (p.hidden = p.dataset.pane !== k));
    if (k === "model") { refreshOllama(); refreshPcLink(); }
    if (k === "library") refreshLibrary();
    if (k === "fetch") refreshBrowser();
    if (k === "general") refreshStorage();
    if (k === "about") refreshLog();
  };
  $$(".dlg-tabs button", dlg).forEach(b => (b.onclick = () => showTab(b.dataset.tab)));
  wireGeneral(dlg);
  wireAppearance(dlg);
  wireModel(dlg);
  wireSearch(dlg);
  wireLibrary(dlg);
  wirePrompts(dlg);
  wireFetch(dlg);
  wireAbout(dlg);
  $("#saveSettings").onclick = save;
  showTab(TABS.some(x => x[0] === tab) ? tab : "general");
  if (!dlg.open) dlg.showModal();
}

function collect() {
  const out = structuredClone(S.settings);
  $$("[data-path]", S.dlg).forEach(el => {
    let v = el.dataset.type === "bool" ? el.checked : el.value;
    if (el.dataset.type === "number") v = v === "" ? null : Number(v);
    setPath(out, el.dataset.path, v);
  });
  return out;
}

async function save() {
  const before = S.settings.app.language;
  try {
    S.settings = await api("/api/settings", { method: "POST", body: collect() });
    S.dlg.close();
    toast(t("set.saved"));
    S.onSaved?.(S.settings, before !== S.settings.app.language);
  } catch (e) { toast(t("set.saveFailed", { e: e.message }), 4000); }
}

// general
function generalPane(sc, st) {
  const langs = uiLanguages();
  const sys = langs.find(l => l.code === uiLang())?.native || "English";
  const mode = st.app.ui_mode;
  const other = mode === "desktop" ? "browser" : "desktop";
  return `<h3>${h(t("tab.general"))}</h3><p>${h(t("set.generalIntro"))}</p>
    <div class="field-grid">
      <div class="field"><label>${h(t("gen.language"))}</label><select data-path="app.language">
        <option value="auto">${h(t("gen.languageAuto", { x: sys }))}</option>
        ${langs.map(l => `<option value="${l.code}" ${l.code === st.app.language ? "selected" : ""}>${h(l.native)}</option>`).join("")}</select></div>
      <div class="field"><label>${h(t("gen.answerLang"))}</label><select data-path="app.answer_language">
        <option value="auto" ${st.app.answer_language === "auto" ? "selected" : ""}>${h(t("gen.answerAuto"))}</option>
        <option value="ui" ${st.app.answer_language === "ui" ? "selected" : ""}>${h(t("gen.answerUi"))}</option>
        ${sc.languages.map(l => `<option value="${l.code}" ${l.code === st.app.answer_language ? "selected" : ""}>${h(l.native)} (${h(l.name)})</option>`).join("")}</select>
        <div class="help">${h(t("gen.answerHelp"))}</div></div>
    </div>
    ${android() ? "" : `<h4>${h(t("gen.window"))}</h4>
    <div class="status-card"><span class="dot ok"></span><div class="grow"><b>${h(t("gen." + mode))}</b><div class="muted" style="font-size:12.5px">${h(t("gen.windowHelp"))}</div></div>
      ${S.info.can_restart ? `<button type="button" class="btn sm" id="switchMode" data-mode="${other}">${icon("refresh")}${h(t("gen.switchTo", { x: t("gen." + other) }))}</button>`
        : `<span class="muted" style="font-size:12.5px">${h(t("gen.restartManual"))}</span>`}</div>`}
    <h4>${h(t("gen.updates"))}</h4>
    ${field(sc.app.find(f => f.key === "check_updates"), "app", "app.check_updates", st.app.check_updates)}
    <div class="row" style="margin-bottom:8px"><button type="button" class="btn sm" id="checkUpd">${icon("refresh")}${h(t("gen.checkNow"))}</button>
      <button type="button" class="btn sm" id="checkRepair">${icon("check")}${h(t("repair.check"))}</button><span class="status-line" id="updStatus"></span></div>
    <div id="repairBox" style="margin-bottom:14px"></div>
    <h4>${h(t("gen.storage"))}</h4>
    <div class="list-box" id="storageBox"><div class="list-empty">${h(t("common.loading"))}</div></div>
    <div class="field-grid">${field(sc.app.find(f => f.key === "history_limit"), "app", "app.history_limit", st.app.history_limit)}
      ${android() ? "" : field(sc.app.find(f => f.key === "port"), "app", "app.port", st.app.port)}</div>`;
}

function wireGeneral(dlg) {
  $("#switchMode", dlg)?.addEventListener("click", async e => {
    const m = e.currentTarget.dataset.mode;
    await api("/api/settings", { method: "POST", body: collect() }).catch(() => {});
    await api("/api/app/restart", { method: "POST", body: { mode: m } });
    toast(t("gen.restarting"), 6000);
  });
  $("#checkRepair", dlg).onclick = runRepairCheck;
  $("#checkUpd", dlg).onclick = async () => {
    const el = $("#updStatus");
    el.className = "status-line";
    el.textContent = t("common.checking");
    const u = await api("/api/update/check?force=true").catch(e => ({ error: e.message }));
    if (u.newer) {
      el.className = "status-line ok";
      el.textContent = t("banner.update", { v: u.latest });
      showUpdatePopup(u);
    } else if (u.error) { el.className = "status-line err"; el.textContent = u.error; }
    else { el.className = "status-line ok"; el.textContent = t("gen.upToDate", { v: u.current }); }
  };
}

// check & repair
async function runRepairCheck() {
  const box = $("#repairBox");
  box.innerHTML = `<div class="status-line">${h(t("common.checking"))}</div>`;
  const r = await api("/api/repair/check").catch(e => ({ error: e.message }));
  if (r.error) { box.innerHTML = `<div class="status-line err">${h(r.error)}</div>`; return; }
  const row = (ok, title, detail) => `<div class="list-row"><span class="dot ${ok ? "ok" : "err"}"></span><div class="grow"><div class="lr-t">${h(title)}</div>${detail ? `<div class="lr-s">${h(detail)}</div>` : ""}</div></div>`;
  const app = r.app.checked
    ? row(r.app.ok, t("repair.app"), r.app.ok ? t("repair.appOk", { n: r.app.total }) : t("repair.appBad", { n: r.app.missing.length + r.app.changed.length }))
    : row(true, t("repair.app"), t(r.app.reason === "source" ? "repair.appSource" : "repair.appSkipped"));
  box.innerHTML = `<div class="list-box">${app}
      ${row(r.settings.ok, t("repair.settings"), r.settings.ok ? "" : t("repair.settingsBad"))}
      ${row(r.library.ok, t("repair.library"), r.library.ok ? "" : t("repair.libraryBad"))}
      ${row(r.history.ok, t("repair.history"), r.history.ok ? "" : t("repair.historyBad", { n: r.history.bad_count }))}</div>
    <div class="row" style="margin-top:8px">
      ${r.ok ? `<span class="status-line ok">${h(t("repair.allOk"))}</span>` : `<button type="button" class="btn sm primary" id="doRepair">${icon("refresh")}${h(t("repair.fix"))}</button>`}
      ${r.can_reinstall ? `<button type="button" class="btn sm ghost" id="doReinstall" title="${h(t("repair.reinstallHelp"))}">${icon("download")}${h(t("repair.reinstall", { v: r.version }))}</button>` : ""}
      <span class="status-line" id="repairStatus"></span></div>`;
  const follow = async job => {
    const st = $("#repairStatus");
    const fin = await pollJob(job, j => { st.className = "status-line"; st.textContent = `${j.message || ""} ${j.progress ? Math.round(j.progress * 100) + "%" : ""}`; });
    if (fin.status === "error") { st.className = "status-line err"; st.textContent = fin.error; return; }
    toast(t("repair.done"), 4000);
    runRepairCheck();
  };
  $("#doRepair")?.addEventListener("click", async e => {
    e.currentTarget.disabled = true;
    follow(await api("/api/repair", { method: "POST" }).catch(err => ({ status: "error", error: err.message })));
  });
  $("#doReinstall")?.addEventListener("click", async e => {
    if (!confirm(t("repair.reinstallConfirm"))) return;
    e.currentTarget.disabled = true;
    follow(await api("/api/repair/reinstall", { method: "POST" }).catch(err => ({ status: "error", error: err.message })));
  });
}

async function refreshStorage() {
  const box = $("#storageBox");
  if (!box) return;
  const s = await api("/api/app/storage").catch(() => null);
  if (!s) return;
  box.innerHTML = `
    <div class="list-row"><div class="grow"><div class="lr-t">${h(t("gen.history"))}</div><div class="lr-s">${h(t("gen.historyItems", { n: s.history_count }))} · ${fmtBytes(s.history)}</div></div>
      <button type="button" class="btn sm danger" id="clearHist">${icon("trash")}${h(t("gen.clearHistory"))}</button></div>
    <div class="list-row"><div class="grow"><div class="lr-t">${h(t("gen.dataFolder"))}</div><div class="lr-s">${h(S.info.config_dir)}</div></div>
      <button type="button" class="btn sm" data-open="config">${icon("folder")}${h(t("gen.openFolder"))}</button></div>
    <div class="list-row"><div class="grow"><div class="lr-t">${h(t("gen.cacheFolder"))}</div><div class="lr-s">${h(S.info.local_dir)} · ${fmtBytes(s.library + s.browser + s.logs + s.updates)}</div></div>
      <button type="button" class="btn sm" data-open="local">${icon("folder")}${h(t("gen.openFolder"))}</button></div>`;
  $("#clearHist").onclick = async () => {
    if (!confirm(t("gen.clearConfirm"))) return;
    await api("/api/history", { method: "DELETE" });
    refreshStorage();
    window.dispatchEvent(new CustomEvent("airag:history"));
  };
  $$("[data-open]", box).forEach(b => (b.onclick = () => api("/api/app/open-folder", { method: "POST", body: { target: b.dataset.open } })));
}

// appearance
function appearancePane() {
  const a = getAppearance();
  const custom = !(a.accent in ACCENTS);
  return `<h3>${h(t("tab.appearance"))}</h3><p>${h(t("set.appearanceIntro"))}</p>
    <div class="field"><label>${h(t("app.theme"))}</label><div class="seg" id="themeSeg">
      ${["system", "light", "dark"].map(x => `<button type="button" data-theme-opt="${x}" class="${a.theme === x ? "on" : ""}">${h(t("theme." + x))}</button>`).join("")}</div></div>
    <div class="field"><label>${h(t("app.palette"))}</label><div class="palettes">
      ${Object.entries(PALETTES).map(([k, p]) => `<button type="button" class="pal ${a.palette === k ? "on" : ""}" data-pal="${k}">
        <div class="pal-prev">${[...p.light, ...p.dark].map(c => `<span style="background:${c}"></span>`).join("")}</div>${h(t("pal." + k))}</button>`).join("")}</div></div>
    <div class="field"><label>${h(t("app.accent"))}</label><div class="swatches">
      ${Object.entries(ACCENTS).map(([k, c]) => `<button type="button" class="swatch ${a.accent === k ? "on" : ""}" data-acc="${k}" title="${h(t("acc." + k))}" style="background:${c || "linear-gradient(135deg,#27272a 50%,#e4e4e7 50%)"}"></button>`).join("")}
      <label class="swatch swatch-custom ${custom ? "on" : ""}" title="${h(t("app.accentCustom"))}"><input type="color" id="accCustom" value="${custom ? a.accent : "#2563eb"}"></label>
      <button type="button" class="btn sm ghost" id="appReset">${h(t("app.reset"))}</button></div></div>`;
}

function wireAppearance(dlg) {
  const refresh = () => {
    const a = getAppearance();
    $$("[data-theme-opt]", dlg).forEach(b => b.classList.toggle("on", b.dataset.themeOpt === a.theme));
    $$("[data-pal]", dlg).forEach(b => b.classList.toggle("on", b.dataset.pal === a.palette));
    $$("[data-acc]", dlg).forEach(b => b.classList.toggle("on", b.dataset.acc === a.accent));
    $(".swatch-custom", dlg).classList.toggle("on", !(a.accent in ACCENTS));
  };
  $$("[data-theme-opt]", dlg).forEach(b => (b.onclick = () => { setAppearance({ theme: b.dataset.themeOpt }); refresh(); }));
  $$("[data-pal]", dlg).forEach(b => (b.onclick = () => { setAppearance({ palette: b.dataset.pal }); refresh(); }));
  $$("[data-acc]", dlg).forEach(b => (b.onclick = () => { setAppearance({ accent: b.dataset.acc }); refresh(); }));
  $("#accCustom", dlg).oninput = e => { setAppearance({ accent: e.target.value }); refresh(); };
  $("#appReset", dlg).onclick = () => { setAppearance({ theme: "system", palette: "zinc", accent: "graphite" }); refresh(); };
}

// AI model
function modelPane(sc, st) {
  const hide = android() ? DESKTOP_ONLY_PROVIDERS : PHONE_ONLY_PROVIDERS;
  const provOpts = sc.llm.providers.filter(p => !hide.includes(p.name) || p.name === st.llm.provider).map(p => `<option value="${p.name}" ${p.name === st.llm.provider ? "selected" : ""}>${h(p.label)}</option>`).join("");
  return `<h3>${h(t("tab.model"))}</h3><p>${h(t("set.modelIntro"))}</p>
    <div class="field"><label>${h(t("model.provider"))}</label><select data-path="llm.provider" id="provSel">${provOpts}</select></div>
    <div id="ollamaPanel" hidden></div>
    ${sc.llm.providers.map(p => `<div class="sub-box" data-prov-box="${p.name}">${fields(p.fields, "p", `llm.providers.${p.name}`, st.llm.providers[p.name])}</div>`).join("")}
    ${fields(sc.llm.fields, "llm", "llm", st.llm)}
    <div class="row"><button type="button" class="btn sm" id="loadModels">${icon("list")}${h(t("model.load"))}</button>
      <button type="button" class="btn sm" id="testLlm">${icon("check")}${h(t("model.test"))}</button><span class="status-line" id="llmStatus"></span></div>
    ${android() ? "" : `<h4>${h(t("pclink.title"))}</h4><p class="muted" style="font-size:13px">${h(t("pclink.intro"))}</p><div id="pcLinkPanel"></div>`}`;
}

function provPayload() {
  const c = collect(), p = c.llm.provider;
  return { provider: p, config: c.llm.providers[p], temperature: c.llm.temperature };
}

function wireModel(dlg) {
  const sync = () => {
    const p = $("#provSel").value;
    $$("[data-prov-box]", dlg).forEach(b => (b.hidden = b.dataset.provBox !== p));
    $("#ollamaPanel").hidden = p !== "ollama";
    $("#llmStatus").textContent = "";
    if (p === "ollama") refreshOllama();
  };
  $("#provSel").onchange = sync;
  sync();
  const status = (txt, cls = "") => { const el = $("#llmStatus"); el.textContent = txt; el.className = "status-line " + cls; };
  $("#loadModels").onclick = async () => {
    status(t("model.loading"));
    try {
      const { models } = await api("/api/models", { method: "POST", body: provPayload() });
      const p = $("#provSel").value, dl = $(`[data-prov-box="${p}"] datalist`, dlg);
      if (dl) dl.innerHTML = models.map(m => `<option value="${h(m)}">`).join("");
      status(models.length ? t("model.loaded", { n: models.length }) : t("model.none"), models.length ? "ok" : "err");
    } catch (e) { status(e.message, "err"); }
  };
  $("#testLlm").onclick = async () => {
    status(t("common.checking"));
    try {
      const r = await api("/api/test-llm", { method: "POST", body: provPayload() });
      status(t("model.connected", { r: r.reply.slice(0, 40) }), "ok");
    } catch (e) { status(e.message, "err"); }
  };
}

let recommended = null;
async function refreshOllama() {
  const panel = $("#ollamaPanel");
  if (!panel || panel.hidden) return;
  const url = $('[data-path="llm.providers.ollama.base_url"]')?.value || "";
  const q = url ? `?url=${encodeURIComponent(url)}` : "";
  const [st, rec] = await Promise.all([api("/api/ollama/status" + q).catch(e => ({ error: e.message, models: [] })),
    recommended ? Promise.resolve(recommended) : api("/api/ollama/recommended").catch(() => ({ models: [] }))]);
  recommended = rec;
  const modelInput = $('[data-path="llm.providers.ollama.model"]');
  const current = modelInput?.value;
  const installed = new Set((st.models || []).map(m => m.name));
  const dot = st.running ? "ok" : st.installed ? "warn" : "err";
  const msg = st.running ? t("ollama.running", { v: st.version }) : st.installed ? t("ollama.stopped") : t("ollama.notInstalled");
  panel.innerHTML = `
    <div class="status-card"><span class="dot ${dot}"></span><div class="grow"><b>Ollama</b> · ${h(msg)}
      ${rec.ram_gb ? `<div class="muted" style="font-size:12.5px">${h(t("ollama.ram", { n: rec.ram_gb }))}</div>` : ""}</div>
      ${!st.running && st.installed ? `<button type="button" class="btn sm primary" id="olStart">${icon("power")}${h(t("ollama.start"))}</button>` : ""}
      ${!st.installed ? `<a class="btn sm primary" href="${h(st.download_url || "https://ollama.com/download")}" target="_blank" rel="noopener">${icon("download")}${h(t("ollama.download"))}</a>` : ""}
      <button type="button" class="btn sm ghost" id="olRefresh">${icon("refresh")}</button></div>
    ${st.running ? `
    <h4>${h(t("ollama.installed"))}</h4>
    <div class="list-box">${(st.models || []).map(m => `<div class="list-row"><div class="grow"><div class="lr-t">${h(m.name)}</div>
        <div class="lr-s">${h([m.parameters, m.quantization, fmtBytes(m.size)].filter(Boolean).join(" · "))}</div></div>
        ${m.name === current || m.name === current + ":latest" ? `<span class="tag strong">${h(t("ollama.inUse"))}</span>` : `<button type="button" class="btn sm" data-use="${h(m.name)}">${h(t("ollama.use"))}</button>`}
        <button type="button" class="icon-btn" data-del="${h(m.name)}" title="${h(t("ollama.delete"))}">${icon("trash")}</button></div>`).join("")
      || `<div class="list-empty">${h(t("ollama.noModels"))}</div>`}</div>
    <h4>${h(t("ollama.get"))}</h4>
    <div class="list-box">${rec.models.filter(m => !installed.has(m.name)).map(m => `<div class="list-row" data-pull-row="${h(m.name)}"><div class="grow">
        <div class="lr-t">${h(m.name)} ${m.recommended ? `<span class="tag strong">${h(t("ollama.recommended"))}</span>` : ""} ${!m.fits ? `<span class="tag" style="color:var(--bad)">${h(t("ollama.tooBig"))}</span>` : ""}</div>
        <div class="lr-s">~${m.size_gb} GB · ${h(has("om." + m.name) ? t("om." + m.name) : m.note)}</div><div class="pull-prog"></div></div>
        <button type="button" class="btn sm" data-pull="${h(m.name)}">${icon("download")}${h(t("ollama.pull"))}</button></div>`).join("")}
      <div class="list-row"><input class="input" id="olCustom" placeholder="${h(t("ollama.custom"))}" spellcheck="false" style="height:34px">
        <button type="button" class="btn sm" id="olCustomBtn">${icon("download")}${h(t("ollama.pull"))}</button></div></div>` : ""}`;
  $("#olRefresh").onclick = refreshOllama;
  $("#olStart")?.addEventListener("click", async e => {
    e.currentTarget.innerHTML = `<span class="spinner sm"></span>`;
    const r = await api("/api/ollama/start" + q, { method: "POST" }).catch(err => ({ error: err.message }));
    if (r.error) toast(r.error, 4000);
    refreshOllama();
  });
  $$("[data-use]", panel).forEach(b => (b.onclick = () => { if (modelInput) modelInput.value = b.dataset.use; refreshOllama(); }));
  $$("[data-del]", panel).forEach(b => (b.onclick = async () => {
    if (!confirm(t("ollama.deleteConfirm", { m: b.dataset.del }))) return;
    await api("/api/ollama/delete", { method: "POST", body: { model: b.dataset.del, url: url || null } }).catch(e => toast(e.message));
    refreshOllama();
  }));
  const pull = async name => {
    if (!name) return;
    const row = $(`[data-pull-row="${CSS.escape(name)}"]`, panel);
    try {
      const job = await api("/api/ollama/pull", { method: "POST", body: { model: name, url: url || null } });
      const fin = await pollJob(job, j => {
        const box = row?.querySelector(".pull-prog");
        if (box) box.innerHTML = progressBar(j.progress) + `<div class="lr-s">${h(j.detail || "")}${j.extra?.total ? ` · ${fmtBytes(j.extra.completed)} / ${fmtBytes(j.extra.total)}` : ""}</div>`;
      }, 1000);
      if (fin.status === "error") toast(fin.error, 5000);
      else if (modelInput && !modelInput.value) modelInput.value = name;
    } catch (e) { toast(e.message, 4000); }
    refreshOllama();
  };
  $$("[data-pull]", panel).forEach(b => (b.onclick = () => { b.disabled = true; pull(b.dataset.pull); }));
  $("#olCustomBtn")?.addEventListener("click", () => pull($("#olCustom").value.trim()));
}

// search
function searchPane(sc, st) {
  const backOpts = sc.search.backends.map(b => `<option value="${b.name}" ${b.name === st.search.backend ? "selected" : ""}>${h(b.label)}</option>`).join("");
  const imgOpts = `<option value="none">${h(t("search.none"))}</option>` + sc.search.backends.filter(b => b.supports_images)
    .map(b => `<option value="${b.name}" ${b.name === st.search.image_backend ? "selected" : ""}>${h(b.label)}</option>`).join("");
  return `<h3>${h(t("tab.search"))}</h3><p>${h(t("set.searchIntro"))}</p>
    <div class="field"><label>${h(t("search.web"))}</label><select data-path="search.backend" id="backSel">${backOpts}</select></div>
    <div class="field"><label>${h(t("search.images"))}</label><select data-path="search.image_backend" id="imgSel">${imgOpts}</select></div>
    ${sc.search.backends.filter(b => b.fields.length).map(b => `<div class="sub-box" data-backend-box="${b.name}"><div class="side-title">${h(b.label)}</div>${fields(b.fields, "p", `search.backends.${b.name}`, st.search.backends[b.name])}</div>`).join("")}
    <div class="field-grid">${fields(sc.search.fields, "search", "search", st.search)}</div>`;
}

function wireSearch(dlg) {
  const sync = () => {
    const used = new Set([$("#backSel").value, $("#imgSel").value]);
    $$("[data-backend-box]", dlg).forEach(b => (b.hidden = !used.has(b.dataset.backendBox)));
  };
  $("#backSel").onchange = $("#imgSel").onchange = sync;
  sync();
}

// library
function libraryPane(sc, st) {
  return `<h3>${h(t("lib.title"))}</h3><p>${h(t("lib.intro"))}</p>
    <h4>${h(t("my.title"))}</h4><p class="muted" style="font-size:13px">${h(t("my.intro"))}</p>
    <div class="status-card" id="myLibCard"><div class="grow">${h(t("common.loading"))}</div></div>
    <div class="row" style="margin:8px 0 18px"><span class="muted" style="font-size:13px">${h(t("my.addFiles"))}</span>
      <button type="button" class="btn sm" data-import="copy">${icon("copy")}${h(t("my.copy"))}</button>
      <button type="button" class="btn sm" data-import="move">${icon("upload")}${h(t("my.move"))}</button></div>
    <h4>${h(t("my.other"))}</h4>
    <div class="list-box" id="libFolders"><div class="list-empty">${h(t("common.loading"))}</div></div>
    <div class="row" style="margin-bottom:14px"><button type="button" class="btn sm primary" id="libPick">${icon("folder")}${h(t("lib.add"))}</button>
      <input class="input" id="libPath" placeholder="${h(t("lib.addPath"))}" style="flex:1;min-width:200px;height:34px" spellcheck="false">
      <button type="button" class="btn sm" id="libAddPath">${h(t("common.add"))}</button></div>
    <div class="status-card" id="libStats"></div>
    ${fields(sc.library, "library", "library", st.library)}`;
}

async function refreshMyLibrary() {
  const card = $("#myLibCard");
  if (!card) return;
  const m = await api("/api/mylibrary").catch(() => null);
  if (!m) return;
  card.innerHTML = `${icon("book")}<div class="grow"><div class="lr-t mono" style="word-break:break-all">${h(m.path)}</div>
      <div class="muted" style="font-size:12.5px">${m.exists ? h(t("my.files", { n: m.files })) : h(t("my.notYet"))}</div></div>
    <button type="button" class="btn sm" id="myChange">${icon("folder")}${h(t("my.change"))}</button>
    ${m.custom ? `<button type="button" class="btn sm ghost" id="myDefault" title="${h(m.default)}">${h(t("my.default"))}</button>` : ""}
    ${m.exists && !android() ? `<button type="button" class="btn sm ghost" id="myOpen">${icon("ext")}${h(t("gen.openFolder"))}</button>` : ""}`;
  const set = async path => {
    const r = await api("/api/mylibrary/folder", { method: "POST", body: { path } }).catch(e => { toast(e.message, 5000); return null; });
    if (r) refreshMyLibrary();
  };
  $("#myChange").onclick = () => set(null);
  $("#myDefault")?.addEventListener("click", () => set(""));
  $("#myOpen")?.addEventListener("click", () => api("/api/mylibrary/open", { method: "POST" }).catch(e => toast(e.message)));
}

async function refreshLibrary() {
  refreshMyLibrary();
  const box = $("#libFolders");
  if (!box) return;
  const s = await api("/api/library/status").catch(() => null);
  if (!s) return;
  box.innerHTML = s.folders.map(f => `<div class="list-row">${icon("folder")}<div class="grow"><div class="lr-t">${h(f.path)}</div>
      ${f.exists ? "" : `<div class="lr-s" style="color:var(--bad)">${h(t("lib.missing"))}</div>`}</div>
      <button type="button" class="icon-btn" data-rm="${h(f.path)}" title="${h(t("lib.remove"))}">${icon("trash")}</button></div>`).join("")
    || `<div class="list-empty">${h(t("lib.noFolders"))}</div>`;
  $$("[data-rm]", box).forEach(b => (b.onclick = async () => { await api("/api/library/folders/remove", { method: "POST", body: { path: b.dataset.rm } }); syncFolders(); }));
  const st = s.stats;
  $("#libStats").innerHTML = `<span class="dot ${st.files ? "ok" : ""}"></span><div class="grow">
      <b>${h(t("lib.stats", { files: st.files, size: fmtBytes(st.bytes) }))}</b>
      <div class="muted" style="font-size:12.5px">${st.last_sync ? h(t("lib.lastSync", { t: fmtAgo(new Date(st.last_sync * 1000).toISOString()) })) : h(t("lib.never"))}${st.errors ? ` · ${h(t("lib.errors", { n: st.errors }))}` : ""}</div>
      <div id="libProg"></div></div>
    <button type="button" class="btn sm" id="libSync" ${s.folders.length ? "" : "disabled"}>${icon("refresh")}${h(t("lib.index"))}</button>
    <button type="button" class="btn sm ghost" id="libClear">${h(t("lib.rebuild"))}</button>`;
  $("#libSync").onclick = () => runSync();
  $("#libClear").onclick = async () => { await api("/api/library/clear", { method: "POST" }); runSync(); };
  if (s.job) runSync(s.job);
}

async function runSync(existing) {
  const job = existing || await api("/api/library/sync", { method: "POST" }).catch(e => { toast(e.message); return null; });
  if (!job) return;
  const fin = await pollJob(job, j => {
    const el = $("#libProg");
    if (el) el.innerHTML = progressBar(j.progress) + `<div class="lr-s">${h(j.message || t("lib.indexing"))} ${h(j.detail || "")}</div>`;
  });
  if (fin.status === "error") toast(fin.error, 5000);
  refreshLibrary();
}

async function syncFolders() {
  const st = await api("/api/settings").catch(() => null);
  if (st) S.settings.library.folders = st.library.folders;
  await refreshLibrary();
  window.dispatchEvent(new CustomEvent("airag:library"));
}

function wireLibrary(dlg) {
  const add = async path => {
    if (!path) return;
    try { await api("/api/library/folders/add", { method: "POST", body: { path } }); await syncFolders(); runSync(); }
    catch (e) { toast(e.message, 4000); }
  };
  $("#libPick", dlg).onclick = async e => {
    const b = e.currentTarget;
    b.disabled = true;
    const r = await api("/api/library/pick-folder", { method: "POST" }).catch(() => ({}));
    b.disabled = false;
    if (r.path) add(r.path);
  };
  $("#libAddPath", dlg).onclick = () => { add($("#libPath").value.trim()); $("#libPath").value = ""; };
  $$("[data-import]", dlg).forEach(b => (b.onclick = async () => {
    const move = b.dataset.import === "move";
    if (move && !confirm(t("my.moveConfirm"))) return;
    b.disabled = true;
    const r = await api("/api/mylibrary/import", { method: "POST", body: { move } }).catch(e => { toast(e.message, 5000); return null; });
    b.disabled = false;
    if (r?.added?.length) {
      toast(t(move && r.moved < r.added.length ? "my.addedCopied" : "my.added", { n: r.added.length }), 5000);
      refreshMyLibrary();
      runSync();
    }
  }));
}

// prompts
function wirePrompts(dlg) {
  $$("[data-prompt-load]", dlg).forEach(b => (b.onclick = () => { const ta = $("#" + b.dataset.promptLoad); if (!ta.value.trim()) ta.value = S.schema.default_article_prompt; }));
  $$("[data-prompt-reset]", dlg).forEach(b => (b.onclick = () => { $("#" + b.dataset.promptReset).value = ""; }));
}

// page reading
// PC link: share this PC's Ollama with the phone app
async function refreshPcLink() {
  const box = $("#pcLinkPanel");
  if (!box) return;
  const st = await api("/api/pclink").catch(e => ({ error: e.message }));
  const on = st.running;
  const addr = on ? (st.addresses || []).map(ip => `${ip}:${st.port}`) : [];
  box.innerHTML = `
    <div class="status-card"><span class="dot ${on ? "ok" : ""}"></span><div class="grow"><b>${h(t(on ? "pclink.on" : "pclink.off"))}</b>
      <div class="muted" style="font-size:12.5px">${h(st.error || (on ? t("pclink.onHelp") : t("pclink.offHelp")))}</div></div>
      <button type="button" class="btn sm ${on ? "ghost" : "primary"}" id="pclToggle">${icon(on ? "x" : "power")}${h(t(on ? "pclink.stop" : "pclink.start"))}</button></div>
    ${on ? `<div class="list-box">
      <div class="list-row"><div class="grow"><div class="lr-t">${h(t("pclink.address"))}</div>
        <div class="lr-s mono">${addr.length ? addr.map(a => h(a)).join("<br>") : h(t("pclink.noNetwork"))}</div></div>
        ${addr.length ? `<button type="button" class="btn sm" data-copy="${h(addr[0])}">${icon("copy")}${h(t("pclink.copy"))}</button>` : ""}</div>
      <div class="list-row"><div class="grow"><div class="lr-t">${h(t("pclink.code"))}</div><div class="lr-s mono" style="font-size:15px;letter-spacing:.06em">${h(st.code)}</div></div>
        <button type="button" class="btn sm" data-copy="${h(st.code)}">${icon("copy")}${h(t("pclink.copy"))}</button>
        <button type="button" class="btn sm ghost" id="pclNewCode" title="${h(t("pclink.newCodeHelp"))}">${icon("refresh")}${h(t("pclink.newCode"))}</button></div>
    </div>
    <div class="help">${h(t("pclink.steps"))}</div>
    <div class="field"><label class="switch"><input type="checkbox" id="pclInternet" ${st.allow_internet ? "checked" : ""}> ${h(t("pclink.internet"))}</label>
      <div class="help">${h(t("pclink.internetHelp"))}</div></div>` : ""}`;
  const set = async body => {
    const r = await api("/api/pclink", { method: "POST", body }).catch(e => { toast(e.message, 4000); return null; });
    if (r?.error) toast(r.error, 4000);
    refreshPcLink();
  };
  $("#pclToggle").onclick = e => { e.currentTarget.disabled = true; set({ enabled: !on }); };
  $("#pclNewCode")?.addEventListener("click", () => { if (confirm(t("pclink.newCodeConfirm"))) set({ new_code: true }); });
  $("#pclInternet")?.addEventListener("change", e => set({ allow_internet: e.target.checked }));
  $$("[data-copy]", box).forEach(b => (b.onclick = async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy); toast(t("pclink.copied")); } catch { toast(b.dataset.copy, 5000); }
  }));
}

function fetchPane(sc, st) {
  if (android()) return `<h3>${h(t("tab.fetch"))}</h3><p>${h(t("set.fetchIntro"))}</p>${fields(sc.fetch.filter(f => f.key !== "fetcher"), "fetch", "fetch", st.fetch)}`;
  return `<h3>${h(t("tab.fetch"))}</h3><p>${h(t("set.fetchIntro"))}</p>
    <div class="status-card" id="browserCard"></div>
    ${fields(sc.fetch, "fetch", "fetch", st.fetch)}`;
}

async function refreshBrowser(job) {
  const card = $("#browserCard");
  if (android()) return;
  if (!card) return;
  const s = await api("/api/browser/status").catch(() => null);
  if (!s) return;
  card.innerHTML = `<span class="dot ${s.ready ? "ok" : ""}"></span><div class="grow"><b>${h(t("fetch.browser"))}</b>
      <div class="muted" style="font-size:12.5px">${s.ready ? h(t("fetch.browserReady", { size: fmtBytes(s.size) })) : h(t("fetch.browserMissing"))}</div><div id="brProg"></div></div>
    ${s.ready ? `<button type="button" class="btn sm ghost" id="brRemove">${icon("trash")}${h(t("fetch.uninstall"))}</button>`
      : `<button type="button" class="btn sm primary" id="brInstall">${icon("download")}${h(t("fetch.install"))}</button>`}`;
  $("#brRemove")?.addEventListener("click", async () => { await api("/api/browser/uninstall", { method: "POST" }); refreshBrowser(); });
  $("#brInstall")?.addEventListener("click", async e => {
    e.currentTarget.disabled = true;
    const j = await api("/api/browser/install", { method: "POST" }).catch(err => { toast(err.message); return null; });
    if (!j) return;
    const fin = await pollJob(j, x => { const el = $("#brProg"); if (el) el.innerHTML = progressBar(x.progress) + `<div class="lr-s">${h(x.message || "")} ${h(x.detail || "")}</div>`; });
    if (fin.status === "error") toast(fin.error, 6000);
    refreshBrowser();
  });
}

function wireFetch() { /* buttons are wired in refreshBrowser */ }

// about
function aboutPane() {
  const i = S.info;
  return `<h3>AIRAG ${h(i.version)}</h3><p>${h(t("app.tagline"))}</p>
    <div class="list-box">
      <div class="list-row"><div class="grow"><div class="lr-t">${h(t("about.version"))}</div><div class="lr-s">${h(i.version)}${i.frozen ? "" : " (source)"}${i.portable ? " · portable" : ""}</div></div></div>
      ${i.port ? `<div class="list-row"><div class="grow"><div class="lr-t">${h(t("about.port"))}</div><div class="lr-s mono">${h(i.port)}</div></div></div>` : ""}
      <div class="list-row"><div class="grow"><div class="lr-t">${h(t("about.license"))}</div><div class="lr-s">MIT</div></div></div>
      <div class="list-row"><div class="grow"><div class="lr-t">GitHub</div><div class="lr-s">github.com/${h(i.repo)}</div></div>
        <a class="btn sm" href="https://github.com/${h(i.repo)}" target="_blank" rel="noopener">${icon("ext")}${h(t("about.open"))}</a></div>
      ${android() ? "" : `<div class="list-row"><div class="grow"><div class="lr-t">${h(t("about.logs"))}</div><div class="lr-s">${h(i.local_dir)}</div></div>
        <button type="button" class="btn sm" onclick="fetch('/api/app/open-folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:'logs'})})">${icon("folder")}${h(t("gen.openFolder"))}</button></div>`}
    </div>
    <h4>${h(t("log.title"))}</h4>
    <div class="row" style="margin-bottom:8px"><select id="logLevel" style="width:auto">
        <option value="">${h(t("log.all"))}</option><option value="WARNING">${h(t("log.warnings"))}</option><option value="ERROR">${h(t("log.errors"))}</option></select>
      <button type="button" class="btn sm" id="logRefresh">${icon("refresh")}${h(t("log.refresh"))}</button>
      <button type="button" class="btn sm ghost" id="logCopy">${icon("copy")}${h(t("pclink.copy"))}</button></div>
    <pre class="log-view" id="logView">${h(t("common.loading"))}</pre>
    <div class="help">${h(t("log.help"))}</div>
    <p class="muted" style="font-size:13px">${h(t("banner.disclaimer"))}</p>`;
}

async function refreshLog() {
  const view = $("#logView");
  if (!view) return;
  const r = await api("/api/app/log?lines=400&level=" + ($("#logLevel")?.value || "")).catch(e => ({ lines: [e.message] }));
  view.textContent = r.lines.length ? r.lines.join("\n") : t("log.empty");
  view.scrollTop = view.scrollHeight;
}

function wireAbout(dlg) {
  $("#logRefresh", dlg).onclick = refreshLog;
  $("#logLevel", dlg).onchange = refreshLog;
  $("#logCopy", dlg).onclick = async () => {
    try { await navigator.clipboard.writeText($("#logView").textContent); toast(t("pclink.copied")); } catch { toast(t("log.copyFailed")); }
  };
}
