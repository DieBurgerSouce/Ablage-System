# -*- coding: utf-8 -*-
"""First-Admin-CLI fuer das Ablage-System (M-07, Phase 0 Betriebsreife).

Legt idempotent den ersten Admin-Benutzer an bzw. befoerdert einen
bestehenden Benutzer:

- E-Mail:   argv[1] oder ENV ``ADMIN_EMAIL``
- Passwort: ENV ``ADMIN_PASSWORD``; fehlt es, wird ein sicheres
  Zufallspasswort erzeugt und EINMALIG auf stdout ausgegeben.
- Existiert der Benutzer bereits, wird er auf ``is_superuser=True`` und
  ``is_active=True`` gesetzt (idempotent); das Passwort bleibt unveraendert.
- Company: Es wird die erste aktive Company verwendet (Default-Company
  bevorzugt). Ist die Datenbank komplett leer, wird eine Company angelegt
  (Name via ENV ``ADMIN_COMPANY_NAME``, Default "Firmenich").

Hinweis: ``app/services/user_service.py`` erzwingt beim regulaeren
Registrieren bewusst ``is_superuser=False``. Dieses Skript setzt das Flag
direkt am ORM-Objekt und ist der vorgesehene Weg fuer den ersten Admin.

Aufruf im Backend-Container (scripts/ ist read-only gemountet):

    docker compose exec backend python scripts/create_admin.py admin@firmenich.de
    docker compose exec -e ADMIN_PASSWORD='...' backend python scripts/create_admin.py admin@firmenich.de

Das Skript ist idempotent: Mehrfachlaeufe lassen die Datenbank unveraendert.
Es werden keine Secrets geloggt; ein generiertes Passwort wird genau einmal
angezeigt.
"""
from __future__ import annotations

import asyncio
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

# sys.path-Bootstrap: Beim Direktaufruf "python scripts/create_admin.py" ist
# sys.path[0] das scripts/-Verzeichnis — Projekt-Root ergaenzen, damit "app.*"
# ohne PYTHONPATH importierbar ist (DoD: First-Admin ohne Vorwissen anlegbar).
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import select, text

import app.db.all_models  # noqa: F401  # registriert den vollstaendigen ORM-Modellgraphen
from app.core.security_auth import get_password_hash
from app.db.models import User
from app.db.models_cash_company import Company, UserCompany
from app.db.session import get_async_session_context

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 12
DEFAULT_COMPANY_NAME = "Firmenich"


def _abort(message: str) -> None:
    print(f"[create_admin] FEHLER: {message}")
    sys.exit(1)


def _resolve_email() -> str:
    """E-Mail aus argv[1] oder ENV ADMIN_EMAIL ermitteln und validieren."""
    email: Optional[str] = None
    if len(sys.argv) > 1 and sys.argv[1].strip():
        email = sys.argv[1].strip()
    elif os.getenv("ADMIN_EMAIL", "").strip():
        email = os.getenv("ADMIN_EMAIL", "").strip()

    if not email:
        _abort(
            "Keine E-Mail angegeben. Aufruf: python scripts/create_admin.py <email> "
            "oder ENV ADMIN_EMAIL setzen."
        )
    assert email is not None
    email = email.lower()
    if not EMAIL_RE.match(email):
        _abort(f"'{email}' ist keine gueltige E-Mail-Adresse.")
    return email


def _resolve_password() -> Tuple[str, bool]:
    """Passwort aus ENV ADMIN_PASSWORD oder sicher generieren.

    Returns:
        (passwort, wurde_generiert)
    """
    env_password = os.getenv("ADMIN_PASSWORD", "")
    if env_password:
        if len(env_password) < MIN_PASSWORD_LENGTH:
            _abort(
                f"ADMIN_PASSWORD ist zu kurz (mindestens {MIN_PASSWORD_LENGTH} Zeichen)."
            )
        return env_password, False
    # token_urlsafe(18) -> 24 Zeichen, URL-sicher, kryptographisch zufaellig
    return secrets.token_urlsafe(18), True


def _username_from_email(email: str) -> str:
    """Benutzernamen aus dem Localpart der E-Mail ableiten (a-z0-9._-)."""
    localpart = email.split("@", 1)[0].lower()
    username = re.sub(r"[^a-z0-9._-]", "-", localpart).strip("-._") or "admin"
    return username[:50]


async def _resolve_username(session, email: str) -> str:
    """Eindeutigen Benutzernamen bestimmen (Kollisionen bekommen ein Suffix)."""
    candidate = _username_from_email(email)
    existing = (
        await session.execute(select(User).where(User.username == candidate))
    ).scalar_one_or_none()
    if existing is None:
        return candidate
    return f"{candidate}-{secrets.token_hex(3)}"


async def _get_or_create_company(session) -> Tuple[Company, bool]:
    """Erste aktive Company verwenden; leere DB -> Company anlegen."""
    company = (
        (
            await session.execute(
                select(Company)
                .where(Company.is_active.is_(True))
                .order_by(Company.is_default.desc(), Company.created_at.asc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if company is not None:
        return company, False

    name = os.getenv("ADMIN_COMPANY_NAME", "").strip() or DEFAULT_COMPANY_NAME
    short_name = re.sub(r"[^a-z0-9]", "", name.lower())[:20] or "firma"
    company = Company(
        id=uuid4(),
        name=name,
        short_name=short_name,
        is_active=True,
        is_default=True,
    )
    session.add(company)
    await session.flush()
    return company, True


async def _ensure_membership(session, *, user: User, company: Company) -> bool:
    """UserCompany-Mitgliedschaft (owner, alle Rechte) sicherstellen.

    Achtung Partial-Unique ``uq_user_companies_one_current``: pro Benutzer darf
    genau EINE Mitgliedschaft ``is_current=True`` tragen. Hat der Benutzer
    bereits eine aktive Firma (z. B. Bestands-User in einer nicht-leeren DB),
    wird die neue Mitgliedschaft mit ``is_current=False`` angelegt und die
    bestehende Zuordnung nicht angefasst.
    """
    existing = (
        await session.execute(
            select(UserCompany).where(
                UserCompany.user_id == user.id,
                UserCompany.company_id == company.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False

    has_current = (
        await session.execute(
            select(UserCompany.id).where(
                UserCompany.user_id == user.id,
                UserCompany.is_current.is_(True),
            )
        )
    ).first() is not None

    session.add(
        UserCompany(
            id=uuid4(),
            user_id=user.id,
            company_id=company.id,
            role="owner",
            is_current=not has_current,
            can_manage_cash=True,
            can_approve_expenses=True,
            can_export_datev=True,
            can_manage_settings=True,
        )
    )
    return True


async def main() -> None:
    email = _resolve_email()
    password, password_generated = _resolve_password()

    async with get_async_session_context() as session:
        # Cross-Tenant-Setup (erste Einrichtung) -> RLS-Bypass wie in scripts/seed_e2e.py
        await session.execute(text("SELECT set_config('app.rls_bypass', 'true', true)"))

        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        user_created = False
        if user is None:
            username = await _resolve_username(session, email)
            user = User(
                id=uuid4(),
                email=email,
                username=username,
                hashed_password=get_password_hash(password),
                full_name="Administrator",
                is_active=True,
                # user_service.create_user erzwingt bewusst is_superuser=False;
                # der First-Admin wird deshalb hier direkt am ORM-Objekt gesetzt.
                is_superuser=True,
                email_verified=True,
            )
            session.add(user)
            await session.flush()
            user_created = True
        else:
            user.is_superuser = True
            user.is_active = True
            user.email_verified = True

        company, company_created = await _get_or_create_company(session)
        membership_created = await _ensure_membership(session, user=user, company=company)

    # --- Ausgaben (deutsch, keine Secrets ausser der Einmal-Ausgabe) ---------
    if user_created:
        print(f"[create_admin] Admin-Benutzer angelegt: {email}")
        if password_generated:
            print("")
            print("=" * 62)
            print("  WARNUNG: Es wurde ein Zufallspasswort generiert.")
            print("  Es wird NUR DIESES EINE MAL angezeigt — jetzt sicher")
            print("  ablegen (Passwort-Manager) und nach dem ersten Login")
            print("  aendern:")
            print("")
            print(f"      {password}")
            print("=" * 62)
            print("")
        else:
            print("[create_admin] Passwort aus ADMIN_PASSWORD uebernommen (wird nicht angezeigt).")
    else:
        print(
            f"[create_admin] Benutzer {email} existiert bereits — "
            "is_superuser=True und is_active=True gesetzt."
        )
        print("[create_admin] Passwort blieb unveraendert (kein Passwort-Reset).")

    print(
        f"[create_admin] Company: '{company.name}' "
        f"({'neu angelegt' if company_created else 'vorhanden'})"
    )
    print(
        f"[create_admin] Mitgliedschaft (owner): "
        f"{'neu angelegt' if membership_created else 'vorhanden'}"
    )
    print("[create_admin] Fertig.")


if __name__ == "__main__":
    asyncio.run(main())
