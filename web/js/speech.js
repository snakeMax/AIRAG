// Microphone button: speak your search instead of typing it.
// Phone app: Android's own speech recognition (window.AIRAGNative).
// Browsers: the Web Speech API where the browser has it. Hidden when neither exists.
import { $, $$, icon, toast } from "./util.js";
import { t, uiLang } from "./i18n.js";

const Native = window.AIRAGNative;
const WebSpeech = window.SpeechRecognition || window.webkitSpeechRecognition;
let active = null;   // { input, button, rec? }

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
  if (active) setState(active.button, false);
  active = null;
}

function onResult(text, final) {
  if (!active || !text) return;
  active.input.value = text;
  active.input.dispatchEvent(new Event("input", { bubbles: true }));
  if (final) active.input.focus();
}

window.airagSpeech = ev => {   // called by the Android app
  if (ev.type === "partial") onResult(ev.text, false);
  else if (ev.type === "final") onResult(ev.text, true);
  else if (ev.type === "error") toast(t(ev.text === "permission" ? "mic.denied" : ev.text === "nomatch" ? "mic.nomatch" : "mic.error"), 4000);
  else if (ev.type === "end") finish();
};

function start(input, button) {
  if (active) { const same = active.button === button; stop(); if (same) return; }
  active = { input, button };
  setState(button, true);
  if (Native) {
    Native.startSpeech(lang());
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

/** Adds a microphone button to every search box (when speech input is available). */
export function initSpeech(desktopWindow = false) {
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
