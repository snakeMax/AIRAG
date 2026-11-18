// Sound effects. Built-in sounds are in web/sounds/; the user's own clips come from /api/sounds/<name>.
// On the phone the sounds play on the media channel, so the phone's media volume is the master volume;
// on the PC the master slider is AIRAG's own volume.
export const SOUNDS = ["mic_start", "mic_stop", "search_done", "explainer_done", "task_failed"];
const Native = window.AIRAGAudio;
let A = { enabled: true, master: 80, sounds: {} };

export function setAudio(audio) { if (audio) A = audio; }

export const onPhone = () => { try { return typeof Native?.getMediaVolume === "function"; } catch { return false; } };

export function soundUrl(name, audio = A) {
  const file = audio.sounds?.[name]?.file;
  return file ? `/api/sounds/${name}?v=${encodeURIComponent(file)}` : `sounds/${name.replace(/_/g, "-")}.wav`;
}

/** Plays a sound effect. `opts` can override the clip (a data: URL being previewed) and the volume (0-100). */
export function play(name, opts = {}) {
  const audio = opts.audio || A;
  if (!opts.force && audio.enabled === false) return;
  const per = opts.vol ?? audio.sounds?.[name]?.vol ?? 70;
  const master = onPhone() ? 100 : (opts.master ?? audio.master ?? 80);
  const v = Math.max(0, Math.min(1, (per / 100) * (master / 100)));
  if (v <= 0) return;
  try {
    const el = new Audio(opts.src || soundUrl(name, audio));
    el.volume = v;
    el.play().catch(() => { /* autoplay blocked or file missing: stay quiet */ });
  } catch { /* no audio support */ }
}

// The phone's media volume (0-100), used as the master volume on Android.
export function mediaVolume() { try { return Native.getMediaVolume(); } catch { return null; } }
export function setMediaVolume(v) { try { Native.setMediaVolume(Math.round(v)); } catch { /* old app */ } }
