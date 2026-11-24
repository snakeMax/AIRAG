// Live resource graphs (Settings -> System, off by default): a chip under the top bar with a small
// line graph; tap it for three cards (processor or battery, memory, AI tokens per minute).
// Only polls while it is switched on and the page is visible. Colours: the accent colour, or plain grey.
import { $, h, icon, api } from "./util.js";
import { t } from "./i18n.js";

const N = 30;                       // samples kept (every 2 s = the last minute)
const R = { on: false, style: "accent", timer: null, cpu: [], mem: [], memPct: [], batt: [], last: null, open: false };
const Device = window.AIRAGDevice;  // Android: read-only battery status

const phone = () => !!Device;

export function applyResourceSettings(settings) {
  const app = settings?.app || {};
  R.on = !!app.resource_graphs;
  R.style = app.resource_style === "plain" ? "plain" : "accent";
  const bar = $("#resBar");
  if (!bar) return;
  bar.dataset.style = R.style;
  if (!R.on) { stop(); bar.hidden = true; bar.innerHTML = ""; return; }
  bar.hidden = false;
  start();
}

function start() {
  if (R.timer) return;
  const tick = async () => {
    if (!document.hidden) await sample();
    R.timer = setTimeout(tick, 2000);
  };
  tick();
}

function stop() { clearTimeout(R.timer); R.timer = null; }

const push = (arr, v) => { arr.push(v); if (arr.length > N) arr.shift(); };

async function sample() {
  let d;
  try { d = await api("/api/resources"); } catch { return; }
  R.last = d;
  push(R.cpu, d.cpu);
  push(R.mem, d.app_mem_mb);
  push(R.memPct, d.mem_pct);
  if (phone()) {
    try { R.battery = JSON.parse(Device.battery() || "{}"); } catch { R.battery = {}; }
    push(R.batt, R.battery.level ?? null);
  }
  draw();
}

// one SVG line (and soft area) for a series; values scaled to max (or 100 for percentages)
function line(values, max, { w = 200, hgt = 100, dashed = false, area = true } = {}) {
  const vs = values.map(v => (v == null ? null : Math.max(0, v)));
  const top = Math.max(max || 0, ...vs.filter(v => v != null), 1);
  const step = w / Math.max(1, N - 1), off = (N - vs.length) * step;
  const pts = vs.map((v, i) => (v == null ? null : [off + i * step, hgt - (v / top) * (hgt - 6) - 3])).filter(Boolean);
  if (!pts.length) return "";
  const p = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const fill = area && !dashed ? `<polygon class="res-fill" points="${pts[0][0].toFixed(1)},${hgt} ${p} ${pts.at(-1)[0].toFixed(1)},${hgt}"/>` : "";
  return `${fill}<polyline class="res-line${dashed ? " res-line2" : ""}" points="${p}"/>`;
}

function bars(values) {
  const top = Math.max(...values, 1), w = 200 / values.length;
  return values.map((v, i) => { const bh = (v / top) * 96; return `<rect class="res-bar" x="${(i * w + 2).toFixed(1)}" y="${(100 - bh).toFixed(1)}" width="${(w - 4).toFixed(1)}" height="${bh.toFixed(1)}" rx="2"/>`; }).join("");
}

const fmtK = n => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));
const pct = v => (v == null ? "–" : `${Math.round(v)}%`);
const mb = v => (v == null ? "–" : v >= 1024 ? `${(v / 1024).toFixed(1)} GB` : `${Math.round(v)} MB`);

function draw() {
  const bar = $("#resBar"), d = R.last;
  if (!bar || !d) return;
  const first = phone()
    ? (R.battery?.level != null ? `${t("res.battery")} ${R.battery.level}%${R.battery.temp != null ? ` · ${R.battery.temp.toFixed(1)} °C` : ""}` : t("res.app") + " " + mb(d.app_mem_mb))
    : `${t("res.cpuShort")} ${pct(d.cpu)}`;
  const spark = phone() ? line(R.mem, 0, { w: 44, hgt: 16, area: false }) : line(R.cpu, 100, { w: 44, hgt: 16, area: false });
  const chip = `<button type="button" class="res-chip" id="resChip" aria-expanded="${R.open}" aria-controls="resPanel" title="${h(t("res.open"))}">
      <svg viewBox="0 0 44 16" width="44" height="16" aria-hidden="true">${spark}</svg>
      <span>${h(first)}</span><span class="res-dot">·</span><span>${h(t("res.app"))} ${h(mb(d.app_mem_mb))}</span>
      <span class="res-dot">·</span><span>${h(t(d.tasks === 1 ? "res.task" : "res.tasks", { n: d.tasks }))}</span></button>`;
  const card1 = phone()
    ? `<div class="res-card"><div class="res-k">${h(t("res.battery"))}</div><div class="res-v">${R.battery?.level != null ? `${R.battery.level}%` : "–"}
        <small>${R.battery?.temp != null ? `${R.battery.temp.toFixed(1)} °C` : ""}${R.battery?.charging ? ` · ${h(t("res.charging"))}` : ""}</small></div>
        <svg viewBox="0 0 200 100" preserveAspectRatio="none" role="img" aria-label="${h(t("res.battery"))}">${line(R.batt, 100)}</svg>
        <div class="res-note">${h(t("res.last60"))}</div></div>`
    : `<div class="res-card"><div class="res-k">${h(t("res.cpu"))}</div><div class="res-v">${pct(d.cpu)}</div>
        <svg viewBox="0 0 200 100" preserveAspectRatio="none" role="img" aria-label="${h(t("res.cpuAria"))}">${line(R.cpu, 100)}</svg>
        <div class="res-note">${h(t("res.last60"))}</div></div>`;
  const memScale = Math.max(...R.mem.filter(v => v != null), 1) * 1.25;
  const card2 = `<div class="res-card"><div class="res-k">${h(t(d.mem_pct != null ? "res.memBoth" : "res.mem"))}</div>
      <div class="res-v">${mb(d.app_mem_mb)}${d.mem_pct != null ? ` <small>/ ${pct(d.mem_pct)}</small>` : ""}</div>
      <svg viewBox="0 0 200 100" preserveAspectRatio="none" role="img" aria-label="${h(t("res.memAria"))}">${line(R.mem, memScale)}${d.mem_pct != null ? line(R.memPct.map(v => (v == null ? null : (v / 100) * memScale)), memScale, { dashed: true }) : ""}</svg>
      <div class="res-note">${h(t(d.mem_pct != null ? "res.memNote" : "res.last60"))}</div></div>`;
  const tpm = d.tokens_per_min || [];
  const card3 = `<div class="res-card"><div class="res-k">${h(t("res.tokens"))}</div><div class="res-v">${fmtK(d.tokens_now || 0)}</div>
      <svg viewBox="0 0 200 100" preserveAspectRatio="none" role="img" aria-label="${h(t("res.tokensAria"))}">${bars(tpm)}</svg>
      <div class="res-note">${h(t("res.last10"))}</div></div>`;
  bar.innerHTML = chip + (R.open ? `<section class="res-panel" id="resPanel" aria-label="${h(t("res.title"))}">
      <div class="res-head"><b>${h(t("res.title"))}</b><button type="button" class="icon-btn sm" id="resClose" aria-label="${h(t("common.close"))}">${icon("x")}</button></div>
      <div class="res-cards">${card1}${card2}${card3}</div></section>` : "");
  $("#resChip").onclick = () => { R.open = !R.open; draw(); };
  $("#resClose")?.addEventListener("click", () => { R.open = false; draw(); });
}
