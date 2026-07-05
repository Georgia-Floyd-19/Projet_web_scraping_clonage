# Architecture

## Vue d'ensemble

Web Cloner est une application Python qui utilise **Playwright** pour automatiser un navigateur (Edge par défaut), naviguer sur un site cible, capturer toutes ses ressources, et les réécrire pour fonctionner localement.

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   CLI / UI  │────▶│   core/      │────▶│  Playwright  │
│  (utilisateur)│    │  (moteur)    │     │  (navigateur)│
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────▼───────┐
                    │  _clones/    │
                    │  (sauvegarde)│
                    └──────────────┘
```

## Structure en couches

### 1. Couche présentation (utilisateur)

| Module | Rôle |
|--------|------|
| `main.py` | CLI argparse : point d'entrée principal |
| `webui/` | Serveur FastAPI avec WebSocket, templates Jinja2, statiques |
| `utils/cli.py` | Affichage Rich (bannière, spinner, résumé) |
| `utils/progress.py` | Barres de progression |

### 2. Couche métier (core/)

| Module | Responsabilité | Dépendances |
|--------|---------------|-------------|
| `crawler.py` | Orchestrateur : crawl, collecte, réécriture | Tous les autres modules |
| `browser.py` | Configuration et cycle de vie du navigateur Playwright | Playwright |
| `downloader.py` | Téléchargement des ressources (CSS, JS, images...) | aiohttp |
| `interceptor.py` | Capture réseau : intercepte requêtes API/XHR | Playwright |
| `interactions.py` | Automatisation : scroll, clics, formulaires | Playwright |
| `animations.py` | Détection et capture d'animations (Three.js, CSS, Vue) | Playwright |
| `fonts.py` | Capture des polices (Tailwind, Google Fonts, WOFF2) | Playwright |
| `rewriter.py` | Réécriture HTML/CSS (chemins relatifs, assets inline) | BeautifulSoup |
| `screenshot.py` | Capture d'écran de secours | Playwright |
| `storage.py` | Sauvegarde des métadonnées et état du clonage | - |
| `utils.py` | Utilitaires : normalisation URL, extraction liens, helpers | - |

### 3. Couche utilitaires

| Module | Rôle |
|--------|------|
| `utils/groq.py` | Client Groq pour résumé IA (optionnel) |
| `utils/cli.py` | Fonctions d'affichage CLI (Rich) |

## Flux de clonage

```
1. UTILISATEUR
   │
   ├─ CLI :  main.py --args
   └─ UI :   webui/ (FastAPI + WebSocket)
              │
2. BROWSER (core/browser.py)
   │
   ├─ Lance Edge (headless ou non)
   ├─ Applique stealth si demandé
   └─ Configure proxy, cookies, user-agent
      │
3. CRAWLER (core/crawler.py)
   │
   ├─ Visite chaque page
   ├─ Détecte framework (Nuxt, Next, React, Vue...)
   │
   ├─ INTERCEPTEUR (core/interceptor.py)
   │   └─ Capture réponses API/XHR → _clones/api/
   │
   ├─ DOWNLOADER (core/downloader.py)
   │   └─ Télécharge styles/scripts/images → _clones/{styles,scripts,images}/
   │
   ├─ INTERACTIONS (core/interactions.py)
   │   ├─ Scroll progressif
   │   ├─ Clique sur "Afficher plus"
   │   ├─ Soumet formulaires
   │   └─ Déplie accordéons
   │
   ├─ ANIMATIONS (core/animations.py)
   │   ├─ Détecte Three.js/WebGL → capture frames
   │   ├─ Détecte animations CSS → sauvegarde keyframes
   │   ├─ Détecte transitions Vue → état réactif
   │   └─ Détecte particules et scroll animations
   │
   ├─ FONTS (core/fonts.py)
   │   └─ Capture polices Tailwind/Google/WOFF2 → _clones/fonts/
   │
   └─ REWRITER (core/rewriter.py)
       └─ Réécrit HTML/CSS (chemins absolus → relatifs)
          └─ Sauvegarde → _clones/pages/
             │
4. FIN
   │
   ├─ Résumé IA (utils/groq.py) → resume.md
   └─ Rapport final (utils/cli.py) → console
```

## Modes de clonage

```
auto          → Détection automatique du meilleur mode
static        → Télécharge HTML + assets bruts
hybrid        → Télécharge HTML + rejoue les API capturées
snapshot      → Figer le DOM après rendu complet
screenshot    → Force capture canvas (sites full-canvas)
nuxt-perfect  → Copie conforme avec animations + polices
```

## Communication inter-modules

```
webui/server.py
    ↓ WebSocket (progression temps réel)
core/crawler.py (CrawlConfig → CrawlResult)
    ↓ appelle
core/browser.py (BrowserConfig → BrowserManager)
core/downloader.py (ResourceDownloader)
core/interceptor.py (NetworkInterceptor)
core/interactions.py (PageInteractor)
core/animations.py (AnimationDetector)
core/fonts.py (FontCapture)
core/rewriter.py (HTMLRewriter, CSSRewriter)
core/storage.py (StorageManager)
```

## Structure des clones sauvegardés

```
_clones/<domaine>_<timestamp>/
├── pages/          ← HTML réécrit (rewriter.py)
├── styles/         ← CSS
├── scripts/        ← JavaScript
├── images/         ← Images (jpg, png, webp, svg...)
├── fonts/          ← Polices (woff2, woff, ttf, otf...)
├── media/          ← Vidéos, audio
├── api/            ← Réponses API/XHR capturées
├── animations/     ← Données d'animations (mode nuxt-perfect)
├── misc/           ← Autres ressources
├── resume.md       ← Résumé IA (si --summarize)
└── metadata.json   ← Métadonnées (framework, stats...)
```

## Technologies & dépendances

| Technologie | Version min | Usage |
|-------------|-------------|-------|
| Python | 3.8 | Langage |
| Playwright | 1.40 | Automatisation navigateur |
| playwright-stealth | 1.0 | Anti-détection |
| FastAPI | 0.110 | API backend WebSocket |
| Jinja2 | 3.1 | Templates HTML UI |
| Rich | 13.0 | CLI stylisée |
| BeautifulSoup4 | 4.12 | Parsing/réécriture HTML |
| lxml | 5.0 | Parsing rapide |
| aiohttp | 3.9 | Téléchargement asynchrone |
| Groq | 0.5 | Résumé IA (optionnel) |
| python-dotenv | 1.0 | Configuration env |
