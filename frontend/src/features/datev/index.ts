/**
 * DATEV Feature - Barrel Export
 *
 * DATEV Buchungsstapel Export Funktionalität für deutsche Buchhaltung.
 * Unterstützt SKR03/SKR04 Kontenrahmen und generiert DATEV-konforme CSV-Dateien.
 */

// API Service und Types
export {
    datevService,
    type Kontenrahmen,
    type DATEVExportStatus,
    type DATEVExportType,
    type DATEVConfigurationCreate,
    type DATEVConfigurationUpdate,
    type DATEVConfigurationResponse,
    type DATEVVendorMappingCreate,
    type DATEVVendorMappingUpdate,
    type DATEVVendorMappingResponse,
    type DATEVExportRequest,
    type DATEVExportPreview,
    type DATEVExportHistoryItem,
    type DATEVExportHistoryResponse,
    type KontenrahmenInfo,
} from '@/lib/api/services/datev';

// Query Hooks
export {
    datevQueryKeys,
    useConfigs,
    useDefaultConfig,
    useCreateConfig,
    useUpdateConfig,
    useDeleteConfig,
    useVendorMappings,
    useCreateVendorMapping,
    useUpdateVendorMapping,
    useDeleteVendorMapping,
    useExportPreview,
    useExecuteExport,
    useExportHistory,
    useKontenrahmen,
} from './hooks/use-datev-queries';

// Utils
export {
    formatDate,
    formatDateTime,
    formatCurrency,
    formatPeriod,
    formatNumber,
    formatIban,
    formatVatId,
    formatExportStatus,
    formatKontenrahmen,
    getExportStatusVariant,
} from './utils';

// Validation Schemas
export {
    configurationSchema,
    vendorMappingSchema,
    exportRequestSchema,
    type ConfigurationFormData,
    type VendorMappingFormData,
    type ExportRequestFormData,
} from './utils/validation';

// Components
export {
    ConfigPage,
    ConfigDialog,
    VendorsPage,
    VendorMappingDialog,
    ExportPage,
    ExportPreview,
    ExportWarnings,
    HistoryPage,
    ExportStatusBadge,
} from './components';
