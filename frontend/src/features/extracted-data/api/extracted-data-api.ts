/**
 * API Service für Strukturierte Dokumenten-Extraktion.
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
     * Listet alle Rechnungen mit Filtermöglichkeiten.
     */
    async listInvoices(params: InvoiceListParams): Promise<PaginatedInvoiceList> {
        const response = await apiClient.get<PaginatedInvoiceList>(
            `${BASE_URL}/invoices`,
            { params }
        );
        return response.data;
    },

    /**
     * Aggregierte Statistiken über extrahierte Daten.
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
     * Statistik über Dokumenttypen.
     */
    async getDocumentTypeStats(): Promise<Record<string, number>> {
        const response = await apiClient.get<Record<string, number>>(
            `${BASE_URL}/document-types/stats`
        );
        return response.data;
    },

    /**
     * Generiert Export-URL für CSV.
     */
    getExportCsvUrl(params: {
        document_type?: string;
        date_from?: string;
        date_to?: string;
        min_amount?: number;
        max_amount?: number;
    }): string {
        const searchParams = new URLSearchParams();
        if (params.document_type) searchParams.set("document_type", params.document_type);
        if (params.date_from) searchParams.set("date_from", params.date_from);
        if (params.date_to) searchParams.set("date_to", params.date_to);
        if (params.min_amount !== undefined) searchParams.set("min_amount", params.min_amount.toString());
        if (params.max_amount !== undefined) searchParams.set("max_amount", params.max_amount.toString());

        const queryString = searchParams.toString();
        return `${BASE_URL}/export/csv${queryString ? `?${queryString}` : ""}`;
    },

    /**
     * Generiert Export-URL für Excel.
     */
    getExportExcelUrl(params: {
        document_type?: string;
        date_from?: string;
        date_to?: string;
        min_amount?: number;
        max_amount?: number;
    }): string {
        const searchParams = new URLSearchParams();
        if (params.document_type) searchParams.set("document_type", params.document_type);
        if (params.date_from) searchParams.set("date_from", params.date_from);
        if (params.date_to) searchParams.set("date_to", params.date_to);
        if (params.min_amount !== undefined) searchParams.set("min_amount", params.min_amount.toString());
        if (params.max_amount !== undefined) searchParams.set("max_amount", params.max_amount.toString());

        const queryString = searchParams.toString();
        return `${BASE_URL}/export/excel${queryString ? `?${queryString}` : ""}`;
    },

    /**
     * Generiert Export-URL für alle Dokumenttypen (Excel mit Tabs).
     */
    getExportAllExcelUrl(params?: {
        date_from?: string;
        date_to?: string;
    }): string {
        const searchParams = new URLSearchParams();
        if (params?.date_from) searchParams.set("date_from", params.date_from);
        if (params?.date_to) searchParams.set("date_to", params.date_to);

        const queryString = searchParams.toString();
        return `${BASE_URL}/export/excel/all${queryString ? `?${queryString}` : ""}`;
    },

    /**
     * Führt einen Download aus (mit Auth-Token).
     */
    async downloadExport(url: string, filename: string): Promise<void> {
        const response = await apiClient.get(url, {
            responseType: "blob",
        });

        // Blob erstellen und downloaden
        const blob = new Blob([response.data]);
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = downloadUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(downloadUrl);
    },
};
