/**
 * Extracted Data Feature - Index
 *
 * Re-exportiert alle oeffentlichen Komponenten, Hooks und Types.
 */

// Components
export { ExtractedDataPanel } from "./components/ExtractedDataPanel";
export { InvoiceDataDisplay } from "./components/InvoiceDataDisplay";
export { PaymentTermsCard } from "./components/PaymentTermsCard";
export { LineItemsTable } from "./components/LineItemsTable";
export { AddressCard } from "./components/AddressCard";
export {
    CopyableField,
    formatCurrency,
    formatDate,
    formatIBAN,
} from "./components/CopyableField";

// Hooks
export {
    useExtractedData,
    useExtractedDataSearch,
    useInvoiceList,
    useExtractedDataAggregations,
    useDocumentTypeStats,
    useInvalidateExtractedData,
    extractedDataKeys,
} from "./hooks/useExtractedData";

// API
export { extractedDataApi } from "./api/extracted-data-api";

// Types
export type {
    ExtractedDocumentType,
    ExtractedAddress,
    ExtractedLineItem,
    ExtractedInvoiceData,
    ExtractedOrderData,
    ExtractedContractData,
    DocumentClassification,
    ExtractedDocumentData,
    ExtractedDataSearchResult,
    PaginatedSearchResponse,
    InvoiceSummary,
    PaginatedInvoiceList,
    MonthlyAggregation,
    ExtractedDataAggregations,
    ExtractedDataSearchParams,
    InvoiceListParams,
} from "./types/extracted-data.types";
