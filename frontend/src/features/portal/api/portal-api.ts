/**
 * Portal API Client
 *
 * Handles all API calls for the customer self-service portal.
 * Backend Router: /api/v1/portal
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios';
import type {
  PortalLoginRequest,
  PortalLoginResponse,
  PortalActivateRequest,
  PortalActivateResponse,
  PortalRefreshRequest,
  PortalChangePasswordRequest,
  PortalSuccessResponse,
  PortalUser,
  PortalInvoice,
  PortalInvoiceSummary,
  PortalInvoiceFilter,
  PortalInvoiceListResponse,
  PortalPaymentConfirmRequest,
  PortalPaymentConfirmResponse,
  PortalPayment,
  PortalPaymentFilter,
  PortalPaymentListResponse,
  PortalComplaintCreateRequest,
  PortalComplaintCreateResponse,
  PortalComplaintAddInfoRequest,
  PortalComplaint,
  PortalComplaintFilter,
  PortalComplaintListResponse,
  PortalComplaintSummary,
  ComplaintTypeInfo,
  PortalDocumentUploadResponse,
  PortalDocument,
  PortalDocumentFilter,
  PortalDocumentListResponse,
  AllowedFileTypesInfo,
  PortalMessageSendRequest,
  PortalMessageSendResponse,
  PortalMessage,
  PortalMessageFilter,
  PortalMessageListResponse,
  PortalConversationResponse,
  PortalMessageSummary,
  PortalUnreadCountResponse,
  PortalMarkAllReadResponse,
} from '../types';

// ============================================================================
// PORTAL AUTH TOKEN MANAGEMENT
// ============================================================================

const PORTAL_TOKEN_KEY = 'portal_auth_token';
const PORTAL_REFRESH_TOKEN_KEY = 'portal_refresh_token';
const PORTAL_USER_KEY = 'portal_user';
const PORTAL_COMPANY_ID_KEY = 'portal_company_id';

/**
 * Get stored portal access token
 */
export function getPortalToken(): string | null {
  return localStorage.getItem(PORTAL_TOKEN_KEY);
}

/**
 * Get stored portal refresh token
 */
export function getPortalRefreshToken(): string | null {
  return localStorage.getItem(PORTAL_REFRESH_TOKEN_KEY);
}

/**
 * Get stored portal user
 */
export function getPortalUser(): PortalUser | null {
  const userJson = localStorage.getItem(PORTAL_USER_KEY);
  if (!userJson) return null;
  try {
    return JSON.parse(userJson) as PortalUser;
  } catch {
    return null;
  }
}

/**
 * Get stored company ID for portal
 */
export function getPortalCompanyId(): string | null {
  return localStorage.getItem(PORTAL_COMPANY_ID_KEY);
}

/**
 * Store portal auth data
 */
export function setPortalAuth(
  accessToken: string,
  refreshToken: string,
  user: PortalUser,
  companyId: string
): void {
  localStorage.setItem(PORTAL_TOKEN_KEY, accessToken);
  localStorage.setItem(PORTAL_REFRESH_TOKEN_KEY, refreshToken);
  localStorage.setItem(PORTAL_USER_KEY, JSON.stringify(user));
  localStorage.setItem(PORTAL_COMPANY_ID_KEY, companyId);
}

/**
 * Clear portal auth data
 */
export function clearPortalAuth(): void {
  localStorage.removeItem(PORTAL_TOKEN_KEY);
  localStorage.removeItem(PORTAL_REFRESH_TOKEN_KEY);
  localStorage.removeItem(PORTAL_USER_KEY);
  localStorage.removeItem(PORTAL_COMPANY_ID_KEY);
}

/**
 * Check if portal user is authenticated
 */
export function isPortalAuthenticated(): boolean {
  return !!getPortalToken();
}

// ============================================================================
// PORTAL API CLIENT
// ============================================================================

// API Base URL - portal has its own prefix
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';
const PORTAL_BASE = '/portal';

/**
 * Create portal-specific axios instance
 */
function createPortalClient(): AxiosInstance {
  const client = axios.create({
    baseURL: API_BASE_URL,
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: 10000,
  });

  // Request interceptor - add portal auth token
  client.interceptors.request.use(
    (config) => {
      const token = getPortalToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error) => Promise.reject(error)
  );

  // Response interceptor - handle auth errors
  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const originalRequest = error.config;

      // Handle 401 - try token refresh
      if (
        error.response?.status === 401 &&
        originalRequest &&
        !originalRequest.url?.includes('/auth/')
      ) {
        const refreshToken = getPortalRefreshToken();
        if (refreshToken) {
          try {
            const response = await portalApi.auth.refresh({ refresh_token: refreshToken });
            setPortalAuth(
              response.access_token,
              response.refresh_token,
              response.portal_user,
              response.portal_user.company_id
            );
            // Retry original request
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${response.access_token}`;
            }
            return client(originalRequest);
          } catch {
            // Refresh failed - clear auth
            clearPortalAuth();
            window.dispatchEvent(new CustomEvent('portal-session-expired'));
          }
        } else {
          clearPortalAuth();
          window.dispatchEvent(new CustomEvent('portal-session-expired'));
        }
      }

      return Promise.reject(error);
    }
  );

  return client;
}

const portalClient = createPortalClient();

/**
 * Extract data from axios response
 */
function extractData<T>(response: { data: T }): T {
  return response.data;
}

/**
 * Build query string from filter params
 */
function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, String(value));
    }
  });
  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

// ============================================================================
// PORTAL API
// ============================================================================

export const portalApi = {
  // ==========================================================================
  // AUTH
  // ==========================================================================
  auth: {
    /**
     * Login to portal
     */
    async login(data: PortalLoginRequest): Promise<PortalLoginResponse> {
      const response = await portalClient.post<PortalLoginResponse>(
        `${PORTAL_BASE}/auth/login`,
        data
      );
      const result = extractData(response);
      // Store auth data
      setPortalAuth(
        result.access_token,
        result.refresh_token,
        result.portal_user,
        data.company_id
      );
      return result;
    },

    /**
     * Logout from portal
     */
    async logout(): Promise<PortalSuccessResponse> {
      try {
        const response = await portalClient.post<PortalSuccessResponse>(
          `${PORTAL_BASE}/auth/logout`
        );
        return extractData(response);
      } finally {
        clearPortalAuth();
      }
    },

    /**
     * Refresh access token
     */
    async refresh(data: PortalRefreshRequest): Promise<PortalLoginResponse> {
      const response = await portalClient.post<PortalLoginResponse>(
        `${PORTAL_BASE}/auth/refresh`,
        data
      );
      return extractData(response);
    },

    /**
     * Activate account with invitation token
     */
    async activate(data: PortalActivateRequest): Promise<PortalActivateResponse> {
      const response = await portalClient.post<PortalActivateResponse>(
        `${PORTAL_BASE}/auth/activate`,
        data
      );
      return extractData(response);
    },

    /**
     * Change password
     */
    async changePassword(data: PortalChangePasswordRequest): Promise<PortalSuccessResponse> {
      const response = await portalClient.post<PortalSuccessResponse>(
        `${PORTAL_BASE}/auth/change-password`,
        data
      );
      return extractData(response);
    },

    /**
     * Get current user profile
     */
    async getMe(): Promise<PortalUser> {
      const response = await portalClient.get<PortalUser>(`${PORTAL_BASE}/auth/me`);
      return extractData(response);
    },
  },

  // ==========================================================================
  // INVOICES
  // ==========================================================================
  invoices: {
    /**
     * List invoices with filters
     */
    async list(filter?: PortalInvoiceFilter): Promise<PortalInvoiceListResponse> {
      const qs = buildQueryString({
        status: filter?.status,
        from_date: filter?.from_date,
        to_date: filter?.to_date,
        limit: filter?.limit ?? 50,
        offset: filter?.offset ?? 0,
      });
      const response = await portalClient.get<PortalInvoiceListResponse>(
        `${PORTAL_BASE}/invoices${qs}`
      );
      return extractData(response);
    },

    /**
     * Get invoice summary for dashboard
     */
    async getSummary(): Promise<PortalInvoiceSummary> {
      const response = await portalClient.get<PortalInvoiceSummary>(
        `${PORTAL_BASE}/invoices/summary`
      );
      return extractData(response);
    },

    /**
     * Get open invoices
     */
    async getOpen(): Promise<{ items: PortalInvoice[] }> {
      const response = await portalClient.get<{ items: PortalInvoice[] }>(
        `${PORTAL_BASE}/invoices/open`
      );
      return extractData(response);
    },

    /**
     * Get invoice detail
     */
    async getDetail(invoiceId: string): Promise<PortalInvoice> {
      const response = await portalClient.get<PortalInvoice>(
        `${PORTAL_BASE}/invoices/${invoiceId}`
      );
      return extractData(response);
    },

    /**
     * Download invoice PDF
     * Returns blob for file download
     */
    async downloadPdf(invoiceId: string): Promise<Blob> {
      const response = await portalClient.get<Blob>(
        `${PORTAL_BASE}/invoices/${invoiceId}/download`,
        {
          responseType: 'blob',
        }
      );
      return extractData(response);
    },
  },

  // ==========================================================================
  // PAYMENTS
  // ==========================================================================
  payments: {
    /**
     * Confirm a payment
     */
    async confirmPayment(data: PortalPaymentConfirmRequest): Promise<PortalPaymentConfirmResponse> {
      const response = await portalClient.post<PortalPaymentConfirmResponse>(
        `${PORTAL_BASE}/payments/confirm`,
        data
      );
      return extractData(response);
    },

    /**
     * List payment confirmations
     */
    async list(filter?: PortalPaymentFilter): Promise<PortalPaymentListResponse> {
      const qs = buildQueryString({
        status: filter?.status,
        invoice_tracking_id: filter?.invoice_tracking_id,
        limit: filter?.limit ?? 50,
        offset: filter?.offset ?? 0,
      });
      const response = await portalClient.get<PortalPaymentListResponse>(
        `${PORTAL_BASE}/payments/confirmations${qs}`
      );
      return extractData(response);
    },

    /**
     * Get payment confirmation detail
     */
    async getDetail(confirmationId: string): Promise<PortalPayment> {
      const response = await portalClient.get<PortalPayment>(
        `${PORTAL_BASE}/payments/confirmations/${confirmationId}`
      );
      return extractData(response);
    },

    /**
     * Cancel a pending payment confirmation
     */
    async cancel(confirmationId: string): Promise<PortalSuccessResponse> {
      const response = await portalClient.delete<PortalSuccessResponse>(
        `${PORTAL_BASE}/payments/confirmations/${confirmationId}`
      );
      return extractData(response);
    },
  },

  // ==========================================================================
  // COMPLAINTS
  // ==========================================================================
  complaints: {
    /**
     * Get available complaint types
     */
    async getTypes(): Promise<{ types: ComplaintTypeInfo[] }> {
      const response = await portalClient.get<{ types: ComplaintTypeInfo[] }>(
        `${PORTAL_BASE}/complaints/types`
      );
      return extractData(response);
    },

    /**
     * Create a new complaint
     */
    async create(data: PortalComplaintCreateRequest): Promise<PortalComplaintCreateResponse> {
      const response = await portalClient.post<PortalComplaintCreateResponse>(
        `${PORTAL_BASE}/complaints`,
        data
      );
      return extractData(response);
    },

    /**
     * List complaints with filters
     */
    async list(filter?: PortalComplaintFilter): Promise<PortalComplaintListResponse> {
      const qs = buildQueryString({
        status: filter?.status,
        complaint_type: filter?.complaint_type,
        limit: filter?.limit ?? 50,
        offset: filter?.offset ?? 0,
      });
      const response = await portalClient.get<PortalComplaintListResponse>(
        `${PORTAL_BASE}/complaints${qs}`
      );
      return extractData(response);
    },

    /**
     * Get complaint summary for dashboard
     */
    async getSummary(): Promise<PortalComplaintSummary> {
      const response = await portalClient.get<PortalComplaintSummary>(
        `${PORTAL_BASE}/complaints/summary`
      );
      return extractData(response);
    },

    /**
     * Get complaint detail
     */
    async getDetail(complaintId: string): Promise<PortalComplaint> {
      const response = await portalClient.get<PortalComplaint>(
        `${PORTAL_BASE}/complaints/${complaintId}`
      );
      return extractData(response);
    },

    /**
     * Add additional info to a complaint
     */
    async addInfo(
      complaintId: string,
      data: PortalComplaintAddInfoRequest
    ): Promise<PortalSuccessResponse> {
      const response = await portalClient.post<PortalSuccessResponse>(
        `${PORTAL_BASE}/complaints/${complaintId}/info`,
        data
      );
      return extractData(response);
    },
  },

  // ==========================================================================
  // DOCUMENTS
  // ==========================================================================
  documents: {
    /**
     * Get allowed file types for upload
     */
    async getAllowedTypes(): Promise<AllowedFileTypesInfo> {
      const response = await portalClient.get<AllowedFileTypesInfo>(
        `${PORTAL_BASE}/documents/allowed-types`
      );
      return extractData(response);
    },

    /**
     * Upload a document
     */
    async upload(
      file: File,
      options?: {
        description?: string;
        document_type?: string;
        complaint_id?: string;
        message_id?: string;
      }
    ): Promise<PortalDocumentUploadResponse> {
      const formData = new FormData();
      formData.append('file', file);
      if (options?.description) {
        formData.append('description', options.description);
      }
      if (options?.document_type) {
        formData.append('document_type', options.document_type);
      }
      if (options?.complaint_id) {
        formData.append('complaint_id', options.complaint_id);
      }
      if (options?.message_id) {
        formData.append('message_id', options.message_id);
      }

      const response = await portalClient.post<PortalDocumentUploadResponse>(
        `${PORTAL_BASE}/documents/upload`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );
      return extractData(response);
    },

    /**
     * List uploaded documents
     */
    async list(filter?: PortalDocumentFilter): Promise<PortalDocumentListResponse> {
      const qs = buildQueryString({
        complaint_id: filter?.complaint_id,
        document_type: filter?.document_type,
        limit: filter?.limit ?? 50,
        offset: filter?.offset ?? 0,
      });
      const response = await portalClient.get<PortalDocumentListResponse>(
        `${PORTAL_BASE}/documents${qs}`
      );
      return extractData(response);
    },

    /**
     * Get document detail
     */
    async getDetail(documentId: string): Promise<PortalDocument> {
      const response = await portalClient.get<PortalDocument>(
        `${PORTAL_BASE}/documents/${documentId}`
      );
      return extractData(response);
    },

    /**
     * Download a document
     * Returns blob for file download
     */
    async download(documentId: string): Promise<Blob> {
      const response = await portalClient.get<Blob>(
        `${PORTAL_BASE}/documents/${documentId}/download`,
        {
          responseType: 'blob',
        }
      );
      return extractData(response);
    },

    /**
     * Delete an uploaded document
     */
    async delete(documentId: string): Promise<PortalSuccessResponse> {
      const response = await portalClient.delete<PortalSuccessResponse>(
        `${PORTAL_BASE}/documents/${documentId}`
      );
      return extractData(response);
    },
  },

  // ==========================================================================
  // MESSAGES
  // ==========================================================================
  messages: {
    /**
     * Send a message
     */
    async send(data: PortalMessageSendRequest): Promise<PortalMessageSendResponse> {
      const response = await portalClient.post<PortalMessageSendResponse>(
        `${PORTAL_BASE}/messages`,
        data
      );
      return extractData(response);
    },

    /**
     * List messages with filters
     */
    async list(filter?: PortalMessageFilter): Promise<PortalMessageListResponse> {
      const qs = buildQueryString({
        complaint_id: filter?.complaint_id,
        direction: filter?.direction,
        unread_only: filter?.unread_only,
        limit: filter?.limit ?? 50,
        offset: filter?.offset ?? 0,
      });
      const response = await portalClient.get<PortalMessageListResponse>(
        `${PORTAL_BASE}/messages${qs}`
      );
      return extractData(response);
    },

    /**
     * Get conversation (chronological messages)
     */
    async getConversation(
      complaintId?: string,
      limit = 100
    ): Promise<PortalConversationResponse> {
      const qs = buildQueryString({
        complaint_id: complaintId,
        limit,
      });
      const response = await portalClient.get<PortalConversationResponse>(
        `${PORTAL_BASE}/messages/conversation${qs}`
      );
      return extractData(response);
    },

    /**
     * Get message summary for dashboard
     */
    async getSummary(): Promise<PortalMessageSummary> {
      const response = await portalClient.get<PortalMessageSummary>(
        `${PORTAL_BASE}/messages/summary`
      );
      return extractData(response);
    },

    /**
     * Get unread message count
     */
    async getUnreadCount(): Promise<PortalUnreadCountResponse> {
      const response = await portalClient.get<PortalUnreadCountResponse>(
        `${PORTAL_BASE}/messages/unread-count`
      );
      return extractData(response);
    },

    /**
     * Mark a message as read
     */
    async markRead(messageId: string): Promise<PortalSuccessResponse> {
      const response = await portalClient.post<PortalSuccessResponse>(
        `${PORTAL_BASE}/messages/${messageId}/read`
      );
      return extractData(response);
    },

    /**
     * Mark all messages as read
     */
    async markAllRead(): Promise<PortalMarkAllReadResponse> {
      const response = await portalClient.post<PortalMarkAllReadResponse>(
        `${PORTAL_BASE}/messages/mark-all-read`
      );
      return extractData(response);
    },
  },
};

export default portalApi;
