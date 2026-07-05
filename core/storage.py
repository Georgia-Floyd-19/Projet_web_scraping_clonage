from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote

log = logging.getLogger("cloner.storage")

INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*]')
MAX_SEGMENT_LENGTH = 60
MAX_TOTAL_PATH = 220


def _sanitize_segment(segment: str) -> str:
    s = INVALID_WIN_CHARS.sub("_", segment)
    s = s.replace(",", "_").replace(" ", "_")
    s = re.sub(r"\.(?=.*\.)", "_", s)
    s = s.strip(". ")
    if not s:
        s = "_"
    if len(s) > MAX_SEGMENT_LENGTH:
        h = hashlib.md5(s.encode()).hexdigest()[:12]
        s = s[:MAX_SEGMENT_LENGTH].rstrip("._") + "_" + h
    return s


def _ensure_path(path: Path) -> Path:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except FileNotFoundError:
        if os.name == "nt" and len(str(path)) > 240:
            full_str = str(path.absolute())
            if not full_str.startswith("\\\\?\\"):
                prefix = "\\\\?\\"
                full_str = prefix + full_str
                try:
                    Path(full_str).parent.mkdir(parents=True, exist_ok=True)
                    return Path(full_str)
                except Exception:
                    pass
        raise


@dataclass
class CloneManifest:
    start_url: str
    start_time: str
    end_time: Optional[str] = None
    pages_cloned: int = 0
    resources_saved: int = 0
    api_calls_saved: int = 0
    total_size_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    framework_detected: Optional[str] = None
    completed: bool = False


class StorageManager:
    CATEGORIES = ["pages", "styles", "scripts", "images", "fonts", "media", "api", "docs", "screenshots", "misc"]

    def __init__(self, output_folder: Path, start_url: str) -> None:
        self.output_folder = output_folder
        self.start_url = start_url
        self._url_map: dict[str, str] = {}
        self._manifest = CloneManifest(
            start_url=start_url,
            start_time=datetime.now(timezone.utc).isoformat(),
        )
        self._setup_directories()

    def _setup_directories(self) -> None:
        self.output_folder.mkdir(parents=True, exist_ok=True)
        for cat in self.CATEGORIES:
            (self.output_folder / cat).mkdir(exist_ok=True)
        log.debug("Structure créée dans %s", self.output_folder)

    def load_existing(self) -> bool:
        url_map_path = self.output_folder / "url_map.json"
        if not url_map_path.exists():
            return False
        try:
            self._url_map = json.loads(url_map_path.read_text(encoding="utf-8"))
            log.info("Reprise : %d URLs chargées", len(self._url_map))
            return True
        except Exception as exc:
            log.warning("Impossible de charger url_map.json : %s", exc)
            return False

    def resolve_path(self, url: str, category: str = "misc", default_ext: str = "") -> Path:
        if url in self._url_map:
            return self.output_folder / self._url_map[url]
        parsed = urlparse(url)
        path = unquote(parsed.path)
        if not path or path.endswith("/"):
            path = (path or "/").rstrip("/") + "/index.html"
        elif not os.path.splitext(os.path.basename(path))[1]:
            path = path + (default_ext or ".html")
        if parsed.query:
            h = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
            stem, ext = os.path.splitext(path)
            path = f"{stem}_{h}{ext}"
        clean_parts = [
            _sanitize_segment(p)
            for p in path.split("/")
            if p and p not in (".", "..")
        ]
        relative = Path(category) / "/".join(clean_parts)
        full = self.output_folder / relative
        if len(str(full)) > MAX_TOTAL_PATH:
            h = hashlib.md5(str(relative).encode()).hexdigest()[:16]
            ext = relative.suffix
            relative = Path(category) / h / f"{relative.stem[:40]}_{h[:8]}{ext}"
            full = self.output_folder / relative
        return full

    def register(self, url: str, local_path: Path) -> None:
        try:
            rel = local_path.relative_to(self.output_folder)
            self._url_map[url] = str(rel)
        except ValueError:
            self._url_map[url] = str(local_path)

    def get_local_path(self, url: str) -> Optional[Path]:
        rel = self._url_map.get(url)
        if rel:
            return self.output_folder / rel
        return None

    @property
    def url_to_path_map(self) -> dict[str, Path]:
        return {url: self.output_folder / rel for url, rel in self._url_map.items()}

    def save_page(self, url: str, content: str) -> Path:
        local_path = self.resolve_path(url, category="pages", default_ext=".html")
        _ensure_path(local_path)
        local_path.write_text(content, encoding="utf-8")
        self.register(url, local_path)
        return local_path

    def save_api_response(self, url: str, body: bytes, is_graphql: bool = False) -> Path:
        parsed = urlparse(url)
        h = hashlib.md5(url.encode()).hexdigest()[:12]
        safe_name = parsed.path.rstrip("/").split("/")[-1] or "response"
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_.")[:40]
        prefix = "graphql_" if is_graphql else "api_"
        filename = f"{prefix}{safe_name}_{h}.json"
        local_path = self.output_folder / "api" / filename
        _ensure_path(local_path)
        local_path.write_bytes(body)
        self.register(url, local_path)
        return local_path

    def save_url_map(self) -> None:
        url_map_path = self.output_folder / "url_map.json"
        url_map_path.write_text(
            json.dumps(self._url_map, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def save_manifest(self) -> None:
        manifest_path = self.output_folder / "manifest.json"
        manifest_path.write_text(
            json.dumps(asdict(self._manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def generate_service_worker(self) -> None:
        api_map = {}
        for url, rel_path in self._url_map.items():
            normalized = rel_path.replace("\\", "/")
            if normalized.startswith("api/"):
                api_map[url] = normalized

        if not api_map:
            return

        api_map_path = self.output_folder / "api_map.json"
        api_map_path.write_text(
            json.dumps(api_map, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        sw_code = """self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

let apiMap = {};

self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'API_MAP') {
        apiMap = event.data.map || {};
    }
});

self.addEventListener('fetch', (event) => {
    const url = event.request.url;
    const localPath = apiMap[url];
    if (localPath) {
        event.respondWith(
            fetch(localPath).catch(() => new Response('', { status: 404 }))
        );
    }
});"""
        sw_path = self.output_folder / "service-worker.js"
        sw_path.write_text(sw_code, encoding="utf-8")

        reg_code = """(async () => {
    try {
        const reg = await navigator.serviceWorker.register('service-worker.js', { scope: './' });
        await navigator.serviceWorker.ready;
        const resp = await fetch('api_map.json');
        const map = await resp.json();
        reg.active.postMessage({ type: 'API_MAP', map });
    } catch(e) {
        console.warn('SW init failed:', e);
    }
})();"""
        reg_path = self.output_folder / "sw-register.js"
        reg_path.write_text(reg_code, encoding="utf-8")
        log.info("Service Worker généré (%d routes API)", len(api_map))

    def finalize(
        self,
        pages_cloned: int,
        resources_saved: int,
        api_calls_saved: int,
        errors: list[str],
        framework: Optional[str] = None,
        clone_mode: str = "hybrid",
    ) -> None:
        self._manifest.end_time = datetime.now(timezone.utc).isoformat()
        self._manifest.pages_cloned = pages_cloned
        self._manifest.resources_saved = resources_saved
        self._manifest.api_calls_saved = api_calls_saved
        self._manifest.errors = errors
        self._manifest.framework_detected = framework
        self._manifest.completed = True
        total = sum(
            f.stat().st_size
            for f in self.output_folder.rglob("*")
            if f.is_file() and f.name not in ("manifest.json", "url_map.json", "api_map.json", "service-worker.js", "sw-register.js")
        )
        self._manifest.total_size_bytes = total
        self.save_url_map()
        self.save_manifest()
        if clone_mode == "hybrid":
            self.generate_service_worker()
        log.info(
            "Clone finalisé : %d pages, %d ressources, %.1f Mo",
            pages_cloned, resources_saved, total / 1_048_576,
        )

    @property
    def manifest(self) -> CloneManifest:
        return self._manifest
