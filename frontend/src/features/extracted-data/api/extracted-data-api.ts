/**
 * API Service fuer Strukturierte Dokumenten-Extraktion.
 *
 * Kommuniziert mit /api/v1/extracted-data Endpoints.
 */

import { apiClient } from "@/lib/api/client";
import type {
    ExtractedDocumentData,
    PaginatedSearchResponse,
    PaginatedInvoiceList,
    ExtractedDataAggregations,
    ExtractedDataSearchParams,
    InvoiceListParams,
} from "../types/extracted-data.types";

const BASE_URL = "/extracted-data";

export const extractedDataApi = {
    /**
     * Liefert alle extrahierten Daten eines Dokuments.
     */
    async getByDocumentId(documentId: string): Promise<ExtractedDocumentData> {
        const response = await apiClient.get<ExtractedDocumentData>(
            `${BASE_URL}/${documentId}`
        );
        return response.data;
    },

    /**
     * Sucht Dokumente nach extrahierten Feldern.
     */
    async search(params: ExtractedDataSearchParams): Promise<PaginatedSearchResponse> {
        const response = await apiClient.get<PaginatedSearchResponse>(
            `${BASE_URL}/search`,
            { params }
        );
        return response.data;
    },

    /**
     * Listet alle Rechnungen mit Filtermoeglichkeiten.
     */
    async listInvoices(params: InvoiceListParams): Promise<PaginatedInvoiceList> {
        const response = await apiClient.get<PaginatedInvoiceList>(
            `${BASE_URL}/invoices`,
            { params }
        );
        return response.data;
    },

    /**
     * Aggregierte Statistiken ueber extrahierte Daten.
     */
    async getAggregations(params?: {
        document_type?: string;
        date_from?: string;
        date_to?: string;
    }): Promise<ExtractedDataAggregations> {
        const response = await apiClient.get<ExtractedDataAggregations>(
            `${BASE_URL}/aggregations`,
            { params }
        );
        return response.data;
    },

    /**
     * Statistik ueber Dokumenttypen.
     */
    async getDocumentTypeStats(): Promise<Record<string, number>> {
        const response = await apiClient.get<Record<string, number>>(
            `${BASE_URL}/document-types/stats`
        );
        return response.data;
    },
};
