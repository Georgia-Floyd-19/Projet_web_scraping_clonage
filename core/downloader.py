from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import aiohttp

from .interceptor import CapturedResource
from .storage import _ensure_path

log = logging.getLogger("cloner.downloader")


@dataclass
class DownloadResult:
    url: str
    local_path: Optional[Path] = None
    success: bool = False
    cached: bool = False
    error: Optional[str] = None
    size_bytes: int = 0


class RateLimiter:
    def __init__(self, requests_per_second: float = 5.0) -> None:
        self.min_interval = 1.0 / requests_per_second
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            from time import monotonic
            now = monotonic()
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_call = monotonic()


class ResourceDownloader:
    def __init__(
        self,
        output_folder: Path,
        max_concurrent: int = 8,
        requests_per_second: float = 5.0,
        request_timeout: int = 30,
        max_retries: int = 3,
        user_agent: str = "Mozilla/5.0 (compatible; SiteArchiver/2.0)",
        session_cookies: Optional[dict[str, str]] = None,
    ) -> None:
        self.output_folder = output_folder
        self.max_concurrent = max_concurrent
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self.session_cookies = session_cookies or {}
        self._rate_limiter = RateLimiter(requests_per_second)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._cache: dict[str, Path] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        connector = aiohttp.TCPConnector(limit=self.max_concurrent, ssl=False)
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        headers = {"User-Agent": self.user_agent}
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers,
            cookies=self.session_cookies,
        )

    async def stop(self) -> None:
        if self._session:
            await self._session.close()

    async def __aenter__(self) -> "ResourceDownloader":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()

    async def save_intercepted(self, resource: CapturedResource, local_path: Path) -> DownloadResult:
        if resource.url in self._cache:
            return DownloadResult(
                url=resource.url,
                local_path=self._cache[resource.url],
                success=True,
                cached=True,
            )
        if not resource.body:
            return DownloadResult(url=resource.url, success=False, error="Corps vide")
        try:
            _ensure_path(local_path)
            local_path.write_bytes(resource.body)
            self._cache[resource.url] = local_path
            resource.saved_path = str(local_path)
            return DownloadResult(
                url=resource.url,
                local_path=local_path,
                success=True,
                size_bytes=len(resource.body),
            )
        except OSError as exc:
            err = f"Erreur écriture {local_path}: {exc}"
            log.warning(err)
            return DownloadResult(url=resource.url, success=False, error=err)

    async def download(self, url: str, local_path: Path) -> DownloadResult:
        if url in self._cache:
            return DownloadResult(url=url, local_path=self._cache[url], success=True, cached=True)
        if local_path.exists() and local_path.stat().st_size > 0:
            self._cache[url] = local_path
            return DownloadResult(url=url, local_path=local_path, success=True, cached=True)
        async with self._semaphore:
            return await self._download_with_retry(url, local_path)

    async def _download_with_retry(self, url: str, local_path: Path) -> DownloadResult:
        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                result = await self._do_download(url, local_path)
                if result.success:
                    return result
                last_error = result.error or "Erreur inconnue"
            except asyncio.TimeoutError:
                last_error = f"Timeout (tentative {attempt}/{self.max_retries})"
            except Exception as exc:
                last_error = str(exc)
            if attempt < self.max_retries:
                await asyncio.sleep(1.5 * attempt)
        return DownloadResult(url=url, success=False, error=last_error)

    async def _do_download(self, url: str, local_path: Path) -> DownloadResult:
        async with self._session.get(url, allow_redirects=True) as response:
            if response.status >= 400:
                return DownloadResult(url=url, success=False, error=f"HTTP {response.status}")
            content = await response.read()
            _ensure_path(local_path)
            local_path.write_bytes(content)
            self._cache[url] = local_path
            return DownloadResult(url=url, local_path=local_path, success=True, size_bytes=len(content))

    async def download_many(self, items: list[tuple[str, Path]]) -> list[DownloadResult]:
        tasks = [self.download(url, path) for url, path in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        final: list[DownloadResult] = []
        for url_path, result in zip(items, results):
            if isinstance(result, Exception):
                final.append(DownloadResult(url=url_path[0], success=False, error=str(result)))
            else:
                final.append(result)
        return final

    def is_cached(self, url: str) -> bool:
        return url in self._cache

    def cached_path(self, url: str) -> Optional[Path]:
        return self._cache.get(url)

    def register_cached(self, url: str, local_path: Path) -> None:
        self._cache[url] = local_path
