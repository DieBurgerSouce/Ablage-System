/**
 * Portal Feature Types
 *
 * TypeScript types for the customer self-service portal.
 * Matches backend API at /api/v1/portal/*
 */

// ============================================================================
// ENUMS
// ============================================================================

/** Portal user account status */
export type PortalUserStatus = 'pending' | 'active' | 'suspended' | 'deactivated';

/** Complaint status workflow */
export type ComplaintStatus =
  | 'new'
  | 'in_review'
  | 'accepted'
  | 'rejected'
  | 'resolved'
  | 'closed';

/** Complaint type classification */
export type ComplaintType =
  | 'invoice_error'
  | 'delivery_issue'
  | 'quality_issue'
  | 'payment_dispute'
  | 'other';

/** Message direction */
export type MessageDirection = 'inbound' | 'outbound';

/** Payment confirmation status */
export type PaymentConfirmationStatus = 'pending' | 'verified' | 'rejected';

/** Document processing status */
export type DocumentProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';

/** Invoice payment status */
export type InvoiceStatus = 'open' | 'partially_paid' | 'paid' | 'overdue' | 'cancelled';

/** Complaint priority */
export type ComplaintPriority = 'low' | 'normal' | 'high' | 'urgent';

// ============================================================================
// USER & AUTH TYPES
// ============================================================================

/** Portal user permissions */
export interface PortalUserPermissions {
  can_view_invoices: boolean;
  can_confirm_payments: boolean;
  can_submit_complaints: boolean;
  can_upload_documents: boolean;
  can_view_all_entity_data?: boolean;
}

/** Portal user data */
export interface PortalUser {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  position: string | null;
  entity_id: string;
  company_id: string;
  status: PortalUserStatus;
  permissions: PortalUserPermissions;
  last_login_at: string | null;
}

/** Login request */
export interface PortalLoginRequest {
  email: string;
  password: string;
  company_id: string;
}

/** Login response */
export interface PortalLoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  portal_user: PortalUser;
}

/** Account activation request */
export interface PortalActivateRequest {
  invitation_token: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

/** Account activation response */
export interface PortalActivateResponse {
  success: boolean;
  message: string;
  portal_user_id: string;
}

/** Token refresh request */
export interface PortalRefreshRequest {
  refresh_token: string;
}

/** Password change request */
export interface PortalChangePasswordRequest {
  current_password: string;
  new_password: string;
}

/** Generic success response */
export interface PortalSuccessResponse {
  success: boolean;
  message: string;
}

// ============================================================================
// INVOICE TYPES
// ============================================================================

/** Invoice data for portal view */
export interface PortalInvoice {
  id: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  amount: number;
  outstanding_amount: number;
  status: InvoiceStatus;
  currency: string;
  document_id: string | null;
  entity_name?: string;
  description?: string;
  skonto_percentage?: number;
  skonto_deadline?: string;
  skonto_amount?: number;
  dunning_level?: number;
  created_at: string;
  updated_at?: string;
}

/** Invoice summary for dashboard */
export interface PortalInvoiceSummary {
  total_count: number;
  total_amount: number;
  open_count: number;
  open_amount: number;
  paid_count: number;
  paid_amount: number;
  overdue_count: number;
  overdue_amount: number;
  currency: string;
}

/** Invoice list filter */
export interface PortalInvoiceFilter {
  status?: InvoiceStatus;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
}

/** Invoice list response */
export interface PortalInvoiceListResponse {
  items: PortalInvoice[];
  total: number;
  limit: number;
  offset: number;
}

// ============================================================================
// PAYMENT TYPES
// ============================================================================

/** Payment confirmation request */
export interface PortalPaymentConfirmRequest {
  invoice_tracking_id: string;
  payment_date: string;
  payment_amount: string;
  payment_reference?: string;
  payment_method?: string;
  attachment_ids?: string[];
  notes?: string;
}

/** Payment confirmation data */
export interface PortalPayment {
  id: string;
  invoice_tracking_id: string;
  payment_date: string;
  payment_amount: string;
  payment_reference: string | null;
  payment_method: string | null;
  status: PaymentConfirmationStatus;
  verified_at: string | null;
  rejection_reason: string | null;
  notes: string | null;
  created_at: string;
}

/** Payment confirmation response */
export interface PortalPaymentConfirmResponse {
  success: boolean;
  confirmation_id: string;
  message: string;
}

/** Payment confirmation list filter */
export interface PortalPaymentFilter {
  status?: PaymentConfirmationStatus;
  invoice_tracking_id?: string;
  limit?: number;
  offset?: number;
}

/** Payment confirmation list response */
export interface PortalPaymentListResponse {
  items: PortalPayment[];
  total: number;
  limit: number;
  offset: number;
}

// ============================================================================
// COMPLAINT TYPES
// ============================================================================

/** Complaint type info for UI */
export interface ComplaintTypeInfo {
  value: ComplaintType;
  label: string;
  description?: string;
}

/** Complaint creation request */
export interface PortalComplaintCreateRequest {
  complaint_type: ComplaintType;
  subject: string;
  description: string;
  document_id?: string;
  invoice_tracking_id?: string;
  priority?: ComplaintPriority;
  metadata?: Record<string, unknown>;
}

/** Complaint creation response */
export interface PortalComplaintCreateResponse {
  success: boolean;
  complaint_id: string;
  reference_number: string;
  message: string;
}

/** Add info to complaint request */
export interface PortalComplaintAddInfoRequest {
  additional_info: string;
  attachment_ids?: string[];
}

/** Complaint data */
export interface PortalComplaint {
  id: string;
  reference_number: string;
  complaint_type: ComplaintType;
  subject: string;
  description: string;
  status: ComplaintStatus;
  priority: ComplaintPriority;
  document_id: string | null;
  invoice_tracking_id: string | null;
  resolution: string | null;
  created_at: string;
  updated_at: string;
  first_response_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  metadata?: Record<string, unknown>;
}

/** Complaint list filter */
export interface PortalComplaintFilter {
  status?: ComplaintStatus;
  complaint_type?: ComplaintType;
  limit?: number;
  offset?: number;
}

/** Complaint list response */
export interface PortalComplaintListResponse {
  items: PortalComplaint[];
  total: number;
  limit: number;
  offset: number;
}

/** Complaint summary for dashboard */
export interface PortalComplaintSummary {
  total_count: number;
  new_count: number;
  in_review_count: number;
  resolved_count: number;
  avg_resolution_time_hours?: number;
}

// ============================================================================
// DOCUMENT TYPES
// ============================================================================

/** Allowed file types info */
export interface AllowedFileTypesInfo {
  types: string[];
  max_file_size: number;
  max_file_size_mb: number;
}

/** Document upload response */
export interface PortalDocumentUploadResponse {
  success: boolean;
  document_id: string;
  filename: string;
  file_size: number;
  message: string;
}

/** Portal document data */
export interface PortalDocument {
  id: string;
  original_filename: string;
  file_size: number | null;
  mime_type: string | null;
  description: string | null;
  document_type: string | null;
  processing_status: DocumentProcessingStatus;
  processed_at: string | null;
  complaint_id: string | null;
  message_id: string | null;
  document_id: string | null;
  created_at: string;
}

/** Document list filter */
export interface PortalDocumentFilter {
  complaint_id?: string;
  document_type?: string;
  limit?: number;
  offset?: number;
}

/** Document list response */
export interface PortalDocumentListResponse {
  items: PortalDocument[];
  total: number;
  limit: number;
  offset: number;
}

// ============================================================================
// MESSAGE TYPES
// ============================================================================

/** Message send request */
export interface PortalMessageSendRequest {
  content: string;
  subject?: string;
  complaint_id?: string;
  attachments?: string[];
}

/** Message send response */
export interface PortalMessageSendResponse {
  success: boolean;
  message_id: string;
  message: string;
}

/** Portal message data */
export interface PortalMessage {
  id: string;
  direction: MessageDirection;
  subject: string | null;
  content: string;
  attachments: string[];
  is_read: boolean;
  read_at: string | null;
  complaint_id: string | null;
  portal_user_id: string | null;
  internal_user_id: string | null;
  created_at: string;
  // UI helper fields
  sender_name?: string;
  sender_type?: 'customer' | 'company';
}

/** Message list filter */
export interface PortalMessageFilter {
  complaint_id?: string;
  direction?: MessageDirection;
  unread_only?: boolean;
  limit?: number;
  offset?: number;
}

/** Message list response */
export interface PortalMessageListResponse {
  items: PortalMessage[];
  total: number;
  limit: number;
  offset: number;
}

/** Conversation response */
export interface PortalConversationResponse {
  messages: PortalMessage[];
}

/** Message summary for dashboard */
export interface PortalMessageSummary {
  total_count: number;
  unread_count: number;
  inbound_count: number;
  outbound_count: number;
  last_message_at: string | null;
}

/** Unread count response */
export interface PortalUnreadCountResponse {
  unread_count: number;
}

/** Mark all read response */
export interface PortalMarkAllReadResponse {
  success: boolean;
  marked_count: number;
}

// ============================================================================
// GENERIC TYPES
// ============================================================================

/** Paginated list params */
export interface PaginationParams {
  limit?: number;
  offset?: number;
}

/** Paginated response base */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** API error response */
export interface PortalApiError {
  detail: string;
  status_code?: number;
}

// ============================================================================
// UI CONSTANTS (Shared across components to avoid duplication)
// ============================================================================

/** Invoice status labels in German */
export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  open: 'Offen',
  partially_paid: 'Teilweise bezahlt',
  paid: 'Bezahlt',
  overdue: 'Überfällig',
  cancelled: 'Storniert',
};

/** Invoice status color classes for Badge component */
export const INVOICE_STATUS_COLORS: Record<InvoiceStatus, string> = {
  open: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  partially_paid: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  paid: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  overdue: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  cancelled: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
};

/** Payment confirmation status labels in German */
export const PAYMENT_STATUS_LABELS: Record<PaymentConfirmationStatus, string> = {
  pending: 'Ausstehend',
  verified: 'Bestätigt',
  rejected: 'Abgelehnt',
};

/** Payment confirmation status color classes */
export const PAYMENT_STATUS_COLORS: Record<PaymentConfirmationStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  verified: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
};

/** Complaint status labels in German */
export const COMPLAINT_STATUS_LABELS: Record<ComplaintStatus, string> = {
  new: 'Neu',
  in_review: 'In Bearbeitung',
  accepted: 'Akzeptiert',
  rejected: 'Abgelehnt',
  resolved: 'Gelöst',
  closed: 'Geschlossen',
};

/** Filter options for invoice status (includes 'all' option) */
export const INVOICE_STATUS_OPTIONS: { value: InvoiceStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Status' },
  { value: 'open', label: 'Offen' },
  { value: 'partially_paid', label: 'Teilweise bezahlt' },
  { value: 'paid', label: 'Bezahlt' },
  { value: 'overdue', label: 'Überfällig' },
];
