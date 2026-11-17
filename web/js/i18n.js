// Translations. Strings live in web/i18n/<code>.json; anything missing falls back to English.
// Use t("key", {var: value}) in code and data-i18n / data-i18n-title / data-i18n-ph attributes in HTML.

let dict = {}, fallback = {}, current = "en";
let available = [{ code: "en", native: "English" }];

const ALIASES = { no: "nb", nn: "nb", "zh-cn": "zh", "zh-hans": "zh", "zh-sg": "zh" };

export function normalize(code) {
  if (!code) return null;
  const c = code.toLowerCase().replace("_", "-");
  if (ALIASES[c]) return ALIASES[c];
  const base = c.split("-")[0];
  return ALIASES[base] || base;
}

export function systemLanguage() {
  const codes = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"]).map(normalize);
  return codes.find(c => available.some(l => l.code === c)) || "en";
}

async function load(code) {
  try {
    const r = await fetch(`/static/i18n/${code}.json`, { cache: "no-cache" });
    return r.ok ? await r.json() : {};
  } catch { return {}; }
}

export async function initI18n(pref, languages) {
  if (languages?.length) available = languages.filter(l => l.ui);
  current = pref && pref !== "auto" && available.some(l => l.code === pref) ? pref : systemLanguage();
  fallback = await load("en");
  dict = current === "en" ? fallback : await load(current);
  document.documentElement.lang = current;
  applyI18n(document);
}

export const uiLang = () => current;
export const uiLanguages = () => available;

export function t(key, vars) {
  let s = dict[key] ?? fallback[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(v);
  return s;
}

export function has(key) {
  return key in dict || key in fallback;
}

export function applyI18n(root) {
  root.querySelectorAll("[data-i18n]").forEach(el => (el.textContent = t(el.dataset.i18n)));
  root.querySelectorAll("[data-i18n-title]").forEach(el => (el.title = t(el.dataset.i18nTitle)));
  root.querySelectorAll("[data-i18n-ph]").forEach(el => (el.placeholder = t(el.dataset.i18nPh)));
}
