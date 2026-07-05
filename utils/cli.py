import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box

console = Console()


BANNER = r"""
[bold cyan]
  __        __   _          ___ _
  \ \      / /__| | ___ ___/ __| |___  ___ _ __
   \ \ /\ / / _ \ |/ __|_ _/__   / __|/ _ \ '__|
    \ V  V /  __/ | (__ | |  / /| (__|  __/ |
     \_/\_/ \___|_|\___|___| /_(_)\___|\___|_|
[/bold cyan]
[dim]Web Cloner - Clonez n'importe quel site web en local[/dim]
"""


def show_banner():
    console.print(BANNER)


def show_info(message: str):
    console.print(f"[blue]i[/] {message}")


def show_success(message: str):
    console.print(f"[bold green]v[/] {message}")


def show_warning(message: str):
    console.print(f"[bold yellow]![/] {message}")


def show_error(message: str):
    console.print(f"[bold red]x[/] {message}")


def create_progress_spinner(text: str = "Chargement en cours..."):
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )


def show_summary(url: str, output_dir: Path, duration: float, asset_summary: str, rewrite_count: int, total_size: int, groq_summary: str | None = None):
    table = Table(title="Récapitulatif du clonage", box=box.ROUNDED, border_style="cyan")

    table.add_column("Propriété", style="bold", width=20)
    table.add_column("Valeur")

    table.add_row("URL clonée", url)
    table.add_row("Dossier", str(output_dir))
    table.add_row("Durée", f"{duration:.2f}s")
    table.add_row("Assets téléchargés", asset_summary)
    table.add_row("Liens réécrits", str(rewrite_count))
    table.add_row("Taille totale", _format_size(total_size))

    console.print()
    console.print(table)

    if groq_summary:
        panel = Panel(
            Text(groq_summary, style="white"),
            title="[bold green]Résumé IA (Groq)[/]",
            border_style="green",
            box=box.ROUNDED,
        )
        console.print()
        console.print(panel)

    console.print()


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} o"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} Ko"
    else:
        return f"{size / (1024 * 1024):.1f} Mo"


_format_size = format_size
