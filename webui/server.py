import asyncio
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.crawler import clone_site_async
from core.utils import human_size
from utils.groq import GroqSummarizer

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
static_dir = os.path.join(os.path.dirname(__file__), "static")
clones_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_clones")

app = FastAPI(title="Web Cloner")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/preview/{clone_name:path}")
async def preview_clone(clone_name: str):
    clone_path = Path(clones_dir) / clone_name
    if not clone_path.exists():
        return HTMLResponse("Clone introuvable", status_code=404)

    index = clone_path / "pages" / "index.html"
    if index.exists():
        return RedirectResponse(f"/_clones/{clone_name}/pages/index.html")

    html_files = sorted(clone_path.rglob("*.html"))
    if html_files:
        rel = html_files[0].relative_to(clone_path)
        return RedirectResponse(f"/_clones/{clone_name}/{rel}")

    return HTMLResponse("Aucune page HTML trouvée dans le clone", status_code=404)


clones_abs = os.path.abspath(clones_dir)
os.makedirs(clones_abs, exist_ok=True)
app.mount("/_clones", StaticFiles(directory=clones_abs), name="clones")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    start_time = time.time()

    try:
        data_raw = await websocket.receive_text()
        data = json.loads(data_raw)
        url = data.get("url", "").strip()
        options = data.get("options", {})
        if not url:
            await send_json(websocket, {"type": "error", "message": "URL manquante"})
            return
        if not url.startswith("http"):
            url = f"https://{url}"

        from datetime import datetime
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(clones_dir) / f"{domain}_{ts}"
        output_dir.mkdir(parents=True, exist_ok=True)
        clone_name = output_dir.name

        await send_json(websocket, {"type": "log", "message": f"Clonage de {url}...", "level": "info"})

        summarize = options.get("summarize", False)

        async def progress_callback(data: dict):
            try:
                await send_json(websocket, data)
            except Exception:
                pass

        result = await clone_site_async(
            start_url=url,
            output_folder=output_dir,
            max_pages=options.get("max_pages", 10),
            headless=True,
            channel="msedge",
            enable_interactions=options.get("enable_interactions", True),
            save_api_responses=options.get("save_api", True),
            request_delay_s=options.get("request_delay", 0.5),
            progress_callback=progress_callback,
            stealth=options.get("stealth", False),
            wait_strategy=options.get("wait_strategy", "networkidle"),
            wait_for_selector=options.get("wait_selector", None),
            page_timeout_ms=options.get("page_timeout", 60000),
            scroll_steps=options.get("scroll_steps", 5),
            clone_mode=options.get("clone_mode", "auto"),
            persistent_profile=options.get("persistent_profile", None),
        )

        duration = time.time() - start_time
        await send_json(websocket, {"type": "log", "message": f"Clonage terminé en {duration:.1f}s", "level": "success"})

        groq_summary_text = None
        if summarize:
            groq = GroqSummarizer()
            if groq.is_available():
                await send_json(websocket, {"type": "log", "message": "Génération du résumé IA...", "level": "info"})
                try:
                    first_html = next(output_dir.rglob("*.html"), None)
                    if first_html:
                        summary_path = groq.save_summary(
                            first_html.read_text(encoding="utf-8", errors="replace"),
                            str(output_dir),
                        )
                        if summary_path:
                            groq_summary_text = summary_path.read_text(encoding="utf-8").replace("# Résumé IA du site cloné\n\n", "")
                            await send_json(websocket, {"type": "log", "message": "Résumé IA généré", "level": "success"})
                except Exception as e:
                    await send_json(websocket, {"type": "log", "message": f"Erreur résumé Groq : {e}", "level": "warning"})

        await send_json(websocket, {
            "type": "complete",
            "url": url,
            "clone_name": clone_name,
            "output_dir": str(output_dir.resolve()),
            "summary": {
                "duration": duration,
                "pages_cloned": result.pages_cloned,
                "resources_saved": result.resources_saved,
                "api_calls_saved": result.api_calls_saved,
                "total_size": result.total_size_bytes,
                "framework": result.framework_detected or "",
                "groq_summary": groq_summary_text,
            },
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await send_json(websocket, {"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


async def send_json(websocket: WebSocket, data: dict):
    await websocket.send_text(json.dumps(data, ensure_ascii=False))


async def run_server(port: int = 8501, open_browser: bool = True):
    import uvicorn
    import webbrowser
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
