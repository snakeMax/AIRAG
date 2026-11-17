"""Domain reputation priors. The AI still judges each page, but this gives it
a starting point. Edit/extend RULES freely: (domain or .suffix, score 0-10, label).
More specific entries must come before broader suffixes."""
from __future__ import annotations

from typing import Tuple

RULES = [
    ("pubmed.ncbi.nlm.nih.gov", 9, "PubMed – index of peer-reviewed research"),
    ("ncbi.nlm.nih.gov", 9, "NCBI / PubMed Central – research archive"),
    ("medlineplus.gov", 9, "MedlinePlus – US National Library of Medicine"),
    ("who.int", 9, "World Health Organization"),
    ("cochranelibrary.com", 9, "Cochrane – systematic reviews"),
    ("nature.com", 9, "Peer-reviewed journal"), ("science.org", 9, "Peer-reviewed journal"),
    ("thelancet.com", 9, "Peer-reviewed journal"), ("nejm.org", 9, "Peer-reviewed journal"),
    ("bmj.com", 9, "Peer-reviewed journal"), ("jamanetwork.com", 9, "Peer-reviewed journal"),
    ("plos.org", 8, "Peer-reviewed open-access journal"), ("cell.com", 9, "Peer-reviewed journal"),
    ("sciencedirect.com", 8, "Journal publisher"), ("springer.com", 8, "Journal publisher"),
    ("wiley.com", 8, "Journal publisher"), ("tandfonline.com", 8, "Journal publisher"),
    ("acs.org", 8, "Scientific society publisher"), ("rsc.org", 8, "Scientific society publisher"),
    ("frontiersin.org", 7, "Open-access journal"), ("mdpi.com", 6, "Open-access publisher (variable rigor)"),
    ("arxiv.org", 6, "Preprint server – not peer reviewed"), ("biorxiv.org", 6, "Preprint – not peer reviewed"),
    ("medrxiv.org", 6, "Preprint – not peer reviewed"), ("researchgate.net", 6, "Academic sharing site"),
    ("semanticscholar.org", 7, "Research index"), ("scholar.google.com", 7, "Research index"),
    ("europa.eu", 8, "EU institution"), ("un.org", 8, "United Nations"), ("oecd.org", 8, "OECD"),
    ("britannica.com", 8, "Encyclopaedia Britannica"), ("wikipedia.org", 7, "Wikipedia – crowd-edited encyclopedia"),
    ("mayoclinic.org", 8, "Medical institution"), ("clevelandclinic.org", 8, "Medical institution"),
    ("nhs.uk", 9, "UK National Health Service"), ("drugs.com", 7, "Drug reference database"),
    ("drugbank.com", 8, "Drug reference database"), ("rxlist.com", 7, "Drug reference"),
    ("pubchem.ncbi.nlm.nih.gov", 9, "PubChem – chemical database"), ("echa.europa.eu", 9, "EU Chemicals Agency"),
    ("webmd.com", 6, "Consumer health site"), ("healthline.com", 6, "Consumer health site"),
    ("verywellhealth.com", 6, "Consumer health site"),
    ("reuters.com", 8, "News agency"), ("apnews.com", 8, "News agency"), ("bbc.com", 7, "Major news outlet"),
    ("bbc.co.uk", 7, "Major news outlet"), ("nytimes.com", 7, "Major news outlet"),
    ("theguardian.com", 7, "Major news outlet"), ("washingtonpost.com", 7, "Major news outlet"),
    ("nrk.no", 7, "Public broadcaster"), ("npr.org", 7, "Public broadcaster"),
    ("stackoverflow.com", 6, "Developer Q&A"), ("stackexchange.com", 6, "Expert Q&A community"),
    ("github.com", 6, "Code repository"), ("developer.mozilla.org", 8, "MDN – technical reference"),
    ("erowid.org", 5, "Harm-reduction archive (mix of references and user reports)"),
    ("psychonautwiki.org", 5, "Community wiki"), ("tripsit.me", 5, "Harm-reduction community"),
    ("bluelight.org", 3, "Forum – user-generated"), ("reddit.com", 3, "Forum – user-generated"),
    ("quora.com", 3, "Q&A – user-generated"), ("medium.com", 4, "Blog platform"), ("substack.com", 4, "Newsletter/blog"),
    ("blogspot.com", 3, "Personal blog"), ("wordpress.com", 3, "Personal blog"), ("fandom.com", 4, "Fan wiki"),
    ("tumblr.com", 2, "Social media"), ("pinterest.com", 2, "Social media"), ("tiktok.com", 2, "Social media"),
    ("youtube.com", 4, "Video platform"), ("amazon.com", 3, "Retail listing"),
    (".gov", 9, "Government agency"), (".gov.uk", 9, "Government agency"), (".mil", 8, "Government / military"),
    (".edu", 8, "Academic institution"), (".ac.uk", 8, "Academic institution"), (".int", 8, "International organization"),
]


def domain_prior(domain: str, scholarly: bool = False) -> Tuple[int, str]:
    d = (domain or "").lower()
    for pattern, score, label in RULES:
        if pattern.startswith("."):
            if d.endswith(pattern) or ("." + d).endswith(pattern + ".") or (pattern + ".") in ("." + d + "."):
                return score, label
        elif d == pattern or d.endswith("." + pattern):
            return score, label
    if scholarly:
        return 8, "Scholarly publication (has citation metadata)"
    return 5, "Unknown / general website"
