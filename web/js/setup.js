// First-run setup, and the "API key missing" popup shown at launch when needed.
import { $, $$, h, icon, api, toast } from "./util.js";
import { t, uiLang, uiLanguages } from "./i18n.js";

const KEY_LINKS = {
  anthropic: "https://console.anthropic.com/settings/keys",
  openai: "https://platform.openai.com/api-keys",
  deepseek: "https://platform.deepseek.com/api_keys",
};

let onDone = () => {};
export function setSetupHooks(x) { onDone = x.onDone || onDone; }

// Decide on launch whether to show the popup.
export function needsSetup(status) {
  if (!status.setup_done) return "welcome";
  if (status.needs_key) return "key";
  if (status.provider === "ollama" && status.ollama && !status.ollama.installed && !status.ollama.running) return "ollama";
  return null;
}

export async function openSetup(reason = "welcome") {
  const dlg = $("#setupDlg");
  const [schema, settings, oll] = await Promise.all([api("/api/schema"), api("/api/settings"),
    api("/api/ollama/status").catch(() => ({ installed: false, running: false, models: [] }))]);
  const cloud = schema.llm.providers.filter(p => p.name !== "ollama");
  let choice;
  if (reason === "key") choice = "cloud";
  else if (reason === "ollama") choice = "local";
  else choice = oll.installed || oll.running ? "local" : "cloud";
  let provider = settings.llm.provider !== "ollama" ? settings.llm.provider : "anthropic";
  const title = reason === "key" ? t("setup.keyTitle") : reason === "ollama" ? t("setup.ollamaTitle") : t("setup.title");
  const intro = reason === "key" ? t("setup.missingKey", { p: cloud.find(p => p.name === settings.llm.provider)?.label || "" }) : t("setup.intro");

  const render = () => {
    dlg.innerHTML = `
      <form method="dialog">
        <div class="dlg-head"><h2>${h(title)}</h2><button class="icon-btn" value="skip">${icon("x")}</button></div>
        <div class="dlg-body plain">
          <p class="setup-intro">${h(intro)}</p>
          ${reason === "welcome" ? `<div class="field"><label>${h(t("gen.language"))}</label><select id="suLang">
            <option value="auto">${h(t("gen.languageAuto", { x: uiLanguages().find(l => l.code === uiLang())?.native || "English" }))}</option>
            ${uiLanguages().map(l => `<option value="${l.code}" ${l.code === settings.app.language ? "selected" : ""}>${h(l.native)}</option>`).join("")}</select></div>` : ""}
          <div class="choice-grid">
            <button type="button" class="choice ${choice === "local" ? "on" : ""}" data-choice="local"><b>${icon("cpu")}${h(t("setup.local"))}</b><span>${h(t("setup.localDesc"))}</span></button>
            <button type="button" class="choice ${choice === "cloud" ? "on" : ""}" data-choice="cloud"><b>${icon("globe")}${h(t("setup.cloud"))}</b><span>${h(t("setup.cloudDesc"))}</span></button>
          </div>
          ${choice === "local" ? localPart(oll, settings) : cloudPart(cloud, provider, settings)}
          <details style="margin-top:6px"><summary style="cursor:pointer;font-weight:600;font-size:13.5px">${h(t("setup.searchKeys"))}</summary>
            <p class="muted" style="font-size:12.5px">${h(t("setup.searchKeysDesc"))}</p>
            <div class="field"><label>Brave Search API key</label><input class="input" type="password" id="suBrave" autocomplete="off" placeholder="${h(settings.search.backends.brave?.api_key || "")}">
              <div class="help"><a href="https://api-dashboard.search.brave.com/" target="_blank" rel="noopener">api-dashboard.search.brave.com</a></div></div>
          </details>
          <div class="status-line" id="suStatus" style="margin-top:10px"></div>
        </div>
        <div class="dlg-foot"><span class="muted">${h(t("setup.later"))}</span>
          <button class="btn ghost" value="skip">${h(t("setup.skip"))}</button>
          <button type="button" class="btn primary" id="suDone">${h(t("setup.done"))}</button></div>
      </form>`;
    $$("[data-choice]", dlg).forEach(b => (b.onclick = () => { choice = b.dataset.choice; render(); }));
    $("#suProv")?.addEventListener("change", e => { provider = e.target.value; render(); });
    $("#suStart")?.addEventListener("click", async e => {
      e.currentTarget.innerHTML = `<span class="spinner sm"></span>`;
      Object.assign(oll, await api("/api/ollama/start", { method: "POST" }).catch(() => oll));
      render();
    });
    $("#suDone").onclick = () => finish(choice, provider, settings);
  };
  dlg.onclose = async () => {
    if (dlg.returnValue === "skip") {
      await api("/api/settings", { method: "POST", body: { app: { setup_done: true } } }).catch(() => {});
      onDone(false);
    }
  };
  render();
  if (!dlg.open) dlg.showModal();
}

function localPart(oll, settings) {
  const models = oll.models || [];
  const cur = settings.llm.providers.ollama.model;
  if (!oll.installed && !oll.running) {
    return `<div class="status-card"><span class="dot err"></span><div class="grow">${h(t("setup.ollamaMissing"))}<div class="muted" style="font-size:12.5px">${h(t("setup.ollamaHow"))}</div></div>
      <a class="btn sm primary" href="https://ollama.com/download" target="_blank" rel="noopener">${icon("download")}${h(t("ollama.download"))}</a></div>`;
  }
  if (!oll.running) {
    return `<div class="status-card"><span class="dot warn"></span><div class="grow">${h(t("setup.ollamaInstalled"))}</div>
      <button type="button" class="btn sm primary" id="suStart">${icon("power")}${h(t("ollama.start"))}</button></div>`;
  }
  return `<div class="status-card"><span class="dot ok"></span><div class="grow">${h(t("ollama.running", { v: oll.version }))}</div></div>
    <div class="field"><label>${h(t("f.p.model"))}</label>
      ${models.length ? `<select id="suModel">${models.map(m => `<option ${m.name === cur || m.name === cur + ":latest" ? "selected" : ""}>${h(m.name)}</option>`).join("")}</select>`
        : `<div class="muted" style="font-size:13px">${h(t("setup.noModels"))}</div>`}</div>`;
}

function cloudPart(cloud, provider, settings) {
  const cfg = settings.llm.providers[provider] || {};
  return `<div class="field"><label>${h(t("model.provider"))}</label><select id="suProv">${cloud.map(p => `<option value="${p.name}" ${p.name === provider ? "selected" : ""}>${h(p.label)}</option>`).join("")}</select></div>
    ${provider === "openai_compatible" ? `<div class="field"><label>${h(t("f.p.base_url"))}</label><input class="input" id="suUrl" value="${h(cfg.base_url || "")}"></div>` : ""}
    <div class="field"><label>${h(t("f.p.api_key"))}</label><input class="input" type="password" id="suKey" autocomplete="off" spellcheck="false" placeholder="${h(cfg.api_key || "")}">
      ${KEY_LINKS[provider] ? `<div class="help"><a href="${KEY_LINKS[provider]}" target="_blank" rel="noopener">${h(t("setup.getKey"))}</a> · ${h(t("setup.keyPrivate"))}</div>` : ""}</div>
    <div class="field"><label>${h(t("f.p.model"))}</label><input class="input" id="suModelText" value="${h(cfg.model || "")}" spellcheck="false"></div>`;
}

async function finish(choice, provider, settings) {
  const status = $("#suStatus");
  const patch = { app: { setup_done: true }, llm: { providers: {} }, search: { backends: {} } };
  const lang = $("#suLang")?.value;
  if (lang) patch.app.language = lang;
  if (choice === "local") {
    patch.llm.provider = "ollama";
    const m = $("#suModel")?.value;
    if (m) patch.llm.providers.ollama = { model: m };
  } else {
    patch.llm.provider = provider;
    const p = {};
    const key = $("#suKey")?.value.trim();
    if (key) p.api_key = key;
    const model = $("#suModelText")?.value.trim();
    if (model) p.model = model;
    const url = $("#suUrl")?.value.trim();
    if (url) p.base_url = url;
    patch.llm.providers[provider] = p;
    if (!key && !settings.llm.providers[provider]?.api_key && provider !== "openai_compatible") {
      status.className = "status-line err";
      status.textContent = t("setup.needKey");
      return;
    }
  }
  const brave = $("#suBrave")?.value.trim();
  if (brave) { patch.search.backends.brave = { api_key: brave }; patch.search.backend = "brave"; patch.search.image_backend = "brave"; }
  status.className = "status-line";
  status.textContent = t("common.checking");
  try {
    await api("/api/settings", { method: "POST", body: patch });
    if (choice === "cloud") {
      const s = await api("/api/settings");
      await api("/api/test-llm", { method: "POST", body: { provider, config: s.llm.providers[provider] } });
    }
    $("#setupDlg").close("done");
    toast(t("setup.ok"));
    onDone(lang && lang !== settings.app.language);
  } catch (e) {
    status.className = "status-line err";
    status.textContent = e.message;
  }
}
