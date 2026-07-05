from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright, ProxySettings

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    async def stealth_async(page: Page) -> None:
        pass

log = logging.getLogger("cloner.browser")


class BrowserConfig:
    def __init__(
        self,
        headless: bool = True,
        channel: str = "chromium",
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None,
        user_agent: Optional[str] = None,
        cookies_file: Optional[Path] = None,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        locale: str = "fr-FR",
        timezone: str = "Europe/Paris",
        extra_http_headers: Optional[dict[str, str]] = None,
        http_credentials: Optional[dict[str, str]] = None,
        slow_mo: int = 0,
        stealth: bool = False,
        persistent_profile: Optional[Path] = None,
    ) -> None:
        self.headless = headless
        self.channel = channel
        self.proxy_url = proxy_url
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.cookies_file = cookies_file
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.locale = locale
        self.timezone = timezone
        self.extra_http_headers = extra_http_headers or {}
        self.http_credentials = http_credentials
        self.slow_mo = slow_mo
        self.stealth = stealth
        self.persistent_profile = persistent_profile

    @property
    def proxy_settings(self) -> Optional[ProxySettings]:
        if not self.proxy_url:
            return None
        settings: ProxySettings = {"server": self.proxy_url}
        if self.proxy_username:
            settings["username"] = self.proxy_username
        if self.proxy_password:
            settings["password"] = self.proxy_password
        return settings


class BrowserManager:
    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def start(self) -> None:
        profile = self.config.persistent_profile
        mode = "persistant" if profile else "temporaire"
        log.info("Démarrage Playwright (channel=%s, headless=%s, mode=%s)",
                 self.config.channel, self.config.headless, mode)
        self._playwright = await async_playwright().start()
        launch_kwargs: dict = {
            "headless": self.config.headless,
            "slow_mo": self.config.slow_mo,
        }
        if self.config.channel != "chromium":
            launch_kwargs["channel"] = self.config.channel
        if self.config.proxy_settings:
            launch_kwargs["proxy"] = self.config.proxy_settings
        browser_type = self._playwright.chromium
        self._browser = await browser_type.launch(**launch_kwargs)
        self._context = await self._create_context()
        log.info("Navigateur prêt")

    async def stop(self) -> None:
        if self._context:
            await self._save_cookies()
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        log.info("Navigateur arrêté")

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()

    async def _create_context(self) -> BrowserContext:
        context_kwargs: dict = {
            "user_agent": self.config.user_agent,
            "viewport": {"width": self.config.viewport_width, "height": self.config.viewport_height},
            "locale": self.config.locale,
            "timezone_id": self.config.timezone,
            "extra_http_headers": self.config.extra_http_headers,
            "ignore_https_errors": True,
        }
        if self.config.http_credentials:
            context_kwargs["http_credentials"] = self.config.http_credentials
        context = await self._browser.new_context(**context_kwargs)
        if self.config.cookies_file and self.config.cookies_file.exists():
            await self._load_cookies(context)
        return context

    async def _load_cookies(self, context: BrowserContext) -> None:
        try:
            cookies = json.loads(self.config.cookies_file.read_text(encoding="utf-8"))
            await context.add_cookies(cookies)
            log.info("Cookies chargés (%d entrées)", len(cookies))
        except Exception as exc:
            log.warning("Impossible de charger les cookies : %s", exc)

    async def _save_cookies(self) -> None:
        if not self.config.cookies_file or not self._context:
            return
        try:
            cookies = await self._context.cookies()
            self.config.cookies_file.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.info("Cookies sauvegardés (%d entrées)", len(cookies))
        except Exception as exc:
            log.warning("Impossible de sauvegarder les cookies : %s", exc)

    async def inject_cookies(self, cookies: list[dict]) -> None:
        if self._context:
            await self._context.add_cookies(cookies)

    async def new_page(self) -> Page:
        if not self._context:
            raise RuntimeError("Le navigateur n'est pas démarré. Appelez start() d'abord.")
        page = await self._context.new_page()
        if self.config.stealth:
            await self._apply_stealth(page)
        return page

    async def _apply_stealth(self, page: Page) -> None:
        if HAS_STEALTH:
            await stealth_async(page)
        try:
            await page.evaluate("""
                () => {
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1,2,3,4,5].map(() => ({ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' }))
                    });
                    Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr', 'en-US', 'en'] });
                    if (!navigator.language) Object.defineProperty(navigator, 'language', { get: () => 'fr-FR' });
                    if (!navigator.deviceMemory) Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                    if (!navigator.hardwareConcurrency) Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                    if (!navigator.maxTouchPoints) Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
                    if (!chrome) var chrome = { loadTimes: function() {}, csi: function() {} };
                    try {
                        const getImageData = CanvasRenderingContext2D.prototype.getImageData;
                        CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {
                            const imageData = getImageData.call(this, x, y, w, h);
                            const p = imageData.data;
                            for (let i = 0; i < p.length; i += 4) { p[i] ^= 1; }
                            return imageData;
                        };
                    } catch(e) {}
                }
            """)
        except Exception as exc:
            log.warning("Erreur fingerprint : %s", exc)

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context

    @property
    def browser(self) -> Optional[Browser]:
        return self._browser
