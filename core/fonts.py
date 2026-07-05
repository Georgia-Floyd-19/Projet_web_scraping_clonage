from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import aiohttp

from playwright.async_api import Page

log = logging.getLogger("cloner.fonts")


class FontCapture:
    """Capture et stocke toutes les polices utilisées par le site.
    
    Extrait toutes les polices utilisés par le site, récupère les fichiers via HTTP,
    et stocke les fichiers de polices pour utilisation dans les clones parfaits.
    """

    def __init__(self, page: Page, output_folder: Path) -> None:
        self.page = page
        self.output_folder = output_folder
        self.fonts_dir = output_folder / "fonts"
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        self.font_metadata_path = output_folder / "font_metadata.json"

    async def capture_all_fonts(self) -> dict:
        """Capture toutes les polices utilisées par le site.
        
        Returns:
            Dict contenant les polices détectées et sauvegardées.
        """
        font_data = {
            "google_fonts": await self._capture_google_fonts(),
            "local_fonts": await self._detect_local_fonts(),
            "web_fonts": await self._detect_web_fonts(),
            "font_faces": await self._extract_font_faces(),
            "font_files": await self._collect_font_files(),
        }

        await self._save_font_metadata(font_data)
        return font_data

    async def _capture_google_fonts(self) -> list:
        """Capture les polices Google Fonts.
        
        Returns:
            Liste des polices Google Fonts trouvées.
        """
        log.info("Détection polices Google Fonts...")

        google_fonts = await self.page.evaluate("""
            () => {
                const fonts = [];
                
                // Rechercher les liens Google Fonts
                document.querySelectorAll('link[href*="fonts.googleapis.com"]').forEach(link => {
                    const href = link.getAttribute('href');
                    try {
                        const url = new URL(href);
                        const params = new URLSearchParams(url.search);
                        const families = params.get('family');
                        if (families) {
                            families.split(',').forEach(family => {
                                const [name, subsets] = family.split(':');
                                fonts.push({
                                    family: name.replace(/\\s+/g, '+'),
                                    subsets: subsets || 'latin',
                                    source: href
                                });
                            });
                        }
                    } catch(e) {
                    }
                });
                
                return fonts;
            }
        """)

        saved_fonts = []
        for font in google_fonts:
            font_filename = f"google_{font['family'].replace('+', '_').replace('/', '')}.css"
            font_url = font["source"]

            try:
                google_font_css = await self._fetch_font_css(font_url)
                font_path = self.fonts_dir / font_filename
                font_path.write_text(google_font_css, encoding='utf-8')

                font["local_path"] = str(font_path.relative_to(self.output_folder))
                font["css_file"] = font_filename

                saved_fonts.append(font)
                log.info("Police Google Fonts sauvegardée: %s", font_filename)

            except Exception as exc:
                log.warning("Impossible de récupérer Google Font %s: %s", font["family"], exc)

        return saved_fonts

    async def _fetch_font_css(self, font_url: str) -> str:
        """Récupère le CSS de police Google Fonts.
        
        Args:
            font_url: URL du fichier CSS de police Google Fonts.
            
        Returns:
            Contenu CSS.
        """
        try:
            timeout = aiohttp.ClientTimeout(total=10.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(font_url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                    if response.status == 200:
                        return await response.text()
                    return ""
        except Exception:
            return ""

    async def _detect_local_fonts(self) -> list:
        """Détecte les polices localement définies via @font-face.
        
        Returns:
            Liste des polices @font-face locales.
        """
        log.info("Détection polices @font-face locales...")

        local_fonts = await self.page.evaluate("""
            () => {
                const fontFaces = [];
                
                for (const fontFace of document.styleSheets) {
                    try {
                        for (const rule of fontFace.cssRules || []) {
                            if (rule.type === CSSRule.FONT_FACE) {
                                const fontFaceRule = rule;
                                fontFaces.push({
                                    family: fontFaceRule.style.fontFamily,
                                    style: fontFaceRule.style.fontStyle,
                                    weight: fontFaceRule.style.fontWeight,
                                    stretch: fontFaceRule.style.fontStretch,
                                    src: fontFaceRule.style.src,
                                    formats: fontFaceRule.style.getPropertyValue('src'),
                                    unicode_range: fontFaceRule.style.fontUnicodeRange,
                                    variations: fontFaceRule.style.getPropertyValue('font-variation-settings')
                                });
                            }
                        }
                    } catch (e) {
                    }
                }
                
                return fontFaces;
            }
        """)

        for font in local_fonts:
            if font.get("src"):
                await self._process_font_face_source(font)

        return local_fonts

    async def _process_font_face_source(self, font_data: dict) -> None:
        """Traite une source @font-face et sauvegarde les fichiers.
        
        Args:
            font_data: Données de police @font-face.
        """
        src = font_data["src"]
        if not src:
            return

        try:
            font_url_match = re.search(r'url\([\'"]?([^\'"]+?)[\'"]?\)', src)
            if not font_url_match:
                return

            font_url = font_url_match.group(1)
            if not font_url.startswith('http'):
                font_url = urljoin(self.page.url, font_url)
            font_name = re.sub(r'\s+', '_', font_data["family"])

            try:
                timeout = aiohttp.ClientTimeout(total=15.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(font_url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                        if response.status != 200:
                            font_response = None
                        else:
                            font_response = await response.read()

                ext_match = re.search(r'\.(woff2?|ttf|otf|eot|svg)$', font_url, re.IGNORECASE)
                if ext_match:
                    ext = ext_match.group(1)
                    font_filename = f"{font_name}.{ext}"
                    font_path = self.fonts_dir / font_filename

                    if font_response:
                        font_path = self.fonts_dir / font_filename
                        font_path.write_bytes(font_response)

                        font_data["local_path"] = str(font_path.relative_to(self.output_folder))
                        font_data["extension"] = ext
                        font_data["file_size"] = len(font_bytes)

                        log.info("Police locale sauvegardée: %s (%d octets)", font_filename, len(font_bytes))

            except Exception as exc:
                log.warning("Impossible de récupérer font locale %s: %s", font_data["family"], exc)

        except Exception as exc:
            log.warning("Erreur traitement font-face %s: %s", font_data["family"], exc)

    async def _detect_web_fonts(self) -> list:
        """Détecte les polices web (web fonts) utilisées par les éléments.
        
        Returns:
            Liste des polices web utilisées.
        """
        log.info("Détection polices web utilisées...")

        web_fonts = await self.page.evaluate("""
            () => {
                const fonts = [];
                
                for (const element of document.querySelectorAll('*')) {
                    const computed = window.getComputedStyle(element);
                    const fontFamily = computed.fontFamily;
                    
                    if (fontFamily && fontFamily !== 'inherit' && fontFamily !== 'initial' &&
                        !fontFamily.includes('serif') && !fontFamily.includes('monospace') &&
                        !fontFamily.includes('-apple-system') && !fontFamily.includes('system-ui')) {
                        
                        const parts = fontFamily.split(',').map(f => f.trim().replace(/['"]/g, ''));
                        const primaryFont = parts[0];
                        
                        const fontInfo = {
                            font_family: primaryFont,
                            element_type: element.tagName.toLowerCase(),
                            element_id: element.id || '',
                            element_class: element.className || '',
                            weight: computed.fontWeight,
                            style: computed.fontStyle,
                            size: computed.fontSize,
                            text_decoration: computed.textDecoration
                        };
                        
                        fonts.push(fontInfo);
                    }
                }
                
                return fonts;
            }
        """)

        return web_fonts

    async def _extract_font_faces(self) -> list:
        """Extrait toutes les règles @font-face du DOM.
        
        Returns:
            Liste des règles de polices @font-face.
        """
        log.info("Extraction règles @font-face...")

        font_faces = await self.page.evaluate("""
            () => {
                const faces = [];
                
                for (const styleSheet of document.styleSheets) {
                    try {
                        for (const rule of styleSheet.cssRules || []) {
                            if (rule.type === CSSRule.FONT_FACE) {
                                const fontFace = rule;
                                
                                const faceData = {
                                    font_family: fontFace.style.fontFamily,
                                    font_style: fontFace.style.fontStyle,
                                    font_weight: fontFace.style.fontWeight,
                                    font_stretch: fontFace.style.fontStretch,
                                    src: fontFace.style.src,
                                    unicode_range: fontFace.style.fontUnicodeRange,
                                    font_display: fontFace.style.getPropertyValue('--font-display') || 'swap',
                                    variations: fontFace.style.getPropertyValue('font-variation-settings'),
                                    ascent_override: fontFace.style.getPropertyValue('ascent-override'),
                                    descent_override: fontFace.style.getPropertyValue('descent-override'),
                                    line_gap_override: fontFace.style.getPropertyValue('line-gap-override'),
                                    size_adjust: fontFace.style.getPropertyValue('size-adjust')
                                };
                                
                                faces.push(faceData);
                            }
                        }
                    } catch (e) {
                    }
                }
                
                return faces;
            }
        """)

        for face in font_faces:
            if face.get("src"):
                await self._process_font_face_source(face)

        return font_faces

    async def _collect_font_files(self) -> list:
        """Collecte tous les fichiers de polices liés dans le HTML et CSS.
        
        Returns:
            Liste des fichiers de polices.
        """
        log.info("Collecte fichiers de polices liés...")

        js_code = r"""
            () => {
                const files = [];
                
                document.querySelectorAll('link[rel*="stylesheet"]').forEach(link => {
                    const href = link.getAttribute('href');
                    if (href && (href.includes('.css') || href.includes('.woff') || 
                               href.includes('.woff2') || href.includes('.ttf') ||
                               href.includes('.otf'))) {
                        files.push({
                            type: 'link',
                            url: href,
                            rel: link.getAttribute('rel') || ''
                        });
                    }
                });
                
                document.querySelectorAll('style').forEach(style => {
                    const cssText = style.textContent || '';
                    const re = /url\(['""]?([^'""]+?)['""]?\)/g;
                    let match;
                    while ((match = re.exec(cssText)) !== null) {
                        const extractedUrl = match[1];
                        if (extractedUrl && !extractedUrl.startsWith('data:')) {
                            files.push({
                                type: 'inline_css',
                                url: extractedUrl,
                                source: 'style_tag'
                            });
                        }
                    }
                });
                
                return files;
            }
        """

        font_files = await self.page.evaluate(js_code)

        for font_file in font_files:
            if font_file.get("url"):
                await self._download_font_file(font_file)

        return font_files

    async def _download_font_file(self, font_file: dict) -> None:
        """Télécharge un fichier de police.
        
        Args:
            font_file: Données du fichier de police à télécharger.
        """
        url = font_file["url"]
        if not url:
            return

        try:
            if url.startswith('data:'):
                return

            if not url.startswith('http'):
                page_url = self.page.url
                from urllib.parse import urljoin
                url = urljoin(page_url, url)

            font_name = url.split('/')[-1].split('?')[0]
            if font_name == url or not font_name:
                ext = ''.join(filter(None, re.findall(r'\.(woff2?|ttf|otf|eot|svg)$', url, re.IGNORECASE)))
                if ext:
                    font_name = f"font.{ext}"
                else:
                    font_name = f"font_{int(time.time())}.unknown"

            font_path = self.fonts_dir / font_name

            if font_path.exists():
                font_file["local_path"] = str(font_path.relative_to(self.output_folder))
                return

            timeout = aiohttp.ClientTimeout(total=15.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                    if response.status == 200:
                        font_bytes = await response.read()
                        font_path.write_bytes(font_bytes)

                        font_file["local_path"] = str(font_path.relative_to(self.output_folder))
                        font_file["file_size"] = len(font_bytes)
                        font_file["downloaded"] = True

                        log.info("Fichier font téléchargé: %s (%d octets)", font_name, len(font_bytes))

        except Exception as exc:
            log.warning("Erreur téléchargement font %s: %s", url, exc)

    async def _save_font_metadata(self, font_data: dict) -> None:
        """Sauvegarde les métadonnées des polices.
        
        Args:
            font_data: Toutes les données de polices.
        """
        with self.font_metadata_path.open('w', encoding='utf-8') as f:
            json.dump(font_data, f, ensure_ascii=False, indent=2)
        log.info("Métadonnées de polices sauvegardées: %s", self.font_metadata_path)
