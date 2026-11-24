// Settings dialog. Generic fields are rendered from the server's schema, so new
// providers/backends/options show up automatically; a few tabs have custom panels
// (Ollama models, library folders, headless browser, appearance, updates).
import { taskModelsPane, taskModelsValue, wireTaskModels, addLoadedModels } from "./taskmodels.js";
import { $, $$, h, icon, api, toast, pollJob, progressBar, fmtBytes, fmtAgo } from "./util.js";
import { t, has, uiLang, uiLanguages } from "./i18n.js";
import { PALETTES, ACCENTS, UI_FONTS, ARTICLE_FONTS, TEXT_SIZES, getAppearance, setAppearance } from "./theme.js";
import { showUpdatePopup } from "./banners.js";
import { SOUNDS, play, soundUrl, onPhone, mediaVolume, setMediaVolume, setAudio } from "./sound.js";
import { ttsAvailable, loadVoices, speak as ttsSpeak, stop as ttsStop, setSpeech } from "./tts.js";

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

// dialog: 7 tabs, each made of titled sections (the older, smaller tabs). Old tab names still work as links:
// openSettings("model") opens the AI tab at its AI model section.
const TABS = [
  ["general", "home", ["general", "defaults", "about"]],
  ["look", "palette", ["appearance"]],
  ["ai", "cpu", ["model", "taskmodels", "usage", "prompts"]],
  ["searching", "globe", ["search", "research"]],
  ["storage", "folder", ["library"]],
  ["tools", "tool", ["tools"]],
  ["system", "cpu2", ["system"]],
];
const TAB_OF = Object.fromEntries(TABS.flatMap(([k, , subs]) => [[k, k], ...subs.map(x => [x, k])]));
const REFRESH = {
  model: () => { refreshOllama(); refreshPcLink(); },
  library: () => { refreshLibrary(); import("./offline.js").then(m => m.refreshOffline()); },
  research: () => refreshBrowser(),
  usage: () => refreshUsage(),
  system: () => { refreshSystem(); refreshStorage(); refreshLog(); },
};
const subTitle = x => t("tab." + x);

const SUBPANE = {
  general: (sc, st) => generalPane(sc, st),
  defaults: (sc, st) => defaultsPane(sc, st),
  about: () => aboutPane(),
  appearance: () => appearancePane() + textPane() + audioPane(S.settings.audio) + readAloudPane(S.settings.speech),
  model: (sc, st) => modelPane(sc, st),
  taskmodels: (sc, st) => taskModelsPane(sc, st),
  usage: (sc, st) => usagePane(sc, st),
  prompts: (sc, st) => `<h3>${h(t("tab.prompts"))}</h3><p>${h(t("set.promptsIntro"))}</p>${fields(sc.prompts, "prompts", "prompts", st.prompts)}`,
  search: (sc, st) => searchPane(sc, st),
  research: (sc, st) => `<h3>${h(t("tab.research"))}</h3><p>${h(t("set.researchIntro"))}</p>
            <div class="field-grid">${fields(sc.research.filter(f => f.type === "number"), "research", "research", st.research)}</div>
            ${fields(sc.research.filter(f => f.type !== "number"), "research", "research", st.research)}
            ${fetchPane(sc, st)}`,
  library: (sc, st) => libraryPane(sc, st),
  tools: (sc, st) => agentToolsPane() + buttonsPane(sc, st),
  system: (sc, st) => systemPane(sc, st),
};

// "Search settings…": every label, heading and help text, across all tabs; a result opens its tab and
// highlights the setting for a moment
function wireSettingsSearch(dlg, showTab) {
  const box = $("#setSearch", dlg), out = $("#setResults", dlg);
  const norm = x => (x || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const index = () => {
    const items = [];
    $$("[data-sub]", dlg).forEach(sec => {
      const sub = sec.dataset.sub, tab = TAB_OF[sub];
      let heading = "";
      $$("h3, h4, .field > label, label.check, .check > span, .field .help, .help", sec).forEach(el => {
        if (/^H[34]$/.test(el.tagName)) heading = el.textContent.trim();
        const text = el.textContent.replace(/\s+/g, " ").trim();
        if (!text || text.length > 400) return;
        const target = el.closest(".field, label.check, .check, h3, h4") || el;
        if (items.some(x => x.target === target)) return;
        const label = (target.querySelector?.(":scope > label, :scope > span") || target).textContent.replace(/\s+/g, " ").trim().slice(0, 90);
        items.push({ tab, sub, target, label, where: [t("tab." + tab), heading].filter(Boolean).join(" › "), text: norm(text) });
      });
    });
    return items;
  };
  let items = null;
  box.oninput = () => {
    const q = norm(box.value.trim());
    if (!q) { out.hidden = true; $$("[data-pane]", dlg).forEach(p => (p.hidden = !$$(".dlg-tabs button.on", dlg).some(b => b.dataset.tab === p.dataset.pane))); return; }
    items ||= index();
    const words = q.split(/\s+/);
    const hits = items.filter(x => words.every(w => x.text.includes(w) || norm(x.where).includes(w))).slice(0, 30);
    $$("[data-pane]", dlg).forEach(p => (p.hidden = true));
    out.hidden = false;
    out.innerHTML = `<p class="muted">${h(t(hits.length === 1 ? "set.searchOne" : "set.searchMany", { n: hits.length, q: box.value.trim() }))}</p>`
      + hits.map((x, i) => `<button type="button" class="set-hit" data-hit="${i}"><b>${h(x.label)}</b><small>${h(x.where)}</small></button>`).join("");
    $$("[data-hit]", out).forEach(b => (b.onclick = () => {
      const x = hits[+b.dataset.hit];
      box.value = "";
      showTab(x.sub, x.sub);
      x.target.scrollIntoView({ block: "center" });
      x.target.classList.add("set-flash");
      setTimeout(() => x.target.classList.remove("set-flash"), 1800);
    }));
  };
  box.onkeydown = e => {
    if (e.key === "Enter") { e.preventDefault(); $(".set-hit", out)?.click(); }
    if (e.key === "Escape" && box.value) { e.preventDefault(); e.stopPropagation(); box.value = ""; box.oninput(); }
  };
}

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
      <div class="dlg-head"><h2>${h(t("set.title"))}</h2>
        <label class="set-search"><span class="visually-hidden">${h(t("set.search"))}</span>${icon("search")}<input type="search" id="setSearch" autocomplete="off" placeholder="${h(t("set.searchPh"))}"></label>
        <button class="icon-btn" value="cancel" formnovalidate aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
      <div class="dlg-main">
        <nav class="dlg-tabs" aria-label="${h(t("set.title"))}">${TABS.map(([k, ic]) => `<button type="button" data-tab="${k}" title="${h(t(`tab.${k}.tip`))}">${icon(ic)}<span class="tab-long">${h(t("tab." + k))}</span><span class="tab-short">${h(t("tab." + k + ".short"))}</span></button>`).join("")}</nav>
        <div class="dlg-body set-body">
          ${TABS.map(([k, , subs]) => `<div data-pane="${k}" hidden>
            ${subs.length > 1 ? `<nav class="set-jump" aria-label="${h(t("set.onThisTab"))}"><span>${h(t("set.onThisTab"))}</span>${subs.map(x => `<button type="button" data-jump="${x}">${h(subTitle(x))}</button>`).join("")}</nav>` : ""}
            ${subs.map(x => `<section data-sub="${x}">${SUBPANE[x](sc, st)}</section>`).join("")}</div>`).join("")}
          <div class="set-results" id="setResults" hidden></div>
        </div>
      </div>
      <div class="dlg-foot"><span class="muted" title="${h(S.info.config_dir)}">${h(t("set.storedIn", { dir: S.info.config_dir }))}</span>
        <button class="btn ghost" value="cancel" formnovalidate>${h(t("common.cancel"))}</button>
        <button type="button" class="btn primary" id="saveSettings">${h(t("common.save"))}</button></div>
    </form>`;

  const showTab = (k, sub = null) => {
    const tab = TAB_OF[k] || "general";
    $$(".dlg-tabs button", dlg).forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
    $$("[data-pane]", dlg).forEach(p => (p.hidden = p.dataset.pane !== tab));
    $("#setResults").hidden = true;
    TABS.find(x => x[0] === tab)[2].forEach(x => REFRESH[x]?.());
    const target = sub || (k !== tab ? k : null);
    const body = $(".set-body", dlg);
    if (target) $(`[data-sub="${target}"]`, dlg)?.scrollIntoView({ block: "start" });
    else body.scrollTop = 0;
  };
  S.showTab = showTab;
  $$(".dlg-tabs button", dlg).forEach(b => (b.onclick = () => showTab(b.dataset.tab)));
  $$("[data-jump]", dlg).forEach(b => (b.onclick = () => showTab(b.dataset.jump, b.dataset.jump)));
  wireSettingsSearch(dlg, showTab);
  wireGeneral(dlg);
  wireTaskModels(dlg);
  wireAppearance(dlg);
  wireAudio(dlg);
  wireAgentTools(dlg);
  wireReadAloud(dlg);
  wireModel(dlg);
  wireSearch(dlg);
  wireLibrary(dlg);
  wirePrompts(dlg);
  wireSystem(dlg);
  wireUsage(dlg);
  $("#saveSettings").onclick = save;
  const touch = matchMedia("(pointer: coarse)").matches || matchMedia("(hover: none)").matches || navigator.maxTouchPoints > 0;
  if (touch) $(`.dlg-tabs [data-tab="${TAB_OF[tab] || "general"}"]`, dlg)?.setAttribute("autofocus", "");   // not the search box
  if (!dlg.open) dlg.showModal();
  showTab(TAB_OF[tab] ? tab : "general");      // after opening, so a section link can scroll to it
  // touch screens: don't start in the search box (it would pop up the keyboard); tap it to search
  if (touch && document.activeElement === $("#setSearch", dlg)) $(".dlg-tabs button.on", dlg)?.focus({ preventScroll: true });
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
    const out = collect();
    await saveAudio(out);
    if (S.wikis) out.search.wikis = S.wikis;
    if (taskModelsValue()) out.llm.task_models = taskModelsValue();
    S.settings = await api("/api/settings", { method: "POST", body: out });
    const later = S.settings._applies_later;
    delete S.settings._applies_later;
    S.saved = true;
    setAudio(S.settings.audio);
    S.dlg.close();
    toast(t(later ? "set.savedLater" : "set.saved"), later ? 6000 : 2500);
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
    <div class="field-grid">${field(sc.app.find(f => f.key === "history_limit"), "app", "app.history_limit", st.app.history_limit)}</div>`;
}

function wireGeneral(dlg) {
  $("#switchMode", dlg)?.addEventListener("click", async e => {
    const m = e.currentTarget.dataset.mode;
    await api("/api/settings", { method: "POST", body: collect() }).catch(() => {});
    await api("/api/app/restart", { method: "POST", body: { mode: m } });
    toast(t("gen.restarting"), 6000);
  });
}

// system: this device, updates, storage, maintenance, logs
function systemPane(sc, st) {
  return `<h3>${h(t("tab.system"))}</h3><p>${h(t("sys.intro"))}</p>
    <h4>${h(t("sys.device"))}</h4>
    <div class="list-box" id="sysBox"><div class="list-empty">${h(t("common.loading"))}</div></div>
    <h4>${h(t("gen.updates"))}</h4>
    ${field(sc.app.find(f => f.key === "check_updates"), "app", "app.check_updates", st.app.check_updates)}
    <div class="row" style="margin-bottom:8px"><button type="button" class="btn sm" id="checkUpd">${icon("refresh")}${h(t("gen.checkNow"))}</button>
      <button type="button" class="btn sm" id="checkRepair">${icon("check")}${h(t("repair.check"))}</button><span class="status-line" id="updStatus"></span></div>
    <div id="repairBox" style="margin-bottom:14px"></div>
    <h4>${h(t("gen.storage"))}</h4>
    <div class="list-box" id="storageBox"><div class="list-empty">${h(t("common.loading"))}</div></div>
    <h4>${h(t("res.title"))}</h4>
    ${field(sc.app.find(f => f.key === "resource_graphs"), "app", "app.resource_graphs", st.app.resource_graphs)}
    ${field(sc.app.find(f => f.key === "resource_style"), "app", "app.resource_style", st.app.resource_style)}
    <h4>${h(t("sys.maintenance"))}</h4>
    ${field(sc.app.find(f => f.key === "guarded_execution"), "app", "app.guarded_execution", st.app.guarded_execution)}
    <div class="list-box">
      <div class="list-row"><div class="grow"><div class="lr-t">${h(t("sys.cache"))}</div><div class="lr-s">${h(t("sys.cacheHelp"))}</div></div>
        <button type="button" class="btn sm" id="clearCache">${icon("refresh")}${h(t("sys.clearCache"))}</button></div>
      <div class="list-row"><div class="grow"><div class="lr-t">${h(t("sys.backup"))}</div><div class="lr-s">${h(t("sys.backupHelp"))}</div>
          <label class="switch" style="margin-top:6px;font-size:12.5px"><input type="checkbox" id="bkKeys"> ${h(t("sys.backupKeys"))}</label></div>
        <button type="button" class="btn sm" id="bkExport">${icon("download")}${h(t("sys.export"))}</button>
        <button type="button" class="btn sm" id="bkImport">${icon("upload")}${h(t("sys.import"))}</button></div>
    </div>
    ${android() ? "" : `<div class="field-grid">${field(sc.app.find(f => f.key === "port"), "app", "app.port", st.app.port)}</div>`}
    <h4>${h(t("log.title"))}</h4>
    ${android() ? "" : `<div class="row" style="margin-bottom:8px"><span class="muted grow" style="font-size:12.5px">${h(S.info.local_dir)}</span>
      <button type="button" class="btn sm ghost" data-open-logs>${icon("folder")}${h(t("gen.openFolder"))}</button></div>`}
    <div class="row" style="margin-bottom:8px"><select id="logLevel" style="width:auto">
        <option value="">${h(t("log.all"))}</option><option value="WARNING">${h(t("log.warnings"))}</option><option value="ERROR">${h(t("log.errors"))}</option></select>
      <button type="button" class="btn sm" id="logRefresh">${icon("refresh")}${h(t("log.refresh"))}</button>
      <button type="button" class="btn sm ghost" id="logCopy">${icon("copy")}${h(t("pclink.copy"))}</button></div>
    <pre class="log-view" id="logView">${h(t("common.loading"))}</pre>
    <div class="help">${h(t("log.help"))}</div>`;
}

async function refreshSystem() {
  const box = $("#sysBox");
  if (!box) return;
  const d = await api("/api/system").catch(e => ({ error: e.message }));
  if (d.error) { box.innerHTML = `<div class="list-empty">${h(d.error)}</div>`; return; }
  const row = (k, v) => v ? `<div class="list-row"><div class="grow"><div class="lr-t">${h(k)}</div><div class="lr-s">${h(v)}</div></div></div>` : "";
  const dev = d.device || {};
  box.innerHTML = [
    dev.model ? row(t("sys.phone"), `${dev.manufacturer || ""} ${dev.model}`.trim()) : "",
    row(t("sys.os"), d.os),
    row(t("sys.cpu"), [dev.soc || d.cpu, `${d.cores} ${t("sys.cores")}`].filter(Boolean).join(" · ")),
    row(t("sys.ram"), d.ram_gb ? `${d.ram_gb} GB` + (dev.ram_free_gb ? ` · ${t("sys.free", { n: dev.ram_free_gb })}` : "") : ""),
    ...(d.gpus || []).map(g => row(t("sys.gpu"), g.name + (g.vram_gb ? ` · ${g.vram_gb} GB ${t("sys.vram")}` : ""))),
    dev.storage_total_gb ? row(t("sys.storage"), `${t("sys.free", { n: dev.storage_free_gb })} / ${dev.storage_total_gb} GB`) : "",
    ...(d.disks || []).map(k => row(t("sys.disk"), `${t("sys.free", { n: k.free_gb })} / ${k.total_gb} GB · ${k.path}`)),
    row(t("sys.app"), `AIRAG ${versionLabel(d.app_version, d.build)} · Python ${d.python}`),
  ].join("");
}

function wireSystem(dlg) {
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
    else {
      el.className = "status-line ok";
      el.textContent = u.channel === "test" ? t("upd.testUpToDate", { v: u.latest || u.current }) : t("gen.upToDate", { v: u.current });
    }
  };
  $("#clearCache", dlg).onclick = async () => {
    const r = await api("/api/app/clear-cache", { method: "POST" }).catch(e => ({ error: e.message }));
    if (r.error) { toast(r.error, 7000); return; }
    toast(t("sys.cacheCleared"), 3000);
    setTimeout(() => location.reload(), 600);
  };
  $("#bkExport", dlg).onclick = async () => {
    const r = await api("/api/backup/export", { method: "POST", body: { include_keys: $("#bkKeys").checked } }).catch(e => ({ error: e.message }));
    toast(r.error || t("sys.exported", { path: r.path }), 7000);
  };
  $("#bkImport", dlg).onclick = async () => {
    if (!confirm(t("sys.importConfirm"))) return;
    const r = await api("/api/backup/import", { method: "POST" }).catch(e => ({ error: e.message }));
    if (r.error) { toast(r.error, 6000); return; }
    if (!r.imported) return;
    toast(t("sys.imported", { s: r.settings ? "✓" : "-", n: r.history }), 6000);
    setTimeout(() => location.reload(), 1200);
  };
  $("[data-open-logs]", dlg)?.addEventListener("click", () => api("/api/app/open-folder", { method: "POST", body: { target: "logs" } }));
  $("#logRefresh", dlg).onclick = refreshLog;
  $("#logLevel", dlg).onchange = refreshLog;
  $("#logCopy", dlg).onclick = async () => {
    try { await navigator.clipboard.writeText($("#logView").textContent); toast(t("pclink.copied")); } catch { toast(t("log.copyFailed")); }
  };
}

// defaults: what new searches start with
function defaultsPane(sc, st) {
  const d = st.defaults || {};
  const langs = sc.languages || [];
  return `<h3>${h(t("tab.defaults"))}</h3><p>${h(t("def.intro"))}</p>
    ${fields(sc.defaults, "defaults", "defaults", d)}
    <div class="field"><label>${h(t("f.defaults.translate_to"))}</label><select data-path="defaults.translate_to">
      <option value="">${h(t("def.translateUi"))}</option>
      ${langs.map(l => `<option value="${l.code}" ${l.code === d.translate_to ? "selected" : ""}>${h(l.native)}${l.native !== l.name ? ` (${h(l.name)})` : ""}</option>`).join("")}</select></div>`;
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
    try { await api("/api/history", { method: "DELETE" }); }
    catch (e) { toast(e.message, 7000); return; }
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

// Text: interface font, article font, text size. Like the colours, it applies at once (and is saved with them).
function textPane() {
  const a = getAppearance();
  const sel = (id, opts, cur) => `<select id="${id}">${opts.map(k => `<option value="${k}" ${k === cur ? "selected" : ""}>${h(t(`txt.${id}.${k}`))}</option>`).join("")}</select>`;
  return `<h3 style="margin-top:22px" id="txtHead">${h(t("txt.title"))}</h3>
    <div class="field"><label for="uiFont">${h(t("txt.uiFont"))}</label>${sel("uiFont", Object.keys(UI_FONTS), a.uiFont || "system")}</div>
    <div class="field"><label for="articleFont">${h(t("txt.articleFont"))}</label>${sel("articleFont", Object.keys(ARTICLE_FONTS), a.articleFont || "serif")}</div>
    <div class="field"><label>${h(t("txt.size"))} <b id="txtSizeV">${h(t("txt.size." + (a.textSize ?? 2)))}</b></label>
      <div class="txt-sizes" role="radiogroup" aria-label="${h(t("txt.size"))}">${TEXT_SIZES.map((_, i) => `<button type="button" role="radio" data-tsize="${i}" aria-checked="${i === (a.textSize ?? 2)}" class="${i === (a.textSize ?? 2) ? "on" : ""}" aria-label="${h(t("txt.size." + i))}">${["A−−", "A−", "A", "A+", "A++"][i]}</button>`).join("")}</div>
      <div class="help">${h(t(android() ? "txt.sizeHelpPhone" : "txt.sizeHelp"))}</div>
      <div class="txt-preview" aria-hidden="true"><div class="t-h">${h(t("txt.previewHead"))}</div><div class="t-b">${h(t("txt.previewBody"))}</div></div></div>`;
}

function wireText(dlg) {
  $("#uiFont", dlg).onchange = e => setAppearance({ uiFont: e.target.value });
  $("#articleFont", dlg).onchange = e => setAppearance({ articleFont: e.target.value });
  $$("[data-tsize]", dlg).forEach(b => (b.onclick = () => {
    const i = +b.dataset.tsize;
    setAppearance({ textSize: i });
    $$("[data-tsize]", dlg).forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", String(x === b)); });
    $("#txtSizeV", dlg).textContent = t("txt.size." + i);
  }));
}

// customize audio: one row per sound (volume + own clip), master volume, reset.
// Nothing here takes effect until Save; Cancel leaves everything as it was (the phone volume is put back too).
const AUDIO_EXT = ".mp3,.ogg,.wav,.m4a,.aac,.opus,.flac,.webm,audio/*";
const AUDIO_DEFAULT_VOL = 70, AUDIO_DEFAULT_MASTER = 80;

function audioPane(audio) {
  const phone = onPhone();
  const master = phone ? (mediaVolume() ?? 50) : (audio.master ?? AUDIO_DEFAULT_MASTER);
  return `<h3 style="margin-top:22px">${h(t("aud.title"))}</h3><p>${h(t("aud.intro"))}</p>
    <div class="field"><label class="switch"><input type="checkbox" id="audEnabled" ${audio.enabled !== false ? "checked" : ""}> ${h(t("aud.enabled"))}</label></div>
    <div class="field aud-row"><label>${icon("volume")} ${h(t(phone ? "aud.masterPhone" : "aud.master"))} <b id="audMasterV">${master}%</b></label>
      <input type="range" min="0" max="100" step="1" id="audMaster" value="${master}">
      <div class="help">${h(t(phone ? "aud.masterPhoneHelp" : "aud.masterHelp"))}</div></div>
    ${SOUNDS.map(n => {
      const s = audio.sounds?.[n] || {};
      return `<div class="field aud-row" data-sound="${n}"><label>${h(t("aud." + n))} <b class="aud-v">${s.vol ?? AUDIO_DEFAULT_VOL}%</b></label>
        <div class="aud-ctl"><button type="button" class="icon-btn sm" data-aud-play title="${h(t("aud.play"))}">${icon("play")}</button>
          <input type="range" min="0" max="100" step="1" data-aud-vol value="${s.vol ?? AUDIO_DEFAULT_VOL}"></div>
        <div class="aud-file"><span class="aud-name">${h(s.file ? t("aud.custom", { f: s.file }) : t("aud.builtIn"))}</span>
          <label class="btn sm ghost">${icon("upload")}${h(t("aud.choose"))}<input type="file" accept="${AUDIO_EXT}" data-aud-file hidden></label>
          <button type="button" class="btn sm ghost" data-aud-clear ${s.file ? "" : "hidden"}>${h(t("aud.useBuiltIn"))}</button></div></div>`;
    }).join("")}
    <div class="row"><button type="button" class="btn sm ghost" id="audReset">${icon("refresh")}${h(t("aud.reset"))}</button>
      <span class="help">${h(t("aud.resetHelp"))}</span></div>`;
}

function wireAudio(dlg) {
  const phone = onPhone();
  const startVolume = phone ? mediaVolume() : null;
  // per sound: {src: data URL, ext, name} for a new clip, "builtin" to go back to the built-in one
  S.pendingSounds = {};
  S.saved = false;
  dlg.addEventListener("close", () => {
    if (!S.saved && phone && startVolume != null) setMediaVolume(startVolume);   // Cancel: phone volume back
  }, { once: true });
  const draft = () => {
    const audio = structuredClone(S.settings.audio);
    audio.enabled = $("#audEnabled", dlg).checked;
    audio.master = Number($("#audMaster", dlg).value);
    $$("[data-sound]", dlg).forEach(row => {
      const n = row.dataset.sound;
      audio.sounds[n] = { ...(audio.sounds[n] || {}), vol: Number($("[data-aud-vol]", row).value) };
      if (S.pendingSounds[n] === "builtin") audio.sounds[n].file = "";
    });
    return audio;
  };
  let playing = null;   // { el, btn }
  const stopPreview = () => {
    if (!playing) return;
    try { playing.el.pause(); } catch { /* */ }
    if (playing.btn) playing.btn.innerHTML = icon("play");
    playing = null;
  };
  // plays a sound with the volumes set on this page; its play button turns into stop while it plays
  const preview = n => {
    stopPreview();
    const p = S.pendingSounds[n];
    const audio = draft();
    const el = play(n, { force: true, audio, src: p && p !== "builtin" ? p.src : p === "builtin" ? soundUrl(n, audio, true) : undefined });
    if (!el) { toast(t("aud.muted"), 2500); return; }
    const btn = $(`[data-sound="${n}"] [data-aud-play]`, dlg);
    playing = { el, btn };
    if (btn) btn.innerHTML = icon("stop");
    const done = () => { if (playing?.el === el) stopPreview(); };
    el.addEventListener("ended", done);
    el.addEventListener("error", () => { done(); toast(t("aud.cantPlay"), 3500); });
  };
  dlg.addEventListener("close", stopPreview, { once: true });
  $("#audMaster", dlg).oninput = e => { $("#audMasterV", dlg).textContent = e.target.value + "%"; };
  $("#audMaster", dlg).onchange = e => {   // released: apply (phone) and play an example
    if (phone) setMediaVolume(Number(e.target.value));
    preview("search_done");
  };
  $$("[data-sound]", dlg).forEach(row => {
    const n = row.dataset.sound, vol = $("[data-aud-vol]", row);
    vol.oninput = () => { $(".aud-v", row).textContent = vol.value + "%"; };
    vol.onchange = () => preview(n);
    $("[data-aud-play]", row).onclick = () => (playing?.btn === $("[data-aud-play]", row) ? stopPreview() : preview(n));
    $("[data-aud-file]", row).onchange = e => {
      const f = e.target.files[0];
      e.target.value = "";
      if (!f) return;
      if (f.size > 3 * 1024 * 1024) { toast(t("aud.tooBig"), 4000); return; }
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      const r = new FileReader();
      r.onload = () => {
        S.pendingSounds[n] = { src: r.result, ext, name: f.name };
        $(".aud-name", row).textContent = t("aud.newClip", { f: f.name });
        $("[data-aud-clear]", row).hidden = false;
        preview(n);
      };
      r.readAsDataURL(f);
    };
    $("[data-aud-clear]", row).onclick = () => {
      S.pendingSounds[n] = "builtin";
      $(".aud-name", row).textContent = t("aud.builtIn");
      $("[data-aud-clear]", row).hidden = true;
    };
  });
  $("#audReset", dlg).onclick = () => {
    $("#audEnabled", dlg).checked = true;
    $("#audMaster", dlg).value = phone ? $("#audMaster", dlg).value : AUDIO_DEFAULT_MASTER;
    $("#audMasterV", dlg).textContent = $("#audMaster", dlg).value + "%";
    $$("[data-sound]", dlg).forEach(row => {
      $("[data-aud-vol]", row).value = AUDIO_DEFAULT_VOL;
      $(".aud-v", row).textContent = AUDIO_DEFAULT_VOL + "%";
      S.pendingSounds[row.dataset.sound] = "builtin";
      $(".aud-name", row).textContent = t("aud.builtIn");
      $("[data-aud-clear]", row).hidden = true;
    });
    toast(t("aud.resetDone"), 3500);
  };
  S.audioDraft = draft;
}

// which tools each AI agent may use: one set per agent type, saved the moment a switch changes
function agentToolsPane() {
  return `<h3>${h(t("atools.title"))}</h3><p>${h(t("atools.intro"))}</p>
    <div class="field"><label for="atAgent">${h(t("atools.agent"))}</label>
      <select id="atAgent">${["standard", "autonomous", "subagents"].map(a => `<option value="${a}">${h(t("atools." + a))}</option>`).join("")}</select>
      <div class="help" id="atAgentHelp"></div></div>
    <div id="atList" class="btn-grid"><div class="status-line"><span class="spinner sm"></span></div></div>
    <p class="help">${icon("check")} ${h(t("atools.autosave"))}</p>`;
}

async function wireAgentTools(dlg) {
  const sel = $("#atAgent", dlg);
  if (!sel) return;
  let data;
  try { data = await api("/api/agent-tools"); } catch (e) { $("#atList", dlg).innerHTML = `<div class="status-line err">${h(e.message)}</div>`; return; }
  const draw = () => {
    const agent = sel.value, on = new Set(data.sets[agent] || []);
    $("#atAgentHelp", dlg).textContent = t("atools." + agent + "Help");
    const L = (tl, k) => has(`tool.${tl.name}${k}`) ? t(`tool.${tl.name}${k}`) : (k ? tl.help : tl.label);
    $("#atList", dlg).innerHTML = data.tools.map(tl => `<div class="field"><label class="switch">
        <input type="checkbox" data-tool="${h(tl.name)}" ${on.has(tl.name) ? "checked" : ""}> ${h(L(tl, ""))}${tl.costly ? ` <span class="pill-cost">${h(t("atools.costly"))}</span>` : ""}</label>
        <div class="help">${h(L(tl, ".help"))}</div></div>`).join("");
    $$("[data-tool]", dlg).forEach(cb => (cb.onchange = async () => {
      const tools = $$("[data-tool]", dlg).filter(x => x.checked).map(x => x.dataset.tool);
      try { data = await api("/api/agent-tools", { method: "POST", body: { agent, tools } }); toast(t("atools.saved"), 1500); }
      catch (e) { toast(e.message, 4000); cb.checked = !cb.checked; }
    }));
  };
  sel.value = data.picker || "autonomous";
  sel.onchange = () => { draw(); api("/api/agent-tools", { method: "POST", body: { picker: sel.value } }).catch(() => {}); };
  draw();
}

// which tool buttons are shown
function buttonsPane(sc, st) {
  if (!sc.buttons) return "";
  return `<h3 style="margin-top:22px">${h(t("btns.title"))}</h3><p>${h(t("btns.intro"))}</p>
    <div class="btn-grid">${fields(sc.buttons, "buttons", "buttons", st.buttons)}</div>`;
}

// read aloud: voice (female / male / a specific installed voice) and speed
function readAloudPane(sp = {}) {
  if (!ttsAvailable()) return "";
  const rate = Number(sp.rate) || 1;
  return `<h3 style="margin-top:22px">${h(t("tts.title"))}</h3><p>${h(t("tts.intro"))}</p>
    <div class="field"><label for="ttsVoice">${h(t("tts.voice"))}</label>
      <select id="ttsVoice" data-path="speech.voice"><option value="female" ${sp.voice === "female" || !sp.voice ? "selected" : ""}>${h(t("tts.female"))}</option>
        <option value="male" ${sp.voice === "male" ? "selected" : ""}>${h(t("tts.male"))}</option>
        ${sp.voice && sp.voice !== "female" && sp.voice !== "male" ? `<option value="${h(sp.voice)}" selected>${h(sp.voice)}</option>` : ""}</select>
      <div class="help">${h(t("tts.voiceHelp"))}</div></div>
    <div class="field aud-row"><label>${h(t("tts.rate"))} <b id="ttsRateV">${rate.toFixed(1)}×</b></label>
      <div class="aud-ctl"><input type="range" min="0.5" max="2" step="0.1" id="ttsRate" data-path="speech.rate" data-type="number" value="${rate}">
      <button type="button" class="btn sm ghost" id="ttsTest">${icon("speak")}${h(t("tts.test"))}</button></div></div>`;
}

function wireReadAloud(dlg) {
  const sel = $("#ttsVoice", dlg);
  if (!sel) return;
  loadVoices().then(list => {
    const keep = sel.value;
    const base = uiLang().slice(0, 2);
    const mine = list.filter(v => (v.lang || "").toLowerCase().startsWith(base)), other = list.filter(v => !mine.includes(v));
    const opt = v => `<option value="${h(v.id)}">${h(v.name)}${v.gender ? ` (${t("tts." + v.gender)})` : ""} · ${h(v.lang)}</option>`;
    sel.innerHTML = `<option value="female">${h(t("tts.female"))}</option><option value="male">${h(t("tts.male"))}</option>`
      + (mine.length ? `<optgroup label="${h(t("tts.yourLang"))}">${mine.map(opt).join("")}</optgroup>` : "")
      + (other.length ? `<optgroup label="${h(t("tts.otherLangs"))}">${other.map(opt).join("")}</optgroup>` : "");
    sel.value = [...sel.options].some(o => o.value === keep) ? keep : "female";
  });
  $("#ttsRate", dlg).oninput = e => { $("#ttsRateV", dlg).textContent = Number(e.target.value).toFixed(1) + "×"; };
  $("#ttsTest", dlg).onclick = () => {
    const before = structuredClone(S.settings.speech || {});
    setSpeech({ voice: sel.value, rate: Number($("#ttsRate", dlg).value) });
    ttsSpeak(t("tts.sample"), uiLang(), st => { if (st === "ended" || st === "error") setSpeech(before); });
  };
  dlg.addEventListener("close", () => { ttsStop(); setSpeech(S.settings.speech); }, { once: true });
}

/** On Save: upload new clips / remove replaced ones, then store the audio settings with the rest. */
async function saveAudio(out) {
  if (!S.audioDraft) return;
  const audio = S.audioDraft();
  for (const [n, p] of Object.entries(S.pendingSounds || {})) {
    if (p === "builtin") {
      await api(`/api/sounds/${n}`, { method: "DELETE" });
      audio.sounds[n].file = "";
    } else {
      const r = await api(`/api/sounds/${n}`, { method: "POST", body: { data: p.src, ext: p.ext } });
      audio.sounds[n].file = r.file;
    }
  }
  if (onPhone()) audio.master = S.settings.audio.master ?? AUDIO_DEFAULT_MASTER;   // the phone's own volume is the master there
  out.audio = audio;
  S.pendingSounds = {};
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
  wireText(dlg);
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
      if (p === "anthropic") addLoadedModels(models, dlg);
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
    <div class="field-grid">${fields(sc.search.fields, "search", "search", st.search)}</div>
    <h4>${h(t("wiki.title"))}</h4><p class="muted" style="font-size:13px">${h(t("wiki.intro"))}</p>
    <div id="wikiList"></div>
    <div class="row" style="margin-top:8px"><input type="text" class="input" id="wikiAdd" placeholder="${h(t("wiki.addPh"))}" style="flex:1;min-width:180px">
      <button type="button" class="btn sm" id="wikiAddBtn">${icon("plus")}${h(t("wiki.add"))}</button></div>
    <div class="status-line" id="wikiStatus"></div>`;
}

// wikis searched next to the search engine; edited here and stored on Save
function drawWikis(dlg) {
  const list = S.wikis;
  $("#wikiList", dlg).innerHTML = list.map((w, i) => `<div class="wiki-row" data-wi="${i}">
      <label class="switch"><input type="checkbox" data-w="enabled" ${w.enabled !== false ? "checked" : ""}> <b>${h(w.name)}</b></label>
      <span class="muted wiki-api">${h(w.api === "wikipedia" ? t("wiki.wikipediaApi") : w.api)}</span>
      <input type="text" class="input" data-w="about" value="${h(w.about || "")}" placeholder="${h(t("wiki.aboutPh"))}">
      <div class="row"><label class="muted" style="font-size:12.5px">${h(t("wiki.trust"))} <input type="number" class="input" min="1" max="10" data-w="trust" value="${w.trust ?? 6}" style="width:70px;padding:4px 8px"></label>
        <button type="button" class="btn sm ghost" data-w-describe>${icon("sparkle")}${h(t("wiki.describe"))}</button>
        ${w.api === "wikipedia" ? "" : `<button type="button" class="btn sm ghost" data-w-remove>${icon("trash")}${h(t("wiki.remove"))}</button>`}</div></div>`).join("")
    || `<div class="h-empty">${h(t("wiki.none"))}</div>`;
  $$(".wiki-row", dlg).forEach(row => {
    const w = list[+row.dataset.wi];
    $$("[data-w]", row).forEach(inp => (inp.oninput = inp.onchange = () => {
      const k = inp.dataset.w;
      w[k] = k === "enabled" ? inp.checked : k === "trust" ? Math.max(1, Math.min(10, Number(inp.value) || 6)) : inp.value;
    }));
    const rm = $("[data-w-remove]", row);
    if (rm) rm.onclick = () => { list.splice(+row.dataset.wi, 1); drawWikis(dlg); };
    $("[data-w-describe]", row).onclick = async e => {
      const b = e.currentTarget;
      b.disabled = true;
      try {
        const r = await api("/api/wikis/describe", { method: "POST", body: { api: w.api === "wikipedia" ? "https://en.wikipedia.org/w/api.php" : w.api, ui_lang: uiLang() } });
        w.about = r.about;
        $("[data-w=about]", row).value = r.about;
      } catch (err) { toast(err.message, 4000); }
      b.disabled = false;
    };
  });
}

function wireWikis(dlg) {
  S.wikis = structuredClone(S.settings.search.wikis || []);
  drawWikis(dlg);
  $("#wikiAddBtn", dlg).onclick = async () => {
    const v = $("#wikiAdd", dlg).value.trim();
    if (!v) return;
    const st = $("#wikiStatus", dlg);
    st.className = "status-line";
    st.innerHTML = `<span class="spinner sm"></span>${h(t("wiki.checking"))}`;
    try {
      const info = await api("/api/wikis/check", { method: "POST", body: { api: v } });
      if (S.wikis.some(w => w.api === info.api)) { st.textContent = t("wiki.already"); return; }
      S.wikis.push({ name: info.name, api: info.api, about: "", enabled: true, trust: 6 });
      $("#wikiAdd", dlg).value = "";
      st.textContent = t("wiki.added", { name: info.name });
      drawWikis(dlg);
    } catch (e) { st.className = "status-line err"; st.textContent = e.message; }
  };
}

function wireSearch(dlg) {
  wireWikis(dlg);
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
    <h4>${h(t("off.settingsTitle"))}</h4>
    <div class="status-card" id="offCard"><div class="grow">${h(t("common.loading"))}</div></div>
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
  $("#libClear").onclick = async () => {
    try { await api("/api/library/clear", { method: "POST" }); } catch (e) { toast(e.message, 7000); return; }
    runSync();
  };
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
</div>` : ""}`;
  const set = async body => {
    const r = await api("/api/pclink", { method: "POST", body }).catch(e => { toast(e.message, 4000); return null; });
    if (r?.error) toast(r.error, 4000);
    refreshPcLink();
  };
  $("#pclToggle").onclick = e => { e.currentTarget.disabled = true; set({ enabled: !on }); };
  $("#pclNewCode")?.addEventListener("click", () => { if (confirm(t("pclink.newCodeConfirm"))) set({ new_code: true }); });
  $$("[data-copy]", box).forEach(b => (b.onclick = async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy); toast(t("pclink.copied")); } catch { toast(b.dataset.copy, 5000); }
  }));
}

function fetchPane(sc, st) {
  if (android()) return `<h4>${h(t("tab.fetch"))}</h4><p class="muted" style="font-size:13px">${h(t("set.fetchIntro"))}</p>${fields(sc.fetch.filter(f => f.key !== "fetcher"), "fetch", "fetch", st.fetch)}`;
  return `<h4>${h(t("tab.fetch"))}</h4><p class="muted" style="font-size:13px">${h(t("set.fetchIntro"))}</p>
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


// about
// "0.2.0", "Test build (based on 0.2.0 · abc1234)" or "0.2.0 (source)"
function versionLabel(v, build) {
  if (build?.channel === "test") return t("about.testBuild", { v, c: build.commit || "?" });
  return v + (build?.channel === "source" ? " (source)" : "");
}

// usage: tokens and cost per model this month, against the monthly budget
function usagePane(sc, st) {
  return `<h3>${h(t("tab.usage"))}</h3><p>${h(t("usage.intro"))}</p>
    <div id="usageBox"><div class="status-line">${h(t("common.checking"))}</div></div>
    <h3 style="margin-top:20px">${h(t("effort.title"))}</h3><p>${h(t("effort.intro"))}</p>
    <div id="effortBox" class="effort-box"></div>
    ${fields(sc.usage, "usage", "usage", st.usage)}`;
}

const money = v => "$" + (v < 0.01 && v > 0 ? v.toFixed(4) : v.toFixed(2));
const tokens = n => n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : String(n);

let usageUnit = (() => { try { return localStorage.getItem("airag.usageUnit") || "money"; } catch { return "money"; } })();

async function refreshUsage() {
  const box = $("#usageBox");
  if (!box) return;
  const u = await api("/api/usage").catch(e => ({ error: e.message }));
  if (u.error) { box.innerHTML = `<div class="status-line err">${h(u.error)}</div>`; return; }
  const tok = usageUnit === "tokens";
  const val = (cost, n) => tok ? tokens(n) : money(cost);
  const share = u.budget ? Math.min(1, u.spent / u.budget) : 0;
  const level = share >= 1 ? "bad" : share >= 0.7 ? "warn" : "ok";
  const left = u.budget ? (tok ? (u.tokens_left != null ? "≈ " + tokens(u.tokens_left) : "?") : money(Math.max(0, u.left))) : "-";
  const maxDay = Math.max(1e-9, ...u.days.map(d => tok ? d.tokens : d.cost));
  const spark = u.days.length > 1 ? `<div class="u-spark" aria-hidden="true">${u.days.map(d =>
      `<i style="height:${Math.max(4, ((tok ? d.tokens : d.cost) / maxDay) * 100).toFixed(1)}%" title="${h(d.day)}: ${h(val(d.cost, d.tokens))}"></i>`).join("")}</div>` : "";
  const rows = u.rows.map(r => `<tr><td><div class="lr-t">${h(r.model || "?")}</div><div class="lr-s">${h(r.provider)}${r.estimated ? ` · ${h(t("usage.estimated"))}` : ""}</div></td>
      <td>${r.calls}</td><td>${tokens(r.in)}</td><td>${tokens(r.out)}</td><td>${r.priced === false ? "?" : money(r.cost)}</td></tr>`).join("");
  const stat = (label, v) => `<div class="u-stat"><div class="u-stat-v">${h(v)}</div><div class="u-stat-l">${h(label)}</div></div>`;
  box.innerHTML = `<div class="u-hero ${level}">
      <div class="u-hero-top"><div><div class="u-hero-l">${h(t("usage.month"))}</div>
          <div class="usage-big">${h(val(u.spent, u.tokens))}</div></div>
        <button type="button" class="u-unit ${tok ? "tok" : ""}" id="usageUnit" role="switch" aria-checked="${tok}" aria-label="${h(t("usage.unit"))}">
          <span>$</span><span>${h(t("usage.tokens"))}</span><i></i></button></div>
      ${u.budget ? `<div class="budget-bar ${level}"><span style="width:${(share * 100).toFixed(1)}%"></span></div>
        <div class="u-hero-row"><span>${h(t("usage.used", { p: Math.round(share * 100) }))}</span><span>${h(t("usage.left", { v: left }))}</span></div>`
        : `<div class="lr-s">${h(t("usage.noBudgetShort"))}</div>`}
      ${spark}
    </div>
    <div class="u-stats">${stat(t("usage.today"), val(u.today.cost, u.today.tokens))}
      ${stat(t("usage.calls"), String(u.calls))}
      ${stat(t("usage.avgCall"), tokens(u.avg_call_tokens))}
      ${!tok && u.projected ? stat(t("usage.projected"), money(u.projected)) : ""}
      ${u.local_tokens ? stat(t("usage.local"), tokens(u.local_tokens)) : ""}
      ${u.top_model ? stat(t("usage.topModel"), u.top_model) : ""}</div>
    ${u.local_compare ? `<div class="help">${h(t("usage.localCompare", { v: money(u.local_compare.cost), model: u.local_compare.model }))}</div>` : ""}
    ${u.rows.length ? `<div class="table-wrap"><table class="usage-table"><thead><tr><th>${h(t("usage.model"))}</th><th>${h(t("usage.calls"))}</th><th>${h(t("usage.in"))}</th><th>${h(t("usage.out"))}</th><th>${h(t("usage.cost"))}</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="h-empty">${h(t("usage.none"))}</div>`}
    ${u.unpriced.length ? `<div class="help">${h(t("usage.unpriced"))}</div>` : ""}
    <div class="help">${h(u.prices_updated ? t("usage.prices", { when: fmtAgo(u.prices_updated * 1000, uiLang()) }) : t("usage.pricesBuiltIn"))}</div>
    <div class="row" style="margin:8px 0 14px"><button type="button" class="btn sm ghost" id="usagePrices">${icon("refresh")}${h(t("usage.refreshPrices"))}</button>
      <button type="button" class="btn sm ghost" id="usageReset">${icon("trash")}${h(t("usage.reset"))}</button></div>`;
  $("#usageUnit").onclick = () => {
    usageUnit = tok ? "money" : "tokens";
    try { localStorage.setItem("airag.usageUnit", usageUnit); } catch { /* not kept */ }
    $("#usageUnit").classList.toggle("tok", !tok);
    setTimeout(refreshUsage, 220);   // let the switch slide first
  };
  $("#usagePrices").onclick = async () => { await api("/api/usage/prices", { method: "POST" }).catch(() => {}); refreshUsage(); };
  $("#usageReset").onclick = async () => { if (!confirm(t("usage.resetConfirm"))) return; await api("/api/usage/reset", { method: "POST" }); refreshUsage(); };
}

// quality vs. token saving: one mode per agent type, saved the moment it changes
async function drawEffort() {
  const box = $("#effortBox");
  if (!box) return;
  let data;
  try { data = await api("/api/agent-tools"); } catch (e) { box.innerHTML = `<div class="status-line err">${h(e.message)}</div>`; return; }
  box.innerHTML = ["standard", "autonomous", "subagents"].map(a => `<div class="effort-row">
      <div class="effort-name">${h(t("atools." + a))}</div>
      <div class="effort-seg" role="radiogroup" aria-label="${h(t("atools." + a))}" style="--i:${data.levels.indexOf(data.effort[a])};--n:${data.levels.length}">
        <i aria-hidden="true"></i>${data.levels.map(l => `<button type="button" role="radio" aria-checked="${l === data.effort[a]}" data-agent="${a}" data-level="${l}" title="${h(t("effort." + l + "Help"))}">${h(t("effort." + l))}</button>`).join("")}</div>
      <div class="help">${h(t("effort." + data.effort[a] + "Help"))}</div></div>`).join("");
  $$("[data-level]", box).forEach(b => (b.onclick = async () => {
    const seg = b.parentElement;
    seg.style.setProperty("--i", data.levels.indexOf(b.dataset.level));
    try { await api("/api/agent-tools", { method: "POST", body: { effort: { [b.dataset.agent]: b.dataset.level } } }); toast(t("atools.saved"), 1200); }
    catch (e) { toast(e.message, 4000); }
    drawEffort();
  }));
}

function wireUsage() { drawEffort(); /* the usage buttons are wired each time the box is drawn */ }

function aboutPane() {
  const i = S.info;
  return `<h3>AIRAG ${h(i.version)}</h3><p>${h(t("app.tagline"))}</p>
    <div class="list-box">
      <div class="list-row"><div class="grow"><div class="lr-t">${h(t("about.version"))}</div><div class="lr-s">${h(versionLabel(i.version, i.build))}${i.portable ? " · portable" : ""}</div></div></div>
      ${i.port ? `<div class="list-row"><div class="grow"><div class="lr-t">${h(t("about.port"))}</div><div class="lr-s mono">${h(i.port)}</div></div></div>` : ""}
      <div class="list-row"><div class="grow"><div class="lr-t">GitHub</div><div class="lr-s">github.com/${h(i.repo)}</div></div>
        <a class="btn sm" href="https://github.com/${h(i.repo)}" target="_blank" rel="noopener">${icon("ext")}${h(t("about.open"))}</a></div>
    </div>
    <h4>${h(t("about.license"))}</h4>
    <div class="license">
      <p>${h(t("lic.summary"))}</p>
      <ul><li>${h(t("lic.can"))}</li><li>${h(t("lic.must"))}</li><li>${h(t("lic.not"))}</li><li>${h(t("lic.name"))}</li></ul>
      <details><summary>${h(t("lic.full"))}</summary><pre class="log-view">${h(MIT)}</pre></details>
    </div>
    <p class="muted" style="font-size:13px">${h(t("banner.disclaimer"))}</p>`;
}

const MIT = `MIT License

Copyright (c) 2026 snakeMax

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`;

async function refreshLog() {
  const view = $("#logView");
  if (!view) return;
  const r = await api("/api/app/log?lines=400&level=" + ($("#logLevel")?.value || "")).catch(e => ({ lines: [e.message] }));
  view.textContent = r.lines.length ? r.lines.join("\n") : t("log.empty");
  view.scrollTop = view.scrollHeight;
}

