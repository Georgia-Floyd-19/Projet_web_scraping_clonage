from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import Page, Request, Response, Route

log = logging.getLogger("cloner.interceptor")

RESOURCE_TYPES_TO_CAPTURE = {
    "document", "stylesheet", "script", "image", "media",
    "font", "fetch", "xhr", "other",
}

EXTENSION_CATEGORY: dict[str, str] = {
    ".html": "pages", ".htm": "pages",
    ".css": "styles",
    ".js": "scripts", ".mjs": "scripts",
    ".json": "api",
    ".svg": "images", ".png": "images", ".jpg": "images",
    ".jpeg": "images", ".gif": "images", ".webp": "images",
    ".ico": "images",
    ".woff": "fonts", ".woff2": "fonts", ".ttf": "fonts",
    ".otf": "fonts", ".eot": "fonts",
    ".mp4": "media", ".webm": "media",
    ".mp3": "media", ".ogg": "media",
    ".pdf": "docs",
}


@dataclass
class CapturedResource:
    url: str
    resource_type: str
    status: int = 0
    content_type: str = ""
    body: bytes = field(default_factory=bytes, repr=False)
    is_api: bool = False
    is_graphql: bool = False
    saved_path: Optional[str] = None
    error: Optional[str] = None

    @property
    def extension(self) -> str:
        path = urlparse(self.url).path
        ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return ext if len(ext) <= 6 else ""

    @property
    def category(self) -> str:
        return EXTENSION_CATEGORY.get(self.extension, "misc")


class NetworkInterceptor:
    def __init__(self, block_ads: bool = True, block_anti_bot: bool = True) -> None:
        self.block_ads = block_ads
        self.block_anti_bot = block_anti_bot
        self._resources: dict[str, CapturedResource] = {}
        self._api_calls: list[CapturedResource] = []
        self._ws_urls: list[str] = []

    async def attach(self, page: Page) -> None:
        await page.route("**/*", self._handle_route)
        page.on("response", self._handle_response)
        page.on("websocket", self._handle_websocket)
        log.debug("Intercepteur réseau attaché")

    async def _handle_route(self, route: Route) -> None:
        request = route.request
        if self.block_ads and self._is_ad_domain(request.url):
            await route.abort()
            return
        if self.block_anti_bot and self._is_anti_bot_domain(request.url):
            await route.abort()
            return
        await route.continue_()

    async def _handle_response(self, response: Response) -> None:
        request = response.request
        url = request.url
        resource_type = request.resource_type
        if resource_type not in RESOURCE_TYPES_TO_CAPTURE:
            return
        try:
            body = await response.body()
        except Exception:
            body = b""
        content_type = response.headers.get("content-type", "")
        is_api = resource_type in ("fetch", "xhr")
        is_graphql = self._detect_graphql(url, request, body)
        resource = CapturedResource(
            url=url, resource_type=resource_type, status=response.status,
            content_type=content_type, body=body, is_api=is_api, is_graphql=is_graphql,
        )
        self._resources[url] = resource
        if is_api:
            self._api_calls.append(resource)

    def _handle_websocket(self, ws) -> None:
        self._ws_urls.append(ws.url)
        log.debug("WebSocket : %s", ws.url)

    @staticmethod
    def _detect_graphql(url: str, request: Request, body: bytes) -> bool:
        url_lower = url.lower()
        if "graphql" in url_lower or "/gql" in url_lower:
            return True
        try:
            if body:
                data = json.loads(body)
                if isinstance(data, dict) and ("query" in data or "mutation" in data):
                    return True
        except Exception:
            pass
        return False

    _AD_DOMAINS = frozenset([
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "adnxs.com", "outbrain.com", "taboola.com", "moatads.com",
        "adsymptotic.com", "amazon-adsystem.com",
    ])

    _ANTI_BOT_DOMAINS = frozenset([
        "datadome.co", "js.datadome.co", "api.datadome.co",
        "sentry.io", "datadoghq.com", "browser-intake-datadoghq.com",
        "fingerprint.com", "fingerprintjs.com", "fpjs.io",
        "perimeterx.net", "px-cdn.net", "px.d.t", "px-",
        "recaptcha.net", "hcaptcha.com", "hcaptcha.net",
        "botd.adtimide.com", "botd.fpapi.io",
        "arkoselabs.com", "funcaptcha.com",
        "cloudflare.com/cdn-cgi", "challenges.cloudflare.com",
        "geetest.com", "gt3.geetest.com",
        "akamai.com", "akamaized.net",
        "imperva.com", "incapsula.com",
        "distilnetworks.com",
        "stackpath.com",
        "shape.com",
    ])

    @classmethod
    def _is_ad_domain(cls, url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
            return any(ad in host for ad in cls._AD_DOMAINS)
        except Exception:
            return False

    @classmethod
    def _is_anti_bot_domain(cls, url: str) -> bool:
        try:
            url_lower = url.lower()
            for bot in cls._ANTI_BOT_DOMAINS:
                if bot in url_lower:
                    return True
            return False
        except Exception:
            return False

    @property
    def resources(self) -> dict[str, CapturedResource]:
        return self._resources

    @property
    def api_calls(self) -> list[CapturedResource]:
        return self._api_calls

    @property
    def websocket_urls(self) -> list[str]:
        return self._ws_urls

    def get_by_type(self, resource_type: str) -> list[CapturedResource]:
        return [r for r in self._resources.values() if r.resource_type == resource_type]

    def clear(self) -> None:
        self._resources.clear()
        self._api_calls.clear()
        self._ws_urls.clear()
