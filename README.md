# Web Cloner

![GitHub issues](https://img.shields.io/github/issues/anomalyco/web_cloner.svg)
![GitHub stars](https://img.shields.io/github/stars/anomalyco/web_cloner.svg)

Un outil puissant de clonage de sites web qui capture n'importe quelle page web et ses ressources (HTML, CSS, JavaScript, images, vidéos, polices, API, etc.) en un clone de site web autonome et entièrement fonctionnel.

---

## Fonctionnement

Cet outil utilise **Playwright** avec le navigateur **Microsoft Edge** (navigateur par défaut) pour naviguer sur les sites web, analyser leur contenu et tout télécharger localement. Vous n'avez qu'à copier l'URL du site que vous souhaitez cloner et la fournir à l'outil (en CLI ou via l'interface web).

Par exemple :
1. Ouvrez votre navigateur (Edge recommandé)
2. Copiez l'URL du site à cloner (ex: `https://example.com`)
3. Lancez le clonage avec la commande ou l'interface web
4. Visualisez le clone local instantanément

---

## Aperçu

Web Cloner extrait le contenu dynamique et statique d'un site web cible, le sauvegarde localement et le sert via un serveur de visualisation. Il peut cloner des sites JavaScript riches et préserver les animations, les transitions et les effets visuels, y compris les pages Next.js/Nuxt rendues côté serveur.

---

## Fonctionnalités

### Clonage complet
- Pages HTML statiques et dynamiques
- Ressources externes (CSS, JavaScript, images, vidéos, polices)
- Réponses API et XHR sauvegardées pour relecture
- Détection automatique du framework utilisé
- Mode anti-bot stealth intégré

### Modes de clonage
| Mode | Description |
|------|-------------|
| `auto` | Détection automatique du meilleur mode |
| `static` | HTML + assets (mode basique) |
| `hybrid` | HTML + rejeu des appels API |
| `snapshot` | DOM figé (instantané complet) |
| `screenshot` | Capture canvas forcée |
| `nuxt-perfect` | Copie conforme avec animations et polices |

### Résumé par IA
- Intégration **Groq** pour analyse et résumé de contenu
- Identification du type de site, objectif et sections clés
- Résumé généré automatiquement en français

### Interface web
- Interface moderne avec progression en temps réel via WebSocket
- Visualisation instantanée des clones
- Options avancées configurables (pages max, délais, stealth, etc.)
- Accès aux clones via `/preview/{clone_name}`

### Anti-détection
- Mode stealth intégré
- Profil Chrome persistant personnalisable
- User-Agent configurable
- Stratégies d'attente multiples (networkidle, domcontentloaded, load)
- Scroll progressif simulé

---

## Installation

### Prérequis
- **Python 3.8+**
- **Microsoft Edge** (navigateur recommandé)

### Étapes

```bash
# Cloner le dépôt
git clone https://github.com/anomalyco/web_cloner.git
cd web_cloner

# Installer les dépendances
pip install -r requirements.txt

# Installer le package en mode développement
pip install -e .
```

### Navigateur Edge
L'outil utilise **Microsoft Edge** par défaut pour la navigation. Assurez-vous qu'il est installé sur votre système.

```bash
# Playwright installera automatiquement Edge si nécessaire
playwright install msedge
```

---

## Utilisation

### En ligne de commande

```bash
# Clonage simple
python main.py https://example.com

# Avec interface web
python main.py --ui

# Avec options avancées
python main.py https://example.com --max-pages 20 --clone-mode nuxt-perfect --summarize

# Mode stealth anti-bot
python main.py https://example.com --stealth --no-headless

# Spécifier un dossier de sortie
python main.py https://example.com -o ./mon_clone
```

### Interface web

```bash
# Lancer l'interface web
python main.py --ui

# Sur un port personnalisé
python main.py --ui --port 8080
```

Ouvrez ensuite votre navigateur (Edge recommandé) et accédez à `http://localhost:8501`.

---

## Options CLI

| Option | Description | Défaut |
|--------|-------------|--------|
| `url` | URL du site à cloner | — |
| `--ui` | Lancer l'interface web | `false` |
| `--port` | Port pour l'interface web | `8501` |
| `--no-open` | Ne pas ouvrir le navigateur auto | `false` |
| `-o, --output` | Dossier de sortie | `_clones/<domaine>` |
| `--max-pages` | Nombre max de pages à cloner | `10` |
| `--no-interactions` | Désactiver les interactions auto | `false` |
| `--no-api` | Ne pas sauvegarder les réponses API | `false` |
| `--request-delay` | Délai entre requêtes (secondes) | `0.5` |
| `--headless` | Mode headless | `true` |
| `--no-headless` | Afficher le navigateur | `false` |
| `--verbose, -v` | Mode verbeux | `false` |
| `--groq-key` | Clé API Groq | — |
| `--summarize` | Générer un résumé IA | `false` |
| `--overwrite` | Écraser le dossier existant | `false` |
| `--user-agent` | User-Agent personnalisé | — |
| `--stealth` | Mode stealth anti-bot | `false` |
| `--persistent-profile` | Profil Chrome persistant | — |
| `--wait-strategy` | Stratégie d'attente | `networkidle` |
| `--page-timeout` | Timeout navigation (ms) | `60000` |
| `--scroll-steps` | Étapes de scroll progressif | `5` |
| `--clone-mode` | Mode de clonage | `auto` |

---

## Structure du projet

```
web_cloner/
├── main.py                    # Point d'entrée CLI
├── core/                      # Moteur principal
│   ├── browser.py             # Configuration et gestion du navigateur
│   ├── crawler.py             # Moteur de crawl et clonage
│   ├── downloader.py          # Téléchargement des ressources
│   ├── interactions.py        # Interactions automatiques sur les pages
│   ├── interceptor.py         # Interception réseau (API/XHR)
│   ├── animations.py          # Capture d'animations (Three.js, CSS, Vue)
│   ├── fonts.py               # Capture de polices
│   ├── rewriter.py            # Réécriture HTML/CSS
│   ├── screenshot.py          # Capture d'écran
│   └── storage.py             # Gestion du stockage
├── webui/                     # Interface web FastAPI
│   ├── server.py              # Serveur backend
│   ├── templates/             # Templates HTML
│   │   └── index.html
│   └── static/                # Assets statiques
│       ├── style.css
│       └── script.js
├── utils/                     # Utilitaires
│   ├── cli.py                 # Interface CLI (Rich)
│   ├── groq.py                # Client de résumé Groq
│   └── progress.py            # Barres de progression
├── _clones/                   # Clones sauvegardés (ignoré par git)
├── .env.example               # Exemple de configuration
├── requirements.txt           # Dépendances Python
└── .gitignore                 # Fichiers ignorés
```

---

## Résumé IA avec Groq

Pour utiliser la fonctionnalité de résumé IA :

1. Obtenez une clé API Groq sur [console.groq.com](https://console.groq.com)
2. Configurez-la dans le fichier `.env` :

```bash
GROQ_API_KEY=votre_clé_ici
```

3. Lancez le clonage avec l'option `--summarize` :

```bash
python main.py https://example.com --summarize
```

Le résumé sera sauvegardé dans le dossier du clone sous le nom `resume.md`.

---

## Exemples d'utilisation

### Cloner un blog
```bash
python main.py https://mon-blog.com --max-pages 50 --clone-mode static
```

### Cloner une application Nuxt/Next.js
```bash
python main.py https://app-moderne.com --clone-mode nuxt-perfect --scroll-steps 10
```

### Cloner avec interface web et résumé IA
```bash
python main.py https://example.com --ui --summarize
```

### Mode stealth pour sites protégés
```bash
python main.py https://site-avec-anti-bot.com --stealth --no-headless --wait-strategy load --request-delay 2
```

---

## Configuration avancée

### Variables d'environnement

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Clé API Groq pour le résumé IA |

### Personnalisation du navigateur

Par défaut, l'outil utilise **Microsoft Edge** en mode headless. Vous pouvez modifier le navigateur en changeant le paramètre `channel` dans `core/crawler.py` ou en utilisant `--no-headless` pour voir le navigateur en action.

---

## FAQ

### Quel navigateur est recommandé ?

**Microsoft Edge** est le navigateur par défaut recommandé. Il offre la meilleure compatibilité avec Playwright sur Windows.

### Comment copier et utiliser une URL ?

1. Ouvrez Microsoft Edge
2. Naviguez vers le site que vous voulez cloner
3. Copiez l'URL depuis la barre d'adresse (Ctrl+C)
4. Lancez Web Cloner avec l'URL copiée

### Ai-je besoin d'une clé API Groq ?

Non, le résumé IA est optionnel. Toutes les autres fonctionnalités fonctionnent sans clé API.

### Qu'est-ce que le mode stealth ?

Le mode stealth modifie les empreintes du navigateur pour éviter d'être détecté comme un bot. Il désactive le mode headless automatiquement.

### Les clones sont-ils fonctionnels hors ligne ?

Oui, tous les assets sont téléchargés localement et les chemins sont réécrits pour fonctionner sans connexion internet.

### Puis-je cloner un site nécessitant une connexion ?

Oui, utilisez `--no-headless` pour interagir manuellement avec le site (connexion, formulaires) avant le clonage.

---

## 🚀 Déploiement sur Render.com (gratuit)

Web Cloner peut être déployé gratuitement sur [Render.com](https://render.com) avec Docker.

### Prérequis
- Un compte GitHub (pour héberger le code)
- Un compte Render.com (gratuit, sans carte bancaire)

### Étapes

1. **Poussez le projet sur GitHub**
   ```bash
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

2. **Créez un Web Service sur Render**
   - Allez sur [dashboard.render.com](https://dashboard.render.com)
   - Cliquez **"New +" → "Web Service"**
   - Connectez votre repo GitHub
   - Sélectionnez `web-cloner`

3. **Configuration Render**
   | Champ | Valeur |
   |-------|--------|
   | Name | `web-cloner` |
   | Environment | `Docker` |
   | Branch | `main` |
   | Plan | **Free** |
   | Health Check Path | `/health` |

4. **Variables d'environnement**
   Dans l'onglet **Environment** du service Render, ajoutez :
   ```env
   GROQ_API_KEY=votre_cle_groq    # Optionnel
   TZ=Europe/Paris
   ```

5. **Déployez**
   - Cliquez **"Create Web Service"**
   - Render build l'image Docker et déploie automatiquement
   - Le déploiement initial prend 5-10 minutes (installation de Chromium)

### ⚠️ Limitations du plan gratuit Render
- **512 MB RAM** : suffisant pour 1 clonage à la fois
- **0.1 CPU** : les clonages sont lents mais fonctionnent
- **Sommeil après 15min d'inactivité** : le service s'éteint et se réveille automatiquement
- **750 heures/mois** : largement suffisant pour un usage personnel
- **Bandwidth limité** : 100 GB/mois

### Accès
Une fois déployé, votre app est accessible sur :
```
https://web-cloner.onrender.com
```

---

## Technologies utilisées

- **Python 3.8+**
- **Playwright** — Automatisation de navigateur
- **Microsoft Edge** — Navigateur par défaut
- **FastAPI** — Serveur web pour l'interface
- **Rich** — CLI moderne et colorée
- **Jinja2** — Templates HTML
- **Groq** — Résumé IA (optionnel)
- **BeautifulSoup4** — Parsing HTML
- **aiohttp** — Requêtes HTTP asynchrones

---

## Contribution

Les contributions sont les bienvenues !

1. Forkez le projet
2. Créez une branche : `git checkout -b feature/ma-fonctionnalite`
3. Commitez vos changements : `git commit -am 'Ajout de ma fonctionnalité'`
4. Poussez : `git push origin feature/ma-fonctionnalite`
5. Ouvrez une Pull Request

---

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

---

## Support

Si vous trouvez cet outil utile, n'hésitez pas à laisser une ⭐ sur GitHub !

Pour signaler un bug ou suggérer une amélioration : [ouvrir une issue](https://github.com/anomalyco/web_cloner/issues)
