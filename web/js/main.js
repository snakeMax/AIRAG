// Entry point: start-up, routing and the search box.
import { initHelp } from "./help.js";
import { showNotes, notesDirty, saveNotes } from "./notes.js";
import { applyResourceSettings } from "./resources.js";
import { $, $$, h, api, hydrateIcons, icon, toast } from "./util.js";
import { initI18n, t, applyI18n } from "./i18n.js";
import { loadLocal, setAppearance, onAppearanceChange, effectiveTheme } from "./theme.js";
import { RUN, startResearch, openRecord, openSaved, attachRun, setRunHooks, toolbarAction, reloadRecord } from "./run.js";
import { openSettings, setSettingsHooks } from "./settings.js";
import { openSetup, needsSetup, setSetupHooks } from "./setup.js";
import { showDisclaimer, checkUpdates } from "./banners.js";
import { openDrawer, closeDrawer, refreshRecent } from "./history.js";
import { closeSummary } from "./summary.js";
import { chipHtml, openDatePicker, emptyRange, hasRange } from "./dates.js";
import { initSpeech, setAutoSearch } from "./speech.js";
import { setAudio } from "./sound.js";
import { setSpeech } from "./tts.js";
import { applyButtons } from "./buttons.js";
import { initActivity, markSeen } from "./activity.js";
import { loadPins, openPinned, setPinHooks } from "./pins.js";
import { initToolbar } from "./toolbar.js";
import { initImageAsk, updateImageButton, pickImage } from "./imageask.js";
import { initOpenFile } from "./openfile.js";
import { initShareText } from "./sharetext.js";
import { initOffline, onOfflineChange } from "./offline.js";

const state = {
  mode: "auto",
  library: false,
  dates: emptyRange(),   // optional date range for the next search
  extras: true,          // pictures + interactive explainer check
  settings: null,
  status: null,
};

// views + routing
function showView(name) {
  $("#tip").hidden = true;
  $("#view-home").hidden = name !== "home";
  $("#view-run").hidden = name !== "run";
  $("#view-notes").hidden = name !== "notes";
  $("#topSearch").hidden = name === "home" || name === "notes";
  $("#topLib").hidden = name === "home" || name === "notes";
  document.body.classList.toggle("running", name === "run");
  document.body.classList.toggle("notes-mode", name === "notes");
  $$(".mode-switch a").forEach(a => a.classList.toggle("on", (a.dataset.modeto === "notes") === (name === "notes")));
}

function go(q, mode = state.mode, library = state.library, fromId = null, dates = state.dates, mergeId = null, extras = state.extras) {
  q = (q || "").trim();
  if (!q) return;
  const hash = `#/search?q=${encodeURIComponent(q)}&mode=${mode}${library ? "&lib=1" : ""}` +
    (fromId ? "&from=" + encodeURIComponent(fromId) : "") + (mergeId ? "&merge=" + encodeURIComponent(mergeId) : "") +
    (dates?.from ? "&df=" + dates.from : "") + (dates?.to ? "&dt=" + dates.to : "") + (extras === false ? "&x=0" : "");
  if (location.hash === hash) route();
  else location.hash = hash;
}

function goQuick(q, library = state.library) {
  q = (q || "").trim();
  if (!q) { $("#homeSearch input").focus(); return; }
  const hash = `#/quick?q=${encodeURIComponent(q)}${library ? "&lib=1" : ""}`;
  if (location.hash === hash) route();
  else location.hash = hash;
}

function route() {
  const hash = location.hash || "#/";
  if (hash.startsWith("#/notes")) {
    RUN.ctrl?.abort();
    RUN.current = null;
    showView("notes");
    document.title = "AIRAG Notes";
    showNotes();
    return;
  }
  if (notesDirty()) saveNotes();         // leaving Notes: unsaved typing is saved first
  if (hash.startsWith("#/quick")) {
    const p = new URLSearchParams(hash.split("?")[1] || "");
    if (p.get("q")) { startResearch(p.get("q"), "article", p.get("lib") === "1", null, undefined, null, false, null, {}); return; }
  }
  if (hash.startsWith("#/search")) {
    const p = new URLSearchParams(hash.split("?")[1] || "");
    const q = p.get("q");
    if (q) {
      startResearch(q, p.get("mode") || state.mode, p.get("lib") === "1", p.get("from"),
                    { from: p.get("df") || "", to: p.get("dt") || "" }, p.get("merge"), p.get("x") !== "0");
      return;
    }
  }
  if (hash.startsWith("#/view/")) {
    const [id, extra] = hash.slice(7).split("?");
    if (extra === "explainer") history.replaceState(null, "", `#/view/${id}`);
    openRecord(decodeURIComponent(id), extra === "explainer");
    return;
  }
  if (hash.startsWith("#/pinned/")) { openPinned(decodeURIComponent(hash.slice(9))); return; }
  if (hash.startsWith("#/run/")) { attachRun(decodeURIComponent(hash.slice(6))); return; }
  if (hash.startsWith("#/saved/")) { openSaved(decodeURIComponent(hash.slice(8))); return; }
  if (hash.startsWith("#/settings")) { showHome(); openSettings(hash.split("/")[2] || "general"); history.replaceState(null, "", "#/"); return; }
  showHome();
}

function showHome() {
  RUN.ctrl?.abort();
  RUN.current = null;
  showView("home");
  document.title = "AIRAG";
  $("#homeSearch input").value = "";
  setTimeout(() => $("#homeSearch input").focus(), 30);
  refreshStatus();
  refreshRecent();
}

// home widgets
/** What new searches start with (Settings -> Defaults). */
function applyDefaults(d) {
  if (!d) return;
  state.mode = ["auto", "article", "results"].includes(d.mode) ? d.mode : "auto";
  state.library = !!d.library;
  state.extras = d.extras !== false;
  state.dates = presetRange(d.dates);
}

function presetRange(name) {
  const days = { week: 7, month: 31, year: 365 }[name];
  if (!days) return emptyRange();
  const d = new Date(Date.now() - days * 864e5);
  return { from: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`, to: "" };
}

function renderHomeDates() {
  $("#homeDates").innerHTML = chipHtml("dateChip", state.dates);
  $("#dateChip").onclick = e => openDatePicker(e.currentTarget, state.dates, d => { state.dates = d; renderHomeDates(); });
}

function renderModes() {
  $$("#modes button").forEach(b => b.classList.toggle("on", b.dataset.mode === state.mode));
  for (const id of ["#libChk", "#topLibChk"]) $(id).checked = state.library;
  $$(".lib-chip").forEach(c => c.classList.toggle("on", state.library));
  $("#xChk").checked = state.extras;
  $("#xChip").classList.toggle("on", state.extras);
}

async function refreshStatus() {
  try {
    const st = await api("/api/status");
    state.status = st;
    const warn = st.needs_key || (st.ollama && (!st.ollama.running || !st.ollama.model_present));
    $("#engineLine").innerHTML = `<span class="dot ${warn ? "off" : ""}"></span>${h(st.llm)} &nbsp;·&nbsp; ${h(st.search)}`;
    $("#engineLine").title = warn ? t("home.engineWarn") : "";
    // the tickbox is always shown; with no folders added it leads to Settings -> Library
    if (!(st.library_folders > 0)) state.library = false;
    renderModes();
    updateImageButton();
  } catch {
    $("#engineLine").textContent = t("home.offline");
  }
}

// wiring
function wire() {
  $("#homeSearch").onsubmit = e => { e.preventDefault(); go(e.target.q.value); };
  $("#quickBtn").onclick = () => goQuick($("#homeSearch input").value);
  $("#quickBtn2").onclick = () => goQuick($("#homeSearch input").value);      // phones: buttons under the box
  $("#searchBtn2").onclick = () => go($("#homeSearch input").value);
  $("#homeSearch input").addEventListener("keydown", e => {   // Shift+Enter: a quick search
    if (e.key === "Enter" && e.shiftKey && !e.isComposing) { e.preventDefault(); goQuick(e.target.value); }
  });
  $("#topSearch").onsubmit = e => { e.preventDefault(); e.target.q.blur(); go(e.target.q.value); };
  // these only change the next searches; the permanent choice is in Settings -> Defaults
  $$("#modes button").forEach(b => (b.onclick = () => { state.mode = b.dataset.mode; renderModes(); }));
  $("#xChk").onchange = e => { state.extras = e.target.checked; renderModes(); };
  for (const id of ["#libChk", "#topLibChk"]) {
    $(id).onchange = e => {
      if (e.target.checked && !(state.status?.library_folders > 0)) {
        e.target.checked = false;
        toast(t("lib.needFolder"), 5000);
        openSettings("library");
        return;
      }
      state.library = e.target.checked;
      renderModes();
    };
  }
  $("#engineLine").onclick = () => openSettings("model");
  $("#settingsBtn").onclick = () => openSettings();
  $("#historyBtn").onclick = () => { markSeen(); openDrawer(); };
  $("#drawerClose").onclick = closeDrawer;
  $("#scrim").onclick = () => { closeDrawer(); closeSummary(); };
  $("#themeBtn").onclick = () => setAppearance({ theme: effectiveTheme() === "dark" ? "light" : "dark" });
  document.addEventListener("keydown", e => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if (e.key === "/" && !typing && !e.isComposing && !document.querySelector("dialog[open]")) {
      e.preventDefault();
      const inp = $("#view-home").hidden ? $("#topSearch input") : $("#homeSearch input");
      inp.focus();
      inp.select();
    }
    if (e.key === "Escape") { closeDrawer(); closeSummary(); }
  });
  addEventListener("scroll", () => document.body.classList.toggle("scrolled", scrollY > 4), { passive: true });
  addEventListener("hashchange", route);
  addEventListener("airag:library", refreshStatus);
}

function applyAudio(s) {
  if (!s) return;
  setAudio(s.audio);
  setSpeech(s.speech);
  setAutoSearch(s.defaults?.speech_autosearch);
  applyButtons(s.buttons);
}

// start-up
async function boot() {
  loadLocal();
  let info = null;
  try {
    [info, state.settings] = await Promise.all([api("/api/app/info"), api("/api/settings")]);
  } catch { /* server not reachable; English UI */ }
  await initI18n(state.settings?.app.language || "auto", info?.languages);
  if (state.settings?.app.appearance) setAppearance(state.settings.app.appearance, false);
  onAppearanceChange((appearance, theme) => {
    api("/api/settings", { method: "POST", body: { app: { appearance, theme_hint: theme } } }).catch(() => {});
  });
  applyDefaults(state.settings?.defaults);
  applyAudio(state.settings);
  applyResourceSettings(state.settings);
  hydrateIcons();
  wire();
  initSpeech(info?.mode === "desktop");
  initActivity();
  initHelp();
  setPinHooks({ showView, defaultView: () => state.settings?.defaults?.pinned_view });
  initImageAsk({ vision: () => !!state.status?.vision });
  initOpenFile();
  initShareText({ go: q => go(q) });
  initOffline();
  onOfflineChange(() => refreshStatus());
  $("#imgAskBtn").onclick = pickImage;
  $(".img-chip-ic").innerHTML = icon("eye");
  initToolbar({ getRun: () => RUN.current, reload: reloadRecord, act: toolbarAction,
                citeStyle: () => state.settings?.defaults?.citation_style || "apa" });
  loadPins();
  setRunHooks({ go, openSettings, showView, refreshRecent, defaults: () => state.settings?.defaults });
  setSettingsHooks({ onSaved: (s, langChanged) => {
    state.settings = s;
    if (langChanged) { location.reload(); return; }
    applyDefaults(s.defaults);
    applyAudio(s);
    applyResourceSettings(s);
    renderModes();
    renderHomeDates();
    refreshStatus();
  } });
  setSetupHooks({ onDone: langChanged => (langChanged ? location.reload() : refreshStatus()) });
  renderModes();
  renderHomeDates();
  route();
  if (!state.settings) return;
  showDisclaimer(state.settings);
  checkUpdates(state.settings);
  const st = await api("/api/status").catch(() => null);
  const why = st && needsSetup(st);
  if (why && !location.hash.startsWith("#/settings")) openSetup(why);
}

boot();
