/**
 * GoBD Feature Types
 *
 * TypeScript Definitionen fuer GoBD-konforme Archivierung.
 */

// ==================================================
// Archive Types
// ==================================================

export type RetentionCategory =
  | 'invoice'
  | 'contract'
  | 'correspondence'
  | 'tax_document'
  | 'bank_statement'
  | 'receipt'
  | 'other'

export interface ArchiveEntry {
  id: string
  document_id: string
  content_hash: string
  hash_algorithm: string
  signature_timestamp: string
  retention_category: RetentionCategory
  retention_years: number
  retention_expires_at: string
  archived_at: string
  archived_by_id: string | null
  is_verified: boolean
  last_verified_at: string | null
  verification_count: number
}

export interface ArchiveDocumentRequest {
  document_id: string
  retention_category: RetentionCategory
  signature_certificate?: string
  metadata?: Record<string, unknown>
}

export interface VerificationResult {
  is_valid: boolean
  document_id: string
  content_hash: string
  stored_hash: string
  hash_algorithm: string
  verified_at: string
  verification_message: string
}

export interface ArchiveStatistics {
  total_archived: number
  by_category: Record<RetentionCategory, number>
  expiring_soon: number
  expired: number
  unverified: number
  last_verification_run: string | null
  storage_size_bytes: number
}

export interface ExpiringArchive {
  id: string
  document_id: string
  document_title: string
  retention_category: RetentionCategory
  retention_expires_at: string
  days_until_expiry: number
}

// ==================================================
// Retention Settings Types
// ==================================================

export interface RetentionSetting {
  id: string
  category: RetentionCategory
  years: number
  description: string
  legal_basis: string
  is_custom: boolean
  company_id: string | null
  created_at: string
  updated_at: string
}

export interface RetentionSettingUpdate {
  years: number
  description?: string
  legal_basis?: string
}

// ==================================================
// Procedure Documentation Types
// ==================================================

export interface ProcedureDocSection {
  id: string
  title: string
  content: string
  order: number
  category: 'general' | 'user' | 'technical' | 'operation' | 'iks' | 'archiving'
}

export interface ProcedureDocVersion {
  id: string
  version_number: number
  generated_at: string
  generated_by_id: string | null
  sections: ProcedureDocSection[]
  is_current: boolean
  change_summary: string | null
}

export interface ProcedureDocumentation {
  id: string
  company_id: string
  current_version: number
  versions: ProcedureDocVersion[]
  last_generated_at: string
}

// ==================================================
// GDPdU Export Types
// ==================================================

export interface GDPdUExportOptions {
  start_date: string
  end_date: string
  include_invoices: boolean
  include_contracts: boolean
  include_bank_statements: boolean
  include_receipts: boolean
  include_document_files: boolean
  format: 'xml' | 'csv'
}

export interface GDPdUExportResult {
  export_id: string
  filename: string
  file_size_bytes: number
  record_count: number
  generated_at: string
  download_url: string
  expires_at: string
}

// ==================================================
// Tax Advisor Types
// ==================================================

export interface TaxAdvisorInvite {
  id: string
  email: string
  firm_name: string | null
  access_level: 'read' | 'read_download' | 'full'
  valid_from: string
  valid_until: string
  is_active: boolean
  created_at: string
  accepted_at: string | null
}

export interface CreateTaxAdvisorInviteRequest {
  email: string
  firm_name?: string
  access_level: 'read' | 'read_download' | 'full'
  valid_days: number
}

export interface TaxAdvisorAccessLog {
  id: string
  invite_id: string
  action: string
  resource_type: string
  resource_id: string | null
  ip_address: string
  user_agent: string
  accessed_at: string
}
