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

/**
 * Validation Warning
 *
 * Note: Warnings don't have severity in the API response,
 * but we normalize them to have severity: 'warning' in the frontend
 * for consistent handling with ValidationError.
 */
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
    lineItems: LineItem[]; // Always array (empty if no items) - consistent nullish coalescing
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
// API RESPONSE TYPES (snake_case from backend)
// =============================================================================

/** Raw API response for parse endpoint */
interface ParseApiResponse {
    success: boolean;
    format: string | null;
    profile: string | null;
    version: string | null;
    invoice_data: RawInvoiceData | null;
    xml_content: string | null;
    errors: string[];
}

/** Raw invoice data from API (snake_case) */
interface RawInvoiceData {
    invoice_number?: string;
    invoice_date?: string;
    payment_due_date?: string;
    sender?: string;
    sender_address?: string;
    sender_city?: string;
    sender_postal_code?: string;
    sender_country?: string;
    sender_vat_id?: string;
    recipient?: string;
    recipient_address?: string;
    recipient_city?: string;
    recipient_postal_code?: string;
    recipient_country?: string;
    recipient_vat_id?: string;
    net_amount?: number;
    vat_amount?: number;
    gross_amount?: number;
    vat_rate?: number;
    currency?: string;
    payment_reference?: string;
    buyer_reference?: string;
    line_items?: RawLineItem[];
}

/** Raw line item from API */
interface RawLineItem {
    description: string;
    quantity: number;
    unit_price: number;
    total_price: number;
    vat_rate?: number;
}

/** Raw validation response from API */
interface ValidationApiResponse {
    valid: boolean;
    validator_used: string;
    validated_at: string;
    schema_valid: boolean;
    schematron_valid: boolean;
    pdf_a_compliant: boolean | null;
    errors?: RawValidationError[];
    warnings?: RawValidationWarning[];
    error_count: number;
    warning_count: number;
}

/** Raw validation error from API */
interface RawValidationError {
    code: string;
    location: string;
    message: string;
    severity: 'fatal' | 'error' | 'warning' | 'info';
    rule_id?: string;
}

/** Raw validation warning from API */
interface RawValidationWarning {
    code: string;
    location: string;
    message: string;
}

/** Raw formats response from API */
interface FormatsApiResponse {
    formats?: RawSupportedFormat[];
    default_format: string;
    default_profile: string;
}

/** Raw supported format from API */
interface RawSupportedFormat {
    id: string;
    name: string;
    description: string;
    supported_profiles: string[];
    b2g_compatible: boolean;
}

/** Raw status response from API */
interface StatusApiResponse {
    has_einvoice: boolean;
    document_id: string;
    einvoice_id?: string;
    format?: string;
    profile?: string;
    version?: string;
    is_valid?: boolean;
    was_generated?: boolean;
    was_extracted?: boolean;
    leitweg_id?: string;
    validation_summary?: {
        error_count: number;
        warning_count: number;
    };
    created_at?: string;
}

/** Raw Mustang health response from API */
interface MustangHealthApiResponse {
    status: 'healthy' | 'unavailable' | 'error';
    service: string;
    available: boolean;
    mustang_version?: string;
    java_version?: string;
    features?: {
        xrechnung_ubl: boolean;
        kosit_validation: boolean;
        pdf_extraction: boolean;
    };
    error?: string;
    message?: string;
}

// =============================================================================
// API SERVICE
// =============================================================================

class EInvoiceService {
    private readonly basePath = '/einvoice';

    /**
     * Parse E-Invoice (ZUGFeRD PDF or XRechnung XML)
     *
     * Note: apiClient.post generic specifies the RAW API response type (snake_case),
     * then transformParseResponse converts to the camelCase frontend type.
     */
    async parse(
        file: File,
        extractToDocument: boolean = false
    ): Promise<EInvoiceParseResponse> {
        const formData = new FormData();
        formData.append('file', file);

        // Generic type is ParseApiResponse (raw snake_case from backend)
        // NOT EInvoiceParseResponse (which is the transformed camelCase type)
        const response = await apiClient.post<ParseApiResponse>(
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

        const response = await apiClient.post<ValidationApiResponse>(
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
        const response = await apiClient.post<ValidationApiResponse>(
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
        const response = await apiClient.get<FormatsApiResponse>(`${this.basePath}/formats`);
        return this.transformFormatsResponse(response.data);
    }

    /**
     * Get E-Invoice status for document
     */
    async getStatus(documentId: string): Promise<EInvoiceStatus> {
        const response = await apiClient.get<StatusApiResponse>(`${this.basePath}/${documentId}`);
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
        const response = await apiClient.get<MustangHealthApiResponse>(`${this.basePath}/health/mustang`);
        return this.transformMustangHealthResponse(response.data);
    }

    // =============================================================================
    // RESPONSE TRANSFORMERS (snake_case -> camelCase)
    // =============================================================================

    private transformParseResponse(data: ParseApiResponse | null | undefined): EInvoiceParseResponse {
        // Defensive null check - prevent crash if API returns invalid data
        if (!data) {
            return {
                success: false,
                format: null,
                profile: null,
                version: null,
                invoiceData: null,
                xmlContent: null,
                errors: ['Ungueltige Server-Antwort'],
            };
        }
        return {
            success: data.success,
            format: data.format,
            profile: data.profile,
            version: data.version,
            invoiceData: data.invoice_data ? this.transformInvoiceData(data.invoice_data) : null,
            xmlContent: data.xml_content,
            errors: data.errors ?? [],
        };
    }

    private transformInvoiceData(data: RawInvoiceData): ExtractedInvoiceData {
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
            // Consistent nullish coalescing - always return empty array (not undefined)
            // This matches errors/warnings patterns and allows safe .map() calls
            lineItems: data.line_items?.map(item => ({
                description: item.description,
                quantity: item.quantity,
                unitPrice: item.unit_price,
                totalPrice: item.total_price,
                vatRate: item.vat_rate,
            })) ?? [],
        };
    }

    private transformValidationResponse(data: ValidationApiResponse | null | undefined): EInvoiceValidationResponse {
        // Defensive null check - prevent crash if API returns invalid data
        if (!data) {
            return {
                valid: false,
                validatorUsed: 'unknown',
                validatedAt: new Date().toISOString(),
                schemaValid: false,
                schematronValid: false,
                pdfACompliant: null,
                errors: [{ code: 'INTERNAL', location: '', message: 'Ungueltige Server-Antwort', severity: 'error' }],
                warnings: [],
                errorCount: 1,
                warningCount: 0,
            };
        }
        return {
            valid: data.valid,
            validatorUsed: data.validator_used,
            validatedAt: data.validated_at,
            schemaValid: data.schema_valid,
            schematronValid: data.schematron_valid,
            pdfACompliant: data.pdf_a_compliant,
            errors: data.errors?.map((e: RawValidationError) => ({
                code: e.code,
                location: e.location,
                message: e.message,
                severity: e.severity,
                ruleId: e.rule_id,
            })) ?? [],
            // Warnings are normalized to ValidationError with severity: 'warning'
            // This allows consistent UI rendering for both errors and warnings
            // Note: Backend may include rule_id in warnings for KOSIT validation
            warnings: data.warnings?.map((w: RawValidationWarning & { rule_id?: string }): ValidationError => ({
                code: w.code,
                location: w.location,
                message: w.message,
                severity: 'warning', // Hardcoded as warnings always have 'warning' severity
                ruleId: w.rule_id, // Include ruleId if backend provides it
            })) ?? [],
            errorCount: data.error_count,
            warningCount: data.warning_count,
        };
    }

    private transformFormatsResponse(data: FormatsApiResponse): EInvoiceFormatsResponse {
        return {
            // Type annotation removed - TypeScript infers from FormatsApiResponse.formats
            formats: data.formats?.map(f => ({
                id: f.id,
                name: f.name,
                description: f.description,
                supportedProfiles: f.supported_profiles,
                b2gCompatible: f.b2g_compatible,
            })) ?? [],
            defaultFormat: data.default_format,
            defaultProfile: data.default_profile,
        };
    }

    private transformStatusResponse(data: StatusApiResponse): EInvoiceStatus {
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

    private transformMustangHealthResponse(data: MustangHealthApiResponse): MustangHealthStatus {
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
