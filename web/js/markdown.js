// Small Markdown renderer. HTML is escaped first, so model output can't inject markup.
// Supports headings, paragraphs, nested lists, blockquotes, code, tables, hr, links,
// bold/italic and [n] citations (rendered as <sup class="cite">).

const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
export const slug = s => s.toLowerCase().replace(/<[^>]+>/g, "").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "").slice(0, 60);

function expandCites(inner) {
  const out = [];
  for (const part of inner.split(/\s*[,;]\s*/)) {
    const r = part.match(/^(\d+)\s*[-–]\s*(\d+)$/);
    if (r) {
      const a = +r[1], b = +r[2];
      if (b >= a && b - a < 20) for (let i = a; i <= b; i++) out.push(i);
    } else if (/^\d+$/.test(part)) out.push(+part);
  }
  return out;
}

// Links in AI-written text are only kept when they point to a source of the current
// article, so a web page can't get the AI to slip in a phishing or tracking link.
let allowed = null;
const normUrl = u => String(u || "").replace(/\/+$/, "").replace(/^http:/, "https:");
export function allowLinks(urls) { allowed = urls ? new Set(urls.map(normUrl)) : null; }

export function inline(src) {
  let s = esc(src);
  const codes = [];
  s = s.replace(/`([^`]+)`/g, (m, c) => { codes.push(c); return `\u0001${codes.length - 1}\u0001`; });
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, t, u) =>
    allowed && !allowed.has(normUrl(u.replace(/&amp;/g, "&"))) ? t : `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`);
  s = s.replace(/\[(\d+(?:\s*[,;–-]\s*\d+)*)\]/g, (m, inner) => {
    const ns = expandCites(inner);
    return ns.length ? ns.map(n => `<sup class="cite" data-n="${n}">${n}</sup>`).join("") : m;
  });
  s = s.replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>").replace(/__([^_]+?)__/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*\p{L}\p{N}])\*(?!\s)([^*]+?)\*(?!\*)/gu, "$1<em>$2</em>");
  s = s.replace(/(^|[^\p{L}\p{N}])_(?!\s)([^_]+?)_(?![\p{L}\p{N}])/gu, "$1<em>$2</em>");
  s = s.replace(/\u0001(\d+)\u0001/g, (m, i) => `<code>${codes[+i]}</code>`);
  return s;
}

const isItem = l => /^\s*([-*+]|\d+[.)])\s+/.test(l);
const indent = l => l.match(/^\s*/)[0].replace(/\t/g, "  ").length;
const isTableRow = l => /^\s*\|.*\|\s*$/.test(l);
const isTableSep = l => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
const isHr = l => /^\s*(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$/.test(l);
const startsBlock = (l, next) => /^\s*```/.test(l) || /^#{1,6}\s/.test(l) || /^\s*>/.test(l) || isItem(l) || isHr(l) ||
  (isTableRow(l) && next !== undefined && isTableSep(next));

function dedent(lines) {
  const ind = Math.min(...lines.filter(l => l.trim()).map(indent));
  return lines.map(l => l.slice(Math.min(ind, indent(l))));
}

export function render(md) {
  const lines = (md || "").replace(/\r/g, "").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    let m;
    if (/^\s*```/.test(l)) {
      const buf = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`);
      continue;
    }
    if ((m = l.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/))) {
      out.push(`<h${m[1].length} id="${slug(m[2])}">${inline(m[2])}</h${m[1].length}>`);
      i++;
      continue;
    }
    if (isHr(l)) { out.push("<hr>"); i++; continue; }
    if (/^\s*>/.test(l)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push(`<blockquote>${render(buf.join("\n"))}</blockquote>`);
      continue;
    }
    if (isTableRow(l) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const cells = r => r.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim());
      const head = cells(l);
      const aligns = cells(lines[i + 1]).map(c => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : ""));
      i += 2;
      const rows = [];
      while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]));
      const td = (c, j, tag) => `<${tag}${aligns[j] ? ` style="text-align:${aligns[j]}"` : ""}>${inline(c)}</${tag}>`;
      out.push(`<div class="table-wrap"><table><thead><tr>${head.map((c, j) => td(c, j, "th")).join("")}</tr></thead><tbody>${
        rows.map(r => `<tr>${r.map((c, j) => td(c, j, "td")).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (isItem(l)) {
      const base = indent(l), ordered = /^\s*\d+[.)]/.test(l), items = [];
      while (i < lines.length) {
        const x = lines[i];
        if (!x.trim()) {
          const nx = lines[i + 1];
          if (nx !== undefined && (indent(nx) > base || (isItem(nx) && indent(nx) <= base + 1))) { i++; continue; }
          break;
        }
        if (isItem(x) && indent(x) <= base + 1) { items.push({ text: x.replace(/^\s*([-*+]|\d+[.)])\s+/, ""), sub: [] }); i++; continue; }
        if (indent(x) > base && items.length) { items[items.length - 1].sub.push(x); i++; continue; }
        break;
      }
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>${items.map(it => `<li>${inline(it.text)}${it.sub.length ? render(dedent(it.sub).join("\n")) : ""}</li>`).join("")}</${tag}>`);
      continue;
    }
    if (!l.trim()) { i++; continue; }
    const buf = [l];
    i++;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines[i], lines[i + 1])) buf.push(lines[i++]);
    out.push(`<p>${inline(buf.join(" "))}</p>`);
  }
  return out.join("\n");
}
