"""Загрузка страниц: повторы при ошибках, ограничение скорости, robots.txt и файловый кэш."""

import hashlib
import logging
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; web-parser/1.0; +https://github.com/ZniKDK/web-parser)"
# Коды, при которых есть смысл повторить запрос: перегрузка или временный сбой сервера
RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """Страницу не удалось загрузить даже после всех повторов."""


class BlockedByRobots(FetchError):
    """Сайт запретил эту страницу в robots.txt."""


class Fetcher:
    def __init__(
        self,
        delay: float = 0.2,
        retries: int = 3,
        backoff: float = 1.0,
        timeout: float = 15,
        cache_dir: str | Path | None = None,
        respect_robots: bool = True,
        session: requests.Session | None = None,
    ):
        self.delay = delay
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.respect_robots = respect_robots
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        # Общий замок: даже при нескольких потоках запросы уходят не чаще, чем раз в delay секунд
        self._rate_lock = threading.Lock()
        self._last_request = 0.0
        self._robots: dict[str, RobotFileParser | None] = {}
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0}

    def get(self, url: str) -> str:
        cached = self._read_cache(url)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        if self.respect_robots and not self._allowed(url):
            raise BlockedByRobots(f"robots.txt запрещает: {url}")

        last_error = ""
        for attempt in range(self.retries + 1):
            if attempt:
                self.stats["retries"] += 1
                # Экспоненциальная пауза: 1 с, 2 с, 4 с…
                time.sleep(self.backoff * 2 ** (attempt - 1))
            self._wait_turn()
            try:
                response = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as error:
                last_error = f"{type(error).__name__}: {error}"
                log.warning("Сбой сети (%s), попытка %d: %s", url, attempt + 1, last_error)
                continue
            self.stats["requests"] += 1
            if response.status_code in RETRY_STATUSES:
                last_error = f"HTTP {response.status_code}"
                log.warning("%s для %s, попытка %d", last_error, url, attempt + 1)
                continue
            if response.status_code != 200:
                # 404 и подобные повторять бессмысленно
                raise FetchError(f"HTTP {response.status_code}: {url}")
            # Сайты часто не указывают кодировку — тогда requests ошибочно берёт latin-1
            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding or "utf-8"
            html = response.text
            self._write_cache(url, html)
            return html
        raise FetchError(f"Не удалось загрузить {url}: {last_error}")

    def _wait_turn(self) -> None:
        with self._rate_lock:
            pause = self._last_request + self.delay - time.monotonic()
            if pause > 0:
                time.sleep(pause)
            self._last_request = time.monotonic()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser()
            try:
                response = self.session.get(urljoin(origin, "/robots.txt"), timeout=self.timeout)
            except requests.RequestException:
                parser = None  # robots.txt недоступен — считаем, что ограничений нет
            else:
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:
                    parser = None  # 404 и т. п. — ограничений нет
            self._robots[origin] = parser
        parser = self._robots[origin]
        return parser is None or parser.can_fetch(self.session.headers["User-Agent"], url)

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".html")

    def _read_cache(self, url: str) -> str | None:
        path = self._cache_path(url)
        if path and path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _write_cache(self, url: str, html: str) -> None:
        path = self._cache_path(url)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
