# -*- coding: utf-8 -*-
"""Synchroner Microsoft-Graph-Client (ausschliesslich GET) auf Basis von httpx.

Eigenschaften:
  - Bearer-Auth mit einmaligem Token-Refresh bei HTTP 401
  - Backoff bei 429/503 (und 500/502/504); Retry-After wird respektiert,
    sonst exponentielles Backoff mit Jitter, max. Versuche konfigurierbar (~8)
  - Paging ueber @odata.nextLink (Generator)
  - Timeout 60 s, follow_redirects (fuer Report-CSV-Downloads), fester User-Agent
Jede Anfrage wird geloggt (Datei via mail_lib.log, Konsole knapp).
"""

from __future__ import annotations

import hashlib
import random
import time
from pathlib import Path
from typing import Iterator

from . import USER_AGENT
from .auth import TokenProvider
from .log import get_logger

try:
    import httpx
except ImportError:  # httpx wird erst zur Laufzeit gebraucht (py_compile bleibt gruen).
    httpx = None

GRAPH_BASE = "https://graph.microsoft.com"
# Statuscodes, die einen erneuten Versuch rechtfertigen.
_RETRY_STATUS = (429, 500, 502, 503, 504)

_log = get_logger("graph")


class GraphError(RuntimeError):
    """Nicht behebbarer HTTP-Fehler von Microsoft Graph."""

    def __init__(self, status: int, message: str, url: str):
        super().__init__(f"HTTP {status} bei {_short(url)}: {message}")
        self.status = status
        self.url = url
        self.detail = message


def _short(url: str, n: int = 140) -> str:
    return url if len(url) <= n else url[:n] + "…"


def _err_text(resp) -> str:
    try:
        err = resp.json().get("error", {})
        text = f'{err.get("code", "")}: {err.get("message", "")}'.strip(": ")
        return text or (resp.text or "")[:300]
    except Exception:
        return (resp.text or "")[:300]


class GraphClient:
    """Duenner GET-Client fuer Graph v1.0/beta (rein lesend)."""

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        timeout: float = 60.0,
        max_attempts: int = 8,
        follow_redirects: bool = True,
    ):
        if httpx is None:
            raise RuntimeError(
                "Modul 'httpx' fehlt. Bitte installieren:\n"
                "  pip install -r requirements-m365.txt"
            )
        self.tp = token_provider
        self.max_attempts = max_attempts
        self.request_count = 0
        self._token: str | None = None
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=follow_redirects,
            headers={"User-Agent": USER_AGENT},
        )

    # -- Kontextmanager -------------------------------------------------
    def __enter__(self) -> "GraphClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- intern ---------------------------------------------------------
    def _absolute(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return GRAPH_BASE + "/" + url.lstrip("/")

    def _auth_header(self, refresh: bool = False) -> dict[str, str]:
        if refresh or not self._token:
            self._token = self.tp.get_token(force_refresh=refresh)
        return {"Authorization": f"Bearer {self._token}"}

    def _backoff(self, attempt: int) -> float:
        base = min(2 ** (attempt - 1), 60)
        return base + random.uniform(0, base * 0.25)

    def _retry_delay(self, resp, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 300.0)
            except ValueError:
                pass  # koennte ein HTTP-Datum sein -> Backoff nutzen
        return self._backoff(attempt)

    # -- oeffentlich ----------------------------------------------------
    def get(self, url: str, params: dict | None = None, *, extra_headers: dict | None = None):
        """Ein GET mit Auth, 401-Refresh und 429/503-Backoff. Liefert httpx.Response."""
        full = self._absolute(url)
        attempt = 0
        refreshed = False
        while True:
            attempt += 1
            headers = self._auth_header()
            if extra_headers:
                headers.update(extra_headers)
            self.request_count += 1
            started = time.monotonic()
            resp = self._client.get(full, params=params, headers=headers)
            elapsed_ms = (time.monotonic() - started) * 1000.0
            _log.debug("GET %s -> %s (%.0f ms, Versuch %d)", _short(full), resp.status_code, elapsed_ms, attempt)

            if resp.status_code == 401 and not refreshed:
                _log.info("401 — Token wird erneuert und Anfrage einmal wiederholt.")
                self._auth_header(refresh=True)
                refreshed = True
                continue

            if resp.status_code in _RETRY_STATUS:
                if attempt >= self.max_attempts:
                    raise GraphError(resp.status_code, "Maximale Versuchszahl erreicht", full)
                delay = self._retry_delay(resp, attempt)
                _log.warning(
                    "%s bei %s — warte %.1f s (Versuch %d/%d)",
                    resp.status_code, _short(full), delay, attempt, self.max_attempts,
                )
                time.sleep(delay)
                continue

            if resp.status_code >= 400:
                raise GraphError(resp.status_code, _err_text(resp), full)

            return resp

    def get_json(self, url: str, params: dict | None = None) -> dict:
        return self.get(url, params).json()

    def get_paged(self, url: str, params: dict | None = None) -> Iterator[dict]:
        """Iteriert ueber alle Seiten (@odata.nextLink) und liefert die Items aus 'value'."""
        next_url: str | None = url
        next_params = params
        while next_url:
            data = self.get_json(next_url, next_params)
            for item in data.get("value", []):
                yield item
            next_url = data.get("@odata.nextLink")
            next_params = None  # nextLink enthaelt bereits alle Query-Parameter

    def get_report_csv(self, url: str) -> str:
        """Download fuer /reports/*-Endpunkte.

        Graph antwortet dort mit 302 auf eine bereits vorautorisierte Download-URL,
        die KEINEN Authorization-Header vertraegt (sonst \"400 Request Too Long\").
        Deshalb: Redirect manuell folgen, Ziel ohne Auth-Header abrufen.
        """
        full = self._absolute(url)
        self.request_count += 1
        resp = self._client.get(full, headers=self._auth_header(), follow_redirects=False)
        if resp.status_code in (301, 302, 303, 307, 308):
            target = resp.headers.get("Location", "")
            if not target:
                raise GraphError(resp.status_code, "Redirect ohne Location-Header", full)
            self.request_count += 1
            dl = self._client.get(target, headers={"User-Agent": USER_AGENT, "Authorization": ""},
                                  follow_redirects=True)
            if dl.status_code >= 400:
                raise GraphError(dl.status_code, _err_text(dl), target)
            return dl.text
        if resp.status_code >= 400:
            raise GraphError(resp.status_code, _err_text(resp), full)
        return resp.text

    def stream_to_file(
        self, url: str, dest_path, *, params: dict | None = None, chunk_size: int = 1 << 16
    ) -> tuple[str, int]:
        """Streamt einen GET-Body speicherschonend nach dest_path (fuer .../$value).

        Liefert (sha256_hex, groesse_in_bytes). Auth-Refresh bei 401 und Backoff bei
        429/503 wie bei get(); Netzwerkfehler werden ebenfalls neu versucht. Bei jedem
        Versuch wird dest_path frisch geschrieben (Teil-Downloads werden verworfen).
        """
        full = self._absolute(url)
        dest_path = Path(dest_path)
        attempt = 0
        refreshed = False
        while True:
            attempt += 1
            headers = self._auth_header()
            self.request_count += 1
            started = time.monotonic()
            do_refresh = False
            retry_delay: float | None = None
            try:
                with self._client.stream("GET", full, params=params, headers=headers) as resp:
                    status = resp.status_code
                    if status == 401 and not refreshed:
                        do_refresh = True
                    elif status in _RETRY_STATUS:
                        if attempt >= self.max_attempts:
                            resp.read()
                            raise GraphError(status, "Maximale Versuchszahl erreicht", full)
                        retry_delay = self._retry_delay(resp, attempt)
                    elif status >= 400:
                        resp.read()
                        raise GraphError(status, _err_text(resp), full)
                    else:
                        digest = hashlib.sha256()
                        size = 0
                        with open(dest_path, "wb") as fh:
                            for chunk in resp.iter_bytes(chunk_size):
                                fh.write(chunk)
                                digest.update(chunk)
                                size += len(chunk)
                        elapsed_ms = (time.monotonic() - started) * 1000.0
                        _log.debug("GET(stream) %s -> %s (%d B, %.0f ms, Versuch %d)",
                                   _short(full), status, size, elapsed_ms, attempt)
                        return digest.hexdigest(), size
            except httpx.HTTPError as exc:
                if attempt >= self.max_attempts:
                    raise GraphError(0, f"Netzwerkfehler: {exc}", full)
                retry_delay = self._backoff(attempt)

            if do_refresh:
                _log.info("401 (Stream) — Token wird erneuert und Anfrage wiederholt.")
                self._auth_header(refresh=True)
                refreshed = True
                continue
            if retry_delay is not None:
                _log.warning("Stream-Retry bei %s — warte %.1f s (Versuch %d/%d)",
                             _short(full), retry_delay, attempt, self.max_attempts)
                time.sleep(retry_delay)
                continue
