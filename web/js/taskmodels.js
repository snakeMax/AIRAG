// Settings -> AI -> "Models per task": pick which model each kind of work uses (Claude API for now).
// The table is kept in state here and handed to save() as llm.task_models = {provider: {task: model}}.
// Empty = the provider's main model. A running task keeps the model it started with (guarded execution).
import { $, $$, h, api } from "./util.js";
import { t, has } from "./i18n.js";

const CLAUDE = [
  ["claude-opus-5-5", "Opus 5.5"],
  ["claude-sonnet-5-5", "Sonnet 5.5"],
  ["claude-haiku-5-5", "Haiku 5.5"],
];
const DEFAULT_MODEL = "claude-sonnet-5-5";
const M = { table: null, tasks: [], providers: [], extra: [], prices: {} };

const label = task => (has(`task.${task.id}`) ? t(`task.${task.id}`) : task.label);
const hint = task => (has(`task.${task.id}.hint`) ? t(`task.${task.id}.hint`) : task.hint);
const nice = id => (CLAUDE.find(([m]) => m === id)?.[1] || id);

/** The section's HTML (filled by wireTaskModels). */
export function taskModelsPane(sc, st) {
  M.tasks = sc.tasks || [];
  M.providers = sc.task_providers || [];
  M.table = structuredClone(st.llm.task_models || {});
  return `<h3>${h(t("tm.title"))}</h3>
    <div id="tmBody"></div>`;
}

/** The value save() stores; null = this section was never shown. */
export function taskModelsValue() {
  return M.table;
}

function options(selected, main) {
  const list = [...CLAUDE.map(([m]) => m), ...M.extra.filter(m => !CLAUDE.some(([c]) => c === m))];
  if (selected && !list.includes(selected)) list.push(selected);
  return `<option value="">${h(t("tm.main", { m: nice(main) }))}</option>`
    + list.map(m => `<option value="${h(m)}" ${m === selected ? "selected" : ""}>${h(nice(m))}</option>`).join("");
}

function priceLine() {
  const parts = CLAUDE.map(([m, n]) => {
    const p = M.prices[m];
    return p ? `${n} $${+p[0].toFixed(2)} / $${+p[1].toFixed(2)}` : null;
  }).filter(Boolean);
  return parts.length ? t("tm.prices", { p: parts.join(" · ") }) : "";
}

function render(dlg) {
  const body = $("#tmBody", dlg);
  if (!body) return;
  const prov = $("#provSel", dlg)?.value || "";
  if (!M.providers.includes(prov)) {
    body.innerHTML = `<p class="muted">${h(t("tm.notHere"))}</p>`;
    return;
  }
  const main = $(`[data-path="llm.providers.${prov}.model"]`, dlg)?.value || DEFAULT_MODEL;
  const row = M.table[prov] || {};
  body.innerHTML = `<p>${h(t("tm.intro"))}</p>
    <div class="tm-list">${M.tasks.map(task => `<div class="tm-row">
        <div class="tm-text"><b>${h(label(task))}</b><small>${h(hint(task))}</small></div>
        <select data-tm="${h(task.id)}" aria-label="${h(t("tm.modelFor", { t: label(task) }))}">${options(row[task.id] || "", main)}</select>
      </div>`).join("")}</div>
    <div class="row tm-actions">
      <label class="tm-all"><span>${h(t("tm.setAll"))}</span>
        <select id="tmAll"><option value="">—</option>${CLAUDE.map(([m, n]) => `<option value="${m}">${h(n)}</option>`).join("")}</select></label>
      <button type="button" class="btn sm" id="tmReset">${h(t("tm.reset"))}</button>
    </div>
    <p class="hint" id="tmPrices">${h(priceLine())}</p>`;
  $$("[data-tm]", body).forEach(sel => (sel.onchange = () => {
    const r = (M.table[prov] ||= {});
    if (sel.value) r[sel.dataset.tm] = sel.value; else delete r[sel.dataset.tm];
  }));
  const setAll = m => { M.table[prov] = Object.fromEntries(M.tasks.map(x => [x.id, m])); render(dlg); };
  $("#tmAll", body).onchange = e => e.target.value && setAll(e.target.value);
  $("#tmReset", body).onclick = () => setAll(DEFAULT_MODEL);
}

export function wireTaskModels(dlg) {
  render(dlg);
  $("#provSel", dlg)?.addEventListener("change", () => render(dlg));
  $$('[data-path$=".model"]', dlg).forEach(el => el.addEventListener("change", () => render(dlg)));
  api("/api/model-prices", { method: "POST", body: { provider: "anthropic", models: CLAUDE.map(([m]) => m) } })
    .then(r => { M.prices = r.prices || {}; const p = $("#tmPrices", dlg); if (p) p.textContent = priceLine(); })
    .catch(() => {});
}

/** Models found by "Load models" become choices too. */
export function addLoadedModels(models, dlg) {
  M.extra = (models || []).filter(m => /^claude-/.test(m)).slice(0, 30);
  render(dlg);
}
