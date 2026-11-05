"""Zero-LLM-cost health probe for public, headline-only news discovery.

Runs only against fixed hosts; does not print URL tokens or source text.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def inspect(name: str, url: str, *, rss: bool = False) -> dict:
    try:
        opener = build_opener(NoRedirect)
        req = Request(url, headers={
            "User-Agent": "MarketSignalResearch/0.4 (+https://github.com/nolandrw/marketsignal)",
            "Accept": "application/rss+xml,application/xml,application/json",
        })
        with opener.open(req, timeout=7) as response:
            data = response.read(256_001)
        if len(data) > 256_000:
            return {"endpoint": name, "state": "oversize"}
        if rss:
            root = ElementTree.fromstring(data)
            count = len(root.findall("./channel/item"))
        else:
            count = len(json.loads(data).get("articles", []))
        return {"endpoint": name, "state": "parseable", "items": count}
    except HTTPError as exc:
        return {"endpoint": name, "state": "http_error", "http_status": exc.code}
    except (URLError, TimeoutError, OSError) as exc:
        return {"endpoint": name, "state": "network_error", "error_type": type(exc).__name__}
    except (ValueError, ElementTree.ParseError, AttributeError, TypeError) as exc:
        return {"endpoint": name, "state": "parse_error", "error_type": type(exc).__name__}


def main() -> None:
    query = "Iran ceasefire"
    probes = [
        ("gdelt_json", "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode({
            "query": query, "mode": "artlist", "format": "json", "maxrecords": 8,
            "startdatetime": "20261001000000", "enddatetime": "20261104000000",
        }), False),
        ("google_news_rss", "https://news.google.com/rss/search?" + urlencode({
            "q": query + " before:2026-11-04 after:2026-10-01",
            "hl": "en-US", "gl": "US", "ceid": "US:en",
        }), True),
        ("bing_news_rss", "https://www.bing.com/news/search?" + urlencode({
            "q": query, "format": "rss", "setlang": "en-US",
        }), True),
    ]
    print(json.dumps({"mode": "no_cost_source_health", "paid_calls": 0,
                      "status": [inspect(name, url, rss=is_rss)
                                 for name, url, is_rss in probes]}))


if __name__ == "__main__":
    main()
