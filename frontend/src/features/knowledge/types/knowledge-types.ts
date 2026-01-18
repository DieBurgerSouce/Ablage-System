/**
 * Knowledge Management TypeScript Types
 *
 * Typen fuer Notizen, Checklisten, Knowledge Links und Tags.
 */

// Enums
export type NoteType = 'general' | 'procedure' | 'faq' | 'template' | 'meeting_notes' | 'decision';
export type ContentFormat = 'markdown' | 'html' | 'plain';
export type LinkType = 'related' | 'references' | 'replaces' | 'continues' | 'contradicts' | 'explains';
export type LinkableType = 'note' | 'document' | 'entity' | 'checklist';

// =============================================================================
// Knowledge Notes
// =============================================================================

export interface KnowledgeNote {
  id: string;
  title: string;
  content: string | null;
  content_format: ContentFormat;
  note_type: NoteType;
  linked_document_id: string | null;
  linked_entity_id: string | null;
  linked_company_id: string | null;
  linked_project_id: string | null;
  parent_note_id: string | null;
  is_pinned: boolean;
  is_template: boolean;
  view_count: number;
  tags: string[];
  created_by_id: string | null;
  updated_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeNoteDetail extends KnowledgeNote {
  parent_note?: KnowledgeNote | null;
  child_notes?: KnowledgeNote[];
  links_from?: KnowledgeLink[];
  links_to?: KnowledgeLink[];
}

export interface KnowledgeNoteCreate {
  title: string;
  content?: string;
  content_format?: ContentFormat;
  note_type?: NoteType;
  linked_document_id?: string;
  linked_entity_id?: string;
  linked_company_id?: string;
  linked_project_id?: string;
  parent_note_id?: string;
  is_pinned?: boolean;
  is_template?: boolean;
  tags?: string[];
}

export interface KnowledgeNoteUpdate {
  title?: string;
  content?: string;
  content_format?: ContentFormat;
  note_type?: NoteType;
  linked_document_id?: string | null;
  linked_entity_id?: string | null;
  linked_company_id?: string | null;
  linked_project_id?: string | null;
  parent_note_id?: string | null;
  is_pinned?: boolean;
  is_template?: boolean;
  tags?: string[];
}

export interface KnowledgeNoteListParams {
  note_type?: NoteType;
  linked_document_id?: string;
  linked_entity_id?: string;
  linked_company_id?: string;
  parent_note_id?: string;
  is_pinned?: boolean;
  is_template?: boolean;
  tag?: string;
  search?: string;
  offset?: number;
  limit?: number;
}

export interface KnowledgeNoteListResponse {
  items: KnowledgeNote[];
  total: number;
  offset: number;
  limit: number;
}

// =============================================================================
// Knowledge Checklists
// =============================================================================

export interface KnowledgeChecklistItem {
  id: string;
  checklist_id: string;
  text: string;
  description: string | null;
  is_completed: boolean;
  completed_at: string | null;
  completed_by_id: string | null;
  sort_order: number;
  due_date: string | null;
}

export interface KnowledgeChecklist {
  id: string;
  title: string;
  description: string | null;
  linked_document_id: string | null;
  linked_entity_id: string | null;
  linked_company_id: string | null;
  linked_note_id: string | null;
  is_template: boolean;
  completed_at: string | null;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
  items: KnowledgeChecklistItem[];
}

export interface KnowledgeChecklistCreate {
  title: string;
  description?: string;
  linked_document_id?: string;
  linked_entity_id?: string;
  linked_company_id?: string;
  linked_note_id?: string;
  is_template?: boolean;
  items?: Array<{
    text: string;
    description?: string;
    due_date?: string;
    sort_order?: number;
  }>;
}

export interface KnowledgeChecklistUpdate {
  title?: string;
  description?: string;
  linked_document_id?: string | null;
  linked_entity_id?: string | null;
  linked_company_id?: string | null;
  linked_note_id?: string | null;
  is_template?: boolean;
}

export interface KnowledgeChecklistItemCreate {
  text: string;
  description?: string;
  due_date?: string;
  sort_order?: number;
}

export interface KnowledgeChecklistItemUpdate {
  text?: string;
  description?: string;
  is_completed?: boolean;
  due_date?: string | null;
  sort_order?: number;
}

export interface KnowledgeChecklistListParams {
  linked_document_id?: string;
  linked_entity_id?: string;
  linked_company_id?: string;
  linked_note_id?: string;
  is_template?: boolean;
  search?: string;
  offset?: number;
  limit?: number;
}

export interface KnowledgeChecklistListResponse {
  items: KnowledgeChecklist[];
  total: number;
  offset: number;
  limit: number;
}

// =============================================================================
// Knowledge Links
// =============================================================================

export interface KnowledgeLink {
  id: string;
  source_type: LinkableType;
  source_id: string;
  target_type: LinkableType;
  target_id: string;
  link_type: LinkType;
  description: string | null;
  confidence: number | null;
  is_bidirectional: boolean;
  created_by_id: string | null;
  created_at: string;
}

export interface KnowledgeLinkCreate {
  source_type: LinkableType;
  source_id: string;
  target_type: LinkableType;
  target_id: string;
  link_type?: LinkType;
  description?: string;
  confidence?: number;
  is_bidirectional?: boolean;
}

export interface KnowledgeLinkListParams {
  source_type?: LinkableType;
  source_id?: string;
  target_type?: LinkableType;
  target_id?: string;
  link_type?: LinkType;
  offset?: number;
  limit?: number;
}

export interface KnowledgeLinkListResponse {
  items: KnowledgeLink[];
  total: number;
  offset: number;
  limit: number;
}

// =============================================================================
// Knowledge Tags
// =============================================================================

export interface KnowledgeTag {
  id: string;
  name: string;
  color: string | null;
  description: string | null;
  usage_count: number;
  created_at: string;
}

export interface KnowledgeTagCreate {
  name: string;
  color?: string;
  description?: string;
}

export interface KnowledgeTagUpdate {
  name?: string;
  color?: string;
  description?: string;
}

export interface KnowledgeTagListParams {
  search?: string;
  offset?: number;
  limit?: number;
}

export interface KnowledgeTagListResponse {
  items: KnowledgeTag[];
  total: number;
  offset: number;
  limit: number;
}

// =============================================================================
// Utility Types
// =============================================================================

export const NOTE_TYPE_LABELS: Record<NoteType, string> = {
  general: 'Allgemein',
  procedure: 'Prozess/Anleitung',
  faq: 'FAQ',
  template: 'Vorlage',
  meeting_notes: 'Besprechungsnotiz',
  decision: 'Entscheidung',
};

export const LINK_TYPE_LABELS: Record<LinkType, string> = {
  related: 'Verwandt',
  references: 'Referenziert',
  replaces: 'Ersetzt',
  continues: 'Fortsetzung',
  contradicts: 'Widerspricht',
  explains: 'Erklaert',
};

export const LINKABLE_TYPE_LABELS: Record<LinkableType, string> = {
  note: 'Notiz',
  document: 'Dokument',
  entity: 'Geschaeftspartner',
  checklist: 'Checkliste',
};
