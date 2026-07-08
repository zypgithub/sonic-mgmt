#!/usr/bin/env python3
"""Allure URL → ``agent_full_path`` via MARS BI HTTP API."""
import argparse
import json
import sys
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ALLURE_TO_AGENT_API_BASE = "http://10.80.100.252:8765"
ALLURE_TO_AGENT_API_PATH = "/allure-url-to-agent-full-path"
ALLURE_TO_AGENT_API_TIMEOUT_SEC = 60

FIT69_HOST_PREFIXES = (
    "http://fit69.mtl.labs.mlnx",
    "https://fit69.mtl.labs.mlnx",
)


def strip_fit69_url_prefix(url):
    # type: (str) -> str
    url = (url or "").strip()
    if not url:
        return url
    for pfx in FIT69_HOST_PREFIXES:
        if url.startswith(pfx):
            return url[len(pfx):]
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc == "fit69.mtl.labs.mlnx" and parsed.path:
        return parsed.path
    return url


def lookup_agent_by_allure_url(allure_url):
    # type: (str) -> Optional[str]
    target = (allure_url or "").strip()
    if not target:
        return None
    api_url = "{}{}?{}".format(
        ALLURE_TO_AGENT_API_BASE.rstrip("/"),
        ALLURE_TO_AGENT_API_PATH,
        urlencode({"allure_url": target}),
    )
    req = Request(api_url, headers={"User-Agent": "sonic-mgmt-ai-rca/1.0"}, method="GET")
    try:
        with urlopen(req, timeout=ALLURE_TO_AGENT_API_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        path = (data.get("agent_full_path") or "").strip()
        return path or None
    except (HTTPError, URLError, OSError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lookup-allure", required=True, metavar="URL")
    path = lookup_agent_by_allure_url(ap.parse_args().lookup_allure)
    print(path or "")
    sys.exit(0 if path else 1)
