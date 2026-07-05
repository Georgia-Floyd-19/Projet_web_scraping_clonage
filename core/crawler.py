from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Coroutine, Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .browser import BrowserConfig, BrowserManager
from .downloader import ResourceDownloader
from .interactions import PageInteractor
from .interceptor import NetworkInterceptor
from .animations import AnimationDetector
from .fonts import FontCapture
from .rewriter import HTMLRewriter, CSSRewriter
from .storage import StorageManager
from .utils import (
    get_domain, is_internal_url, is_html_url, normalize_url,
    clean_url, extract_links_from_js, url_depth, human_size,
)

log = logging.getLogger("cloner.crawler")

STATIC_RESOURCE_TYPES = {"stylesheet", "script", "image", "media", "font", "other"}

TYPE_TO_CATEGORY = {
    "stylesheet": "styles", "script": "scripts", "image": "images",
    "media": "media", "font": "fonts", "document": "pages",
    "fetch": "api", "xhr": "api", "other": "misc",
}

ProgressCallback = Optional[Callable[[dict], Coroutine]]


@dataclass
class CrawlConfig:
    start_url: str
    output_folder: Path
    max_pages: int = 50
    max_depth: int = 5
    page_render_wait_ms: int = 2500
    network_idle_timeout_ms: int = 10_000
    navigation_timeout_ms: int = 30_000
    request_delay_s: float = 0.5
    max_concurrent_downloads: int = 8
    enable_interactions: bool = True
    save_api_responses: bool = True
    extract_js_routes: bool = True
    resume_from_existing: bool = True
    max_url_depth: int = 10
    browser_config: Optional[BrowserConfig] = None
    wait_strategy: str = "networkidle"
    wait_for_selector: Optional[str] = None
    page_timeout_ms: int = 60_000
    scroll_steps: int = 5
    content_wait_timeout_ms: int = 30_000
    clone_mode: str = "hybrid"
    tailwind_css_mode: str = "auto"
    include_tailwind_fonts: bool = True
    fix_mobile_viewport: bool = True
    preserve_tailwind_purge: bool = False


@dataclass
class CrawlResult:
    pages_cloned: int = 0
    resources_saved: int = 0
    api_calls_saved: int = 0
    output_folder: str = ""
    errors: list[str] = field(default_factory=list)
    framework_detected: Optional[str] = None
    total_size_bytes: int = 0

    @property
    def success(self) -> bool:
        return self.pages_cloned > 0


class SiteCrawler:
    def __init__(self, config: CrawlConfig, progress_callback: ProgressCallback = None) -> None:
        self.config = config
        self.root_domain = get_domain(config.start_url)
        self._storage = StorageManager(config.output_folder, config.start_url)
        self._visited: set[str] = set()
        self._to_visit: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._errors: list[str] = []
        self._framework: Optional[str] = None
        self._resources_saved: int = 0
        self._api_saved: int = 0
        self._progress_cb = progress_callback

    async def _progress(self, type_: str, step: str, percent: int,
                        message: str = None, level: str = "info", extra: dict = None):
        if not self._progress_cb:
            return
        data = {"type": type_, "step": step, "percent": min(percent, 100)}
        if message:
            data["message"] = message
            data["level"] = level
        if extra:
            data.update(extra)
        await self._progress_cb(data)

    async def run(self) -> CrawlResult:
        log.info("=== Démarrage du clonage de %s ===", self.config.start_url)
        await self._progress("progress", "Initialisation...", 0)

        if self.config.resume_from_existing:
            self._storage.load_existing()
            for url in self._storage.url_to_path_map:
                self._visited.add(url)
            log.info("Reprise : %d URLs déjà traitées", len(self._visited))

        browser_cfg = self.config.browser_config or BrowserConfig()

        await self._progress("progress", "Lancement du navigateur...", 3)

        async with BrowserManager(browser_cfg) as manager:
            async with ResourceDownloader(
                self.config.output_folder,
                max_concurrent=self.config.max_concurrent_downloads,
                requests_per_second=1.0 / max(self.config.request_delay_s, 0.1),
            ) as downloader:
                await self._to_visit.put((self.config.start_url, 0))

                total_pages = self.config.max_pages
                processed = 0

                while not self._to_visit.empty() and len(self._visited) < total_pages:
                    url, depth = await self._to_visit.get()
                    if url in self._visited:
                        continue
                    if depth > self.config.max_depth:
                        continue
                    if url_depth(url) > self.config.max_url_depth:
                        continue

                    processed += 1
                    pct = 5 + int((processed / total_pages) * 70)
                    await self._progress(
                        "progress", f"Page {processed}/{total_pages}...", pct,
                        message=f"Traitement de {url}", level="info",
                    )

                    page = await manager.new_page()
                    try:
                        await self._process_page(page, url, depth, downloader, processed, total_pages)
                    finally:
                        await page.close()

        await self._progress("progress", "Finalisation du clone...", 85)

        self._storage.finalize(
            pages_cloned=len(self._visited),
            resources_saved=self._resources_saved,
            api_calls_saved=self._api_saved,
            errors=self._errors,
            framework=self._framework,
            clone_mode=self.config.clone_mode,
        )

        result = CrawlResult(
            pages_cloned=len(self._visited),
            resources_saved=self._resources_saved,
            api_calls_saved=self._api_saved,
            output_folder=str(self.config.output_folder),
            errors=self._errors,
            framework_detected=self._framework,
            total_size_bytes=self._storage.manifest.total_size_bytes,
        )

        log.info("=== Clonage terminé : %d pages, %d ressources, %s ===",
                 result.pages_cloned, result.resources_saved, human_size(result.total_size_bytes))

        return result

    async def _process_page(
        self, page: Page, url: str, depth: int,
        downloader: ResourceDownloader, page_num: int, total: int,
    ) -> None:
        log.info("[%d/%d] Profondeur %d : %s", len(self._visited) + 1, total, depth, url)

        interceptor = NetworkInterceptor(block_anti_bot=True)
        await interceptor.attach(page)

        wait_until = self.config.wait_strategy
        try:
            await page.goto(url, wait_until=wait_until, timeout=self.config.page_timeout_ms)
        except PlaywrightTimeout:
            log.warning("Timeout navigation %s (%s)", url, wait_until)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.config.page_timeout_ms)
            except PlaywrightTimeout:
                log.warning("Timeout même en domcontentloaded %s", url)
                self._errors.append(f"{url} : timeout")
                self._visited.add(url)
                return
        except Exception as exc:
            log.error("Erreur navigation %s : %s", url, exc)
            self._errors.append(f"{url} : {exc}")
            self._visited.add(url)
            return

        if self.config.wait_for_selector:
            try:
                await page.wait_for_selector(self.config.wait_for_selector, timeout=self.config.page_timeout_ms)
            except PlaywrightTimeout:
                log.warning("Selector introuvable %s : %s", self.config.wait_for_selector, url)

        interactor = PageInteractor(page, scroll_steps=self.config.scroll_steps)
        await interactor.wait_for_stable_network(self.config.network_idle_timeout_ms)

        if not self._framework and len(self._visited) == 0:
            self._framework = await interactor.detect_spa_framework()
            if self._framework:
                await self._progress("log", "", 0, message=f"Framework SPA détecté : {self._framework}", level="success")

        if self.config.enable_interactions:
            await interactor.run_all()
            await interactor.click_load_more_buttons()

            for attempt in range(3):
                await interactor.smart_scroll()
                await interactor.click_load_more_buttons()
                await interactor.wait_for_stable_network(5_000)
                if await interactor.wait_for_real_content(15_000):
                    log.info("Contenu réel détecté (tentative %d/3)", attempt + 1)
                    break
                log.info("Contenu pas encore prêt, tentative %d/3", attempt + 1)

        await interactor.wait_for_stable_network(8_000)

        # ––– Forcer scroll_steps élevé pour mode nuxt-perfect –––
        if self.config.clone_mode == "nuxt-perfect":
            interactor = PageInteractor(page, scroll_steps=30, scroll_pause_ms=500)

        # ––– Frameworks SPA / hydratation –––
        if self._framework:
            if 'Nuxt' in self._framework:
                log.info("Nuxt détecté, attente de l'hydratation…")
                await interactor.wait_for_nuxt_hydration(timeout_ms=30_000)
                await self._progress("log", "", 0,
                                     message="Nuxt hydraté, révélations animations scroll…",
                                     level="info")

            elif 'Angular' in self._framework:
                log.info("Angular détecté, attente de l'hydratation…")
                await interactor.wait_for_angular_hydration(timeout_ms=30_000)
                await self._progress("log", "", 0,
                                     message="Angular hydraté, révélations animations scroll…",
                                     level="info")

            elif 'Vue' in self._framework:
                log.info("Vue détecté, attente de l'hydratation…")
                await interactor.wait_for_nuxt_hydration(timeout_ms=30_000)
                await self._progress("log", "", 0,
                                     message="Vue hydraté, révélations animations scroll…",
                                     level="info")

            elif 'Next.js' in self._framework:
                log.info("Next.js détecté, attente de l'hydratation…")
                await interactor.wait_for_nuxt_hydration(timeout_ms=30_000)
                await self._progress("log", "", 0,
                                     message="Next.js hydraté, révélations animations scroll…",
                                     level="info")

            # Scroll lent jusqu'en bas pour déclencher les animations scroll-reveal / lazy-load
            log.info("Déclenchement des animations au scroll…")
            body_height = await page.evaluate("document.body.scrollHeight")
            viewport_height = await page.evaluate("window.innerHeight")
            scroll_steps = max(20, int(body_height / (viewport_height * 0.15)) + 1)
            for i in range(scroll_steps):
                y = int(i * viewport_height * 0.15)
                await page.evaluate(f"window.scrollTo(0, {y})")
                await page.wait_for_timeout(400)
            # Revenir en haut
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(800)
            log.info("Scroll déclencheur terminé (%d étapes)", scroll_steps)
            await self._progress("log", "", 0,
                                 message=f"Contenu révélé, capture en cours…",
                                 level="info")

            # ––– Tailwind CSS et configuration –––
            if self.config.tailwind_css_mode != "never":
                tail_js = await interactor.extract_tailwind_config(page)
                if tail_js:
                    await self._progress("log", "", 0,
                                         message="Configuration Tailwind extraite, application des styles…",
                                         level="info")
                    await interactor.apply_tailwind_fix(page, self.config)

            # ––– Fixe le viewport des appareils mobiles si nécessaire –––
            if self.config.fix_mobile_viewport:
                await interactor.fix_mobile_viewport()

        # ––– Canvas + animation + clone mode –––
        from .screenshot import CanvasCapture
        canvas_cap = CanvasCapture(page, self.config.output_folder)
        has_canvas = await canvas_cap.has_webgl_canvas()

        if self.config.clone_mode == "nuxt-perfect":
            canvas_html = await canvas_cap.capture_page()
            snapshot_html = await interactor.freeze_dom()
            html = canvas_html if len(canvas_html) > 100 else snapshot_html
            log.info("Nuxt-perfect : canvas extraits (%d car.) + snapshot (%d car.)",
                     len(canvas_html), len(snapshot_html))
        elif has_canvas or self.config.clone_mode in ("screenshot", "auto"):
            html = await canvas_cap.capture_page()
            log.info("Canvas extraits en images (%d caractères)", len(html))
        elif self.config.clone_mode == "snapshot":
            html = await interactor.freeze_dom()
            log.info("DOM figé pour snapshot (%d caractères)", len(html))
        else:
            html = await page.content()

        # ––– Animation detection –––
        animation_detector = AnimationDetector(page, self.config.output_folder)
        await animation_detector.detect_all_animations()
        log.info("Animations détectées (module)")

        # ––– Font capture –––
        font_capture = FontCapture(page, self.config.output_folder)
        await font_capture.capture_all_fonts()
        log.info("Polices capturées (module)")

        final_url = page.url
        if final_url != url:
            log.debug("Redirection : %s → %s", url, final_url)
            self._visited.add(url)
            url = final_url

        await self._save_intercepted_resources(interceptor, downloader)

        if self.config.extract_js_routes and self._framework:
            spa_routes = await interactor.collect_spa_routes()
            for route in spa_routes:
                abs_url = urljoin(url, route)
                normalized = normalize_url(clean_url(abs_url))
                if (normalized and normalized not in self._visited
                        and is_internal_url(normalized, self.root_domain)):
                    await self._to_visit.put((normalized, depth + 1))

        discovered_links = await self._rewrite_and_save(url, html, page_num)
        self._visited.add(url)

        for link in discovered_links:
            normalized = normalize_url(clean_url(link))
            if (normalized and normalized not in self._visited
                    and is_internal_url(normalized, self.root_domain)
                    and is_html_url(normalized)):
                await self._to_visit.put((normalized, depth + 1))

        final_url = page.url
        if final_url != url:
            log.debug("Redirection : %s → %s", url, final_url)
            self._visited.add(url)
            url = final_url

        await self._save_intercepted_resources(interceptor, downloader)

        if self.config.extract_js_routes and self._framework:
            spa_routes = await interactor.collect_spa_routes()
            for route in spa_routes:
                abs_url = urljoin(url, route)
                normalized = normalize_url(clean_url(abs_url))
                if (normalized and normalized not in self._visited
                        and is_internal_url(normalized, self.root_domain)):
                    await self._to_visit.put((normalized, depth + 1))

        discovered_links = await self._rewrite_and_save(url, html, page_num)
        self._visited.add(url)

        for link in discovered_links:
            normalized = normalize_url(clean_url(link))
            if (normalized and normalized not in self._visited
                    and is_internal_url(normalized, self.root_domain)
                    and is_html_url(normalized)):
                await self._to_visit.put((normalized, depth + 1))

        log.debug("Page traitée : %d liens", len(discovered_links))

    async def _save_intercepted_resources(
        self, interceptor: NetworkInterceptor, downloader: ResourceDownloader,
    ) -> None:
        for url, resource in interceptor.resources.items():
            if not resource.body:
                continue
            if resource.is_api and self.config.save_api_responses:
                try:
                    self._storage.save_api_response(url, resource.body, resource.is_graphql)
                    self._api_saved += 1
                except Exception as exc:
                    log.debug("Erreur API %s : %s", url, exc)
                continue
            category = TYPE_TO_CATEGORY.get(resource.resource_type, "misc")
            local_path = self._storage.resolve_path(url, category=category)
            if downloader.is_cached(url):
                continue
            result = await downloader.save_intercepted(resource, local_path)
            if result.success:
                self._storage.register(url, local_path)
                self._resources_saved += 1
                if resource.resource_type == "stylesheet":
                    await self._rewrite_css_file(url, local_path)

    async def _rewrite_and_save(self, url: str, html: str, page_num: int) -> list[str]:
        local_path = self._storage.resolve_path(url, category="pages", default_ext=".html")
        url_map = self._storage.url_to_path_map

        rewriter = HTMLRewriter(
            page_url=url,
            page_local_path=local_path,
            output_folder=self.config.output_folder,
            url_to_path_map=url_map,
            clone_mode=self.config.clone_mode,
        )

        rewritten_html = rewriter.rewrite(html)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        discovered: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            abs_url = urljoin(url, href).split("#")[0]
            if is_internal_url(abs_url, self.root_domain):
                discovered.append(abs_url)

        if self.config.extract_js_routes:
            for script in soup.find_all("script", src=False):
                if script.string:
                    js_links = extract_links_from_js(script.string, url)
                    discovered.extend(l for l in js_links if is_internal_url(l, self.root_domain))

        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(rewritten_html, encoding="utf-8")
        self._storage.register(url, local_path)
        self._storage.save_url_map()

        return discovered

    async def _rewrite_css_file(self, css_url: str, css_local_path: Path) -> None:
        try:
            css_text = css_local_path.read_text(encoding="utf-8", errors="replace")
            rewriter = CSSRewriter(
                css_url=css_url,
                css_local_path=css_local_path,
                output_folder=self.config.output_folder,
                url_to_path_map=self._storage.url_to_path_map,
            )
            rewritten = rewriter.rewrite(css_text)
            css_local_path.write_text(rewritten, encoding="utf-8")
        except Exception as exc:
            log.debug("Erreur réécriture CSS %s : %s", css_url, exc)


async def clone_site_async(
    start_url: str,
    output_folder: Path,
    max_pages: int = 50,
    headless: bool = True,
    channel: str = "chromium",
    proxy_url: Optional[str] = None,
    login_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    user_agent: Optional[str] = None,
    cookies_file: Optional[Path] = None,
    request_delay_s: float = 0.5,
    enable_interactions: bool = True,
    save_api_responses: bool = True,
    progress_callback: ProgressCallback = None,
    stealth: bool = False,
    wait_strategy: str = "networkidle",
    wait_for_selector: Optional[str] = None,
    page_timeout_ms: int = 60_000,
    scroll_steps: int = 5,
    clone_mode: str = "hybrid",
    persistent_profile: Optional[str] = None,
) -> CrawlResult:
    from .browser import BrowserConfig

    browser_config = BrowserConfig(
        headless=headless,
        channel=channel,
        proxy_url=proxy_url,
        user_agent=user_agent,
        cookies_file=cookies_file,
        stealth=stealth,
        persistent_profile=Path(persistent_profile) if persistent_profile else None,
        http_credentials=(
            {"username": username, "password": password}
            if username and password and not login_url
            else None
        ),
    )

    config = CrawlConfig(
        start_url=start_url,
        output_folder=output_folder,
        max_pages=max_pages,
        request_delay_s=request_delay_s,
        enable_interactions=enable_interactions,
        save_api_responses=save_api_responses,
        browser_config=browser_config,
        wait_strategy=wait_strategy,
        wait_for_selector=wait_for_selector,
        page_timeout_ms=page_timeout_ms,
        scroll_steps=scroll_steps,
        clone_mode=clone_mode,
    )

    crawler = SiteCrawler(config, progress_callback=progress_callback)

    if login_url and username and password:
        async with BrowserManager(browser_config) as manager:
            page = await manager.new_page()
            try:
                await page.goto(login_url, wait_until="networkidle", timeout=30_000)
                await page.fill("[name='username'], [name='email'], [id='username'], [id='email']", username)
                await page.fill("[name='password'], [id='password']", password)
                await page.press("[name='password'], [id='password']", "Enter")
                await page.wait_for_load_state("networkidle", timeout=10_000)
                if cookies_file:
                    import json
                    cookies = await manager.context.cookies()
                    cookies_file.write_text(
                        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    log.info("Cookies sauvegardés après login")
            except Exception as exc:
                log.warning("Erreur login : %s", exc)
            finally:
                await page.close()

    return await crawler.run()


def clone_site_sync(
    start_url: str,
    output_folder: Path,
    **kwargs,
) -> CrawlResult:
    return asyncio.run(clone_site_async(start_url, output_folder, **kwargs))
