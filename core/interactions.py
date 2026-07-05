from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

log = logging.getLogger("cloner.interactions")

MENU_SELECTORS = [
    "nav a", "[role='navigation'] a", ".nav-item > a", ".menu-item > a",
    "header a", ".navbar a", ".site-nav a",
]

DROPDOWN_SELECTORS = [
    "[data-toggle='dropdown']", "[aria-haspopup='true']", ".dropdown-toggle",
    "[data-bs-toggle='dropdown']", ".has-submenu > a",
]

ACCORDION_SELECTORS = [
    "[data-toggle='collapse']", "[data-bs-toggle='collapse']", ".accordion-button",
    "[aria-expanded='false']", ".collapsible", "details:not([open]) summary",
]

HOVER_SELECTORS = [
    ".has-dropdown", ".has-mega-menu", "[data-hover]", ".hover-menu",
]

COOKIE_BANNER_SELECTORS = [
    "#cookie-accept", ".cookie-accept", "[id*='cookie'] button",
    "[class*='cookie'] button", "[id*='consent'] button",
    "[class*='consent'] button", "[id*='gdpr'] button",
]

ACCEPT_TEXTS = [
    "accept", "accepter", "tout accepter", "accept all",
    "j'accepte", "agree", "ok", "got it", "compris",
    "i agree", "allow", "autoriser", "consent",
]


CONTENT_INDICATORS = [
    "[data-testid*='result']", "[data-testid*='hotel']", "[data-testid*='card']",
    "[data-testid*='item']", "[data-testid*='listing']",
    "[class*='result']", "[class*='Result']", "[class*='hotel']", "[class*='Hotel']",
    "[class*='listing']", "[class*='Listing']", "[class*='card']", "[class*='Card']",
    "[class*='item']", "[class*='Item']",
    "article", "[role='listitem']", "[role='article']",
    "main img", "[data-index]", "[data-position]",
]


class PageInteractor:
    def __init__(
        self,
        page: Page,
        scroll_steps: int = 15,
        scroll_pause_ms: int = 300,
        interaction_timeout_ms: int = 3000,
        max_interactions_per_type: int = 10,
    ) -> None:
        self.page = page
        self.scroll_steps = scroll_steps
        self.scroll_pause_ms = scroll_pause_ms
        self.interaction_timeout_ms = interaction_timeout_ms
        self.max_interactions_per_type = max_interactions_per_type

    async def run_all(self) -> dict[str, int]:
        stats: dict[str, int] = {}
        log.debug("Fermeture des bannières cookies…")
        stats["cookie_banners"] = await self.dismiss_cookie_banners()
        log.debug("Attente contenu principal…")
        stats["content_loaded"] = 1 if await self.wait_for_content() else 0
        log.debug("Scroll intelligent…")
        stats["scroll_cycles"] = await self.smart_scroll()
        log.debug("Ouverture des accordéons…")
        stats["accordions"] = await self.expand_accordions()
        log.debug("Déclenchement des dropdowns…")
        stats["dropdowns"] = await self.trigger_dropdowns()
        log.debug("Hover sur les menus…")
        stats["hovers"] = await self.hover_interactive_elements()
        log.debug("Découverte des menus de navigation…")
        stats["nav_items"] = await self.interact_nav_menus()
        log.debug("Interactions terminées : %s", stats)
        return stats

    async def dismiss_cookie_banners(self) -> int:
        dismissed = 0
        try:
            script = """
                const texts = %s;
                const elements = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                for (const el of elements) {
                    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (texts.some(x => t === x || t.startsWith(x))) {
                        el.click();
                        return 1;
                    }
                }
                return 0;
            """ % str(ACCEPT_TEXTS)
            result = await self.page.evaluate(script)
            if result:
                dismissed += 1
                await self.page.wait_for_timeout(500)
        except Exception:
            pass
        for selector in COOKIE_BANNER_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                for el in elements[:2]:
                    await el.click(timeout=1000)
                    dismissed += 1
                    await self.page.wait_for_timeout(300)
            except Exception:
                pass
        return dismissed

    async def smart_scroll(self) -> int:
        cycles = 0
        max_cycles = self.scroll_steps * 3
        last_height = await self.page.evaluate("document.body.scrollHeight")
        no_change_count = 0

        for _ in range(max_cycles):
            await self.page.evaluate("""
                window.scrollBy({ top: window.innerHeight * 0.9, behavior: 'smooth' });
            """)
            await self.page.wait_for_timeout(self.scroll_pause_ms)
            cycles += 1

            current_height = await self.page.evaluate("document.body.scrollHeight")
            if current_height == last_height:
                no_change_count += 1
                if no_change_count >= 3:
                    break
            else:
                no_change_count = 0
            last_height = current_height

        await self.page.evaluate("window.scrollTo(0, 0)")
        await self.page.wait_for_timeout(300)
        return cycles

    async def wait_for_content(self, timeout_ms: int = 30_000) -> bool:
        try:
            await self.page.wait_for_function("""
                () => {
                    const indicators = %s;
                    for (const sel of indicators) {
                        const els = document.querySelectorAll(sel);
                        if (els.length >= 3) return true;
                    }
                    const imgs = document.querySelectorAll('img[src*="http"]');
                    if (imgs.length >= 5) return true;
                    const main = document.querySelector('main, #content, #main, .content');
                    if (main && main.querySelectorAll('a, button, div, p').length >= 20) return true;
                    return false;
                }
            """ % str(CONTENT_INDICATORS), timeout=timeout_ms)
            return True
        except PlaywrightTimeout:
            log.debug("Timeout attente contenu (%d ms)", timeout_ms)
            return False
        except Exception as exc:
            log.warning("Erreur wait_for_content : %s", exc)
            return False

    async def wait_for_real_content(self, timeout_ms: int = 60_000) -> bool:
        try:
            await self.page.wait_for_function("""
                () => {
                    var textEls = document.querySelectorAll('p, span, h1, h2, h3, li, a, td, th');
                    var realCount = 0;
                    for (var i = 0; i < textEls.length; i++) {
                        var t = (textEls[i].innerText || textEls[i].textContent || '').trim();
                        if (t.length > 20) realCount++;
                    }
                    if (realCount < 2 && textEls.length < 5) return false;

                    var loaders = document.querySelectorAll('.spinner, .loader, .skeleton, .placeholder, .shimmer, [aria-busy=true], [role=progressbar]');
                    if (loaders.length > 0) return false;

                    var imgs = document.querySelectorAll('img[src]');
                    var loadedImgs = 0;
                    for (var i = 0; i < imgs.length; i++) {
                        if (imgs[i].src.indexOf('http') === 0) loadedImgs++;
                    }
                    if (loadedImgs < 1 && imgs.length > 0) return false;

                    var total = document.querySelectorAll('*').length;
                    if (total < 20) return false;

                    return true;
                }
            """, timeout=timeout_ms)
            return True
        except PlaywrightTimeout:
            log.debug("Timeout wait_for_real_content (%d ms)", timeout_ms)
            return False
        except Exception as exc:
            log.warning("Erreur wait_for_real_content : %s", exc)
            return False

    async def expand_accordions(self) -> int:
        expanded = 0
        for selector in ACCORDION_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                for el in elements[: self.max_interactions_per_type]:
                    try:
                        await el.click(timeout=self.interaction_timeout_ms)
                        expanded += 1
                        await self.page.wait_for_timeout(200)
                    except Exception:
                        pass
            except Exception:
                pass
        return expanded

    async def trigger_dropdowns(self) -> int:
        triggered = 0
        for selector in DROPDOWN_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                for el in elements[: self.max_interactions_per_type]:
                    try:
                        await el.click(timeout=self.interaction_timeout_ms)
                        triggered += 1
                        await self.page.wait_for_timeout(150)
                        await self.page.keyboard.press("Escape")
                        await self.page.wait_for_timeout(100)
                    except Exception:
                        pass
            except Exception:
                pass
        return triggered

    async def hover_interactive_elements(self) -> int:
        hovered = 0
        for selector in HOVER_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                for el in elements[: self.max_interactions_per_type]:
                    try:
                        await el.hover(timeout=self.interaction_timeout_ms)
                        hovered += 1
                        await self.page.wait_for_timeout(200)
                    except Exception:
                        pass
            except Exception:
                pass
        return hovered

    async def interact_nav_menus(self) -> int:
        interacted = 0
        for selector in MENU_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                for el in elements[: self.max_interactions_per_type]:
                    try:
                        await el.hover(timeout=self.interaction_timeout_ms)
                        interacted += 1
                        await self.page.wait_for_timeout(100)
                    except Exception:
                        pass
            except Exception:
                pass
        return interacted

    async def click_load_more_buttons(self) -> int:
        clicked = 0
        load_more_selectors = [
            "button:has-text('Load more')",
            "button:has-text('Voir plus')",
            "button:has-text('Show more')",
            "button:has-text('Afficher plus')",
            "button:has-text('Charger plus')",
            "button:has-text('Plus')",
            "button:has-text('More')",
            "[class*='load-more'] button",
            "[class*='load-more'] a",
            "[class*='show-more']",
            "[class*='voir-plus']",
            "a:has-text('Load more')",
            "a:has-text('Voir plus')",
            "[aria-label*='Load more']",
            "[aria-label*='Show more']",
        ]
        for selector in load_more_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for el in elements[:5]:
                    try:
                        await el.click(timeout=self.interaction_timeout_ms)
                        clicked += 1
                        await self.page.wait_for_timeout(500)
                        await self.wait_for_stable_network(3_000)
                    except Exception:
                        pass
            except Exception:
                pass
        return clicked

    async def wait_for_stable_network(self, timeout_ms: int = 10_000) -> bool:
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
            return True
        except PlaywrightTimeout:
            log.debug("Timeout networkidle (%d ms)", timeout_ms)
            return False

    async def freeze_dom(self) -> str:
        log.debug("Figement du DOM (mode snapshot)...")
        try:
            await self.page.evaluate("""
                () => {
                    try {
                        const blocked = ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource'];
                        for (const key of blocked) {
                            try {
                                window[key] = function() {};
                                window[key].prototype = {};
                            } catch(e) {}
                        }
                        document.querySelectorAll('script[src]').forEach(s => {
                            const src = (s.getAttribute('src') || '').toLowerCase();
                            if (src.includes('api') || src.includes('data') || src.includes('analytics')
                                || src.includes('track') || src.includes('telemetry') || src.includes('sentry')
                                || src.includes('hotjar') || src.includes('gtm') || src.includes('ga.')
                                || src.includes('facebook') || src.includes('ads')) {
                                s.remove();
                            }
                        });
                        document.querySelectorAll('noscript').forEach(s => s.remove());
                        document.querySelectorAll('[data-nscript]').forEach(s => s.remove());
                        document.querySelectorAll('script[defer], script[async]').forEach(s => s.remove());
                        document.querySelectorAll('link[rel="preload"], link[rel="prefetch"], link[rel="dns-prefetch"]').forEach(s => s.remove());
                        document.querySelectorAll('iframe[src*="google"], iframe[src*="facebook"], iframe[src*="doubleclick"]').forEach(s => s.remove());
                    } catch(e) {}
                }
            """)
            await self.page.wait_for_timeout(500)
        except Exception as exc:
            log.warning("Erreur freeze_dom : %s", exc)
        return await self.page.content()

    async def detect_spa_framework(self) -> Optional[str]:
        result = await self.page.evaluate("""
            () => {
                if (window.__NUXT__ || document.querySelector('#__nuxt')) return 'Nuxt';
                if (window.__NEXT_DATA__) return 'Next.js';
                if (window.angular || document.querySelector('[ng-version]')) return 'Angular';
                if (window.__vue_store__ || document.querySelector('[data-v-app]')) return 'Vue';
                if (window.__reactFiber || document.querySelector('[data-reactroot]')) return 'React';
                if (window.Ember) return 'Ember';
                if (window.Svelte) return 'Svelte';
                return null;
            }
        """)
        if result:
            log.info("Framework SPA : %s", result)
        return result

    async def detect_angular_version(self) -> Optional[str]:
        """Détecte la version Angular via l'élément d'attribut ng-version."""
        return await self.page.evaluate("""
            () => {
                const el = document.querySelector('[ng-version]');
                if (!el) return null;
                return el.getAttribute('ng-version');
            }
        """)

    async def wait_for_angular_hydration(self, timeout_ms: int = 30_000) -> bool:
        """Attend que l'application Angular soit totalement hydratée.

        Vérifications : 
        - Zones Angular hydratantes : attendre la fin du champ ng-version, détecteur d'ng-zone, composants Angular vus.
        - Chargement vs contenu réel
        """
        try:
            await self.page.wait_for_function("""
                () => {
                    // Angular a au moins un composant d'application initialisé
                    const ngVersions = document.querySelectorAll('[ng-version]');
                    if (ngVersions.length > 0) {
                        return true;
                    }
                    // Il y a un indicateur Angular d'application Angular au DOM
                    if (window.angular && window.angular.element) {
                        const apps = window.angular.bootstrap(document, []);
                        if (apps && apps injector) return true;
                    }
                    return false;
                }
            """, timeout=timeout_ms)
            return True
        except Exception as exc:
            log.debug("wait_for_angular_hydration échoué: %s", exc)
            return False

    async def detect_nuxt_version(self) -> Optional[str]:
        """Nuxt 2 vs 3."""
        return await self.page.evaluate("""
            () => {
                if (!(window.__NUXT__ || document.querySelector('#__nuxt'))) return null;
                if (document.querySelector('#__NUXT_DATA__')) return 'Nuxt 3';
                if (window.__NUXT__ && window.__NUXT__.config) return 'Nuxt 3';
                return 'Nuxt 2';
            }
        """)

    async def wait_for_nuxt_hydration(self, timeout_ms: int = 30_000) -> bool:
        """Wait for the Nuxt app to finish hydrating.

        Checks:
        - Preloader is hidden (display:none / opacity:0 / removed)
        - Canvas elements have non-zero dimensions (Three.js initialised)
        - Real visible text content exists
        - Nuxt loading indicators are gone
        """
        try:
            await self.page.wait_for_function("""
                () => {
                    /* 1 – preloader must be hidden */
                    const preloader = document.querySelector('.preloader');
                    if (preloader) {
                        const s = window.getComputedStyle(preloader);
                        if (s.display !== 'none' && s.opacity !== '0'
                            && s.visibility !== 'hidden' && s.pointerEvents !== 'none') {
                            return false;
                        }
                    }

                    /* 2 – Nuxt / app loading indicators */
                    const loaders = document.querySelectorAll(
                        '#nuxt-loading, .nuxt-loading, [data-nuxt-loading], ' +
                        '.nuxt-progress, .loading-indicator, .nprogress'
                    );
                    for (const l of loaders) {
                        if (l.offsetParent !== null) return false;
                    }

                    /* 3 – canvas has been initialised (has dimensions) */
                    const canvases = document.querySelectorAll('canvas');
                    let hasCanvas = false;
                    for (const c of canvases) {
                        if (c.width > 0 || c.height > 0
                            || c.getBoundingClientRect().width > 0) {
                            hasCanvas = true;
                            break;
                        }
                    }

                    /* 4 – visible text content (page is rendered) */
                    const textEls = document.querySelectorAll('p, h1, h2, h3, li, span');
                    let visibleText = 0;
                    for (const el of textEls) {
                        const t = (el.innerText || '').trim();
                        if (t.length > 10) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) visibleText++;
                        }
                    }

                    /* 5 – Nuxt config payload present */
                    const hasNuxtConfig = !!(window.__NUXT__);

                    return hasCanvas || visibleText >= 2 || hasNuxtConfig;
                }
            """, timeout=timeout_ms)
            return True
        except Exception as exc:
            log.debug("wait_for_nuxt_hydration échoué: %s", exc)
            return False

    async def collect_spa_routes(self) -> list[str]:
        routes = await self.page.evaluate("""
            () => {
                const routes = new Set();
                if (window.__NEXT_DATA__) {
                    try { if (window.__NEXT_DATA__.page) routes.add(window.__NEXT_DATA__.page); } catch(e) {}
                }
                try {
                    const app = document.querySelector('#app')?.__vue_app__;
                    if (app?.config?.globalProperties?.$router?.options?.routes) {
                        app.config.globalProperties.$router.options.routes.forEach(r => {
                            if (r.path) routes.add(r.path);
                        });
                    }
                } catch(e) {}
                document.querySelectorAll('[data-route], [href^="/"]').forEach(el => {
                    const href = el.getAttribute('data-route') || el.getAttribute('href');
                    if (href && href.startsWith('/')) routes.add(href);
                });
                return Array.from(routes);
            }
        """)
        return routes or []

    async def extract_tailwind_config(self, page: Page) -> Optional[str]:
        """Détecte le CDN Tailwind externe ou les balises style via HEAD.
        
        Returns le contenu CSS transformé appliqué.
        """
        try:
            script = """
                const styles = [];
                const heads = document.querySelectorAll('link[rel*="stylesheet"][href*="tailwind"]:not([data-dummy])');
                const inlines = document.querySelectorAll('style[type*="tailwind"]');
                heads.forEach(l => {
                    styles.push(l.getAttribute('href'));
                    l.setAttribute('data-dummy', 'true');
                });
                inlines.forEach(s => {
                    styles.push(s.textContent);
                });
                return styles;
            """
            result = await page.evaluate(script)
            return result if result else None
        except Exception as exc:
            log.debug("extract_tailwind_config échoué: %s", exc)
            return None

    async def apply_tailwind_fix(self, page: Page, config) -> None:
        """Applique les styles Tailwind pour la fix mobile et préserve les classes utilitaires.
        
        Args:
            page: Page Playwright à modifier.
            config: Config de crawling contenant tailwind_css_mode.
        """
        try:
            inject_js = """
                window.__tw_fix_applied = true;
                // Empêche l'ajout de script fslightbox block qui inhibe les média queries mobiles dans le clone parfait.
                document.querySelectorAll('[src*="fslightbox"]').forEach(s => {
                    s.setAttribute('data-dummy-fix', 'true');
                });
                // Si Tailwind possède le script du CDN de préchargement des polices, vide-sonne.
                document.querySelectorAll('script[src*="tailwind.com"][src*="font"]').forEach(s => {
                    s.setAttribute('data-dummy-font', 'true');
                });
                // Force la largeur de la viewport de manière plus précise que les balises meta de scale='1'
                const oldMeta = document.querySelector('meta[name="viewport"]');
                if (oldMeta) {
                    oldMeta.setAttribute('content', 'width=device-width, initial-scale=1.0');
                } else {
                    const newMeta = document.createElement('meta');
                    newMeta.setAttribute('name', 'viewport');
                    newMeta.setAttribute('content', 'width=device-width, initial-scale=1.0');
                    document.head.appendChild(newMeta);
                }
                // Insère un style minimal pour prendre en compte les issues de base de Tailwind responsive / mobile-first
                if (!document.getElementById('tw-mobile-fix')) {
                    const style = document.createElement('style');
                    style.id = 'tw-mobile-fix';
                    style.textContent = `
                        @supports (-webkit-appearance:none) { body { padding-bottom: env(safe-area-inset-bottom); } }
                        .tw__safe-area-inset-bottom { padding-bottom: env(safe-area-inset-bottom); }
                        .tw__safe-area-inset-top { padding-top: env(safe-area-inset-top); }
                        .tw__safe-area-inset-left { padding-left: env(safe-area-inset-left); }
                        .tw__safe-area-inset-right { padding-right: env(safe-area-inset-right); }
                    `;
                    document.head.appendChild(style);
                }
            """
            await page.evaluate(inject_js)
        except Exception as exc:
            log.debug("apply_tailwind_fix échoué: %s", exc)

    async def fix_mobile_viewport(self) -> None:
        """Applique la réponse mobile empêchant la compression de l'URL telle que décrite dans le atelier ;
        vise à forcer les balises meta établies par certains frameworks SPA.
        """
        try:
            await self.page.evaluate("""
                const oldMeta = document.querySelector('meta[name="viewport"]');
                if (oldMeta) {
                    const oldContent = oldMeta.getAttribute('content');
                    if (oldContent && !oldContent.includes('width=device-width') && !oldContent.includes('initial-scale')) {
                        oldMeta.setAttribute('content', 'width=device-width, initial-scale=1.0');
                    }
                } else {
                    const newMeta = document.createElement('meta');
                    newMeta.setAttribute('name', 'viewport');
                    newMeta.setAttribute('content', 'width=device-width, initial-scale=1.0');
                    document.head.appendChild(newMeta);
                }
            """)
            await self.page.wait_for_timeout(200)
        except Exception as exc:
            log.debug("fix_mobile_viewport échoué: %s", exc)
