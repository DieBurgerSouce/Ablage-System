#!/usr/bin/env python3
"""
Example Authentication Client for Ablage-System OCR

Demonstrates the complete authentication flow:
1. User registration
2. Login
3. Access protected endpoint
4. Token refresh
5. Logout

Usage:
    python example_auth_client.py
"""

import asyncio
import httpx
from typing import Optional, Dict


class AblageAuthClient:
    """Simple authentication client for Ablage-System API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    async def register(
        self,
        email: str,
        username: str,
        password: str,
        full_name: str = "",
        preferred_language: str = "de"
    ) -> Dict:
        """
        Register a new user.

        Args:
            email: User email address
            username: Unique username
            password: Strong password (8+ chars, uppercase, lowercase, digit, special)
            full_name: Full name (optional)
            preferred_language: Preferred language (de or en)

        Returns:
            User information
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/auth/register",
                json={
                    "email": email,
                    "username": username,
                    "password": password,
                    "full_name": full_name,
                    "preferred_language": preferred_language
                }
            )

            if response.status_code == 201:
                print(f"✓ Benutzer '{username}' erfolgreich registriert!")
                return response.json()
            else:
                error = response.json()
                print(f"✗ Registrierung fehlgeschlagen: {error.get('detail', 'Unknown error')}")
                raise Exception(f"Registration failed: {error}")

    async def login(self, email: str, password: str) -> Dict:
        """
        Login and get JWT tokens.

        Args:
            email: User email
            password: User password

        Returns:
            Token information (access_token, refresh_token, token_type)
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password
                }
            )

            if response.status_code == 200:
                tokens = response.json()
                self.access_token = tokens["access_token"]
                self.refresh_token = tokens["refresh_token"]
                print(f"✓ Login erfolgreich!")
                print(f"  Access Token: {self.access_token[:20]}...")
                print(f"  Refresh Token: {self.refresh_token[:20]}...")
                return tokens
            else:
                error = response.json()
                print(f"✗ Login fehlgeschlagen: {error.get('detail', 'Unknown error')}")
                raise Exception(f"Login failed: {error}")

    async def get_current_user(self) -> Dict:
        """
        Get current user information.

        Requires valid access token.

        Returns:
            User information
        """
        if not self.access_token:
            raise Exception("Not authenticated. Please login first.")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )

            if response.status_code == 200:
                user = response.json()
                print(f"✓ Benutzerinformationen abgerufen:")
                print(f"  Email: {user['email']}")
                print(f"  Username: {user['username']}")
                print(f"  Sprache: {user['preferred_language']}")
                return user
            else:
                error = response.json()
                print(f"✗ Fehler beim Abrufen der Benutzerinformationen: {error.get('detail')}")
                raise Exception(f"Get user failed: {error}")

    async def refresh_access_token(self) -> Dict:
        """
        Refresh access token using refresh token.

        Returns:
            New token information
        """
        if not self.refresh_token:
            raise Exception("No refresh token available. Please login first.")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/auth/refresh",
                json={"refresh_token": self.refresh_token}
            )

            if response.status_code == 200:
                tokens = response.json()
                self.access_token = tokens["access_token"]
                self.refresh_token = tokens["refresh_token"]
                print(f"✓ Token erfolgreich erneuert!")
                return tokens
            else:
                error = response.json()
                print(f"✗ Token-Erneuerung fehlgeschlagen: {error.get('detail')}")
                raise Exception(f"Token refresh failed: {error}")

    async def logout(self) -> Dict:
        """
        Logout and invalidate tokens.

        Returns:
            Logout confirmation message
        """
        if not self.access_token:
            raise Exception("Not authenticated. Please login first.")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/auth/logout",
                json={"refresh_token": self.refresh_token},
                headers={"Authorization": f"Bearer {self.access_token}"}
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✓ {result['message']}")
                self.access_token = None
                self.refresh_token = None
                return result
            else:
                error = response.json()
                print(f"✗ Logout fehlgeschlagen: {error.get('detail')}")
                raise Exception(f"Logout failed: {error}")


async def demo_authentication_flow():
    """Demonstrate complete authentication flow."""
    print("=" * 60)
    print("Ablage-System Authentication Demo")
    print("=" * 60)

    # Initialize client
    client = AblageAuthClient(base_url="http://localhost:8000")

    # Demo credentials
    email = "demo@example.com"
    username = "demouser"
    password = "DemoPass123!"

    try:
        # Step 1: Register (will fail if user already exists)
        print("\n1. Benutzerregistrierung...")
        print("-" * 60)
        try:
            await client.register(
                email=email,
                username=username,
                password=password,
                full_name="Demo User"
            )
        except Exception as e:
            print(f"   (Benutzer existiert möglicherweise bereits)")

        # Step 2: Login
        print("\n2. Login...")
        print("-" * 60)
        await client.login(email=email, password=password)

        # Step 3: Get current user info
        print("\n3. Benutzerinformationen abrufen...")
        print("-" * 60)
        await client.get_current_user()

        # Step 4: Refresh token
        print("\n4. Token erneuern...")
        print("-" * 60)
        await client.refresh_access_token()

        # Step 5: Verify new token works
        print("\n5. Mit neuem Token Benutzerinformationen abrufen...")
        print("-" * 60)
        await client.get_current_user()

        # Step 6: Logout
        print("\n6. Logout...")
        print("-" * 60)
        await client.logout()

        print("\n" + "=" * 60)
        print("✓ Demo erfolgreich abgeschlossen!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Fehler: {e}")
        print("\nStellen Sie sicher, dass der Server läuft:")
        print("  python app/main.py")


async def interactive_demo():
    """Interactive authentication demo with user input."""
    print("=" * 60)
    print("Ablage-System - Interaktive Authentifizierung")
    print("=" * 60)

    client = AblageAuthClient(base_url="http://localhost:8000")

    print("\nWählen Sie eine Aktion:")
    print("1. Neuen Benutzer registrieren")
    print("2. Mit bestehendem Benutzer anmelden")
    print("3. Automatische Demo ausführen")

    choice = input("\nIhre Wahl (1-3): ").strip()

    if choice == "1":
        # Register new user
        print("\n--- Benutzerregistrierung ---")
        email = input("E-Mail: ").strip()
        username = input("Benutzername: ").strip()
        password = input("Passwort (min. 8 Zeichen, Groß-/Kleinbuchstaben, Ziffer, Sonderzeichen): ").strip()
        full_name = input("Vollständiger Name (optional): ").strip()

        await client.register(
            email=email,
            username=username,
            password=password,
            full_name=full_name
        )

        # Auto-login
        print("\nAutomatischer Login...")
        await client.login(email=email, password=password)
        await client.get_current_user()

    elif choice == "2":
        # Login existing user
        print("\n--- Benutzer-Login ---")
        email = input("E-Mail: ").strip()
        password = input("Passwort: ").strip()

        await client.login(email=email, password=password)
        await client.get_current_user()

        # Offer to refresh token
        refresh = input("\nToken erneuern? (j/n): ").strip().lower()
        if refresh == "j":
            await client.refresh_access_token()
            await client.get_current_user()

    elif choice == "3":
        # Run automatic demo
        await demo_authentication_flow()

    else:
        print("Ungültige Auswahl.")


if __name__ == "__main__":
    import sys

    print("\nAblage-System Authentication Client")
    print("====================================\n")

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        asyncio.run(interactive_demo())
    else:
        print("Automatische Demo wird ausgeführt...")
        print("(Verwenden Sie --interactive für interaktiven Modus)\n")
        asyncio.run(demo_authentication_flow())
