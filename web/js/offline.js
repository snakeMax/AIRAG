// Offline mode: nothing is searched or read on the web; answers come from your own files, pinned pages and
// History. Turning it on asks who should write: a local model (nothing leaves your devices) or the model you
// normally use with only local sources. An "Offline" chip next to the search options shows it and turns it off.
import { $, $$, h, icon, api, toast } from "./util.js";
import { t } from "./i18n.js";

let state = null;
const listeners = [];
export const onOfflineChange = fn => listeners.push(fn);
export const isOffline = () => !!state?.on;

export async function refreshOffline() {
  state = await api("/api/offline").catch(() => state);
  draw();
  return state;
}

function draw() {
  const on = !!state?.on;
  for (const el of $$(".off-chip")) {
    el.classList.toggle("on", on);
    el.setAttribute("aria-pressed", String(on));
    el.title = t(on ? "off.chipOnTip" : "off.chipTip");
  }
  $("#topOff")?.toggleAttribute("hidden", !on);
  document.body.classList.toggle("is-offline", on);
  const card = $("#offCard");
  if (card) card.innerHTML = cardHtml();
  $("#offToggle")?.addEventListener("click", toggle);
  listeners.forEach(fn => fn(on));
}

function cardHtml() {
  const on = !!state?.on;
  const who = !on ? "" : state.writer === "local"
    ? t("off.byLocal", { model: (state.model || state.choices.find(c => c.provider === state.provider)?.model || "") })
    : t("off.byCurrent", { model: `${state.current.label} · ${state.current.model}` });
  return `<div class="grow"><div class="lr-t">${h(t(on ? "off.isOn" : "off.isOff"))}</div>
    <div class="lr-s">${h(on ? who : t("off.cardHelp"))}</div></div>
    <button type="button" class="btn sm ${on ? "" : "primary"}" id="offToggle">${icon("offline")}${h(t(on ? "off.turnOff" : "off.turnOnBtn"))}</button>`;
}

async function toggle() {
  if (!state) await refreshOffline();
  if (state?.on) {
    state = await api("/api/offline", { method: "POST", body: { on: false } }).catch(e => { toast(e.message); return state; });
    toast(t(state?.applies_later ? "off.offLater" : "off.offToast"), state?.applies_later ? 6000 : 2500);
    draw();
  } else openOfflineDialog();
}

export function initOffline() {
  $$(".off-chip").forEach(b => (b.onclick = toggle));
  refreshOffline();
}

/** The "Turn on offline mode" dialog. */
export async function openOfflineDialog() {
  await refreshOffline();
  if (!state) return;
  const local = state.choices || [];
  const curIsLocal = state.current.local;
  let d = $("#offDlg");
  if (!d) { d = Object.assign(document.createElement("dialog"), { id: "offDlg", className: "dlg off-dlg" }); document.body.appendChild(d); }
  const pick = local.length ? "local" : "current";
  const prov = state.provider || (curIsLocal ? state.current.provider : local[0]?.provider) || "";
  const modelsOf = c => {
    const names = [...new Set([...(c.models || []), c.model].filter(Boolean))];
    const sel = state.provider === c.provider && state.model ? state.model : c.model;
    return names.map(m => `<option value="${h(m)}" ${m === sel ? "selected" : ""}>${h(m)}</option>`).join("");
  };
  d.innerHTML = `<form method="dialog">
    <div class="dlg-head"><h2>${h(t("off.title"))}</h2><button class="icon-btn" value="close" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
    <div class="dlg-body plain off-body">
      <p class="off-intro">${h(t("off.intro"))}</p>
      <div class="off-choices" role="radiogroup" aria-label="${h(t("off.who"))}">
        <label class="off-choice ${local.length ? "" : "disabled"}"><span class="off-top"><input type="radio" name="offWho" value="local" ${pick === "local" ? "checked" : ""} ${local.length ? "" : "disabled"}>
          <strong>${h(t("off.local"))}</strong></span>
          <span class="off-desc">${h(t("off.localDesc"))}</span>
          ${local.length ? `<span class="off-pick">
            <select class="input" id="offProv" aria-label="${h(t("off.where"))}">${local.map(c => `<option value="${h(c.provider)}" ${c.provider === prov ? "selected" : ""}>${h(c.label)}</option>`).join("")}</select>
            ${local.map(c => `<select class="input off-model" data-for="${h(c.provider)}" aria-label="${h(t("off.model"))}" ${c.provider === prov ? "" : "hidden"}>${modelsOf(c) || `<option value="">${h(t("off.noModel"))}</option>`}</select>`).join("")}
            <span class="help" id="offStartNote">${h(t("off.startNote"))}</span></span>`
          : `<span class="off-note">${icon("info")}<span>${h(t("off.noLocal"))}</span></span>`}
        </label>
        <label class="off-choice"><span class="off-top"><input type="radio" name="offWho" value="current" ${pick === "current" ? "checked" : ""}>
          <strong>${h(curIsLocal ? t("off.keepLocal", { model: state.current.model }) : t("off.keep", { model: state.current.label }))}</strong></span>
          <span class="off-desc">${h(t("off.keepDesc"))}</span>
          ${curIsLocal ? "" : `<span class="off-note">${icon("info")}<span>${h(t("off.sentNote"))}</span></span>`}
        </label>
      </div>
    </div>
    <div class="dlg-foot"><span class="muted off-back">${h(t("off.back"))}</span>
      <button class="btn sm ghost" value="close">${h(t("common.cancel"))}</button>
      <button type="button" class="btn sm primary" id="offGo">${h(t("off.turnOn"))}</button></div></form>`;
  const provSel = $("#offProv", d);
  const syncModels = () => {
    $$(".off-model", d).forEach(s => (s.hidden = s.dataset.for !== provSel.value));
    $("#offStartNote", d)?.toggleAttribute("hidden", provSel.value !== "ollama");
  };
  if (provSel) { provSel.onchange = syncModels; syncModels(); }
  $("#offGo", d).onclick = async () => {
    const writer = $("input[name=offWho]:checked", d)?.value || "current";
    const provider = writer === "local" ? provSel?.value || "" : "";
    const model = writer === "local" ? ($(`.off-model[data-for="${provider}"]`, d)?.value || "") : "";
    try {
      state = await api("/api/offline", { method: "POST", body: { on: true, writer, provider, model } });
      d.close();
      toast(t(state.applies_later ? "off.onLater" : "off.onToast"), state.applies_later ? 6000 : 4000);
      draw();
    } catch (e) { toast(e.message, 6000); }
  };
  d.showModal();
}
