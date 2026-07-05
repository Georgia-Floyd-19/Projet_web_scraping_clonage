from __future__ import annotations

import base64
import logging
from pathlib import Path

from playwright.async_api import Page

log = logging.getLogger("cloner.screenshot")


class CanvasCapture:
    """Captures WebGL/Canvas content as images for faithful clones.

    Replaces <canvas> elements with <img> tags pointing to saved image
    files in screenshots/.  Falls back to a full-page screenshot when
    all canvases are CORS-tainted.
    """

    def __init__(self, page: Page, output_folder: Path) -> None:
        self.page = page
        self.output_folder = output_folder

    async def has_webgl_canvas(self) -> bool:
        """Detect if the page has WebGL / Three.js canvases worth capturing."""
        return await self.page.evaluate("""
            () => {
                const canvases = document.querySelectorAll('canvas');
                if (canvases.length === 0) return false;
                for (const c of canvases) {
                    try {
                        const gl = c.getContext('webgl') || c.getContext('webgl2');
                        if (gl) return true;
                    } catch (e) { /* context may not be available yet */ }
                    if (c.classList.contains('webgl-canvas')) return true;
                    const id = (c.id || '').toLowerCase();
                    if (id.includes('webgl') || id.includes('three')) return true;
                }
                return true;
            }
        """)

    async def capture_page(self) -> str:
        """Replace canvases with image files and return the modified HTML.

        Every <canvas> is snapshot via ``toDataURL('image/webp', 0.92)``
        and saved under ``screenshots/canvas_{N}.webp``.  The HTML is
        updated to point ``<img src="../screenshots/…">`` at these files.

        If *all* canvases are CORS-tainted a full-page fallback screenshot
        is taken and a minimal wrapper page is returned instead.
        """
        screenshots_dir = self.output_folder / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        tainted_count = await self.page.evaluate("""
            () => {
                const canvases = document.querySelectorAll('canvas');
                let tainted = 0;
                canvases.forEach((c, i) => {
                    try {
                        const dataUrl = c.toDataURL('image/webp', 0.92);
                        const img = document.createElement('img');
                        img.src = dataUrl;
                        img.setAttribute('data-canvas-index', i.toString());
                        for (const attr of c.attributes) {
                            if (attr.name !== 'width' && attr.name !== 'height') {
                                try { img.setAttribute(attr.name, attr.value); } catch (e) {}
                            }
                        }
                        img.width = c.width;
                        img.height = c.height;
                        c.parentNode.replaceChild(img, c);
                    } catch (e) {
                        tainted++;
                        c.setAttribute('data-tainted', 'true');
                    }
                });
                return tainted;
            }
        """)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(await self.page.content(), 'html.parser')

        saved = 0
        for img_tag in soup.select('img[data-canvas-index]'):
            src = img_tag.get('src', '')
            if not src.startswith('data:'):
                continue
            try:
                header, data = src.split(',', 1)
                fmt = 'webp' if 'webp' in header else 'png'
                idx = img_tag.get('data-canvas-index', '0')
                filename = f"canvas_{idx}.{fmt}"
                img_bytes = base64.b64decode(data)
                (screenshots_dir / filename).write_bytes(img_bytes)
                img_tag['src'] = f"../screenshots/{filename}"
                del img_tag['data-canvas-index']
                saved += 1
            except Exception as exc:
                log.warning("Erreur sauvegarde canvas %s: %s",
                            img_tag.get('data-canvas-index', '?'), exc)

        total_canvases = len(soup.select('canvas[data-tainted]')) + saved
        if tainted_count > 0 and saved == 0 and total_canvases > 0:
            log.warning("Tous les canvas sont tainted, fallback screenshot")
            return await self._fallback_full_page(screenshots_dir)

        if tainted_count > 0:
            log.warning("%d canvas tainted (laissés vides dans le clone)",
                        tainted_count)

        return str(soup)

    async def _fallback_full_page(self, screenshots_dir: Path) -> str:
        """Take a full-page screenshot and return a wrapper HTML."""
        ss_path = screenshots_dir / "fallback.png"
        log.info("Prise de screenshot de fallback → %s", ss_path)
        await self.page.screenshot(path=str(ss_path), full_page=True)
        return self._fallback_html("../screenshots/fallback.png")

    @staticmethod
    def _fallback_html(img_rel_path: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Page clonée (capture d'écran)</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a1a;color:#aaa;font-family:system-ui,sans-serif;text-align:center;padding:1rem}}
.notice{{margin-bottom:1rem;font-size:0.9rem;opacity:0.7}}
img{{max-width:100%;display:block;margin:0 auto;box-shadow:0 0 30px rgba(0,0,0,.6)}}
</style></head><body>
<div class="notice">Contenu interactif (WebGL / Canvas) capturé comme image</div>
<img src="{img_rel_path}" alt="Capture d'écran de la page originale">
</body></html>"""
