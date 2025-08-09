import time, xml.etree.ElementTree as ET, requests, os
from . import settings

UA = settings.UA

def _get(url, **kw):
    headers = kw.pop("headers", {})
    headers.setdefault("User-Agent", UA)
    return requests.get(url, headers=headers, timeout=kw.pop("timeout", 15), **kw)

def thingisbn_cluster(token: str, isbn: str, *, sleep: float = 0.25) -> list[str]:
    """
    LT thingISBN. If 403/401/5xx, return [] (non-fatal).
    Tries http:// then https:// (LT docs showed http historically).
    """
    if not token:
        return []
    for scheme in ("http", "https"):
        try:
            url = f"{scheme}://www.librarything.com/api/{token}/thingISBN/{isbn}"
            r = _get(url)
            if r.status_code == 404:
                return []
            if r.status_code in (401, 403, 429, 500, 502, 503):
                return []  # treat as unavailable
            r.raise_for_status()
            try:
                root = ET.fromstring(r.text)
            except ET.ParseError:
                return []
            out = []
            for el in root.findall(".//isbn"):
                t = (el.text or "").strip()
                if t:
                    out.append(t)
            if sleep:
                time.sleep(sleep)
            return out
        except requests.RequestException:
            return []
    return []

def explode_isbns_with_lt(token: str | None, base_isbns) -> list[str]:
    seen, out = set(), []
    base = [s for s in base_isbns if s]
    for b in base:
        if b not in seen:
            seen.add(b); out.append(b)
        # lt expansion best-effort
        for x in thingisbn_cluster(token, b):
            if x not in seen:
                seen.add(x); out.append(x)
    return out

def probe_openlibrary_isbns(isbns13) -> list[str]:
    ok, s = [], requests.Session()
    s.headers["User-Agent"] = UA
    for i, isbn in enumerate(isbns13):
        try:
            r = s.get(f"https://openlibrary.org/isbn/{isbn}.json", timeout=12)
            if r.ok:
                ok.append(isbn)
        except requests.RequestException:
            pass
        if (i % 5) == 4:
            time.sleep(0.2)
    return ok

def expand_via_openlibrary(isbn13: str) -> list[str]:
    """
    OpenLibrary-only expansion: hit search.json with the ISBN,
    then collect sibling edition ISBNs from the same work.
    """
    try:
        r = _get(f"https://openlibrary.org/search.json?isbn={isbn13}")
        if not r.ok:
            return []
        j = r.json()
    except Exception:
        return []
    out = set()
    for doc in j.get("docs", []):
        # same work → gather all edition_isbn
        for e in doc.get("edition_isbn", []) or []:
            if isinstance(e, str) and len(e) in (10, 13):
                out.add(e)
    return list(out)
