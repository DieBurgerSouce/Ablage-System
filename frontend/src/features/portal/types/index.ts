/**
 * Portal Types
 *
 * TypeScript-Definitionen fuer das Kundenportal.
 */

// ============================================================================
// USER & AUTH TYPES
// ============================================================================

export interface PortalUser {
    id: string;
    email: string;
    first_name: string | null;
    last_name: string | null;
    phone: string | null;
    position: string | null;
    entity_id: string;
    company_id: string;
    status: 'active' | 'inactive' | 'pending' | 'locked';
    permissions: PortalPermissions;
    last_login_at: string | null;
}

export interface PortalPermissions {
    can_view_invoices: boolean;
    can_confirm_payments: boolean;
    can_submit_complaints: boolean;
    can_upload_documents: boolean;
    can_view_all_entity_data?: boolean;
}

export interface PortalLoginRequest {
    email: string;
    password: string;
    company_id: string;
}

export interface PortalLoginResponse {
    access_token: string;
    refresh_token: string;
    token_type: string;
    expires_in: number;
    portal_user: PortalUser;
}

export interface PortalActivateRequest {
    invitation_token: string;
    password: string;
    first_name?: string;
    last_name?: string;
}

export interface PortalActivateResponse {
    success: boolean;
    message: string;
    portal_user_id: string;
}

export interface PortalRefreshRequest {
    refresh_token: string;
}

export interface PortalChangePasswordRequest {
    current_password: string;
    new_password: string;
}

export interface PortalSuccessResponse {
    success: boolean;
    message?: string;
}

// ============================================================================
// INVOICE TYPES
// ============================================================================

export interface PortalInvoice {
    id: string;
    invoice_number: string;
    invoice_date: string;
    due_date: string;
    amount: number;
    currency: string;
    status: 'open' | 'paid' | 'overdue' | 'partially_paid' | 'cancelled';
    outstanding_amount: number;
    payment_terms: string | null;
    skonto_deadline?: string;
    skonto_percentage?: number;
    skonto_amount?: number;
}

export interface PortalInvoiceSummary {
    total_invoices: number;
    open_invoices: number;
    overdue_invoices: number;
    total_outstanding: number;
    currency: string;
}

export interface PortalInvoiceFilter {
    status?: string;
    from_date?: string;
    to_date?: string;
    limit?: number;
    offset?: number;
}

export interface PortalInvoiceListResponse {
    items: PortalInvoice[];
    total: number;
    limit: number;
    offset: number;
}

// ============================================================================
// PAYMENT TYPES
// ============================================================================

export interface PortalPayment {
    id: string;
    invoice_tracking_id: string;
    amount: number;
    currency: string;
    payment_date: string;
    payment_method: string;
    reference: string | null;
    status: 'pending' | 'confirmed' | 'rejected';
    created_at: string;
}

export interface PortalPaymentConfirmRequest {
    invoice_tracking_id: string;
    amount: number;
    payment_date: string;
    payment_method: string;
    reference?: string;
}

export interface PortalPaymentConfirmResponse {
    success: boolean;
    confirmation_id: string;
    message: string;
}

export interface PortalPaymentFilter {
    status?: string;
    invoice_tracking_id?: string;
    limit?: number;
    offset?: number;
}

export interface PortalPaymentListResponse {
    items: PortalPayment[];
    total: number;
    limit: number;
    offset: number;
}

// ============================================================================
// COMPLAINT TYPES
// ============================================================================

export interface PortalComplaint {
    id: string;
    reference_number: string;
    complaint_type: string;
    subject: string;
    description: string;
    status: 'submitted' | 'in_progress' | 'resolved' | 'closed' | 'rejected';
    priority: 'low' | 'normal' | 'high' | 'urgent';
    created_at: string;
    updated_at: string;
    document_id?: string;
    invoice_tracking_id?: string;
    resolution?: string;
}

export interface ComplaintTypeInfo {
    value: string;
    label: string;
    description: string;
}

export interface PortalComplaintCreateRequest {
    complaint_type: string;
    subject: string;
    description: string;
    document_id?: string;
    invoice_tracking_id?: string;
    priority?: string;
    metadata?: Record<string, unknown>;
}

export interface PortalComplaintCreateResponse {
    success: boolean;
    complaint_id: string;
    reference_number: string;
    message: string;
}

export interface PortalComplaintAddInfoRequest {
    additional_info: string;
    attachment_ids?: string[];
}

export interface PortalComplaintFilter {
    status?: string;
    complaint_type?: string;
    limit?: number;
    offset?: number;
}

export interface PortalComplaintListResponse {
    items: PortalComplaint[];
    total: number;
    limit: number;
    offset: number;
}

export interface PortalComplaintSummary {
    total_complaints: number;
    open_complaints: number;
    resolved_complaints: number;
}

// ============================================================================
// DOCUMENT TYPES
// ============================================================================

export interface PortalDocument {
    id: string;
    original_filename: string;
    file_size: number;
    content_type: string;
    document_type: string | null;
    description: string | null;
    status: 'pending' | 'processing' | 'processed' | 'error';
    uploaded_at: string;
    complaint_id?: string;
}

export interface PortalDocumentUploadResponse {
    success: boolean;
    document_id: string;
    filename: string;
    file_size: number;
    message: string;
}

export interface PortalDocumentFilter {
    complaint_id?: string;
    document_type?: string;
    limit?: number;
    offset?: number;
}

export interface PortalDocumentListResponse {
    items: PortalDocument[];
    total: number;
    limit: number;
    offset: number;
}

export interface AllowedFileTypesInfo {
    types: string[];
    max_file_size: number;
    max_file_size_mb: number;
}

// ============================================================================
// MESSAGE TYPES
// ============================================================================

export interface PortalMessage {
    id: string;
    content: string;
    subject: string | null;
    direction: 'inbound' | 'outbound';
    is_read: boolean;
    sent_at: string;
    sender_name: string;
    attachments: string[];
    complaint_id?: string;
}

export interface PortalMessageSendRequest {
    content: string;
    subject?: string;
    complaint_id?: string;
    attachments?: string[];
}

export interface PortalMessageSendResponse {
    success: boolean;
    message_id: string;
    message: string;
}

export interface PortalMessageFilter {
    complaint_id?: string;
    direction?: 'inbound' | 'outbound';
    unread_only?: boolean;
    limit?: number;
    offset?: number;
}

export interface PortalMessageListResponse {
    items: PortalMessage[];
    total: number;
    limit: number;
    offset: number;
}

export interface PortalConversationResponse {
    messages: PortalMessage[];
}

export interface PortalMessageSummary {
    total_messages: number;
    unread_count: number;
    last_message_at: string | null;
}

export interface PortalUnreadCountResponse {
    unread_count: number;
}

export interface PortalMarkAllReadResponse {
    success: boolean;
    marked_count: number;
}

// ============================================================================
// GENERIC TYPES
// ============================================================================

export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    limit: number;
    offset: number;
}
