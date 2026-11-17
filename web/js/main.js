// Entry point: start-up, routing and the search box.
import { $, $$, h, api, hydrateIcons, icon } from "./util.js";
import { initI18n, t, applyI18n } from "./i18n.js";
import { loadLocal, setAppearance, onAppearanceChange, effectiveTheme } from "./theme.js";
import { RUN, startResearch, openRecord, setRunHooks } from "./run.js";
import { openSettings, setSettingsHooks } from "./settings.js";
import { openSetup, needsSetup, setSetupHooks } from "./setup.js";
import { showDisclaimer, checkUpdates } from "./banners.js";
import { openDrawer, closeDrawer, refreshRecent } from "./history.js";
import { closeSummary } from "./summary.js";

const state = {
  mode: localStorage.getItem("airag.mode") || "auto",
  library: false,
  settings: null,
  status: null,
};

// views + routing
function showView(name) {
  $("#tip").hidden = true;
  $("#view-home").hidden = name !== "home";
  $("#view-run").hidden = name !== "run";
  $("#topSearch").hidden = name === "home";
  $("#topLib").hidden = name === "home" || !state.status?.library_folders;
  document.body.classList.toggle("running", name === "run");
}

function go(q, mode = state.mode, library = state.library) {
  q = (q || "").trim();
  if (!q) return;
  const hash = `#/search?q=${encodeURIComponent(q)}&mode=${mode}${library ? "&lib=1" : ""}`;
  if (location.hash === hash) route();
  else location.hash = hash;
}

function route() {
  const hash = location.hash || "#/";
  if (hash.startsWith("#/search")) {
    const p = new URLSearchParams(hash.split("?")[1] || "");
    const q = p.get("q");
    if (q) { startResearch(q, p.get("mode") || state.mode, p.get("lib") === "1"); return; }
  }
  if (hash.startsWith("#/view/")) { openRecord(decodeURIComponent(hash.slice(7))); return; }
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
function renderModes() {
  $$("#modes button").forEach(b => b.classList.toggle("on", b.dataset.mode === state.mode));
  for (const id of ["#libChk", "#topLibChk"]) $(id).checked = state.library;
  $$(".lib-chip").forEach(c => c.classList.toggle("on", state.library));
}

async function refreshStatus() {
  try {
    const st = await api("/api/status");
    state.status = st;
    const warn = st.needs_key || (st.ollama && (!st.ollama.running || !st.ollama.model_present));
    $("#engineLine").innerHTML = `<span class="dot ${warn ? "off" : ""}"></span>${h(st.llm)} &nbsp;·&nbsp; ${h(st.search)}`;
    $("#engineLine").title = warn ? t("home.engineWarn") : "";
    const hasLib = st.library_folders > 0;
    $("#libChip").hidden = !hasLib;
    if (!$("#view-run").hidden) $("#topLib").hidden = !hasLib;
    if (!hasLib) state.library = false;
    renderModes();
  } catch {
    $("#engineLine").textContent = t("home.offline");
  }
}

// wiring
function wire() {
  $("#homeSearch").onsubmit = e => { e.preventDefault(); go(e.target.q.value); };
  $("#topSearch").onsubmit = e => { e.preventDefault(); e.target.q.blur(); go(e.target.q.value); };
  $$("#modes button").forEach(b => (b.onclick = () => { state.mode = b.dataset.mode; localStorage.setItem("airag.mode", state.mode); renderModes(); }));
  for (const id of ["#libChk", "#topLibChk"]) {
    $(id).onchange = e => {
      state.library = e.target.checked;
      renderModes();
      api("/api/settings", { method: "POST", body: { app: { include_library: state.library } } }).catch(() => {});
    };
  }
  $("#engineLine").onclick = () => openSettings("model");
  $("#settingsBtn").onclick = () => openSettings();
  $("#historyBtn").onclick = openDrawer;
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
  state.library = !!state.settings?.app.include_library;
  hydrateIcons();
  wire();
  setRunHooks({ go, openSettings, showView, refreshRecent });
  setSettingsHooks({ onSaved: (s, langChanged) => { state.settings = s; if (langChanged) location.reload(); else refreshStatus(); } });
  setSetupHooks({ onDone: langChanged => (langChanged ? location.reload() : refreshStatus()) });
  renderModes();
  route();
  if (!state.settings) return;
  showDisclaimer(state.settings);
  checkUpdates(state.settings);
  const st = await api("/api/status").catch(() => null);
  const why = st && needsSetup(st);
  if (why && !location.hash.startsWith("#/settings")) openSetup(why);
}

boot();
