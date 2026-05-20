/**
 * E-Invoice Types
 *
 * Type-Definitionen für E-Invoice Komponenten.
 */

export type ZUGFeRDProfile = 'MINIMUM' | 'BASIC' | 'BASIC_WL' | 'EN16931' | 'EXTENDED' | 'XRECHNUNG';
export type XRechnungSyntax = 'CII' | 'UBL';
export type ValidatorType = 'FACTURX' | 'KOSIT' | 'MUSTANG' | 'AUTO';

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

export interface ValidationError {
    code: string;
    location: string;
    message: string;
    severity: 'fatal' | 'error' | 'warning' | 'info';
    ruleId?: string;
}

export interface ValidationResult {
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

export interface SupportedFormat {
    id: string;
    name: string;
    description: string;
    supportedProfiles: string[];
    b2gCompatible: boolean;
}

// Profile Display Names
export const PROFILE_LABELS: Record<ZUGFeRDProfile, string> = {
    MINIMUM: 'Minimum',
    BASIC: 'Basic',
    BASIC_WL: 'Basic ohne Positionen',
    EN16931: 'EN 16931 (Standard)',
    EXTENDED: 'Extended',
    XRECHNUNG: 'XRechnung (B2G)',
};

// Format Display Names
export const FORMAT_LABELS: Record<string, string> = {
    zugferd: 'ZUGFeRD 2.x',
    xrechnung_cii: 'XRechnung (CII)',
    xrechnung_ubl: 'XRechnung (UBL)',
};

// Syntax Display Names
export const SYNTAX_LABELS: Record<XRechnungSyntax, string> = {
    CII: 'UN/CEFACT CII',
    UBL: 'UBL 2.1',
};

// Validator Display Names
export const VALIDATOR_LABELS: Record<ValidatorType, string> = {
    FACTURX: 'factur-x (Schnell)',
    KOSIT: 'KoSIT (Offiziell)',
    MUSTANG: 'Mustang',
    AUTO: 'Automatisch',
};
