// Date range filter: a chip that opens a small popover with "from" and "to" date pickers.
// Used on the home page (for the next search) and above results (search again with the range).
import { $, h, icon } from "./util.js";
import { t, uiLang } from "./i18n.js";

export const emptyRange = () => ({ from: "", to: "" });
export const hasRange = d => !!(d && (d.from || d.to));

export function fmtRange(d) {
  if (!hasRange(d)) return t("date.any");
  const f = s => new Date(s + "T12:00:00").toLocaleDateString(uiLang(), { day: "numeric", month: "short", year: "numeric" });
  if (d.from && d.to) return d.from === d.to ? f(d.from) : `${f(d.from)} – ${f(d.to)}`;
  return d.from ? t("date.since", { d: f(d.from) }) : t("date.until", { d: f(d.to) });
}

export function chipHtml(id, d) {
  return `<button type="button" class="check-chip date-chip ${hasRange(d) ? "on" : ""}" id="${id}" title="${h(t("date.tip"))}">${icon("clock")}<span>${h(fmtRange(d))}</span></button>`;
}

let open = null;
export function closeDatePicker() { open?.remove(); open = null; }

/** Shows the picker under `anchor`; calls onApply({from, to}) when the user applies or clears. */
export function openDatePicker(anchor, current, onApply, applyLabel = t("date.apply")) {
  if (open) { const was = open.dataset.for === anchor.id; closeDatePicker(); if (was) return; }
  const today = new Date().toISOString().slice(0, 10);
  const pop = document.createElement("div");
  pop.className = "date-pop";
  pop.dataset.for = anchor.id;
  pop.innerHTML = `
    <div class="dp-presets">
      ${[["week", 7], ["month", 31], ["year", 365]].map(([k, n]) => `<button type="button" class="btn sm ghost" data-days="${n}">${h(t("date.last." + k))}</button>`).join("")}
    </div>
    <div class="dp-row">
      <label>${h(t("date.from"))}<input type="date" class="input" id="dpFrom" max="${today}" value="${h(current?.from || "")}"></label>
      <label>${h(t("date.to"))}<input type="date" class="input" id="dpTo" max="${today}" value="${h(current?.to || "")}"></label>
    </div>
    <div class="dp-foot">
      <button type="button" class="btn sm ghost" id="dpClear">${h(t("date.clear"))}</button>
      <button type="button" class="btn sm primary" id="dpApply">${h(applyLabel)}</button>
    </div>`;
  document.body.appendChild(pop);
  open = pop;
  const r = anchor.getBoundingClientRect();
  const w = Math.min(320, window.innerWidth - 16);
  pop.style.width = w + "px";
  pop.style.left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 8)) + "px";
  pop.style.top = (r.bottom + window.scrollY + 8) + "px";
  const from = $("#dpFrom", pop), to = $("#dpTo", pop);
  pop.querySelectorAll("[data-days]").forEach(b => (b.onclick = () => {
    const d = new Date(Date.now() - +b.dataset.days * 864e5);
    from.value = d.toISOString().slice(0, 10);
    to.value = "";
  }));
  $("#dpClear", pop).onclick = () => { closeDatePicker(); onApply(emptyRange()); };
  $("#dpApply", pop).onclick = () => {
    let a = from.value, b = to.value;
    if (a && b && a > b) [a, b] = [b, a];
    closeDatePicker();
    onApply({ from: a, to: b });
  };
  setTimeout(() => document.addEventListener("pointerdown", function away(e) {
    if (open !== pop) { document.removeEventListener("pointerdown", away); return; }
    if (pop.contains(e.target) || anchor.contains(e.target)) return;
    closeDatePicker();
    document.removeEventListener("pointerdown", away);
  }), 0);
}
