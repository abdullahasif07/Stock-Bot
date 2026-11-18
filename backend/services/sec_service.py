"""SEC EDGAR access (free, no API key).

* Company lookup from SEC's official ticker list — also used by chat to resolve
  tickers without spending Alpha Vantage quota.
* Latest annual report (10-K, or 20-F/40-F for foreign filers) download and
  clean-up into plain text with tables kept as pipe-delimited rows.
"""
import json
import os
import re

import requests
from lxml import html as lxml_html

from ..config import SEC_USER_AGENT, FILINGS_DIR
from ..utils import cache

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
ANNUAL_FORMS = ("10-K", "20-F", "40-F")
BUNDLED = {"AMZN": os.path.join(FILINGS_DIR, "AMZN_bundled.txt")}

_SUFFIXES = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|"
    r"the|class [a-z]|nv|sa|ag|llc|lp|de)\b")


def _get(url: str, timeout: int = 30) -> requests.Response:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": SEC_USER_AGENT,
                                                        "Accept-Encoding": "gzip, deflate"})
    resp.raise_for_status()
    return resp


# ── Company directory ───────────────────────────────────────────────────────

def _load_companies() -> list[dict]:
    def fetch():
        data = _get(TICKERS_URL).json()
        return [{"cik": int(v["cik_str"]), "ticker": v["ticker"].upper(), "name": v["title"]}
                for v in data.values()]
    return cache.get_or_fetch("sec:company_tickers", 7 * 86400, fetch) or []


_by_ticker: dict[str, dict] | None = None


def _ticker_map() -> dict[str, dict]:
    global _by_ticker
    if _by_ticker is None:
        companies = _load_companies()
        mapping: dict[str, dict] = {}
        for c in companies:  # first occurrence = primary listing
            mapping.setdefault(c["ticker"], c)
        if companies:
            _by_ticker = mapping
        return mapping
    return _by_ticker


def normalize_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9 ]+", " ", name.lower().replace("&", " and "))
    words = _SUFFIXES.sub(" ", name).split()
    while words and words[-1] == "and":
        words.pop()
    return " ".join(words)


def lookup_ticker(ticker: str) -> dict | None:
    return _ticker_map().get(ticker.strip().upper().replace(".", "-"))


# Brand names that differ from the legal registrant name.
ALIASES = {
    "google": "GOOGL", "alphabet": "GOOGL", "facebook": "META", "instagram": "META",
    "jp morgan": "JPM", "chase": "JPM", "berkshire": "BRK-B", "coke": "KO", "walmart": "WMT",
    "aws": "AMZN", "youtube": "GOOGL", "tsmc": "TSM", "ibm": "IBM", "att": "T", "at&t": "T",
}


def search_companies(query: str, limit: int = 5) -> list[dict]:
    """Rank SEC registrants by how well their ticker/name matches ``query``."""
    q = query.strip()
    if not q:
        return []
    alias = ALIASES.get(q.lower())
    if alias and lookup_ticker(alias):
        return [{**lookup_ticker(alias), "score": 100}]
    qn = normalize_name(q)
    q_compact = qn.replace(" ", "")
    q_upper = q.upper().replace(".", "-")
    scored = []
    seen_ciks = set()
    for c in _load_companies():
        if c["cik"] in seen_ciks:
            continue
        name_n = normalize_name(c["name"])
        if c["ticker"] == q_upper:
            score = 100
        elif qn and name_n == qn:
            score = 95
        elif qn and name_n.startswith(qn + " "):
            score = 80 - min(len(name_n) - len(qn), 30) / 3
        elif qn and f" {qn} " in f" {name_n} ":
            score = 60 - min(len(name_n) - len(qn), 30) / 3
        elif len(q_compact) >= 4 and name_n.replace(" ", "").startswith(q_compact):
            score = 70 - min(len(name_n) - len(qn), 30) / 3
        else:
            continue
        seen_ciks.add(c["cik"])
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{**c, "score": round(s, 1)} for s, c in scored[:limit]]


def resolve_company(query: str) -> tuple[dict | None, list[dict]]:
    """Return (confident_match, candidates)."""
    matches = search_companies(query)
    if not matches:
        return None, []
    top = matches[0]
    runner_up = matches[1]["score"] if len(matches) > 1 else 0
    if top["score"] >= 95 or (top["score"] >= 70 and top["score"] - runner_up >= 15) or len(matches) == 1:
        return top, matches
    return None, matches


# ── Filing download ─────────────────────────────────────────────────────────

def latest_annual_filing(cik: int) -> dict | None:
    def fetch():
        recent = _get(SUBMISSIONS_URL.format(cik=cik)).json()["filings"]["recent"]
        for form in ANNUAL_FORMS:
            for i, f in enumerate(recent["form"]):
                if f == form:
                    return {
                        "form": f,
                        "accession": recent["accessionNumber"][i],
                        "filing_date": recent["filingDate"][i],
                        "report_date": recent["reportDate"][i],
                        "primary_document": recent["primaryDocument"][i],
                    }
        return None
    return cache.get_or_fetch(f"sec:latest_annual:{cik}", 86400, fetch)


_BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section"}
_NOISE_LINE = re.compile(r"^(table of contents|\d{1,3}|page \d+|[ivx]{1,5})$", re.I)


def html_to_text(raw_html: bytes | str) -> str:
    """Convert (inline-XBRL) filing HTML into readable text."""
    doc = lxml_html.fromstring(raw_html)
    for bad in doc.xpath("//script|//style|//*[local-name()='header' and contains(name(),'ix')]"
                         "|//*[contains(translate(@style,' ',''),'display:none')]"):
        bad.drop_tree()
    for table in doc.xpath("//table"):
        rows = []
        for tr in table.xpath(".//tr"):
            cells = [" ".join(td.text_content().split()) for td in tr.xpath("./td|./th")]
            cells = [c for c in cells if c and c not in {"$", "%", ")"}]
            if cells:
                rows.append(" | ".join(cells))
        replacement = lxml_html.Element("pre")
        replacement.text = "\n" + "\n".join(rows) + "\n" if rows else ""
        replacement.tail = table.tail
        table.getparent().replace(table, replacement)
    for el in doc.iter():
        if isinstance(el.tag, str) and el.tag.lower() in _BLOCK_TAGS | {"pre"}:
            el.tail = "\n" + (el.tail or "")
    text = doc.text_content().replace("\xa0", " ")
    lines = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if line and not _NOISE_LINE.match(line):
            lines.append(line)
    return "\n".join(lines)


def strip_preamble(text: str) -> str:
    """Drop leftover XBRL metadata before the cover page, if present."""
    m = re.search(r"UNITED STATES\s+SECURITIES AND EXCHANGE COMMISSION", text[:200000], re.I)
    return text[m.start():] if m else text


def get_annual_report(ticker: str) -> dict | None:
    """Return {"text", "meta"} for the latest annual report, using a disk cache."""
    company = lookup_ticker(ticker)
    if not company:
        return None
    filing = None
    try:
        filing = latest_annual_filing(company["cik"])
    except Exception as e:
        print(f"[SEC] Could not list filings for {ticker}: {e}")

    if filing:
        acc = filing["accession"]
        text_path = os.path.join(FILINGS_DIR, f"{company['ticker']}_{acc}.txt")
        meta = {"ticker": company["ticker"], "company_name": company["name"], "cik": company["cik"], **filing,
                "source_url": ARCHIVE_URL.format(cik=company["cik"], acc=acc.replace("-", ""),
                                                 doc=filing["primary_document"])}
        if os.path.exists(text_path):
            with open(text_path, encoding="utf-8") as f:
                return {"text": f.read(), "meta": meta}
        try:
            print(f"[SEC] Downloading {filing['form']} for {ticker}: {meta['source_url']}")
            text = strip_preamble(html_to_text(_get(meta["source_url"], timeout=90).content))
            if len(text) > 5000:
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(text)
                with open(text_path + ".json", "w") as f:
                    json.dump(meta, f)
                return {"text": text, "meta": meta}
        except Exception as e:
            print(f"[SEC] Download failed for {ticker}: {e}")

    bundled = BUNDLED.get(company["ticker"])
    if bundled and os.path.exists(bundled):
        with open(bundled, encoding="utf-8") as f:
            text = strip_preamble(f.read())
        return {"text": text, "meta": {"ticker": company["ticker"], "company_name": company["name"],
                                       "cik": company["cik"], "form": "10-K", "accession": "bundled",
                                       "report_date": "2024-12-31", "filing_date": "2025-02-07",
                                       "source_url": None}}
    return None
