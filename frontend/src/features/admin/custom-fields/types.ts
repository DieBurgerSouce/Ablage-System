/**
 * Custom Fields Types
 *
 * TypeScript-Typen fuer benutzerdefinierte Felder.
 * Abgeleitet von Backend-Schemas (app/api/schemas/custom_fields.py).
 */

// =============================================================================
// Enums
// =============================================================================

export type FieldType =
  | 'text'
  | 'number'
  | 'date'
  | 'boolean'
  | 'dropdown'
  | 'multi_select'
  | 'lookup'

export const FIELD_TYPE_LABELS: Record<FieldType, string> = {
  text: 'Text',
  number: 'Zahl',
  date: 'Datum',
  boolean: 'Ja/Nein',
  dropdown: 'Dropdown',
  multi_select: 'Mehrfachauswahl',
  lookup: 'Verweis',
}

// =============================================================================
// Sub-Types
// =============================================================================

export interface ValidationRules {
  min_value?: number | null
  max_value?: number | null
  min_length?: number | null
  max_length?: number | null
  pattern?: string | null
}

export interface DropdownOption {
  value: string
  label: string
}

// =============================================================================
// API Request Types
// =============================================================================

export interface CustomFieldDefinitionCreate {
  name: string
  label: string
  description?: string
  field_type: FieldType
  document_type?: string | null
  required: boolean
  default_value?: string | null
  validation_rules?: ValidationRules | null
  dropdown_options?: DropdownOption[] | null
  lookup_entity?: string | null
  sort_order: number
  is_searchable: boolean
  is_filterable: boolean
}

export interface CustomFieldDefinitionUpdate {
  label?: string
  description?: string | null
  required?: boolean
  default_value?: string | null
  validation_rules?: ValidationRules | null
  dropdown_options?: DropdownOption[] | null
  sort_order?: number
  is_searchable?: boolean
  is_filterable?: boolean
  is_active?: boolean
}

// =============================================================================
// API Response Types
// =============================================================================

export interface CustomFieldDefinitionResponse {
  id: string
  name: string
  label: string
  description: string | null
  field_type: FieldType
  document_type: string | null
  required: boolean
  default_value: string | null
  validation_rules: Record<string, number | string | null> | null
  dropdown_options: DropdownOption[] | null
  lookup_entity: string | null
  sort_order: number
  is_searchable: boolean
  is_filterable: boolean
  company_id: string
  created_by: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export interface CustomFieldDefinitionListResponse {
  items: CustomFieldDefinitionResponse[]
  total: number
}

export interface CustomFieldValueSet {
  values: Record<string, string | number | boolean | string[] | null>
}

export interface CustomFieldValueResponse {
  document_id: string
  values: Record<string, string | number | boolean | string[] | null>
}

// =============================================================================
// Document Types (fuer Filter)
// =============================================================================

export const DOCUMENT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'invoice', label: 'Rechnung' },
  { value: 'contract', label: 'Vertrag' },
  { value: 'receipt', label: 'Beleg' },
  { value: 'letter', label: 'Brief' },
  { value: 'offer', label: 'Angebot' },
  { value: 'delivery_note', label: 'Lieferschein' },
  { value: 'order', label: 'Bestellung' },
  { value: 'other', label: 'Sonstige' },
]

export const LOOKUP_ENTITY_OPTIONS: { value: string; label: string }[] = [
  { value: 'business_entity', label: 'Geschaeftspartner' },
  { value: 'document', label: 'Dokument' },
  { value: 'user', label: 'Benutzer' },
  { value: 'company', label: 'Firma' },
  { value: 'tag', label: 'Tag' },
]
