/**
 * SSO Provider Zod Schemas
 *
 * Enterprise-grade type-safe validation schemas for SSO Provider operations.
 * Uses discriminated unions to prevent prototype pollution and ensure
 * type safety at runtime, not just compile time.
 *
 * Security Features:
 * - No index signatures ([key: string]) - prevents prototype pollution
 * - Discriminated unions for preset-specific validation
 * - Runtime validation before API calls
 * - Strict field whitelists
 */

import { z } from 'zod';
import { logger } from '@/lib/logger';

// =============================================================================
// Preset Enums
// =============================================================================

/** OIDC provider presets */
export const OIDC_PRESETS = [
  'microsoft_entra',
  'google_workspace',
  'okta',
  'auth0',
  'keycloak',
  'onelogin',
  'custom_oidc',
] as const;

/** SAML provider preset */
export const SAML_PRESETS = ['custom_saml'] as const;

/** All provider presets */
export const ALL_PRESETS = [...OIDC_PRESETS, ...SAML_PRESETS] as const;

export type OIDCPreset = (typeof OIDC_PRESETS)[number];
export type SAMLPreset = (typeof SAML_PRESETS)[number];
export type ProviderPresetName = (typeof ALL_PRESETS)[number];

// =============================================================================
// Base Schemas (Shared Fields)
// =============================================================================

/** Base fields for all create requests */
const baseCreateSchema = z.object({
  name: z.string().min(1, 'Name ist erforderlich').max(100, 'Maximal 100 Zeichen'),
});

// =============================================================================
// OIDC Create Schemas (Preset-Specific)
// =============================================================================

/** Microsoft Entra ID create schema */
const microsoftEntraCreateSchema = baseCreateSchema.extend({
  preset: z.literal('microsoft_entra'),
  client_id: z.string().min(1, 'Client ID ist erforderlich'),
  client_secret: z.string().min(1, 'Client Secret ist erforderlich'),
  tenant_id: z.string().optional(),
  scopes: z.string().optional().default('openid profile email'),
});

/** Google Workspace create schema */
const googleWorkspaceCreateSchema = baseCreateSchema.extend({
  preset: z.literal('google_workspace'),
  client_id: z.string().min(1, 'Client ID ist erforderlich'),
  client_secret: z.string().min(1, 'Client Secret ist erforderlich'),
  hosted_domain: z.string().optional(),
  scopes: z.string().optional().default('openid profile email'),
});

/** Okta create schema */
const oktaCreateSchema = baseCreateSchema.extend({
  preset: z.literal('okta'),
  client_id: z.string().min(1, 'Client ID ist erforderlich'),
  client_secret: z.string().min(1, 'Client Secret ist erforderlich'),
  issuer: z.string().optional(),
  scopes: z.string().optional().default('openid profile email'),
});

/** Auth0 create schema */
const auth0CreateSchema = baseCreateSchema.extend({
  preset: z.literal('auth0'),
  client_id: z.string().min(1, 'Client ID ist erforderlich'),
  client_secret: z.string().min(1, 'Client Secret ist erforderlich'),
  domain: z.string().optional(),
  scopes: z.string().optional().default('openid profile email'),
});

/** Keycloak create schema */
const keycloakCreateSchema = baseCreateSchema.extend({
  preset: z.literal('keycloak'),
  client_id: z.string().min(1, 'Client ID ist erforderlich'),
  client_secret: z.string().min(1, 'Client Secret ist erforderlich'),
  realm: z.string().optional(),
  server_url: z.string().optional(),
  scopes: z.string().optional().default('openid profile email'),
});

/** OneLogin create schema */
const oneloginCreateSchema = baseCreateSchema.extend({
  preset: z.literal('onelogin'),
  client_id: z.string().min(1, 'Client ID ist erforderlich'),
  client_secret: z.string().min(1, 'Client Secret ist erforderlich'),
  subdomain: z.string().optional(),
  scopes: z.string().optional().default('openid profile email'),
});

/** Custom OIDC create schema */
const customOIDCCreateSchema = baseCreateSchema.extend({
  preset: z.literal('custom_oidc'),
  client_id: z.string().min(1, 'Client ID ist erforderlich'),
  client_secret: z.string().min(1, 'Client Secret ist erforderlich'),
  issuer: z.string().optional(),
  authorization_url: z.string().optional(),
  token_url: z.string().optional(),
  userinfo_url: z.string().optional(),
  scopes: z.string().optional().default('openid profile email'),
});

// =============================================================================
// SAML Create Schema
// =============================================================================

/** Custom SAML create schema */
const customSAMLCreateSchema = baseCreateSchema.extend({
  preset: z.literal('custom_saml'),
  idp_certificate: z.string().min(1, 'IdP Zertifikat ist erforderlich'),
  idp_sso_url: z.string().optional(),
  idp_slo_url: z.string().optional(),
  sp_entity_id: z.string().optional(),
});

// =============================================================================
// Discriminated Union for Create Request
// =============================================================================

/**
 * SSO Provider Create Request Schema (Discriminated Union)
 *
 * Uses preset field as discriminator to validate preset-specific fields.
 * This prevents prototype pollution as only known fields are allowed.
 */
export const ssoProviderCreateSchema = z.discriminatedUnion('preset', [
  microsoftEntraCreateSchema,
  googleWorkspaceCreateSchema,
  oktaCreateSchema,
  auth0CreateSchema,
  keycloakCreateSchema,
  oneloginCreateSchema,
  customOIDCCreateSchema,
  customSAMLCreateSchema,
]);

export type SSOProviderCreateRequest = z.infer<typeof ssoProviderCreateSchema>;

// =============================================================================
// Response Schemas (for API Response Validation)
// =============================================================================

/** SSO Provider List Item schema (from API) */
export const ssoProviderListItemSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  provider_type: z.enum(['oidc', 'saml']),
  preset: z.enum(ALL_PRESETS),
  enabled: z.boolean(),
  is_primary: z.boolean(),
  login_count: z.number().int().nonnegative(),
  last_used_at: z.string().nullable(),
  created_at: z.string(),
});

export type SSOProviderListItem = z.infer<typeof ssoProviderListItemSchema>;

/**
 * Helper: Bounded record schema for API responses
 * Prevents DoS via oversized payloads from server
 * Limits: 100 keys, 500 chars per key/value
 */
const boundedResponseRecordSchema = z.record(
  z.string().max(500),
  z.string().max(500)
).refine(
  (record) => Object.keys(record).length <= 100,
  { message: 'Maximal 100 Einträge erlaubt' }
);

/** Full SSO Provider schema (from API) */
export const ssoProviderSchema = z.object({
  id: z.string().uuid(),
  name: z.string().max(200), // Bounded response
  provider_type: z.enum(['oidc', 'saml']),
  preset: z.enum(ALL_PRESETS),
  enabled: z.boolean(),
  is_primary: z.boolean(),
  auto_create_users: z.boolean(),
  default_role: z.string().max(100), // Bounded response
  allowed_domains: z.array(z.string().max(255)).max(50).nullable().optional(),
  group_mapping: boundedResponseRecordSchema.nullable().optional(), // Now bounded!
  login_count: z.number().int().nonnegative(),
  last_used_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type SSOProviderResponse = z.infer<typeof ssoProviderSchema>;

/** Provider Preset schema (from API) */
export const providerPresetSchema = z.object({
  preset: z.enum(ALL_PRESETS),
  provider_type: z.enum(['oidc', 'saml']),
  required_fields: z.array(z.string()),
  optional_fields: z.array(z.string()),
  description: z.string(),
});

export type ProviderPreset = z.infer<typeof providerPresetSchema>;

// =============================================================================
// Update Schema
// =============================================================================

/**
 * Helper: Bounded record schema to prevent DoS via oversized payloads
 * Limits key count to 100 and key/value length to 500 chars
 */
const boundedRecordSchema = z.record(
  z.string().max(500),
  z.string().max(500)
).refine(
  (record) => Object.keys(record).length <= 100,
  { message: 'Maximal 100 Einträge erlaubt' }
);

/** SSO Provider Update schema */
export const ssoProviderUpdateSchema = z.object({
  name: z.string().min(1).max(100).optional(),
  enabled: z.boolean().optional(),
  auto_create_users: z.boolean().optional(),
  default_role: z.string().max(100).optional(),
  allowed_domains: z.array(z.string().max(255)).max(50).nullable().optional(),
  group_mapping: boundedRecordSchema.nullable().optional(),
  // OIDC fields (optional for update)
  client_id: z.string().max(500).optional(),
  client_secret: z.string().max(1000).optional(),
  scopes: z.string().max(500).optional(),
  claims_mapping: boundedRecordSchema.nullable().optional(),
  // SAML fields (optional for update)
  idp_certificate: z.string().max(10000).optional(), // PEM certs can be large
  sp_entity_id: z.string().max(500).optional(),
  attribute_mapping: boundedRecordSchema.nullable().optional(),
});

export type SSOProviderUpdateRequest = z.infer<typeof ssoProviderUpdateSchema>;

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Check if preset is OIDC type
 */
export function isOIDCPreset(preset: string): preset is OIDCPreset {
  return (OIDC_PRESETS as readonly string[]).includes(preset);
}

/**
 * Check if preset is SAML type
 */
export function isSAMLPreset(preset: string): preset is SAMLPreset {
  return (SAML_PRESETS as readonly string[]).includes(preset);
}

/**
 * Get required fields for a preset
 */
export function getRequiredFieldsForPreset(preset: ProviderPreset['preset']): string[] {
  if (isOIDCPreset(preset)) {
    return ['client_id', 'client_secret'];
  }
  if (isSAMLPreset(preset)) {
    return ['idp_certificate'];
  }
  return [];
}

/**
 * Get preset display label
 */
export function getPresetLabel(preset: string): string {
  const labels: Record<string, string> = {
    microsoft_entra: 'Microsoft Entra ID',
    google_workspace: 'Google Workspace',
    okta: 'Okta',
    auth0: 'Auth0',
    keycloak: 'Keycloak',
    onelogin: 'OneLogin',
    custom_oidc: 'Custom OIDC',
    custom_saml: 'Custom SAML',
  };
  return labels[preset] ?? preset;
}

/**
 * Get preset icon
 */
export function getPresetIcon(preset: string): string {
  const icons: Record<string, string> = {
    microsoft_entra: '🔷',
    google_workspace: '🔴',
    okta: '🔵',
    auth0: '🟠',
    keycloak: '🟤',
    onelogin: '🟢',
    custom_oidc: '🔐',
    custom_saml: '🔏',
  };
  return icons[preset] ?? '🔐';
}

// =============================================================================
// Validation Helpers
// =============================================================================

/**
 * Validate create request with detailed error messages
 */
export function validateCreateRequest(data: unknown): {
  success: true;
  data: SSOProviderCreateRequest;
} | {
  success: false;
  error: string;
  details: z.ZodError['errors'];
} {
  const result = ssoProviderCreateSchema.safeParse(data);
  if (result.success) {
    return { success: true, data: result.data };
  }

  // Get first error message for display
  const firstError = result.error.errors[0];
  const errorPath = firstError.path.join('.');
  const errorMessage = errorPath
    ? `${errorPath}: ${firstError.message}`
    : firstError.message;

  return {
    success: false,
    error: errorMessage,
    details: result.error.errors,
  };
}

/**
 * Validation result type for provider response
 */
export type ValidateProviderResponseResult =
  | { success: true; data: SSOProviderResponse }
  | { success: false; error: string; data: null };

/**
 * Validate API response with detailed error information
 */
export function validateProviderResponse(data: unknown): ValidateProviderResponseResult {
  const result = ssoProviderSchema.safeParse(data);
  if (result.success) {
    return { success: true, data: result.data };
  }
  // Get first error for display
  const firstError = result.error.errors[0];
  const errorPath = firstError.path.join('.');
  const errorMessage = errorPath
    ? `${errorPath}: ${firstError.message}`
    : firstError.message;

  logger.error('[SSO] Validation failed:', errorMessage, result.error.errors);
  return { success: false, error: errorMessage, data: null };
}

/**
 * Validate provider list response
 */
export function validateProviderListResponse(data: unknown): SSOProviderListItem[] {
  if (!Array.isArray(data)) {
    return [];
  }
  return data
    .map(item => ssoProviderListItemSchema.safeParse(item))
    .filter((result): result is z.SafeParseSuccess<SSOProviderListItem> => result.success)
    .map(result => result.data);
}
