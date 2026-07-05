# Changelog

## [1.0.0] - 2026-07-05

### Ajouté
- Version initiale du projet
- Mode CLI avec argparse (toutes options)
- Interface Web (FastAPI + WebSocket + UI moderne)
- 6 modes de clonage : `auto`, `static`, `hybrid`, `snapshot`, `screenshot`, `nuxt-perfect`
- Moteur de crawl avec Playwright (Edge par défaut)
- Détection de framework (Nuxt, Next, React, Vue...)
- Capture et réécriture HTML/CSS complète
- Téléchargement de toutes les ressources (CSS, JS, images, vidéos, polices)
- Interception et sauvegarde des réponses API/XHR
- Mode stealth anti-bot intégré
- Profil Chrome persistant supporté
- Détection et capture d'animations (Three.js, CSS, Vue, particules)
- Capture de polices (Tailwind, Google Fonts, WOFF2)
- Résumé IA via Groq (Llama 3.3 70B)
- Interactions automatiques (scroll, clics, formulaires, accordéons)
- Barres de progression Rich en CLI
- Notification en temps réel via WebSocket
- Ouverture du dossier de clone et visualisation depuis l'UI
- Résumé de session après clonage
