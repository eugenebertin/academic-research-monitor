"""Check arXiv-supplied DOIs against Crossref, without claiming proof of peer review."""

import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 15
USER_AGENT = "academic-research-monitor/0.1 (personal research experiment)"


def lookup(doi):
    doi = doi.strip()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi, flags=re.IGNORECASE):
        return "Invalid arXiv DOI; peer review unverified", ""
    url = "https://api.crossref.org/works/" + quote(doi, safe="/")
    try:
        with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)["message"]
        if not isinstance(data, dict) or str(data.get("DOI", "")).casefold() != doi.casefold():
            return "Crossref DOI mismatch; peer review unverified", ""
        kind = data.get("type", "unknown")
        venue = data.get("container-title") or []
        venue = venue[0] if isinstance(venue, list) and venue and isinstance(venue[0], str) else ""
        if kind == "journal-article":
            return "Crossref journal article; peer review unverified", venue
        return f"Crossref type {kind}; peer review unverified", venue
    except HTTPError as e:
        return f"Crossref lookup failed (HTTP {e.code}); peer review unverified", ""
    except (URLError, TimeoutError, OSError, ValueError, KeyError) as e:
        return f"Crossref lookup failed ({type(e).__name__}); peer review unverified", ""


def normalized(text):
    return " ".join(re.findall(r"\w+", text.casefold(), flags=re.UNICODE))


def find_candidate(title, authors):
    """Find a possible journal DOI by exact normalized title and first author's surname."""
    first_author = authors.split(";", 1)[0].strip()
    surname = normalized(first_author).split()
    if not title.strip() or not surname:
        return "", "Insufficient metadata for Crossref search; peer review unverified", ""
    params = urlencode({"query.bibliographic": title, "rows": 5, "filter": "type:journal-article"})
    try:
        with urlopen(Request("https://api.crossref.org/works?" + params,
                             headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT_SECONDS) as response:
            items = json.load(response)["message"]["items"]
        matches = []
        for item in items:
            titles = item.get("title") or []
            crossref_authors = item.get("author") or []
            first = crossref_authors[0] if crossref_authors else {}
            family = normalized(first.get("family", "")) if isinstance(first, dict) else ""
            doi = item.get("DOI", "")
            if (titles and isinstance(titles[0], str) and normalized(titles[0]) == normalized(title)
                    and surname[-1] == family and re.fullmatch(r"10\.\d{4,9}/\S+", doi, re.IGNORECASE)):
                venue = item.get("container-title") or []
                matches.append((doi, venue[0] if venue and isinstance(venue[0], str) else ""))
        unique = {doi.casefold(): (doi, venue) for doi, venue in matches}
        if len(unique) == 1:
            doi, venue = next(iter(unique.values()))
            return doi, "Possible Crossref journal article (title and author match); peer review unverified", venue
        if len(unique) > 1:
            return "", "Multiple possible journal DOIs; peer review unverified", ""
        return "", "No matching journal DOI found in Crossref; peer review unverified", ""
    except HTTPError as e:
        return "", f"Crossref search failed (HTTP {e.code}); peer review unverified", ""
    except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as e:
        return "", f"Crossref search failed ({type(e).__name__}); peer review unverified", ""


def annotate(papers):
    cache = {}
    count = len({p.get("doi", "").strip().casefold() for p in papers if p.get("doi", "").strip()})
    missing = sum(not p.get("doi", "").strip() for p in papers)
    print(f"Checking {count} arXiv-supplied DOIs and searching {missing} other titles in Crossref; "
          "peer review is not independently verified.")
    made_request = False
    for paper in papers:
        doi = paper.get("doi", "").strip()
        paper["publication_doi"] = ""
        if not doi:
            if made_request:
                time.sleep(DELAY_SECONDS)
            paper["publication_doi"], paper["publication_status"], paper["publication_venue"] = find_candidate(
                paper.get("title", ""), paper.get("authors", ""))
            made_request = True
            continue
        key = doi.casefold()
        if key not in cache:
            if made_request:
                time.sleep(DELAY_SECONDS)
            cache[key] = lookup(doi)
            made_request = True
        paper["publication_status"], paper["publication_venue"] = cache[key]
