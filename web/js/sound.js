// Sound effects. Built-in sounds are in web/sounds/; the user's own clips come from /api/sounds/<name>.
// On the phone the sounds play on the media channel, so the phone's media volume is the master volume;
// on the PC the master slider is AIRAG's own volume.
export const SOUNDS = ["mic_start", "mic_stop", "search_done", "explainer_done", "task_failed"];
const Native = window.AIRAGAudio;
let A = { enabled: true, master: 80, sounds: {} };

export function setAudio(audio) { if (audio) A = audio; }

export const onPhone = () => { try { return typeof Native?.getMediaVolume === "function"; } catch { return false; } };

// /api/sounds/<name> serves your own clip, or the built-in sound when there is none
// (?builtin=1 forces the built-in one, used for previews before Save)
export function soundUrl(name, audio = A, builtin = false) {
  const file = audio.sounds?.[name]?.file;
  return `/api/sounds/${name}?${builtin ? "builtin=1" : "v=" + encodeURIComponent(file || "default")}`;
}

/** Plays a sound effect. `opts` can override the clip (a data: URL being previewed) and the volume (0-100).
 *  Returns the audio element (or null), so a preview button can show pause/stop while it plays. */
export function play(name, opts = {}) {
  const audio = opts.audio || A;
  if (!opts.force && audio.enabled === false) return null;
  const per = opts.vol ?? audio.sounds?.[name]?.vol ?? 70;
  const master = onPhone() ? 100 : (opts.master ?? audio.master ?? 80);
  const v = Math.max(0, Math.min(1, (per / 100) * (master / 100)));
  if (v <= 0) return null;
  try {
    const el = new Audio(opts.src || soundUrl(name, audio));
    el.volume = v;
    el.play().catch(e => { console.warn("sound not played:", name, e?.message); el.dispatchEvent(new Event("ended")); });
    return el;
  } catch { return null; }
}

// The phone's media volume (0-100), used as the master volume on Android.
export function mediaVolume() { try { return Native.getMediaVolume(); } catch { return null; } }
export function setMediaVolume(v) { try { Native.setMediaVolume((window.__airagKey || ""), Math.round(v)); } catch { /* old app */ } }
