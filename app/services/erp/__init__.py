"""
ERP Integration Module.

Enterprise-Level ERP-Anbindung:
- Abstrakte Basisklasse fuer alle ERP-Systeme
- Odoo-spezifische Implementierung
- Bidirektionale Synchronisation
- Konflikt-Management
- Feld-Mapping und Transformationen
- Sync-Engine mit Delta-Sync

Feinpoliert und durchdacht - ERP-Integration auf Enterprise-Niveau.
"""

from app.services.erp.base_connector import (
    ERPConnector,
    ERPConnectionConfig,
    ERPConnectionStatus,
    ERPSyncDirection,
    ERPSyncResult,
    ERPEntity,
    ERPConflict,
)
from app.services.erp.odoo_connector import OdooConnector
from app.services.erp.field_mapping import (
    FieldTransformer,
    EntityMappingService,
    get_mapping_service,
)
from app.services.erp.sync_engine import (
    SyncEngine,
    SyncType,
    SyncStrategy,
    SyncRecord,
    SyncBatch,
    create_sync_engine,
)

__all__ = [
    # Base classes
    "ERPConnector",
    "ERPConnectionConfig",
    "ERPConnectionStatus",
    "ERPSyncDirection",
    "ERPSyncResult",
    "ERPEntity",
    "ERPConflict",
    # Connectors
    "OdooConnector",
    # Field Mapping
    "FieldTransformer",
    "EntityMappingService",
    "get_mapping_service",
    # Sync Engine
    "SyncEngine",
    "SyncType",
    "SyncStrategy",
    "SyncRecord",
    "SyncBatch",
    "create_sync_engine",
]
