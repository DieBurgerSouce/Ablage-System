/**
 * TanStack Query Hooks für Strukturierte Dokumenten-Extraktion.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { extractedDataApi } from "../api/extracted-data-api";
import type {
    ExtractedDataSearchParams,
    InvoiceListParams,
} from "../types/extracted-data.types";

// =============================================================================
// QUERY KEYS
// =============================================================================

export const extractedDataKeys = {
    all: ["extracted-data"] as const,
    byDocument: (documentId: string) =>
        [...extractedDataKeys.all, "document", documentId] as const,
    search: (params: ExtractedDataSearchParams) =>
        [...extractedDataKeys.all, "search", params] as const,
    invoices: (params: InvoiceListParams) =>
        [...extractedDataKeys.all, "invoices", params] as const,
    aggregations: (params?: { document_type?: string; date_from?: string; date_to?: string }) =>
        [...extractedDataKeys.all, "aggregations", params] as const,
    documentTypeStats: () => [...extractedDataKeys.all, "document-type-stats"] as const,
};

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Hook zum Abrufen der extrahierten Daten eines Dokuments.
 * 404 ist erwartet für neue Dokumente ohne extrahierte Daten.
 * Kein Retry, da 404 der Normalfall ist.
 */
export function useExtractedData(documentId: string | undefined) {
    return useQuery({
        queryKey: extractedDataKeys.byDocument(documentId || ""),
        queryFn: () => extractedDataApi.getByDocumentId(documentId!),
        enabled: !!documentId,
        staleTime: 5 * 60 * 1000, // 5 Minuten
        // KEIN Retry - 404 ist erwartet für Dokumente ohne extrahierte Daten
        retry: false,
    });
}

/**
 * Hook zum Suchen von Dokumenten nach extrahierten Feldern.
 */
export function useExtractedDataSearch(params: ExtractedDataSearchParams) {
    return useQuery({
        queryKey: extractedDataKeys.search(params),
        queryFn: () => extractedDataApi.search(params),
        staleTime: 2 * 60 * 1000, // 2 Minuten
        placeholderData: (previousData) => previousData,
    });
}

/**
 * Hook zum Auflisten von Rechnungen.
 */
export function useInvoiceList(params: InvoiceListParams) {
    return useQuery({
        queryKey: extractedDataKeys.invoices(params),
        queryFn: () => extractedDataApi.listInvoices(params),
        staleTime: 2 * 60 * 1000,
        placeholderData: (previousData) => previousData,
    });
}

/**
 * Hook für aggregierte Statistiken.
 */
export function useExtractedDataAggregations(params?: {
    document_type?: string;
    date_from?: string;
    date_to?: string;
}) {
    return useQuery({
        queryKey: extractedDataKeys.aggregations(params),
        queryFn: () => extractedDataApi.getAggregations(params),
        staleTime: 5 * 60 * 1000,
    });
}

/**
 * Hook für Dokumenttyp-Statistiken.
 */
export function useDocumentTypeStats() {
    return useQuery({
        queryKey: extractedDataKeys.documentTypeStats(),
        queryFn: () => extractedDataApi.getDocumentTypeStats(),
        staleTime: 5 * 60 * 1000,
    });
}

/**
 * Hook zum Invalidieren aller Extracted-Data-Queries nach Änderungen.
 */
export function useInvalidateExtractedData() {
    const queryClient = useQueryClient();

    return {
        invalidateAll: () =>
            queryClient.invalidateQueries({ queryKey: extractedDataKeys.all }),
        invalidateDocument: (documentId: string) =>
            queryClient.invalidateQueries({
                queryKey: extractedDataKeys.byDocument(documentId),
            }),
    };
}
