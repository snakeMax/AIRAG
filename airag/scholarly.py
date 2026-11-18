"""Research papers that a site won't show to a program (bot checks, HTTP 403): read the same paper through
Europe PMC's open web service, which is made for exactly this kind of access. Open-access papers come with
their full text; for the rest, the title and abstract.

Used by fetch_page only after the normal read (and the headless browser / Android WebView) failed. Nothing is
bypassed: Europe PMC is a public scholarly database run by EMBL-EBI with a documented REST API.
"""
from __future__ import annotations

import html
import re
from typing import Optional
from urllib.parse import unquote, urlparse

import httpx

API = "https://www.ebi.ac.uk/europepmc/webservices/rest"
MAX_TEXT = 200_000

# sites whose blocked pages are usually papers that Europe PMC also lists
SCHOLARLY = ("ncbi.nlm.nih.gov", "pubmed", "europepmc.org", "sciencedirect.com", "springer.com", "link.springer.com",
             "wiley.com", "tandfonline.com", "researchgate.net", "jamanetwork.com", "nejm.org", "thelancet.com",
             "academic.oup.com", "karger.com", "bmj.com", "frontiersin.org", "mdpi.com", "nature.com", "cell.com",
             "ahajournals.org", "journals.lww.com", "sagepub.com", "mayoclinicproceedings.org", "plos.org",
             "biomedcentral.com", "elsevier.com", "acs.org", "annals.org", "atsjournals.org", "jstor.org",
             "semanticscholar.org", "scielo", "cambridge.org", "psychiatryonline.org", "jneurosci.org",
             "physiology.org", "aspetjournals.org", "emedicine.medscape.com")

_PMC = re.compile(r"\b(PMC\d{4,10})\b", re.I)
_PMID = re.compile(r"pubmed(?:\.ncbi\.nlm\.nih\.gov|/)/?(\d{5,9})")
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s?#&\"'<>]+)")
_TITLE_TAIL = re.compile(r"\s*[|\-–—:]\s*(ScienceDirect|PubMed|PMC|ResearchGate|Springer\w*|Wiley[\w ]*|Taylor[\w &]*|"
                         r"NCBI|NIH|Europe PMC|Semantic Scholar|JAMA[\w ]*|The Lancet|Medscape[\w ]*|"
                         r"Mayo Clinic Proceedings|Nature|Frontiers|MDPI|BMJ)\b.*$", re.I)


def is_scholarly(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(s in host for s in SCHOLARLY) or bool(_DOI.search(unquote(url))) or bool(_PMC.search(url))


def _ids(url: str):
    u = unquote(url)
    pmc = _PMC.search(u)
    pmid = _PMID.search(u)
    doi = _DOI.search(u)
    return (pmc.group(1).upper() if pmc else "", pmid.group(1) if pmid else "",
            doi.group(1).rstrip(".);,") if doi else "")


def _clean_title(t: str) -> str:
    t = re.sub(r"(\.\.\.|…)\s*$", "", (t or "").strip())          # search engines cut long titles
    t = re.sub(r"^\(PDF\)\s*", "", t)
    t = _TITLE_TAIL.sub("", t).strip(" -|")
    return re.sub(r"[\"\\]", " ", t)[:300]


def _xml_text(xml: str) -> str:
    """Readable text from a JATS full-text XML (pattern-based, no XML parser)."""
    keep = re.findall(r"<abstract\b.*?</abstract>", xml, re.S)[:1] + re.findall(r"<body\b.*?</body>", xml, re.S)[:1]
    body = "\n".join(keep) or xml
    body = re.sub(r"<xref\b[^>]*>.*?</xref>", "", body, flags=re.S)       # citation numbers
    for drop in ("ref-list", "table-wrap-foot", "fn-group", "ack", "license", "permissions", "funding-group"):
        body = re.sub(rf"<{drop}\b.*?</{drop}>", " ", body, flags=re.S)
    body = re.sub(r"<title>(.*?)</title>", r"\n\n## \1\n", body, flags=re.S)
    body = re.sub(r"</(p|sec|abstract|caption|tr|list-item)>", "\n", body)
    body = re.sub(r"</t[dh]>", " | ", body)
    body = re.sub(r"<[^>]+>", "", body)
    body = html.unescape(body)
    body = re.sub(r"[ \t]+", " ", body)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", body).strip()


async def _get_json(c: httpx.AsyncClient, query: str) -> Optional[dict]:
    r = await c.get(f"{API}/search", params={"query": query, "resultType": "core", "format": "json", "pageSize": 1})
    if r.status_code != 200:
        return None
    res = (r.json().get("resultList") or {}).get("result") or []
    return res[0] if res else None


async def rescue(url: str, title_hint: str = "", timeout: float = 15.0):
    """A Page for a blocked paper, or None. Imported lazily by fetch (it builds the Page)."""
    from .fetch import Page
    pmc, pmid, doi = _ids(url)
    title = _clean_title(title_hint)
    queries = []
    if pmc:
        queries.append(f"PMCID:{pmc}")
    if pmid:
        queries.append(f"EXT_ID:{pmid} AND SRC:MED")
    if doi:
        queries.append(f'DOI:"{doi}"')
    if title and len(title.split()) >= 4 and is_scholarly(url):
        queries.append(f'TITLE:"{title}"')
    if not queries:
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8), follow_redirects=True,
                                     headers={"User-Agent": "AIRAG research assistant (+https://github.com/snakeMax/AIRAG)"}) as c:
            hit = None
            for q in queries:
                hit = await _get_json(c, q)
                if hit:
                    break
            if not hit:
                return None
            text, full = "", False
            pmcid = hit.get("pmcid") or pmc
            if pmcid and (hit.get("isOpenAccess") == "Y" or hit.get("inEPMC") == "Y"):
                r = await c.get(f"{API}/{pmcid}/fullTextXML")
                if r.status_code == 200 and "<body" in r.text:
                    text, full = _xml_text(r.text), True
            if not text:
                abstract = re.sub(r"<[^>]+>", " ", html.unescape(hit.get("abstractText") or "")).strip()
                if len(abstract) < 80:
                    return None
                text = abstract
    except (httpx.HTTPError, ValueError):
        return None
    head = hit.get("title") or title or url
    note = "Full text from Europe PMC (open access)." if full else \
        "Only the abstract could be read (through Europe PMC); the full paper was not available."
    journal = hit.get("journalTitle") or (hit.get("journalInfo") or {}).get("journal", {}).get("title", "")
    return Page(url, final_url=url, ok=True, text=(note + "\n\n" + text)[:MAX_TEXT], title=re.sub(r"<[^>]+>", "", head),
                via="europepmc" if full else "abstract", scholarly=True, site_name=journal or "",
                published=str(hit.get("firstPublicationDate") or hit.get("pubYear") or ""),
                author=(hit.get("authorString") or "")[:200])
