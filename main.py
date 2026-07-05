 #!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from core.crawler import clone_site_sync
from core.browser import BrowserConfig
from core.utils import setup_logging, human_size
from utils.cli import (
    console, show_banner, show_info, show_success,
    show_warning, show_error, show_summary,
)
from utils.groq import GroqSummarizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="web_cloner",
        description="Clonez n'importe quel site web en local avec tous ses assets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python main.py https://example.com
  python main.py https://example.com --max-pages 3 --no-interactions
  python main.py https://example.com --ui
  python main.py https://example.com --ui --port 8080
  python main.py https://example.com --groq-key gsk_xxx --summarize
        """,
    )

    parser.add_argument("url", type=str, nargs="?", default=None, help="URL du site à cloner")

    parser.add_argument("--ui", action="store_true", help="Lancer l'interface web")
    parser.add_argument("--port", type=int, default=8501, help="Port pour l'interface web (défaut: 8501)")
    parser.add_argument("--no-open", action="store_true", help="Ne pas ouvrir le navigateur automatiquement")

    parser.add_argument("-o", "--output", type=str, default=None, help="Dossier de sortie (défaut: _clones/<domaine>)")
    parser.add_argument("--max-pages", type=int, default=10, help="Nombre max de pages à cloner (défaut: 10)")
    parser.add_argument("--no-interactions", action="store_true", help="Désactiver les interactions automatiques")
    parser.add_argument("--no-api", action="store_true", help="Ne pas sauvegarder les réponses API")
    parser.add_argument("--request-delay", type=float, default=0.5, help="Délai entre requêtes (défaut: 0.5s)")
    parser.add_argument("--headless", action="store_true", default=True, help="Mode headless (par défaut)")
    parser.add_argument("--no-headless", action="store_true", help="Afficher le navigateur")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mode verbeux")
    parser.add_argument("--groq-key", type=str, default=None, help="Clé API Groq")
    parser.add_argument("--summarize", action="store_true", help="Générer un résumé IA")
    parser.add_argument("--overwrite", action="store_true", help="Écraser le dossier existant")
    parser.add_argument("--user-agent", type=str, default=None, help="User-Agent personnalisé")

    parser.add_argument("--stealth", action="store_true", help="Activer le mode stealth anti-bot (désactive headless)")
    parser.add_argument("--persistent-profile", type=str, default=None,
                        help="Chemin vers un dossier de profil Chrome persistant (meilleure anti-détection)")
    parser.add_argument("--wait-strategy", type=str, default="networkidle",
                        choices=["domcontentloaded", "networkidle", "load"],
                        help="Stratégie d'attente navigation (défaut: networkidle)")
    parser.add_argument("--wait-selector", type=str, default=None,
                        help="Sélecteur CSS à attendre après navigation")
    parser.add_argument("--page-timeout", type=int, default=60000,
                        help="Timeout navigation en ms (défaut: 60000)")
    parser.add_argument("--scroll-steps", type=int, default=5,
                        help="Nombre d'étapes de scroll progressif (défaut: 5)")

    parser.add_argument("--clone-mode", type=str, default="auto",
                        choices=["static", "hybrid", "snapshot", "auto", "screenshot", "nuxt-perfect"],
                        help="Mode de clonage : static (HTML+assets), hybrid (rejeu API), snapshot (DOM figé), auto (détection auto, défaut), screenshot (force capture canvas), nuxt-perfect (copie conforme avec animations+polices)")

    return parser.parse_args()


def resolve_output_dir(url: str, output_arg: str | None) -> Path:
    if output_arg:
        output_path = Path(output_arg)
    else:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path("_clones") / f"{domain}_{ts}"
    output_path.parent.mkdir(exist_ok=True)
    return output_path


async def main():
    args = parse_args()

    if args.ui or not args.url:
        from webui.server import run_server
        show_banner()
        show_info(f"Interface web : http://localhost:{args.port}")
        await run_server(port=args.port, open_browser=not args.no_open)
        return

    url = args.url
    start_time = time.time()

    if args.stealth and not args.no_headless:
        show_info("Mode stealth activé — désactivation du headless")
        args.no_headless = True

    if args.verbose:
        setup_logging(log_file=Path("logs") / "cloner.log")

    show_banner()
    show_info(f"Clonage de [bold]{url}[/]...")
    console.print()

    output_dir = resolve_output_dir(url, args.output)
    if not args.overwrite and output_dir.exists():
        show_error(f"Le dossier '{output_dir}' existe déjà. Utilisez --overwrite.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    groq = GroqSummarizer(api_key=args.groq_key)

    try:
        from utils.cli import create_progress_spinner
        spinner_progress = create_progress_spinner()

        with spinner_progress:
            task = spinner_progress.add_task("[cyan]Clonage en cours...", total=None)

            result = await asyncio.to_thread(
                clone_site_sync,
                start_url=url,
                output_folder=output_dir,
                max_pages=args.max_pages,
                headless=not args.no_headless,
                channel="msedge",
                enable_interactions=not args.no_interactions,
                save_api_responses=not args.no_api,
                request_delay_s=args.request_delay,
                user_agent=args.user_agent,
                stealth=args.stealth,
                wait_strategy=args.wait_strategy,
                wait_for_selector=args.wait_selector,
                page_timeout_ms=args.page_timeout,
                scroll_steps=args.scroll_steps,
                clone_mode=args.clone_mode,
                persistent_profile=args.persistent_profile,
            )

        duration = time.time() - start_time
        console.print()

        asset_summary = f"{result.pages_cloned} pages, {result.resources_saved} ressources"
        show_success(f"Clonage terminé en {duration:.1f}s — {asset_summary}")

        groq_summary_text = None
        if args.summarize and groq.is_available():
            html_files = list(output_dir.rglob("*.html"))
            if html_files:
                html_content = html_files[0].read_text(encoding="utf-8", errors="replace")
                with spinner_progress:
                    task = spinner_progress.add_task("[green]Génération du résumé IA...", total=None)
                summary_path = groq.save_summary(html_content, str(output_dir))
                if summary_path:
                    groq_summary_text = summary_path.read_text(encoding="utf-8").replace(
                        "# Résumé IA du site cloné\n\n", ""
                    )
                    show_success(f"Résumé IA sauvegardé : {summary_path}")
        elif args.summarize and not groq.is_available():
            show_warning("Aucune clé Groq trouvée. Passez --groq-key ou définissez GROQ_API_KEY.")

        show_summary(
            url=url,
            output_dir=output_dir.resolve(),
            duration=duration,
            asset_summary=asset_summary,
            rewrite_count=result.pages_cloned,
            total_size=result.total_size_bytes,
            groq_summary=groq_summary_text,
        )

        show_success("Clonage terminé avec succès !")

    except Exception as e:
        show_error(f"Erreur : {e}")
        if args.verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
