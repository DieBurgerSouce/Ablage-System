/**
 * Portal Feature
 *
 * Customer self-service portal module with separate authentication
 * and isolated functionality for invoices, payments, complaints,
 * documents, and messaging.
 */

// Types
export * from './types';

// API
export {
  portalApi,
  getPortalToken,
  getPortalRefreshToken,
  getPortalUser,
  getPortalCompanyId,
  setPortalAuth,
  clearPortalAuth,
  isPortalAuthenticated,
} from './api/portal-api';

// Query Hooks
export {
  // Query Keys
  portalQueryKeys,
  // Toast Messages
  PORTAL_TOAST_MESSAGES,
  // Auth Hooks
  usePortalLogin,
  usePortalLogout,
  usePortalActivate,
  usePortalChangePassword,
  usePortalUser,
  usePortalAuth,
  // Invoice Hooks
  usePortalInvoices,
  usePortalInvoiceSummary,
  usePortalOpenInvoices,
  usePortalInvoiceDetail,
  // Payment Hooks
  usePortalConfirmPayment,
  usePortalPayments,
  usePortalPaymentDetail,
  usePortalCancelPayment,
  // Complaint Hooks
  usePortalComplaintTypes,
  usePortalCreateComplaint,
  usePortalComplaints,
  usePortalComplaintSummary,
  usePortalComplaintDetail,
  usePortalAddComplaintInfo,
  // Document Hooks
  usePortalAllowedFileTypes,
  usePortalUploadDocument,
  usePortalDocuments,
  usePortalDocumentDetail,
  usePortalDeleteDocument,
  // Message Hooks
  usePortalSendMessage,
  usePortalMessages,
  usePortalConversation,
  usePortalMessageSummary,
  usePortalUnreadCount,
  usePortalMarkMessageRead,
  usePortalMarkAllMessagesRead,
  // Utility Hooks
  usePrefetchPortalDashboard,
} from './hooks/use-portal-queries';

// Components
export {
  PortalLayout,
  PortalLoginPage,
  PortalDashboard,
  InvoiceListPage,
  InvoiceDetailPage,
  PortalUploadPage,
} from './components';
