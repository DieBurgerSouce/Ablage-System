/**
 * E-Invoice Hooks
 *
 * React Query Hooks für E-Invoice Operationen.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { einvoiceService, downloadFile } from '@/lib/api/services/einvoice';
import type { ZUGFeRDProfile, XRechnungSyntax, ValidatorType } from '../types/einvoice.types';

// Query Keys
export const einvoiceKeys = {
    all: ['einvoice'] as const,
    status: (documentId: string) => [...einvoiceKeys.all, 'status', documentId] as const,
    formats: () => [...einvoiceKeys.all, 'formats'] as const,
    mustangHealth: () => [...einvoiceKeys.all, 'mustang-health'] as const,
};

/**
 * Hook für E-Invoice Status eines Dokuments
 */
export function useEInvoiceStatus(documentId: string | undefined) {
    return useQuery({
        queryKey: einvoiceKeys.status(documentId || ''),
        queryFn: () => einvoiceService.getStatus(documentId!),
        enabled: !!documentId,
        staleTime: 30 * 1000, // 30 Sekunden
    });
}

/**
 * Hook für unterstützte Formate
 */
export function useEInvoiceFormats() {
    return useQuery({
        queryKey: einvoiceKeys.formats(),
        queryFn: () => einvoiceService.getFormats(),
        staleTime: 5 * 60 * 1000, // 5 Minuten
    });
}

/**
 * Hook für Mustang Health Status
 */
export function useMustangHealth() {
    return useQuery({
        queryKey: einvoiceKeys.mustangHealth(),
        queryFn: () => einvoiceService.checkMustangHealth(),
        staleTime: 60 * 1000, // 1 Minute
        retry: 1,
    });
}

/**
 * Hook für ZUGFeRD PDF Generierung
 */
export function useGenerateZugferd() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            documentId,
            profile,
        }: {
            documentId: string;
            profile: ZUGFeRDProfile;
        }) => {
            const blob = await einvoiceService.generateZugferd(documentId, profile);
            const filename = `zugferd_${documentId}_${profile.toLowerCase()}.pdf`;
            downloadFile(blob, filename);
            return { success: true, filename };
        },
        onSuccess: (_, { documentId }) => {
            // Status invalidieren
            queryClient.invalidateQueries({
                queryKey: einvoiceKeys.status(documentId),
            });
        },
    });
}

/**
 * Hook für XRechnung XML Generierung
 */
export function useGenerateXrechnung() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            documentId,
            syntax,
        }: {
            documentId: string;
            syntax: XRechnungSyntax;
        }) => {
            const blob = await einvoiceService.generateXrechnung(documentId, syntax);
            const filename = `xrechnung_${documentId}_${syntax.toLowerCase()}.xml`;
            downloadFile(blob, filename);
            return { success: true, filename };
        },
        onSuccess: (_, { documentId }) => {
            queryClient.invalidateQueries({
                queryKey: einvoiceKeys.status(documentId),
            });
        },
    });
}

/**
 * Hook für E-Invoice Validierung
 */
export function useValidateEInvoice() {
    return useMutation({
        mutationFn: async ({
            file,
            validator,
        }: {
            file: File;
            validator?: ValidatorType;
        }) => {
            return einvoiceService.validate(file, validator);
        },
    });
}

/**
 * Hook für Validierung nach Document ID
 */
export function useValidateByDocumentId() {
    return useMutation({
        mutationFn: async ({
            documentId,
            validator,
        }: {
            documentId: string;
            validator?: ValidatorType;
        }) => {
            return einvoiceService.validateByDocumentId(documentId, validator);
        },
    });
}

/**
 * Hook für E-Invoice Parsing
 */
export function useParseEInvoice() {
    return useMutation({
        mutationFn: async ({
            file,
            extractToDocument,
        }: {
            file: File;
            extractToDocument?: boolean;
        }) => {
            return einvoiceService.parse(file, extractToDocument);
        },
    });
}

/**
 * Hook für XML Download
 */
export function useDownloadXml() {
    return useMutation({
        mutationFn: async (documentId: string) => {
            const blob = await einvoiceService.downloadXml(documentId);
            const filename = `einvoice_${documentId}.xml`;
            downloadFile(blob, filename);
            return { success: true, filename };
        },
    });
}
