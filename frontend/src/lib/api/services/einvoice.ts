/**
 * E-Invoice API Service
 *
 * TypeScript Client für E-Invoice Operationen:
 * - ZUGFeRD PDF Parsing und Generierung
 * - XRechnung XML Generierung (CII/UBL)
 * - KoSIT Validierung
 *
 * Standards: ZUGFeRD 2.x, XRechnung 3.0.2, EN 16931
 */

import { apiClient } from '../client';

// =============================================================================
// TYPES
// =============================================================================

/** ZUGFeRD Profile */
export type ZUGFeRDProfile = 'MINIMUM' | 'BASIC' | 'BASIC_WL' | 'EN16931' | 'EXTENDED' | 'XRECHNUNG';

/** XRechnung XML Syntax */
export type XRechnungSyntax = 'CII' | 'UBL';

/** Validator Types */
export type ValidatorType = 'FACTURX' | 'KOSIT' | 'MUSTANG' | 'AUTO';

/** E-Invoice Format */
export interface SupportedFormat {
    id: string;
    name: string;
    description: string;
    supportedProfiles: string[];
    b2gCompatible: boolean;
}

/** Validation Error */
export interface ValidationError {
    code: string;
    location: string;
    message: string;
    severity: 'fatal' | 'error' | 'warning' | 'info';
    ruleId?: string;
}

/** Validation Warning */
export interface ValidationWarning {
    code: string;
    location: string;
    message: string;
}

/** Parse Response */
export interface EInvoiceParseResponse {
    success: boolean;
    format: string | null;
    profile: string | null;
    version: string | null;
    invoiceData: ExtractedInvoiceData | null;
    xmlContent: string | null;
    errors: string[];
}

/** Generate Response */
export interface EInvoiceGenerateResponse {
    success: boolean;
    format: string;
    profile: string;
    einvoiceId: string;
    downloadUrl?: string;
}

/** Validation Response */
export interface EInvoiceValidationResponse {
    valid: boolean;
    validatorUsed: string;
    validatedAt: string;
    schemaValid: boolean;
    schematronValid: boolean;
    pdfACompliant: boolean | null;
    errors: ValidationError[];
    warnings: ValidationError[];
    errorCount: number;
    warningCount: number;
}

/** Formats Response */
export interface EInvoiceFormatsResponse {
    formats: SupportedFormat[];
    defaultFormat: string;
    defaultProfile: string;
}

/** E-Invoice Status */
export interface EInvoiceStatus {
    hasEinvoice: boolean;
    documentId: string;
    einvoiceId?: string;
    format?: string;
    profile?: string;
    version?: string;
    isValid?: boolean;
    wasGenerated?: boolean;
    wasExtracted?: boolean;
    leitwegId?: string;
    validationSummary?: {
        errorCount: number;
        warningCount: number;
    };
    createdAt?: string;
}

/** Mustang Health Status */
export interface MustangHealthStatus {
    status: 'healthy' | 'unavailable' | 'error';
    service: string;
    available: boolean;
    mustangVersion?: string;
    javaVersion?: string;
    features?: {
        xrechnungUbl: boolean;
        kositValidation: boolean;
        pdfExtraction: boolean;
    };
    error?: string;
    message?: string;
}

/** Extracted Invoice Data (subset for frontend) */
export interface ExtractedInvoiceData {
    invoiceNumber?: string;
    invoiceDate?: string;
    paymentDueDate?: string;
    sender?: string;
    senderAddress?: string;
    senderCity?: string;
    senderPostalCode?: string;
    senderCountry?: string;
    senderVatId?: string;
    recipient?: string;
    recipientAddress?: string;
    recipientCity?: string;
    recipientPostalCode?: string;
    recipientCountry?: string;
    recipientVatId?: string;
    netAmount?: number;
    vatAmount?: number;
    grossAmount?: number;
    vatRate?: number;
    currency?: string;
    paymentReference?: string;
    buyerReference?: string; // BT-10 Leitweg-ID
    lineItems?: LineItem[];
}

/** Line Item */
export interface LineItem {
    description: string;
    quantity: number;
    unitPrice: number;
    totalPrice: number;
    vatRate?: number;
}

// =============================================================================
// API SERVICE
// =============================================================================

class EInvoiceService {
    private readonly basePath = '/einvoice';

    /**
     * Parse E-Invoice (ZUGFeRD PDF or XRechnung XML)
     */
    async parse(
        file: File,
        extractToDocument: boolean = false
    ): Promise<EInvoiceParseResponse> {
        const formData = new FormData();
        formData.append('file', file);

        const response = await apiClient.post<EInvoiceParseResponse>(
            `${this.basePath}/parse`,
            formData,
            {
                params: { extract_to_document: extractToDocument },
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 60000, // 60s for large PDFs
            }
        );

        return this.transformParseResponse(response.data);
    }

    /**
     * Generate ZUGFeRD PDF
     */
    async generateZugferd(
        documentId: string,
        profile: ZUGFeRDProfile = 'EN16931'
    ): Promise<Blob> {
        const response = await apiClient.post(
            `${this.basePath}/generate/zugferd`,
            null,
            {
                params: {
                    document_id: documentId,
                    profile: profile,
                },
                responseType: 'blob',
                timeout: 120000, // 2 min for PDF generation
            }
        );

        return response.data;
    }

    /**
     * Generate XRechnung XML
     */
    async generateXrechnung(
        documentId: string,
        syntax: XRechnungSyntax = 'CII'
    ): Promise<Blob> {
        const response = await apiClient.post(
            `${this.basePath}/generate/xrechnung`,
            null,
            {
                params: {
                    document_id: documentId,
                    syntax: syntax,
                },
                responseType: 'blob',
                timeout: 60000,
            }
        );

        return response.data;
    }

    /**
     * Validate E-Invoice
     */
    async validate(
        file: File,
        validator: ValidatorType = 'AUTO'
    ): Promise<EInvoiceValidationResponse> {
        const formData = new FormData();
        formData.append('file', file);

        const response = await apiClient.post<any>(
            `${this.basePath}/validate`,
            formData,
            {
                params: { validator },
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 120000, // 2 min for KoSIT validation
            }
        );

        return this.transformValidationResponse(response.data);
    }

    /**
     * Validate by Document ID
     */
    async validateByDocumentId(
        documentId: string,
        validator: ValidatorType = 'AUTO'
    ): Promise<EInvoiceValidationResponse> {
        const response = await apiClient.post<any>(
            `${this.basePath}/validate`,
            null,
            {
                params: {
                    document_id: documentId,
                    validator,
                },
                timeout: 120000,
            }
        );

        return this.transformValidationResponse(response.data);
    }

    /**
     * Get supported formats
     */
    async getFormats(): Promise<EInvoiceFormatsResponse> {
        const response = await apiClient.get<any>(`${this.basePath}/formats`);
        return this.transformFormatsResponse(response.data);
    }

    /**
     * Get E-Invoice status for document
     */
    async getStatus(documentId: string): Promise<EInvoiceStatus> {
        const response = await apiClient.get<any>(`${this.basePath}/${documentId}`);
        return this.transformStatusResponse(response.data);
    }

    /**
     * Download E-Invoice XML
     */
    async downloadXml(documentId: string): Promise<Blob> {
        const response = await apiClient.get(
            `${this.basePath}/${documentId}/xml`,
            { responseType: 'blob' }
        );
        return response.data;
    }

    /**
     * Check Mustang service health
     */
    async checkMustangHealth(): Promise<MustangHealthStatus> {
        const response = await apiClient.get<any>(`${this.basePath}/health/mustang`);
        return this.transformMustangHealthResponse(response.data);
    }

    // =============================================================================
    // RESPONSE TRANSFORMERS (snake_case -> camelCase)
    // =============================================================================

    private transformParseResponse(data: any): EInvoiceParseResponse {
        return {
            success: data.success,
            format: data.format,
            profile: data.profile,
            version: data.version,
            invoiceData: data.invoice_data ? this.transformInvoiceData(data.invoice_data) : null,
            xmlContent: data.xml_content,
            errors: data.errors || [],
        };
    }

    private transformInvoiceData(data: any): ExtractedInvoiceData {
        return {
            invoiceNumber: data.invoice_number,
            invoiceDate: data.invoice_date,
            paymentDueDate: data.payment_due_date,
            sender: data.sender,
            senderAddress: data.sender_address,
            senderCity: data.sender_city,
            senderPostalCode: data.sender_postal_code,
            senderCountry: data.sender_country,
            senderVatId: data.sender_vat_id,
            recipient: data.recipient,
            recipientAddress: data.recipient_address,
            recipientCity: data.recipient_city,
            recipientPostalCode: data.recipient_postal_code,
            recipientCountry: data.recipient_country,
            recipientVatId: data.recipient_vat_id,
            netAmount: data.net_amount,
            vatAmount: data.vat_amount,
            grossAmount: data.gross_amount,
            vatRate: data.vat_rate,
            currency: data.currency,
            paymentReference: data.payment_reference,
            buyerReference: data.buyer_reference,
            lineItems: data.line_items?.map((item: any) => ({
                description: item.description,
                quantity: item.quantity,
                unitPrice: item.unit_price,
                totalPrice: item.total_price,
                vatRate: item.vat_rate,
            })),
        };
    }

    private transformValidationResponse(data: any): EInvoiceValidationResponse {
        return {
            valid: data.valid,
            validatorUsed: data.validator_used,
            validatedAt: data.validated_at,
            schemaValid: data.schema_valid,
            schematronValid: data.schematron_valid,
            pdfACompliant: data.pdf_a_compliant,
            errors: data.errors?.map((e: any) => ({
                code: e.code,
                location: e.location,
                message: e.message,
                severity: e.severity,
                ruleId: e.rule_id,
            })) || [],
            warnings: data.warnings?.map((w: any) => ({
                code: w.code,
                location: w.location,
                message: w.message,
                severity: 'warning' as const,
            })) || [],
            errorCount: data.error_count,
            warningCount: data.warning_count,
        };
    }

    private transformFormatsResponse(data: any): EInvoiceFormatsResponse {
        return {
            formats: data.formats?.map((f: any) => ({
                id: f.id,
                name: f.name,
                description: f.description,
                supportedProfiles: f.supported_profiles,
                b2gCompatible: f.b2g_compatible,
            })) || [],
            defaultFormat: data.default_format,
            defaultProfile: data.default_profile,
        };
    }

    private transformStatusResponse(data: any): EInvoiceStatus {
        return {
            hasEinvoice: data.has_einvoice,
            documentId: data.document_id,
            einvoiceId: data.einvoice_id,
            format: data.format,
            profile: data.profile,
            version: data.version,
            isValid: data.is_valid,
            wasGenerated: data.was_generated,
            wasExtracted: data.was_extracted,
            leitwegId: data.leitweg_id,
            validationSummary: data.validation_summary ? {
                errorCount: data.validation_summary.error_count,
                warningCount: data.validation_summary.warning_count,
            } : undefined,
            createdAt: data.created_at,
        };
    }

    private transformMustangHealthResponse(data: any): MustangHealthStatus {
        return {
            status: data.status,
            service: data.service,
            available: data.available,
            mustangVersion: data.mustang_version,
            javaVersion: data.java_version,
            features: data.features ? {
                xrechnungUbl: data.features.xrechnung_ubl,
                kositValidation: data.features.kosit_validation,
                pdfExtraction: data.features.pdf_extraction,
            } : undefined,
            error: data.error,
            message: data.message,
        };
    }
}

// Export singleton instance
export const einvoiceService = new EInvoiceService();

// Export utility functions
export function downloadFile(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

export function getProfileDisplayName(profile: ZUGFeRDProfile): string {
    const names: Record<ZUGFeRDProfile, string> = {
        MINIMUM: 'Minimum',
        BASIC: 'Basic',
        BASIC_WL: 'Basic WL',
        EN16931: 'EN 16931 (Empfohlen)',
        EXTENDED: 'Extended',
        XRECHNUNG: 'XRechnung (B2G)',
    };
    return names[profile] || profile;
}

export function getSyntaxDisplayName(syntax: XRechnungSyntax): string {
    const names: Record<XRechnungSyntax, string> = {
        CII: 'UN/CEFACT CII',
        UBL: 'UBL 2.1',
    };
    return names[syntax] || syntax;
}
