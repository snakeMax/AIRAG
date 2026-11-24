// Appearance: light/dark/system, colour palette and accent colour.
// Saved in localStorage (instant on start) and in settings (shared by desktop and browser mode).

export const PALETTES = {
  zinc: { light: ["#f4f4f5", "#ffffff", "#e4e4e7", "#52525b"], dark: ["#0f0f11", "#18181b", "#2a2a2f", "#a5a5ad"] },
  slate: { light: ["#f1f4f8", "#ffffff", "#e2e8f0", "#475569"], dark: ["#0b1120", "#111827", "#1f2a3c", "#a3b1c6"] },
  stone: { light: ["#f5f5f3", "#ffffff", "#e7e5e4", "#57534e"], dark: ["#110f0e", "#1c1917", "#2e2926", "#a8a29e"] },
  graphite: { light: ["#e9e9eb", "#f7f7f8", "#d9d9de", "#4a4a52"], dark: ["#000000", "#111113", "#232326", "#a0a0a8"] },
};

export const ACCENTS = {
  graphite: null, // palette default (near-black in light, near-white in dark)
  blue: "#2563eb",
  teal: "#0d9488",
  green: "#16a34a",
  amber: "#d97706",
  rose: "#e11d48",
  violet: "#7c3aed",
};

// Text (Look & sound -> Text): interface font, article font, text size
export const UI_FONTS = {
  system: null,       // the built-in stack (Inter / system UI)
  serif: '"Charter", "Iowan Old Style", "Source Serif Pro", Georgia, Cambria, serif',
  rounded: 'ui-rounded, "SF Pro Rounded", "Nunito", "Varela Round", "Segoe UI", system-ui, sans-serif',
  mono: 'ui-monospace, "Cascadia Code", "SF Mono", Consolas, monospace',
  easy: '"Atkinson Hyperlegible", "Inter", system-ui, sans-serif',
};
export const ARTICLE_FONTS = { serif: null, same: "same", easy: UI_FONTS.easy };
export const TEXT_SIZES = [0.88, 0.94, 1, 1.12, 1.25];

const KEY = "airag.appearance";
const media = matchMedia("(prefers-color-scheme: dark)");
let current = { theme: "system", palette: "zinc", accent: "graphite", uiFont: "system", articleFont: "serif", textSize: 2 };
let onChange = null;

export function loadLocal() {
  try { Object.assign(current, JSON.parse(localStorage.getItem(KEY) || "{}")); } catch { /* ignore */ }
  apply();
  media.addEventListener?.("change", () => current.theme === "system" && apply());
  return current;
}

export const getAppearance = () => ({ ...current });
export const effectiveTheme = () => (current.theme === "system" ? (media.matches ? "dark" : "light") : current.theme);
export function onAppearanceChange(fn) { onChange = fn; }

export function setAppearance(patch, save = true) {
  Object.assign(current, patch);
  apply();
  try { localStorage.setItem(KEY, JSON.stringify(current)); } catch { /* ignore */ }
  if (save && onChange) onChange(getAppearance(), effectiveTheme());
}

function saturation(hex) {
  const [r, g, b] = hex.replace("#", "").match(/.{2}/g).map(x => parseInt(x, 16) / 255);
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  return mx === mn ? 0 : (mx - mn) / (1 - Math.abs(2 * l - 1));
}

function contrastText(hex) {
  const m = hex.replace("#", "").match(/.{2}/g);
  if (!m) return "#ffffff";
  const [r, g, b] = m.map(x => parseInt(x, 16) / 255).map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.45 ? "#111113" : "#ffffff";
}

function apply() {
  const root = document.documentElement;
  root.dataset.theme = effectiveTheme();
  root.dataset.palette = PALETTES[current.palette] ? current.palette : "zinc";
  const hex = ACCENTS[current.accent] !== undefined ? ACCENTS[current.accent] : current.accent;
  // recording colour: the accent when it's a real colour, bright red for grey/desaturated accents
  root.style.setProperty("--rec", hex && /^#[0-9a-f]{6}$/i.test(hex) && saturation(hex) > 0.25 ? hex : "#ef4444");
  // the mark that keeps selected text visible after the phone drops its own selection
  root.style.setProperty("--mark", hex && /^#[0-9a-f]{6}$/i.test(hex) && saturation(hex) > 0.25 ? hex : "#3b82f6");
  const ui = UI_FONTS[current.uiFont];
  if (ui) root.style.setProperty("--ui", ui); else root.style.removeProperty("--ui");
  const art = ARTICLE_FONTS[current.articleFont];
  if (art === "same") root.style.setProperty("--article-font", "var(--ui)");
  else if (art) root.style.setProperty("--article-font", art);
  else root.style.removeProperty("--article-font");
  const size = TEXT_SIZES[current.textSize] ?? 1;
  if (size === 1) root.style.removeProperty("--text-scale"); else root.style.setProperty("--text-scale", String(size));
  if (hex && /^#[0-9a-f]{6}$/i.test(hex)) {
    root.style.setProperty("--accent", hex);
    root.style.setProperty("--accent-text", contrastText(hex));
  } else {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--accent-text");
  }
}
