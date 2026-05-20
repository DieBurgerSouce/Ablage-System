# -*- coding: utf-8 -*-
"""
Security Test Suite - OWASP Top 10 Coverage

Testet alle kritischen Sicherheitsaspekte des Ablage-Systems:

Test-Module:
- test_injection.py: SQL, Command, JSONB Path-Traversal (A03:2021)
- test_broken_auth.py: JWT, Session, MFA, Password (A07:2021)
- test_broken_access.py: Multi-Tenant IDOR, Privilege Escalation (A01:2021)
- test_xss.py: XSS Prevention (A03:2021)
- test_csrf.py: CSRF Token Validation (A01:2021)
- test_ssrf.py: Email/IMAP SSRF, Cloud Metadata (A10:2021)
- test_pii_leakage.py: Log-Sanitization, Response-Scrubbing (GDPR)
- test_secrets_exposure.py: Keine Secrets in Code/Logs (A02:2021)
- test_rate_limiting.py: Bypass-Versuche, DoS-Protection (A05:2021)

Kritische Regeln aus CLAUDE.md:
- "NIEMALS Entity-Namen in Logs/Responses (PII)"
- "NIEMALS Kundennummern, IBANs, VAT-IDs in Logs"
- "Email-Passwoerter verschluesselt (AES-256-GCM)"
- "JSONB Whitelist-Validierung gegen Path-Traversal (CWE-89)"
- "HTTP Header Sanitization gegen CRLF (CWE-113)"

Usage:
    pytest tests/security/ -v
    pytest tests/security/test_injection.py -v
    pytest tests/security/ -k "sql"
"""

__all__ = [
    "test_injection",
    "test_broken_auth",
    "test_broken_access",
    "test_xss",
    "test_csrf",
    "test_ssrf",
    "test_pii_leakage",
    "test_secrets_exposure",
    "test_rate_limiting",
]
