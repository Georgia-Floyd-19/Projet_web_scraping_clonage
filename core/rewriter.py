from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse, unquote

from bs4 import BeautifulSoup

log = logging.getLogger("cloner.rewriter")

CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)""", re.IGNORECASE)

RESOURCE_ATTRS: dict[str, list[str]] = {
    "img": ["src", "data-src", "data-lazy-src", "data-original"],
    "source": ["src", "data-src", "srcset"],
    "video": ["src", "poster"],
    "audio": ["src"],
    "track": ["src"],
    "embed": ["src"],
    "object": ["data"],
    "input": ["src"],
    "link": ["href"],
    "script": ["src"],
    "iframe": ["src"],
    "use": ["href", "xlink:href"],
}


def url_to_local_path(url: str, output_folder: Path, default_ext: str = ".html") -> Path:
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if not path or path.endswith("/"):
        path = path.rstrip("/") + "/index" + default_ext
    elif "." not in os.path.basename(path):
        path = path + default_ext
    if parsed.query:
        h = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
        stem, ext = os.path.splitext(path)
        path = f"{stem}_{h}{ext}"
    clean_parts = []
    for part in path.split("/"):
        part = part.replace("..", "").replace(":", "_").replace("?", "_")
        if part:
            clean_parts.append(part)
    return output_folder / "/".join(clean_parts)


def relative_link(from_file: Path, to_file: Path) -> str:
    return os.path.relpath(to_file, from_file.parent).replace(os.sep, "/")


class HTMLRewriter:
    def __init__(
        self,
        page_url: str,
        page_local_path: Path,
        output_folder: Path,
        url_to_path_map: dict[str, Path],
        clone_mode: str = "static",
    ) -> None:
        self.page_url = page_url
        self.page_local_path = page_local_path
        self.output_folder = output_folder
        self.url_to_path_map = url_to_path_map
        self.rewrite_count = 0
        self.clone_mode = clone_mode

    def rewrite(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        self._rewrite_link_tags(soup)
        self._rewrite_script_tags(soup)
        self._rewrite_media_tags(soup)
        self._rewrite_srcset(soup)
        self._rewrite_anchor_tags(soup)
        self._rewrite_inline_styles(soup)
        self._rewrite_meta_tags(soup)
        self._inject_base_fix(soup)
        if self.clone_mode == "hybrid":
            self._inject_sw_registration(soup)
        html = str(soup)
        html = self._rewrite_remaining_absolute_paths(html)
        return html

    def _inject_sw_registration(self, soup: BeautifulSoup) -> None:
        sw_path = self.output_folder / "sw-register.js"
        if not sw_path.exists():
            return
        rel = relative_link(self.page_local_path, sw_path)
        script = soup.new_tag("script", src=rel)
        head = soup.find("head")
        if head:
            head.append(script)
        else:
            html_tag = soup.find("html")
            if html_tag:
                html_tag.insert(0, script)

    def _rewrite_link_tags(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all("link"):
            rel = tag.get("rel", [])
            href = tag.get("href", "")
            if not href or href.startswith("data:"):
                continue
            abs_url = urljoin(self.page_url, href)
            local_path = self._resolve_local(abs_url)
            if local_path:
                tag["href"] = relative_link(self.page_local_path, local_path)
                self.rewrite_count += 1
            if any(r in rel for r in ("preload", "prefetch", "dns-prefetch")):
                tag.decompose()

    def _rewrite_script_tags(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all("script", src=True):
            abs_url = urljoin(self.page_url, tag["src"])
            local_path = self._resolve_local(abs_url)
            if local_path:
                tag["src"] = relative_link(self.page_local_path, local_path)
                self.rewrite_count += 1
            tag.attrs.pop("crossorigin", None)
            tag.attrs.pop("integrity", None)

    def _rewrite_media_tags(self, soup: BeautifulSoup) -> None:
        for tag_name, attrs in RESOURCE_ATTRS.items():
            for tag in soup.find_all(tag_name):
                for attr in attrs:
                    val = tag.get(attr)
                    if val and not val.startswith("data:"):
                        abs_url = urljoin(self.page_url, val)
                        local_path = self._resolve_local(abs_url)
                        if local_path:
                            tag[attr] = relative_link(self.page_local_path, local_path)
                            self.rewrite_count += 1

    def _rewrite_srcset(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(attrs={"srcset": True}):
            parts: list[str] = []
            for item in tag["srcset"].split(","):
                bits = item.strip().split()
                if not bits:
                    continue
                abs_url = urljoin(self.page_url, bits[0])
                local_path = self._resolve_local(abs_url)
                if local_path:
                    bits[0] = relative_link(self.page_local_path, local_path)
                    self.rewrite_count += 1
                parts.append(" ".join(bits))
            tag["srcset"] = ", ".join(parts)

    def _rewrite_anchor_tags(self, soup: BeautifulSoup) -> None:
        root_domain = urlparse(self.page_url).netloc
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            abs_url = urljoin(self.page_url, href).split("#")[0]
            if urlparse(abs_url).netloc == root_domain:
                local_path = self._resolve_local(abs_url, default_ext=".html")
                if local_path:
                    a["href"] = relative_link(self.page_local_path, local_path)
                    self.rewrite_count += 1

    def _rewrite_inline_styles(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(style=True):
            tag["style"] = self._rewrite_css_urls(tag["style"])
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                style_tag.string.replace_with(self._rewrite_css_urls(style_tag.string))

    def _rewrite_css_urls(self, css_text: str) -> str:
        def replace_url(match: re.Match) -> str:
            quote = match.group(1)
            raw = match.group(2).strip()
            if raw.startswith("data:") or raw.startswith("#"):
                return match.group(0)
            abs_url = urljoin(self.page_url, raw)
            local_path = self._resolve_local(abs_url)
            if local_path:
                rel = relative_link(self.page_local_path, local_path)
                self.rewrite_count += 1
                return f"url({quote}{rel}{quote})"
            return match.group(0)
        return CSS_URL_RE.sub(replace_url, css_text)

    def _rewrite_meta_tags(self, soup: BeautifulSoup) -> None:
        for meta in soup.find_all("meta"):
            prop = meta.get("property", "") or meta.get("name", "")
            if "image" in prop or "url" in prop:
                content = meta.get("content", "")
                if content and content.startswith("http"):
                    local_path = self._resolve_local(content)
                    if local_path:
                        meta["content"] = relative_link(self.page_local_path, local_path)
                        self.rewrite_count += 1

    def _inject_base_fix(self, soup: BeautifulSoup) -> None:
        for base in soup.find_all("base"):
            base.decompose()

    def _rewrite_remaining_absolute_paths(self, html: str) -> str:
        """Rewrite remaining absolute paths to relative paths.
        
        Catches resources not in url_to_path_map by doing a simple
        prefix-based replacement on the raw HTML string.
        """
        from urllib.parse import urlparse, urljoin

        path_map = {
            "/_nuxt/": "scripts/_nuxt/",
            "/_fonts/": "fonts/",
            "/fonts/": "fonts/",
        }

        base_rel = relative_link(self.page_local_path, self.output_folder)

        for abs_prefix, local_prefix in path_map.items():
            def replacer(m, ap=abs_prefix, lp=local_prefix):
                quote = m.group(1)
                path = m.group(2)
                rel_path = os.path.join(base_rel, lp, path)
                rel_path = rel_path.replace("\\", "/")
                self.rewrite_count += 1
                return f"{quote}{rel_path}{quote}"

            html = re.sub(
                rf'([\'"])' + re.escape(abs_prefix) + r'([^\'"]+?)\1',
                replacer,
                html
            )

        return html

    def _resolve_local(self, url: str, default_ext: str = "") -> Optional[Path]:
        if url in self.url_to_path_map:
            return self.url_to_path_map[url]

        # Try matching by path only (ignore domain/protocol differences)
        url_path = urlparse(url).path
        for orig_url, local_path in self.url_to_path_map.items():
            if urlparse(orig_url).path == url_path:
                return local_path

        # Try to resolve known Nuxt path patterns even if not in map
        if url_path.startswith('/'):
            path_checks = [
                ('/_nuxt/', self.output_folder / 'scripts' / '_nuxt'),
                ('/_fonts/', self.output_folder / 'fonts'),
                ('/fonts/', self.output_folder / 'fonts'),
                ('/images/', self.output_folder / 'images'),
                ('/img/', self.output_folder / 'images'),
            ]
            for prefix, base_dir in path_checks:
                if url_path.startswith(prefix):
                    rel_part = url_path[len(prefix):]
                    candidate = base_dir / rel_part
                    if candidate.exists():
                        return candidate

        if default_ext:
            return url_to_local_path(url, self.output_folder, default_ext)
        return None


class CSSRewriter:
    def __init__(
        self,
        css_url: str,
        css_local_path: Path,
        output_folder: Path,
        url_to_path_map: dict[str, Path],
    ) -> None:
        self.css_url = css_url
        self.css_local_path = css_local_path
        self.output_folder = output_folder
        self.url_to_path_map = url_to_path_map

    def rewrite(self, css_text: str) -> str:
        def replace_url(match: re.Match) -> str:
            quote = match.group(1)
            raw = match.group(2).strip()
            if raw.startswith("data:") or raw.startswith("#"):
                return match.group(0)
            abs_url = urljoin(self.css_url, raw)
            if abs_url in self.url_to_path_map:
                local_path = self.url_to_path_map[abs_url]
                rel = relative_link(self.css_local_path, local_path)
                return f"url({quote}{rel}{quote})"
            return match.group(0)
        return CSS_URL_RE.sub(replace_url, css_text)
