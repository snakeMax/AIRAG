// Microphone button: speak your search instead of typing it.
// Phone app: Android's own speech recognition (window.AIRAGNative).
// Browsers: the Web Speech API where the browser has it. Hidden when neither exists.
import { $, $$, icon, toast } from "./util.js";
import { t, uiLang } from "./i18n.js";
import { play } from "./sound.js";

const Native = window.AIRAGNative;
const WebSpeech = window.SpeechRecognition || window.webkitSpeechRecognition;
let active = null;   // { input, button, rec? }
let autoSearch = true;

/** Settings -> Defaults: start the search as soon as speaking ends. */
export function setAutoSearch(on) { autoSearch = on !== false; }

// The desktop window (Edge WebView2) has the Web Speech object but no working recognition service.
export function speechAvailable(desktopWindow = false) {
  try { if (Native?.speechAvailable()) return true; } catch { /* old app */ }
  return !!WebSpeech && !desktopWindow;
}

function lang() {
  const l = navigator.language || uiLang();
  return l.includes("-") ? l : `${l}-${l.toUpperCase()}`;
}

function setState(button, on) {
  button.classList.toggle("listening", on);
  button.title = t(on ? "mic.stop" : "mic.start");
}

function stop() {
  if (!active) return;
  try { Native ? Native.stopSpeech() : active.rec?.stop(); } catch { /* already stopped */ }
}

function finish() {
  if (active) { setState(active.button, false); play("mic_stop"); }
  active = null;
}

function onResult(text, final) {
  if (!active || !text) return;
  active.input.value = text;
  active.input.dispatchEvent(new Event("input", { bubbles: true }));
  if (!final) return;
  if (active.onFinal) { const cb = active.onFinal; cb(text); return; }
  active.input.focus();
  if (autoSearch) {
    const form = active.input.closest("form");
    setTimeout(() => form?.requestSubmit(), 250);   // after the final words are in the box
  }
}

window.airagSpeech = ev => {   // called by the Android app
  if (ev.type === "partial") onResult(ev.text, false);
  else if (ev.type === "final") onResult(ev.text, true);
  else if (ev.type === "error") toast(t(ev.text === "permission" ? "mic.denied" : ev.text === "nomatch" ? "mic.nomatch" : "mic.error"), 4000);
  else if (ev.type === "end") finish();
};

function start(input, button, onFinal = null) {
  if (active) { const same = active.button === button; stop(); if (same) return; }
  active = { input, button, onFinal };
  setState(button, true);
  play("mic_start");
  if (Native) {
    Native.startSpeech((window.__airagKey || ""), lang());   // the key proves the call comes from AIRAG's own page
    return;
  }
  const rec = new WebSpeech();
  active.rec = rec;
  rec.lang = lang();
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  rec.onresult = e => {
    const r = e.results[e.results.length - 1];
    onResult(Array.from(e.results).map(x => x[0].transcript).join(" ").trim(), r.isFinal);
  };
  rec.onerror = e => toast(t(e.error === "not-allowed" || e.error === "service-not-allowed" ? "mic.denied"
    : e.error === "no-speech" ? "mic.nomatch" : "mic.error"), 4000);
  rec.onend = finish;
  try { rec.start(); } catch { finish(); toast(t("mic.error"), 4000); }
}

let desktopWin = false;

/** A microphone button for any text box. onFinal(text) runs when speaking ends (else: the box's form is sent,
 *  if search-after-speaking is on). Returns null when speech input isn't available here. */
export function micButton(input, onFinal = null) {
  if (!speechAvailable(desktopWin)) return null;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "mic-btn";
  b.innerHTML = icon("mic");
  b.title = t("mic.start");
  b.setAttribute("aria-label", t("mic.start"));
  b.onclick = () => start(input, b, onFinal);
  return b;
}

/** Adds a microphone button to every search box (when speech input is available). */
export function initSpeech(desktopWindow = false) {
  desktopWin = desktopWindow;
  if (!speechAvailable(desktopWindow)) return;
  $$("form.searchbox").forEach(form => {
    if (form.querySelector(".mic-btn")) return;
    const input = form.querySelector("input");
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mic-btn";
    b.innerHTML = icon("mic");
    b.title = t("mic.start");
    b.setAttribute("aria-label", t("mic.start"));
    b.onclick = () => start(input, b);
    const go = form.querySelector(".sb-go");
    go ? form.insertBefore(b, go) : form.appendChild(b);
  });
}
