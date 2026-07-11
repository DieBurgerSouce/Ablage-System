# -*- coding: utf-8 -*-
"""Authentifizierung gegen Microsoft Entra (MSAL Client-Credentials-Flow).

Bevorzugt Zertifikat (PEM mit privatem Schluessel + Thumbprint), sonst Client-Secret.
Nur App-Berechtigungen, Scope https://graph.microsoft.com/.default. MSAL haelt den
Token in seinem internen Cache; get_token() bedient den Cache.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config

try:
    import msal
except ImportError:  # msal wird erst zur Laufzeit gebraucht (py_compile bleibt gruen).
    msal = None

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class AuthError(RuntimeError):
    """Token konnte nicht bezogen werden."""


def _require_msal() -> None:
    if msal is None:
        raise RuntimeError(
            "Modul 'msal' fehlt. Bitte installieren:\n"
            "  pip install -r requirements-m365.txt"
        )


class TokenProvider:
    """Haelt die MSAL-App und liefert Access-Tokens (mit internem Cache)."""

    def __init__(self, cfg: Config):
        _require_msal()
        self.cfg = cfg
        self._app = self._build_app()

    def _build_app(self):
        authority = self.cfg.authority()
        if self.cfg.use_cert:
            pem = Path(self.cfg.cert_path).read_bytes()
            thumb = self.cfg.cert_thumbprint.replace(":", "").replace(" ", "")
            credential = {"private_key": pem, "thumbprint": thumb}
            return msal.ConfidentialClientApplication(
                client_id=self.cfg.client_id,
                authority=authority,
                client_credential=credential,
            )
        # Fallback: Client-Secret.
        return msal.ConfidentialClientApplication(
            client_id=self.cfg.client_id,
            authority=authority,
            client_credential=self.cfg.client_secret,
        )

    def get_token(self, force_refresh: bool = False) -> str:
        """Liefert ein gueltiges Access-Token; force_refresh erzwingt eine Neuausstellung."""
        try:
            result = self._app.acquire_token_for_client(
                scopes=GRAPH_SCOPE, force_refresh=force_refresh
            )
        except TypeError:
            # Aeltere MSAL-Version ohne force_refresh-Parameter.
            result = self._app.acquire_token_for_client(scopes=GRAPH_SCOPE)

        if not result or "access_token" not in result:
            info = result or {}
            detail = info.get("error_description") or info.get("error") or "unbekannter Fehler"
            raise AuthError(f"Token-Abruf fehlgeschlagen: {detail}")
        return result["access_token"]
