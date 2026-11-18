// Read aloud (text to speech). Phone app: Android's voices through window.AIRAGAudio.
// Browsers and the PC window: the Web Speech API (speechSynthesis).
// Text is read one sentence at a time, and the spoken word is tracked, so Pause + Resume carries on from the
// word where it stopped (Stop starts over).
const Native = window.AIRAGAudio;
const Web = window.speechSynthesis;
let S = { voice: "female", rate: 1.0 };
let voiceList = [];
let job = null;   // { parts, i, pos, onState, lang }  pos = where in parts[i] the current word starts
let seq = 0;

export function setSpeech(s) { if (s) S = s; }
export const ttsAvailable = () => !!(Native?.ttsSpeak || Web);

// Known voice names. Android voice names often carry "#male_1" / "#female_2";
// Google's English voices have short codes; Windows/Edge voices have first names.
const FEMALE = /female|#f|zira|hazel|susan|aria|jenny|michelle|sonia|libby|natasha|clara|emma|ava|samantha|victoria|karen|moira|tessa|fiona|iselin|pernille|hedda|nora|katja|hortense|denise|helena|laura|elvira|sabina|nanami|ayumi|haruka|xiaoxiao|huihui|yaoyao|-sfg|-tpf|-tpc|-iob|-iog|-cfs/i;
const MALE = /(^|[^e])male|#m|david|mark|george|ryan|guy|davis|tony|james|william|thomas|daniel|alex|fred|finn|jon|christian|stefan|conrad|henri|paul|alvaro|pablo|keita|ichiro|yunxi|kangkang|-iol|-iom|-tpd|-cmj|-tfs/i;

export function genderOf(name = "") {
  const f = FEMALE.test(name), m = MALE.test(name);
  return f && !m ? "female" : m && !f ? "male" : "";
}

/** Voices as [{id, name, lang, gender}], loaded once. */
export function loadVoices() {
  return new Promise(resolve => {
    if (Native?.ttsVoices) {
      window.airagTtsVoices = resolve;
      try { Native.ttsVoices(); } catch { resolve([]); }
      setTimeout(() => resolve(voiceList), 4000);
      return;
    }
    if (!Web) return resolve([]);
    const take = () => {
      voiceList = Web.getVoices().map(v => ({ id: v.voiceURI || v.name, name: v.name, lang: v.lang, gender: genderOf(v.name), web: v }));
      return voiceList;
    };
    if (take().length) return resolve(voiceList);
    Web.onvoiceschanged = () => resolve(take());
    setTimeout(() => resolve(take()), 2000);
  });
}

function pick(lang) {
  const base = (lang || "en").slice(0, 2).toLowerCase();
  const same = voiceList.filter(v => (v.lang || "").toLowerCase().replace("_", "-").startsWith(base));
  const pool = same.length ? same : voiceList;
  if (S.voice && S.voice !== "female" && S.voice !== "male") {
    const exact = voiceList.find(v => v.id === S.voice);
    if (exact) return exact;
  }
  const want = S.voice === "male" ? "male" : "female";
  // prefer installed (non-network) voices of the wanted kind
  return pool.find(v => v.gender === want && !v.network) || pool.find(v => v.gender === want) || pool[0] || null;
}

window.airagTts = ev => {   // called by the Android app
  if (ev.type === "voices") {
    voiceList = (ev.voices || []).map(v => ({ ...v, gender: genderOf(v.name) }));
    window.airagTtsVoices?.(voiceList);
    window.airagTtsVoices = null;
    return;
  }
  if (!job || ev.id !== job.id) return;
  if (ev.type === "range") job.pos = (job.base || 0) + (Number(ev.detail) || 0);
  else if (ev.type === "done") next();
  else if (ev.type === "error") { const j = job; job = null; j.onState("error"); }
};

function splitText(text) {
  const out = [];
  for (const line of text.split(/\n+/)) {
    // sentences: after . ! ? (and the CJK ones) followed by a space or the end
    for (const s of line.split(/(?<=[.!?。!?])\s+/)) {
      const p = s.replace(/\s+/g, " ").trim();
      if (!p) continue;
      if (p.length <= 400) { out.push(p); continue; }
      // a very long "sentence" (lists, tables): break at commas/spaces near 400 characters
      let rest = p;
      while (rest.length > 400) {
        let cut = Math.max(rest.lastIndexOf(", ", 400), rest.lastIndexOf(" ", 400));
        if (cut < 100) cut = 400;
        out.push(rest.slice(0, cut + 1).trim());
        rest = rest.slice(cut + 1);
      }
      if (rest.trim()) out.push(rest.trim());
    }
  }
  return out;
}

function next() {
  if (!job) return;
  job.i++;
  job.pos = 0;
  if (job.i >= job.parts.length) { const j = job; job = null; j.onState("ended"); return; }
  say();
}

function say() {
  // after a pause, carry on from the start of the word that was being spoken
  const full = job.parts[job.i];
  let from = Math.max(0, Math.min(job.pos || 0, full.length - 1));
  while (from > 0 && /\S/.test(full[from - 1])) from--;
  job.base = from;
  const part = full.slice(from);
  job.id = `tts${++seq}`;
  const v = pick(job.lang);
  if (Native?.ttsSpeak) {
    Native.ttsSpeak((window.__airagKey || ""), part, v?.id || "", job.lang || "", Number(S.rate) || 1, job.id);
    return;
  }
  const u = new SpeechSynthesisUtterance(part);
  if (v?.web) u.voice = v.web;
  u.lang = v?.lang || job.lang || "";
  u.rate = Number(S.rate) || 1;
  const id = job.id;
  u.onboundary = e => { if (job?.id === id && e.name !== "sentence") job.pos = job.base + (e.charIndex || 0); };
  u.onend = () => { if (job?.id === id) next(); };
  u.onerror = e => { if (job?.id === id && e.error !== "interrupted" && e.error !== "canceled") { job = null; } };
  Web.speak(u);
}

/** Starts reading `text`. onState gets "playing" | "paused" | "ended" | "error". */
export async function speak(text, lang, onState = () => {}) {
  stop();
  if (!voiceList.length) await loadVoices();
  job = { parts: splitText(text), i: 0, pos: 0, onState, lang };
  if (!job.parts.length) { job = null; return; }
  onState("playing");
  say();
}

export function pause() {
  if (!job) return;
  const j = job;
  j.paused = true;
  job.id = "paused";
  try { Native?.ttsStop ? Native.ttsStop() : Web.cancel(); } catch { /* */ }
  j.onState("paused");
}

export function resume() {
  if (!job || !job.paused) return;
  job.paused = false;
  job.onState("playing");
  say();   // carries on from the word where it was paused
}

export function stop() {
  const j = job;
  job = null;
  try { Native?.ttsStop ? Native.ttsStop() : Web?.cancel(); } catch { /* */ }
  j?.onState("ended");
}

export const speaking = () => !!job && !job.paused;
export const paused = () => !!job?.paused;
