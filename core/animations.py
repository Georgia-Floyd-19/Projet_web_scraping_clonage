from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from playwright.async_api import Page

log = logging.getLogger("cloner.animations")


class AnimationDetector:
    """Détecte et capture les animations WebGL/Three.js, CSS, et Vue.
    
    Captures des animations spécifiques pour préserver les animations dans les clones de sites Nuxt.
    """

    def __init__(self, page: Page, output_folder: Path) -> None:
        self.page = page
        self.output_folder = output_folder
        self.animations_dir = output_folder / "animations"
        self.animations_dir.mkdir(parents=True, exist_ok=True)

    async def detect_all_animations(self) -> dict:
        """Détecte toutes les animations de la page et capture les données relatives.
        
        Returns:
            Dict contenant les animations détectées et sauvegardées.
        """
        animations = {
            "webgl_threejs": await self._detect_webgl_animations(),
            "css_animations": await self._detect_css_animations(),
            "vue_transitions": await self._detect_vue_transitions(),
            "particle_effects": await self._detect_particle_effects(),
            "scroll_animations": await self._detect_scroll_animations(),
        }

        await self._save_animation_data(animations)
        return animations

    async def _detect_webgl_animations(self) -> dict:
        """Détecte les animations WebGL/Three.js et capture les frames.
        
        Returns:
            Dict des animations Three.js avec données capturées.
        """
        log.info("Détection d'animations Three.js/WebGL...")

        try:
            webgl_data = await self.page.evaluate("""
                () => {
                    const webglCanvases = [];
                    const canvases = document.querySelectorAll('canvas');
                    
                    canvases.forEach((canvas, index) => {
                        try {
                            const gl = canvas.getContext('webgl') || canvas.getContext('webgl2');
                            if (!gl) return;
                            
                            const rect = canvas.getBoundingClientRect();
                            const hasAnimation = window.requestAnimationFrame !== undefined;
                            
                            webglCanvases.push({
                                index,
                                has_webgl: true,
                                width: canvas.width,
                                height: canvas.height,
                                position: { x: rect.left, y: rect.top },
                                has_animation: hasAnimation,
                                // Tentative de vérifier si Three.js est actif
                                canvas_id: canvas.id || `canvas_${index}`,
                                class_list: Array.from(canvas.classList || [])
                            });
                        } catch (e) {
                            // Contexte non disponible ou canvas non WebGL
                        }
                    });
                    
                    return webglCanvases;
                }
            """)

            animations_saved = 0
            for canvas_data in webgl_data:
                if canvas_data.get("has_webgl"):
                    await self._capture_webgl_frame(canvas_data)
                    animations_saved += 1

            return {
                "canvases_detected": len(webgl_data),
                "animations_saved": animations_saved,
                "details": webgl_data
            }

        except Exception as exc:
            log.warning("Erreur détection animations WebGL: %s", exc)
            return {"error": str(exc)}

    async def _capture_webgl_frame(self, canvas_data: dict) -> None:
        """Capture une frame WebGL et sauvegarde les données.
        
        Args:
            canvas_data: Données du canvas contenant index, dimensions, position.
        """
        try:
            canvas_index = canvas_data["index"]

            webgl_screenshot = await self.page.evaluate(f"""
                () => {{
                    const canvas = document.querySelector('canvas[data-canvas-index="{canvas_index}"]') || 
                                 Array.from(document.querySelectorAll('canvas'))[{canvas_index}];
                    if (!canvas) return null;
                    
                    try {{
                        const gl = canvas.getContext('webgl') || canvas.getContext('webgl2');
                        if (!gl) return null;
                        
                        const dataUrl = canvas.toDataURL('image/webp', 0.95);
                        
                        return {{
                            canvas_index: {canvas_index},
                            timestamp: Date.now(),
                            width: canvas.width,
                            height: canvas.height,
                            image_data: dataUrl,
                            has_animation: window.requestAnimationFrame ? true : false
                        }};
                    }} catch (e) {{
                        return null;
                    }}
                }}
            """)

            if webgl_screenshot and webgl_screenshot.get("image_data"):
                filename = f"webgl_{canvas_index}_{webgl_screenshot['timestamp']}.webp"
                header, data = webgl_screenshot["image_data"].split(',', 1)
                img_bytes = bytes.fromhex(data.replace('data:image/webp;base64,', ''))

                img_path = self.animations_dir / filename
                img_path.write_bytes(img_bytes)

                webgl_screenshot["saved_path"] = str(img_path.relative_to(self.output_folder))
                log.info("Frame WebGL sauvegardée: %s", filename)

                await self._save_webgl_metadata(webgl_screenshot)

        except Exception as exc:
            log.warning("Erreur capture frame WebGL: %s", exc)

    async def _save_webgl_metadata(self, frame_data: dict) -> None:
        """Sauvegarde les métadonnées d'une frame WebGL.
        
        Args:
            frame_data: Données de la frame à sauvegarder.
        """
        metadata_path = self.animations_dir / f"webgl_metadata_{frame_data['canvas_index']}.json"
        with metadata_path.open('w', encoding='utf-8') as f:
            json.dump(frame_data, f, ensure_ascii=False, indent=2)

    async def _detect_css_animations(self) -> dict:
        """Détecte les animations CSS et sauvegarde les données.
        
        Returns:
            Dict des animations CSS avec styles sauvegardés.
        """
        log.info("Détection animations CSS...")

        try:
            css_animations = await self.page.evaluate("""
                () => {
                    const styles = [];
                    
                    for (const element of document.querySelectorAll('*')) {
                        const computed = window.getComputedStyle(element);
                        const animation = computed.animation || '';
                        const transition = computed.transition || '';
                        
                        if (animation.includes('none') && transition.includes('none')) {
                            continue;
                        }
                        
                        const rect = element.getBoundingClientRect();
                        const hasVisibleText = element.textContent && element.textContent.trim().length > 0;
                        
                        if (rect.width > 0 && rect.height > 0 && hasVisibleText) {
                            styles.push({
                                tag: element.tagName.toLowerCase(),
                                class: Array.from(element.classList || []).join(' '),
                                id: element.id || '',
                                animation: animation,
                                transition: transition,
                                position: { x: rect.left, y: rect.top },
                                dimensions: { width: rect.width, height: rect.height },
                                has_visible_content: true
                            });
                        }
                    }
                    
                    return styles;
                }
            """)

            saved_count = 0
            for anim in css_animations:
                if anim.get("animation") or anim.get("transition"):
                    anim_path = self.animations_dir / f"css_anim_{saved_count}.json"
                    with anim_path.open('w', encoding='utf-8') as f:
                        json.dump(anim, f, ensure_ascii=False, indent=2)
                    saved_count += 1

            return {
                "elements_with_animations": len(css_animations),
                "animations_saved": saved_count,
                "details": css_animations
            }

        except Exception as exc:
            log.warning("Erreur détection animations CSS: %s", exc)
            return {"error": str(exc)}

    async def _detect_vue_transitions(self) -> dict:
        """Détecte les transitions Vue.js et sauvegardes les données.
        
        Returns:
            Dict des données de transition Vue.
        """
        log.info("Détection transitions Vue...")

        try:
            vue_transitions = await self.page.evaluate("""
                () => {
                    // Détecter les composants Vue via la disponibilité de l'API Vue
                    if (typeof window.Vue === 'undefined') {
                        return { vue_detected: false };
                    }
                    
                    const data = {
                        vue_detected: true,
                        version: window.Vue?.version || 'unknown',
                        root_component: null,
                        transitions: []
                    };
                    
                    // Trouver l'application Vue racine
                    const appElement = document.querySelector('[data-v-app]');
                    if (appElement) {
                        data.root_component = {
                            tag: appElement.tagName.toLowerCase(),
                            classes: Array.from(appElement.classList || []),
                            id: appElement.id || ''
                        };
                    }
                    
                    // Rechercher les transitions de Vue
                    document.querySelectorAll('[v-if], [v-show], [v-for]').forEach(el => {
                        const transition = window.getComputedStyle(el).transition;
                        if (transition && transition.includes('opacity') || 
                            transition.includes('transform') ||
                            transition.includes('display')) {
                            data.transitions.push({
                                directive: Array.from(el.attributes).find(attr => 
                                    attr.name.startsWith('v-'))?.name || '',
                                element: el.tagName.toLowerCase(),
                                transition: transition,
                                visible: el.offsetParent !== null
                            });
                        }
                    });
                    
                    return data;
                }
            """)

            transitions_path = self.animations_dir / "vue_transitions.json"
            with transitions_path.open('w', encoding='utf-8') as f:
                json.dump(vue_transitions, f, ensure_ascii=False, indent=2)

            return vue_transitions

        except Exception as exc:
            log.warning("Erreur détection transitions Vue: %s", exc)
            return {"error": str(exc)}

    async def _detect_particle_effects(self) -> dict:
        """Détecte les effets de particules et sauvegarde les données.
        
        Returns:
            Dict des données d'effets de particules.
        """
        log.info("Détection effets de particules...")

        try:
            particles = await self.page.evaluate("""
                () => {
                    const effects = [];
                    
                    // Rechercher les éléments avec noms de classes spécifiques aux particules
                    const particleSelectors = [
                        '.particle',
                        '.particles',
                        '.particle-effect',
                        '.particle-background',
                        '[class*="particle"]'
                    ];
                    
                    for (const selector of particleSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const element of elements) {
                            const rect = element.getBoundingClientRect();
                            const computed = window.getComputedStyle(element);
                            
                            effects.push({
                                selector: selector,
                                element_tag: element.tagName.toLowerCase(),
                                z_index: computed.zIndex,
                                position: { x: rect.left, y: rect.top },
                                dimensions: { width: rect.width, height: rect.height },
                                background: computed.backgroundImage,
                                animation: computed.animation,
                                opacity: computed.opacity,
                                visibility: computed.visibility
                            });
                        }
                    }
                    
                    return effects;
                }
            """)

            particles_path = self.animations_dir / "particle_effects.json"
            with particles_path.open('w', encoding='utf-8') as f:
                json.dump(particles, f, ensure_ascii=False, indent=2)

            return {"effects_detected": len(particles), "details": particles}

        except Exception as exc:
            log.warning("Erreur détection effets de particules: %s", exc)
            return {"error": str(exc)}

    async def _detect_scroll_animations(self) -> dict:
        """Détecte les animations au scroll et sauvegarde les données.
        
        Returns:
            Dict des données d'animations au scroll.
        """
        log.info("Détection animations au scroll...")

        try:
            scroll_animations = await self.page.evaluate("""
                () => {
                    const animations = [];
                    
                    // Rechercher les indicateurs d'animation au scroll
                    const scrollSelectors = [
                        '.scroll-reveal',
                        '.fade-in',
                        '.slide-up',
                        '.zoom-in',
                        '[data-scroll]',
                        '.aos-item'
                    ];
                    
                    for (const selector of scrollSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const element of elements) {
                            const rect = element.getBoundingClientRect();
                            const id = element.getAttribute('data-scroll') || 
                                     element.className.match(/scroll-(\\w+)/)?.[1] ||
                                     'unknown';
                            
                            animations.push({
                                selector: selector,
                                animation_type: id,
                                element_tag: element.tagName.toLowerCase(),
                                classes: element.className || '',
                                position: { x: rect.left, y: rect.top },
                                dimensions: { width: rect.width, height: rect.height },
                                in_viewport: rect.top >= 0 && rect.top <= window.innerHeight
                            });
                        }
                    }
                    
                    return animations;
                }
            """)

            scroll_path = self.animations_dir / "scroll_animations.json"
            with scroll_path.open('w', encoding='utf-8') as f:
                json.dump(scroll_animations, f, ensure_ascii=False, indent=2)

            return {"scroll_animations_detected": len(scroll_animations), "details": scroll_animations}

        except Exception as exc:
            log.warning("Erreur détection animations au scroll: %s", exc)
            return {"error": str(exc)}

    async def _save_animation_data(self, animations: dict) -> None:
        """Sauvegarde les données d'animation complètes.
        
        Args:
            animations: Toutes les données d'animation collectées.
        """
        data_file = self.animations_dir / "animation_metadata.json"
        with data_file.open('w', encoding='utf-8') as f:
            json.dump(animations, f, ensure_ascii=False, indent=2)
        log.info("Métadonnées d'animation sauvegardées: %s", data_file)
