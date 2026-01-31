# -*- coding: utf-8 -*-
"""
DATEVconnect Integration Services.

Vollstaendige bidirektionale Integration mit DATEVconnect API:
- OAuth2 Authentifizierung
- Stammdaten Sync (Kunden/Lieferanten)
- Buchungsstapel Push
- Belegbilder Upload
- Kontierungsvorschlaege (ML-gestuetzt)

Feinpoliert und durchdacht - Enterprise-Ready DATEV Integration.
"""

from .datev_connector import DATEVConnector, get_datev_connector
from .datev_auth_service import DATEVAuthService, get_datev_auth_service
from .kontierung_service import KontierungsvorschlagService, get_kontierung_service
from .gobd_compliance_service import GoBDComplianceService, get_gobd_service

__all__ = [
    # Connector
    "DATEVConnector",
    "get_datev_connector",
    # Auth
    "DATEVAuthService",
    "get_datev_auth_service",
    # Kontierung
    "KontierungsvorschlagService",
    "get_kontierung_service",
    # GoBD
    "GoBDComplianceService",
    "get_gobd_service",
]
