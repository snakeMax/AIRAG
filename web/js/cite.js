// Citations in APA (7th), MLA (9th) and BibTeX, from what AIRAG knows about each source.
const MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."];

function parts(s) {
  const d = s.published || s.date || "";
  const m = String(d).match(/(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/);
  return {
    title: (s.title || s.url || "").trim(),
    site: s.site_name || s.domain || "",
    author: (s.author || "").trim(),
    year: m ? m[1] : "",
    month: m && m[2] ? +m[2] : 0,
    day: m && m[3] ? +m[3] : 0,
    url: s.url || "",
  };
}

const accessed = () => new Date();

export function apa(s) {
  const p = parts(s);
  const who = p.author || p.site;
  const when = p.year ? `(${p.year}${p.month ? `, ${new Date(2000, p.month - 1).toLocaleString("en", { month: "long" })}${p.day ? " " + p.day : ""}` : ""})` : "(n.d.)";
  return `${who}. ${when}. ${p.title}.${p.author && p.site ? ` ${p.site}.` : ""} ${p.url}`.replace(/\.\./g, ".");
}

export function mla(s) {
  const p = parts(s);
  const a = accessed();
  const date = p.year ? `${p.day ? p.day + " " : ""}${p.month ? MONTHS[p.month - 1] + " " : ""}${p.year}, ` : "";
  return `${p.author ? p.author + ". " : ""}"${p.title}." ${p.site}, ${date}${p.url.replace(/^https?:\/\//, "")}. `
    + `Accessed ${a.getDate()} ${MONTHS[a.getMonth()]} ${a.getFullYear()}.`;
}

export function bibtex(s, i = 1) {
  const p = parts(s);
  const key = ((p.author || p.site).split(/[\s,.]+/)[0] || "source").toLowerCase().replace(/[^a-z0-9]/g, "") + (p.year || "nd") + "_" + i;
  const esc = v => String(v).replace(/[{}\\]/g, "");
  const a = accessed().toISOString().slice(0, 10);
  return `@misc{${key},\n  title = {${esc(p.title)}},\n${p.author ? `  author = {${esc(p.author)}},\n` : ""}`
    + `  howpublished = {${esc(p.site)}},\n${p.year ? `  year = {${p.year}},\n` : ""}  url = {${p.url}},\n  note = {Accessed ${a}}\n}`;
}

export const STYLES = { apa, mla, bibtex };
export const cite = (s, style = "apa", i = 1) => (STYLES[style] || apa)(s, i);
