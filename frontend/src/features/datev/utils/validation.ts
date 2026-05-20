/**
 * DATEV Validation Schemas
 *
 * Zod-Schemas für Formularvalidierung.
 * Alle Fehlermeldungen auf Deutsch.
 */

import { z } from 'zod';

// =============================================================================
// VALIDATION PATTERNS
// =============================================================================

/**
 * EU VAT-ID Pattern
 * 2 Buchstaben Ländercode + 8-13 alphanumerische Zeichen
 * Beispiele: DE123456789, ATU12345678, FR12345678901
 */
const VAT_ID_PATTERN = /^[A-Z]{2}[A-Z0-9]{2,13}$/;

/**
 * IBAN Pattern
 * 2 Buchstaben + 2 Prüfziffern + 11-30 alphanumerische Zeichen
 * Beispiel: DE89370400440532013000
 */
const IBAN_PATTERN = /^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/;

/**
 * Kontonummer Pattern
 * 4-10 Ziffern
 */
const ACCOUNT_NUMBER_PATTERN = /^[0-9]{4,10}$/;

// =============================================================================
// CONFIGURATION SCHEMA
// =============================================================================

export const configurationSchema = z.object({
    berater_nr: z
        .string()
        .min(1, 'Beraternummer ist erforderlich')
        .max(7, 'Beraternummer darf maximal 7 Stellen haben')
        .regex(/^\d+$/, 'Beraternummer darf nur Ziffern enthalten'),

    mandanten_nr: z
        .string()
        .min(1, 'Mandantennummer ist erforderlich')
        .max(5, 'Mandantennummer darf maximal 5 Stellen haben')
        .regex(/^\d+$/, 'Mandantennummer darf nur Ziffern enthalten'),

    wj_beginn: z.string().min(1, 'Wirtschaftsjahr-Beginn ist erforderlich'),

    kontenrahmen: z.enum(['SKR03', 'SKR04'], {
        message: 'Bitte Kontenrahmen wählen',
    }),

    incoming_expense_account: z
        .string()
        .regex(ACCOUNT_NUMBER_PATTERN, 'Kontonummer muss 4-10 Ziffern haben')
        .optional()
        .or(z.literal('')),

    incoming_creditor_account: z
        .string()
        .regex(ACCOUNT_NUMBER_PATTERN, 'Kontonummer muss 4-10 Ziffern haben')
        .optional()
        .or(z.literal('')),

    outgoing_revenue_account: z
        .string()
        .regex(ACCOUNT_NUMBER_PATTERN, 'Kontonummer muss 4-10 Ziffern haben')
        .optional()
        .or(z.literal('')),

    outgoing_debtor_account: z
        .string()
        .regex(ACCOUNT_NUMBER_PATTERN, 'Kontonummer muss 4-10 Ziffern haben')
        .optional()
        .or(z.literal('')),

    sammelkonto_kreditoren: z
        .string()
        .regex(ACCOUNT_NUMBER_PATTERN, 'Kontonummer muss 4-10 Ziffern haben'),

    sammelkonto_debitoren: z
        .string()
        .regex(ACCOUNT_NUMBER_PATTERN, 'Kontonummer muss 4-10 Ziffern haben'),

    sachkontenlange: z
        .number()
        .min(4, 'Mindestens 4 Stellen')
        .max(8, 'Maximal 8 Stellen'),

    buchungstext_format: z.string().max(100, 'Maximal 100 Zeichen'),

    is_default: z.boolean(),
});

export type ConfigurationFormData = z.infer<typeof configurationSchema>;

// =============================================================================
// VENDOR MAPPING SCHEMA
// =============================================================================

export const vendorMappingSchema = z
    .object({
        vendor_name: z.string().max(255, 'Maximal 255 Zeichen').optional().or(z.literal('')),

        vendor_vat_id: z
            .string()
            .transform((val) => (val ? val.replace(/[\s\-.]/g, '').toUpperCase() : val))
            .refine(
                (val) => !val || VAT_ID_PATTERN.test(val),
                'Ungültige USt-IdNr (z.B. DE123456789)'
            )
            .optional()
            .or(z.literal('')),

        vendor_iban: z
            .string()
            .transform((val) => (val ? val.replace(/\s/g, '').toUpperCase() : val))
            .refine((val) => !val || IBAN_PATTERN.test(val), 'Ungültige IBAN')
            .optional()
            .or(z.literal('')),

        business_entity_id: z.string().uuid().optional().or(z.literal('')),

        expense_account: z
            .string()
            .min(1, 'Aufwandskonto ist erforderlich')
            .regex(ACCOUNT_NUMBER_PATTERN, 'Kontonummer muss 4-10 Ziffern haben'),

        creditor_account: z
            .string()
            .regex(ACCOUNT_NUMBER_PATTERN, 'Kontonummer muss 4-10 Ziffern haben')
            .optional()
            .or(z.literal('')),

        cost_center: z.string().max(20, 'Maximal 20 Zeichen').optional().or(z.literal('')),

        cost_object: z.string().max(20, 'Maximal 20 Zeichen').optional().or(z.literal('')),
    })
    .refine(
        (data) =>
            data.vendor_name || data.vendor_vat_id || data.vendor_iban || data.business_entity_id,
        {
            message:
                'Mindestens ein Identifikationsmerkmal erforderlich (Name, USt-IdNr, IBAN oder Entity)',
            path: ['vendor_name'],
        }
    );

export type VendorMappingFormData = z.infer<typeof vendorMappingSchema>;

// =============================================================================
// EXPORT REQUEST SCHEMA
// =============================================================================

export const exportRequestSchema = z
    .object({
        config_id: z.string().uuid().optional().or(z.literal('')),

        period_from: z.string().optional().or(z.literal('')),

        period_to: z.string().optional().or(z.literal('')),

        include_already_exported: z.boolean().default(false),
    })
    .refine(
        (data) => {
            if (data.period_from && data.period_to) {
                return new Date(data.period_from) <= new Date(data.period_to);
            }
            return true;
        },
        {
            message: 'Startdatum muss vor oder gleich Enddatum sein',
            path: ['period_from'],
        }
    );

export type ExportRequestFormData = z.infer<typeof exportRequestSchema>;

// =============================================================================
// VALIDATION HELPERS
// =============================================================================

/**
 * Validiert eine USt-IdNr und gibt das normalisierte Ergebnis zurück
 */
export function validateVatId(vatId: string): { valid: boolean; normalized: string | null } {
    const normalized = vatId.replace(/[\s\-.]/g, '').toUpperCase();
    const valid = VAT_ID_PATTERN.test(normalized);
    return { valid, normalized: valid ? normalized : null };
}

/**
 * Validiert eine IBAN und gibt das normalisierte Ergebnis zurück
 */
export function validateIban(iban: string): { valid: boolean; normalized: string | null } {
    const normalized = iban.replace(/\s/g, '').toUpperCase();
    const valid = IBAN_PATTERN.test(normalized);
    return { valid, normalized: valid ? normalized : null };
}

/**
 * Validiert eine Kontonummer
 */
export function validateAccountNumber(
    account: string
): { valid: boolean; normalized: string | null } {
    const normalized = account.trim();
    const valid = ACCOUNT_NUMBER_PATTERN.test(normalized);
    return { valid, normalized: valid ? normalized : null };
}
