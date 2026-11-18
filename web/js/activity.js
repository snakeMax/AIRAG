// Activity indicator: a slim bar under the top bar while searches or explainers run in the
// background, and a dot on the History button while something runs or a result is unread.
// Other modules listen for the "airag:jobs" event ({detail: {items, recent}}) instead of polling.
import { $, h, icon, api } from "./util.js";
import { t } from "./i18n.js";

export const JOBS = { items: [], recent: [] };
let timer = 0, lastSeen = readSeen();

function readSeen() {
  try { return Number(localStorage.getItem("airag.jobsSeen")) || Date.now() / 1000; } catch { return Date.now() / 1000; }
}
function writeSeen(v) {
  lastSeen = v;
  try { localStorage.setItem("airag.jobsSeen", String(v)); } catch { /* storage off */ }
}

/** Mark finished jobs as seen (the History drawer was opened). */
export function markSeen() { writeSeen(Date.now() / 1000); draw(); }

/** Ask for fresh status now (call after starting or cancelling a job). */
export function pokeJobs() { clearTimeout(timer); timer = setTimeout(poll, 150); }

export const jobFor = (kind, ref) => JOBS.items.find(j => j.kind === kind && j.ref === ref);
export const jobHref = j => j.kind === "explainer" ? `#/view/${encodeURIComponent(j.ref)}?explainer` : `#/run/${encodeURIComponent(j.id)}`;

async function poll() {
  clearTimeout(timer);
  if (document.hidden) { timer = setTimeout(poll, 15000); return; }
  try {
    const r = await api("/api/research/active");
    const before = JSON.stringify(JOBS.items.map(j => [j.id, j.status]));
    JOBS.items = r.items || [];
    JOBS.recent = r.recent || [];
    draw();
    if (before !== JSON.stringify(JOBS.items.map(j => [j.id, j.status])))
      window.dispatchEvent(new CustomEvent("airag:jobs", { detail: JOBS }));
  } catch { /* server restarting */ }
  timer = setTimeout(poll, JOBS.items.length ? 2500 : 20000);
}

const what = j => j.kind === "explainer" ? t("act.explainer", { q: j.query }) : t("act.search", { q: j.query });

function draw() {
  const bar = $("#activityBar"), btn = $("#historyBtn");
  const items = JOBS.items;
  const unread = JOBS.recent.some(j => j.status === "done" && (j.finished || 0) > lastSeen);
  btn?.classList.toggle("has-dot", items.length > 0 || unread);
  btn?.classList.toggle("dot-busy", items.length > 0);
  if (!bar) return;
  // the page already shows a search that is running: no need for the bar about that one
  const here = location.hash.startsWith("#/run/") ? decodeURIComponent(location.hash.slice(6)) : "";
  const shown = items.filter(j => j.id !== here);
  if (!shown.length) { bar.hidden = true; return; }
  const running = shown.filter(j => j.status === "running"), queued = shown.length - running.length;
  const main = running[0] || shown[0];
  const extra = [running.length > 1 ? t("act.moreRunning", { n: running.length - 1 }) : "", queued ? t("act.queued", { n: queued }) : ""].filter(Boolean).join(" · ");
  bar.hidden = false;
  bar.innerHTML = `<a class="act-main" href="${jobHref(main)}"><span class="spinner sm"></span>
      <span class="act-t">${h(what(main))}</span>${extra ? `<span class="act-x">${h(extra)}</span>` : ""}</a>
    <button type="button" class="icon-btn sm" id="actCancel" title="${h(t("run.cancel"))}">${icon("x")}</button>`;
  $("#actCancel").onclick = async () => {
    if (!confirm(t("run.cancelConfirm"))) return;
    await api(`/api/research/${encodeURIComponent(main.id)}/cancel`, { method: "POST" }).catch(() => {});
    pokeJobs();
  };
}

export function initActivity() {
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pokeJobs(); });
  window.addEventListener("hashchange", draw);
  poll();
}
