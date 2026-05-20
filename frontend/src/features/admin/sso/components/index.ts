/**
 * SSO Admin Components
 *
 * Exports all SSO administration components.
 */

export { EditProviderDialog } from './EditProviderDialog';
// SSOProvider is now exported from sso-schemas.ts as SSOProviderResponse for type consistency
export type { SSOProviderUpdate, EditProviderDialogProps } from './EditProviderDialog';

// Re-export types and schemas from types directory (includes SSOProviderResponse)
export * from '../types/sso-schemas';
