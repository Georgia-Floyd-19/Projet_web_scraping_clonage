from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

log = logging.getLogger("cloner.utils")

BINARY_EXTENSIONS = frozenset([
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff", ".avif",
    ".svg",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".flac",
    ".pdf", ".zip", ".tar", ".gz", ".rar",
    ".exe", ".dmg", ".pkg",
])

HTML_EXTENSIONS = frozenset([".html", ".htm", ".xhtml", ".php", ".asp", ".aspx", ".jsp"])

JS_URL_RE = re.compile(r"""["'`](/[a-zA-Z0-9_\-/]+(?:\.[a-zA-Z]{2,5})?)["'`]""")


def normalize_url(url: str, base_url: str = "") -> str:
    if not url:
        return ""
    if base_url and not url.startswith(("http://", "https://", "//", "data:", "javascript:", "mailto:", "tel:")):
        url = urljoin(base_url, url)
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    return urlunparse(parsed._replace(fragment=""))


def get_domain(url: str) -> str:
    return urlparse(url).netloc


def is_internal_url(url: str, root_domain: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc
    if not domain:
        return True
    return domain == root_domain or domain.endswith("." + root_domain)


def is_binary_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    return ext in BINARY_EXTENSIONS


def is_html_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if not path or path.endswith("/"):
        return True
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    return not ext or ext in HTML_EXTENSIONS


def extract_links_from_js(js_text: str, base_url: str) -> list[str]:
    links = []
    for match in JS_URL_RE.finditer(js_text):
        path = match.group(1)
        if path.startswith("/api/") or path.startswith("/_next/") or path.startswith("/__"):
            continue
        full_url = urljoin(base_url, path)
        links.append(full_url)
    return links


def clean_url(url: str) -> str:
    TRACKING_PARAMS = frozenset([
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "source", "_ga",
    ])
    parsed = urlparse(url)
    if not parsed.query:
        return url
    from urllib.parse import parse_qs, urlencode
    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {k: v for k, v in params.items() if k not in TRACKING_PARAMS}
    new_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def setup_logging(level: int = logging.INFO, log_file: Optional[Path] = None) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers, force=True)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


def human_size(n_bytes: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} To"


def url_depth(url: str) -> int:
    path = urlparse(url).path
    return len([p for p in path.split("/") if p])
