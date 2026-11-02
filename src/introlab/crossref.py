"""Minimal Crossref REST client. Metadata confirms identifiers, not scientific claims."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

BASE = "https://api.crossref.org"


def normalize_doi(value):
    value = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.strip().lower()
    if not value.startswith("10.") or "/" not in value:
        raise ValueError("Invalid DOI; expected 10.xxxx/...")
    return value


def request_json(path, params=None):
    params = dict(params or {})
    mailto = os.environ.get("INTRO_CROSSREF_EMAIL")
    if mailto:
        params["mailto"] = mailto
    url = BASE + path + ("?" + urlencode(params) if params else "")
    req = Request(url, headers={"User-Agent": "IntroLab/0.1 (academic metadata research)"})
    try:
        with urlopen(req, timeout=25) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Crossref request failed: {exc}") from exc
    if payload.get("status") != "ok":
        raise RuntimeError("Crossref returned a non-ok response")
    return payload["message"]


def fetch_doi(doi):
    return request_json("/works/" + quote(normalize_doi(doi), safe=""))


def search_works(query, journal, rows=10, offset=0, start_year=None, end_year=None):
    if not 1 <= rows <= 20:
        raise ValueError("One batch must contain between 1 and 20 records")
    if not 0 <= offset <= 9999:
        raise ValueError("Crossref offset must be 0..9999")
    filters = ["type:journal-article"]
    if journal:
        filters.append("container-title:" + journal)
    if start_year:
        filters.append(f"from-pub-date:{int(start_year)}-01-01")
    if end_year:
        filters.append(f"until-pub-date:{int(end_year)}-12-31")
    params = {
        "query.bibliographic": query,
        "rows": rows,
        "offset": offset,
        "filter": ",".join(filters),
        "select": "DOI,title,author,container-title,short-container-title,published,issued,volume,issue,page,article-number,URL,type",
    }
    return request_json("/works", params).get("items", [])


def to_record(item):
    doi = normalize_doi(item["DOI"])
    year = None
    for key in ("published", "issued"):
        parts = item.get(key, {}).get("date-parts", [[]])
        if parts and parts[0]:
            year = parts[0][0]
            break
    def first(key):
        values = item.get(key) or []
        return values[0] if values else ""
    return {
        "doi": doi,
        "title": first("title"),
        "journal": first("container-title"),
        "journal_abbrev": first("short-container-title"),
        "year": year,
        "volume": str(item.get("volume") or ""),
        "issue": str(item.get("issue") or ""),
        "pages": str(item.get("page") or item.get("article-number") or ""),
        "authors": item.get("author") or [],
        "url": "https://doi.org/" + doi,
        "metadata": item,
    }
