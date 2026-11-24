// Snap panels: floating boxes (Answers, Calculator, and later the explainer window and others) can be
// dragged by their grip and snap into fixed places, growing or shrinking to fit, so nothing overlaps.
//
// Computers: four snap areas (left/right column, top/bottom half). While a box is dragged the areas glow;
//   the one under the pointer is highlighted and says the box will snap there and resize to fit.
//   One box in a column fills it; two share it (top and bottom). Dropping on a taken area swaps the boxes.
// Phones (layout A): one column above the menu button. While the finger is down the column already makes
//   room: a dashed "will snap here" slot moves between the other boxes, so you see where it lands first.
// Both: minimize turns a box into a pill in the tray ("Answers: “Yes: crossings…”"); tap the pill to bring
//   it back with its content as it was. X closes the box as before.
import { $, $$, h, icon } from "./util.js";
import { t } from "./i18n.js";

const KEY = "airag.snap";
const phone = () => matchMedia("(max-width: 720px)").matches;
const B = new Map();                  // id -> { el, opts, slot, min }
let saved = {};
try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { saved = {}; }
let order = Array.isArray(saved.order) ? saved.order : [];   // phone column order (top to bottom)
const save = () => {
  const slots = Object.fromEntries([...B].filter(([, b]) => b.slot).map(([id, b]) => [id, b.slot]));
  try { localStorage.setItem(KEY, JSON.stringify({ slots, order })); } catch { /* storage off */ }
};

/**
 * Make a floating box snappable.
 * opts: { title: () => string, head: el => element where grip/minimize go (re-added if the box redraws),
 *         slot: default computer slot "right-full" | null (null = stays where its own code put it until dragged),
 *         summary: el => short text for the minimized pill }
 */
export function registerSnap(id, el, opts) {
  if (!el || B.has(id)) return;
  const b = { el, opts, slot: saved.slots?.[id] ?? opts.slot ?? null, min: false };
  B.set(id, b);
  el.classList.add("snap-box");
  el.dataset.snap = id;
  if (!order.includes(id)) order.push(id);
  decorate(b);
  // the box's own code shows/hides it (hidden attribute) and may redraw its content
  new MutationObserver(muts => {
    if (muts.some(m => m.type === "attributes")) {
      if (!el.hidden && b.min) setMin(b, false);
      layout();
    }
    if (muts.some(m => m.type === "childList")) decorate(b);
  }).observe(el, { attributes: true, attributeFilter: ["hidden"], childList: true, subtree: false });
  layout();
}

function decorate(b) {
  const head = b.opts.head(b.el);
  if (!head || head.querySelector(".snap-grip")) return;
  head.classList.add("snap-head");
  head.insertAdjacentHTML("afterbegin", `<span class="snap-grip" aria-hidden="true"></span>`);
  const close = head.querySelector("[data-x], .icon-btn");
  const minBtn = document.createElement("button");
  minBtn.type = "button";
  minBtn.className = "icon-btn sm snap-min-btn";
  minBtn.setAttribute("aria-label", t("snap.minimize"));
  minBtn.title = t("snap.minimize");
  minBtn.innerHTML = icon("minus");
  minBtn.onclick = e => { e.stopPropagation(); setMin(b, true); };
  if (close) close.before(minBtn); else head.appendChild(minBtn);
  head.addEventListener("pointerdown", e => startDrag(e, b));
}

// ---------------------------------------------------------------- minimize / tray
function setMin(b, on) {
  b.min = on;
  b.el.classList.toggle("snap-minimized", on);
  drawTray();
  layout();
}

function drawTray() {
  let tray = $("#snapTray");
  if (!tray) {
    tray = Object.assign(document.createElement("div"), { id: "snapTray", className: "snap-tray" });
    tray.setAttribute("aria-label", t("snap.tray"));
    document.body.appendChild(tray);
  }
  const mins = [...B].filter(([, b]) => b.min && !b.el.hidden);
  tray.hidden = !mins.length;
  tray.innerHTML = mins.map(([id, b]) => {
    const s = (b.opts.summary?.(b.el) || "").replace(/\s+/g, " ").trim();
    const text = s ? `${b.opts.title()}: “${s.slice(0, 40)}${s.length > 40 ? "…" : ""}”` : b.opts.title();
    return `<button type="button" class="snap-pill" data-unmin="${h(id)}" title="${h(t("snap.restore"))}">${h(text)}</button>`;
  }).join("");
  $$("[data-unmin]", tray).forEach(p => (p.onclick = () => setMin(B.get(p.dataset.unmin), false)));
}

// ---------------------------------------------------------------- layout
const GAP = 14;
// below the top bar (and the notice banner when it shows)
const top = () => Math.max(64, Math.round(($("header")?.getBoundingClientRect().bottom || 56) + 8));
function colWidth() { return Math.min(400, Math.max(280, innerWidth * 0.28)); }

function slotRect(side, pos) {
  const w = colWidth(), x = side === "left" ? GAP : innerWidth - GAP - w;
  const T = top(), full = innerHeight - T - GAP;
  const half = (full - GAP) / 2;
  const y = pos === "bottom" ? T + half + GAP : T;
  return { left: x, top: y, width: w, height: pos === "full" ? full : half };
}

const visible = () => [...B].filter(([, b]) => !b.el.hidden && !b.min);

export function layout() {
  const stack = $("#rtStack");
  if (phone()) {
    document.body.classList.remove("snap-l", "snap-r");
    for (const [, b] of B) clearPos(b.el);
    if (stack) {
      // layout A: the boxes in their column order, above the menu (which stays last)
      const dock = $("#rtDock");
      order.filter(id => B.has(id)).forEach(id => stack.insertBefore(B.get(id).el, dock && dock.parentElement === stack ? dock : null));
    }
    return;
  }
  // computers: every snapped box gets its area; a column with one box gives it the full height
  const sides = { left: [], right: [] };
  for (const [id, b] of visible()) {
    if (!b.slot) continue;
    const [side, pos] = b.slot.split("-");
    sides[side]?.push([id, b, pos]);
  }
  for (const side of ["left", "right"]) {
    const list = sides[side];
    if (list.length === 1) place(list[0][1].el, slotRect(side, "full"));
    else {
      list.sort((a, b2) => (a[2] === "bottom") - (b2[2] === "bottom"));
      list.forEach(([, b], i) => place(b.el, slotRect(side, i === 0 ? "top" : "bottom")));
    }
  }
  for (const [, b] of B) if (!b.slot) clearPos(b.el);
  document.body.classList.toggle("snap-l", sides.left.length > 0);
  document.body.classList.toggle("snap-r", sides.right.length > 0);
}

function place(el, r) {
  el.classList.add("snap-placed");
  Object.assign(el.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px", right: "auto", bottom: "auto" });
}
function clearPos(el) {
  if (!el.classList.contains("snap-placed")) return;
  el.classList.remove("snap-placed");
  for (const k of ["left", "top", "width", "height", "right", "bottom"]) el.style[k] = "";
}

addEventListener("resize", () => layout());

// ---------------------------------------------------------------- dragging
let D = null;

function startDrag(e, b) {
  if (e.button > 0 || e.target.closest("button, a, input, select, textarea")) return;
  e.preventDefault();
  const r = b.el.getBoundingClientRect();
  D = { b, dx: e.clientX - r.left, dy: e.clientY - r.top, w: r.width, h: Math.min(r.height, phone() ? 160 : r.height),
        startX: e.clientX, startY: e.clientY, moved: false, target: null, pointer: e.pointerId };
  b.el.setPointerCapture?.(e.pointerId);
  b.el.addEventListener("pointermove", onMove);
  b.el.addEventListener("pointerup", onUp, { once: true });
  b.el.addEventListener("pointercancel", onUp, { once: true });
}

function lift() {
  const { b } = D;
  D.moved = true;
  b.el.classList.add("snap-dragging");
  if (phone()) {
    // the dashed slot takes the box's place in the column straight away
    D.ph = Object.assign(document.createElement("div"), { className: "snap-slot-ph" });
    D.ph.style.height = Math.min(D.h, 140) + "px";
    D.ph.innerHTML = `${icon("arrowDown")}<span>${h(t("snap.willSnap", { b: b.opts.title() }))}</span>`;
    b.el.before(D.ph);
  } else {
    const ov = Object.assign(document.createElement("div"), { className: "snap-overlay", id: "snapOverlay" });
    ov.innerHTML = ["left-top", "left-bottom", "right-top", "right-bottom"].map(s => {
      const [side, pos] = s.split("-"), r = slotRect(side, pos);
      return `<div class="snap-area" data-area="${s}" style="left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px"><span>${h(t("snap.willSnapResize", { b: b.opts.title() }))}</span></div>`;
    }).join("");
    document.body.appendChild(ov);
  }
  Object.assign(b.el.style, { position: "fixed", width: D.w + "px", height: D.h + "px", right: "auto", bottom: "auto", zIndex: 80 });
}

function onMove(e) {
  if (!D) return;
  if (!D.moved) {
    if (Math.hypot(e.clientX - D.startX, e.clientY - D.startY) < 6) return;
    lift();
  }
  const { b } = D;
  b.el.style.left = Math.min(innerWidth - 40, Math.max(-D.w + 40, e.clientX - D.dx)) + "px";
  b.el.style.top = Math.min(innerHeight - 40, Math.max(0, e.clientY - D.dy)) + "px";
  if (phone()) movePlaceholder(e.clientY);
  else {
    const areas = $$(".snap-area");
    let best = null, bestD = Infinity;
    for (const a of areas) {
      const r = a.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      const d = inside ? 0 : Math.hypot(e.clientX - (r.left + r.width / 2), e.clientY - (r.top + r.height / 2));
      if (d < bestD) { bestD = d; best = a; }
    }
    areas.forEach(a => a.classList.toggle("on", a === best));
    D.target = best?.dataset.area || null;
  }
}

// phones: the slot moves to wherever the finger is, between the other boxes, before the finger lifts
function movePlaceholder(y) {
  const stack = $("#rtStack"), dock = $("#rtDock");
  if (!stack || !D.ph) return;
  const others = [...stack.children].filter(c => c !== D.b.el && c !== D.ph && c !== dock && c.classList.contains("snap-box") && !c.hidden && !c.classList.contains("snap-minimized"));
  let before = dock && dock.parentElement === stack ? dock : null;
  for (const o of others) {
    const r = o.getBoundingClientRect();
    if (y < r.top + r.height / 2) { before = o; break; }
  }
  if (D.ph.nextElementSibling !== before) stack.insertBefore(D.ph, before);
}

function onUp() {
  if (!D) return;
  const { b } = D;
  b.el.removeEventListener("pointermove", onMove);
  b.el.classList.remove("snap-dragging");
  for (const k of ["position", "width", "height", "right", "bottom", "zIndex", "left", "top"]) b.el.style[k] = "";
  if (D.moved) {
    if (phone() && D.ph) {
      D.ph.replaceWith(b.el);
      const stack = $("#rtStack");
      order = [...stack.children].map(c => c.dataset?.snap).filter(Boolean).concat(order.filter(id => ![...stack.children].some(c => c.dataset?.snap === id)));
    } else if (D.target) {
      const [side, pos] = D.target.split("-");
      // whoever is in that column keeps the other half (or swaps with this box)
      const prev = b.slot;
      for (const [id, o] of visible()) {
        if (o === b || !o.slot || !o.slot.startsWith(side)) continue;
        o.slot = prev && prev.startsWith(side) ? prev : `${side}-${pos === "top" ? "bottom" : "top"}`;
        void id;
      }
      b.slot = `${side}-${pos}`;
    }
    save();
  }
  $("#snapOverlay")?.remove();
  D.ph?.remove();
  D = null;
  layout();
}
