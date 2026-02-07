/**
 * Portal TanStack Query Hooks
 *
 * Zentrale Query Hooks fuer das Kundenportal.
 * Konsistente Query-Keys und wiederverwendbare Hooks.
 *
 * Alle Mutations beinhalten deutsche Toast-Messages fuer User-Feedback.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/use-toast';
import {
  portalApi,
  isPortalAuthenticated,
  getPortalUser,
  clearPortalAuth,
} from '../api/portal-api';
import type {
  PortalLoginRequest,
  PortalActivateRequest,
  PortalChangePasswordRequest,
  PortalInvoiceFilter,
  PortalPaymentConfirmRequest,
  PortalPaymentFilter,
  PortalComplaintCreateRequest,
  PortalComplaintFilter,
  PortalComplaintAddInfoRequest,
  PortalDocumentFilter,
  PortalMessageSendRequest,
  PortalMessageFilter,
  ComplaintStatus,
  ComplaintType,
  PaymentConfirmationStatus,
} from '../types';

// ============================================================================
// STALE TIME CONFIGURATION
// ============================================================================

const STALE_TIMES = {
  user: 5 * 60 * 1000, // 5 Minuten
  invoices: 2 * 60 * 1000, // 2 Minuten - Rechnungen können sich ändern
  invoiceSummary: 2 * 60 * 1000, // 2 Minuten
  payments: 30 * 1000, // 30 Sekunden - Zahlungen können schnell kommen
  complaints: 60 * 1000, // 1 Minute
  complaintTypes: 30 * 60 * 1000, // 30 Minuten - aendert sich selten
  documents: 60 * 1000, // 1 Minute
  documentTypes: 30 * 60 * 1000, // 30 Minuten
  messages: 30 * 1000, // 30 Sekunden - Nachrichten kommen schnell
  unreadCount: 30 * 1000, // 30 Sekunden
} as const;

// ============================================================================
// QUERY KEYS
// ============================================================================

export const portalQueryKeys = {
  all: ['portal'] as const,

  // User/Auth
  user: () => [...portalQueryKeys.all, 'user'] as const,
  me: () => [...portalQueryKeys.user(), 'me'] as const,

  // Invoices
  invoices: () => [...portalQueryKeys.all, 'invoices'] as const,
  invoiceList: (filter?: PortalInvoiceFilter) =>
    [...portalQueryKeys.invoices(), 'list', filter] as const,
  invoiceSummary: () => [...portalQueryKeys.invoices(), 'summary'] as const,
  invoiceOpen: () => [...portalQueryKeys.invoices(), 'open'] as const,
  invoiceDetail: (id: string) =>
    [...portalQueryKeys.invoices(), 'detail', id] as const,

  // Payments
  payments: () => [...portalQueryKeys.all, 'payments'] as const,
  paymentList: (filter?: PortalPaymentFilter) =>
    [...portalQueryKeys.payments(), 'list', filter] as const,
  paymentDetail: (id: string) =>
    [...portalQueryKeys.payments(), 'detail', id] as const,

  // Complaints
  complaints: () => [...portalQueryKeys.all, 'complaints'] as const,
  complaintTypes: () => [...portalQueryKeys.complaints(), 'types'] as const,
  complaintList: (filter?: PortalComplaintFilter) =>
    [...portalQueryKeys.complaints(), 'list', filter] as const,
  complaintSummary: () => [...portalQueryKeys.complaints(), 'summary'] as const,
  complaintDetail: (id: string) =>
    [...portalQueryKeys.complaints(), 'detail', id] as const,

  // Documents
  documents: () => [...portalQueryKeys.all, 'documents'] as const,
  documentTypes: () => [...portalQueryKeys.documents(), 'types'] as const,
  documentList: (filter?: PortalDocumentFilter) =>
    [...portalQueryKeys.documents(), 'list', filter] as const,
  documentDetail: (id: string) =>
    [...portalQueryKeys.documents(), 'detail', id] as const,

  // Messages
  messages: () => [...portalQueryKeys.all, 'messages'] as const,
  messageList: (filter?: PortalMessageFilter) =>
    [...portalQueryKeys.messages(), 'list', filter] as const,
  messageSummary: () => [...portalQueryKeys.messages(), 'summary'] as const,
  messageConversation: (complaintId?: string) =>
    [...portalQueryKeys.messages(), 'conversation', complaintId] as const,
  messageUnreadCount: () =>
    [...portalQueryKeys.messages(), 'unread-count'] as const,
};

// ============================================================================
// TOAST MESSAGES (German)
// ============================================================================

export const PORTAL_TOAST_MESSAGES = {
  auth: {
    loginSuccess: 'Erfolgreich angemeldet',
    loginError: 'Anmeldung fehlgeschlagen',
    logoutSuccess: 'Erfolgreich abgemeldet',
    activateSuccess: 'Account erfolgreich aktiviert',
    activateError: 'Aktivierung fehlgeschlagen',
    passwordChangeSuccess: 'Passwort erfolgreich geändert',
    passwordChangeError: 'Passwortaenderung fehlgeschlagen',
  },
  payments: {
    confirmSuccess: 'Zahlungsbestaetigung erfolgreich eingereicht',
    confirmError: 'Fehler beim Einreichen der Zahlungsbestaetigung',
    cancelSuccess: 'Zahlungsbestaetigung storniert',
    cancelError: 'Fehler beim Stornieren',
  },
  complaints: {
    createSuccess: 'Reklamation erfolgreich eingereicht',
    createError: 'Fehler beim Einreichen der Reklamation',
    addInfoSuccess: 'Information hinzugefuegt',
    addInfoError: 'Fehler beim Hinzufügen der Information',
  },
  documents: {
    uploadSuccess: 'Dokument erfolgreich hochgeladen',
    uploadError: 'Fehler beim Hochladen des Dokuments',
    deleteSuccess: 'Dokument geloescht',
    deleteError: 'Fehler beim Loeschen des Dokuments',
  },
  messages: {
    sendSuccess: 'Nachricht erfolgreich gesendet',
    sendError: 'Fehler beim Senden der Nachricht',
    markReadSuccess: 'Als gelesen markiert',
    markAllReadSuccess: 'Alle Nachrichten als gelesen markiert',
  },
} as const;

// ============================================================================
// AUTH HOOKS
// ============================================================================

/**
 * Hook for portal login
 */
export function usePortalLogin(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: PortalLoginRequest) => portalApi.auth.login(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.all });
      toast({
        title: PORTAL_TOAST_MESSAGES.auth.loginSuccess,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.auth.loginError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

/**
 * Hook for portal logout
 */
export function usePortalLogout(options?: {
  onSuccess?: () => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => portalApi.auth.logout(),
    onSuccess: () => {
      queryClient.clear();
      toast({
        title: PORTAL_TOAST_MESSAGES.auth.logoutSuccess,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onSettled: () => {
      // Always clear auth even on error
      clearPortalAuth();
    },
  });
}

/**
 * Hook for account activation
 */
export function usePortalActivate(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: PortalActivateRequest) => portalApi.auth.activate(data),
    onSuccess: () => {
      toast({
        title: PORTAL_TOAST_MESSAGES.auth.activateSuccess,
        description: 'Sie können sich jetzt anmelden',
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.auth.activateError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

/**
 * Hook for password change
 */
export function usePortalChangePassword(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: PortalChangePasswordRequest) =>
      portalApi.auth.changePassword(data),
    onSuccess: () => {
      toast({
        title: PORTAL_TOAST_MESSAGES.auth.passwordChangeSuccess,
        description: 'Bitte melden Sie sich erneut an',
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.auth.passwordChangeError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

/**
 * Hook to get current portal user
 */
export function usePortalUser() {
  return useQuery({
    queryKey: portalQueryKeys.me(),
    queryFn: () => portalApi.auth.getMe(),
    staleTime: STALE_TIMES.user,
    enabled: isPortalAuthenticated(),
    placeholderData: () => getPortalUser() ?? undefined,
  });
}

// ============================================================================
// INVOICE HOOKS
// ============================================================================

/**
 * Hook to list invoices
 */
export function usePortalInvoices(filter?: PortalInvoiceFilter) {
  return useQuery({
    queryKey: portalQueryKeys.invoiceList(filter),
    queryFn: () => portalApi.invoices.list(filter),
    staleTime: STALE_TIMES.invoices,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get invoice summary
 */
export function usePortalInvoiceSummary() {
  return useQuery({
    queryKey: portalQueryKeys.invoiceSummary(),
    queryFn: () => portalApi.invoices.getSummary(),
    staleTime: STALE_TIMES.invoiceSummary,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get open invoices
 */
export function usePortalOpenInvoices() {
  return useQuery({
    queryKey: portalQueryKeys.invoiceOpen(),
    queryFn: () => portalApi.invoices.getOpen(),
    staleTime: STALE_TIMES.invoices,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get invoice detail
 */
export function usePortalInvoiceDetail(invoiceId: string) {
  return useQuery({
    queryKey: portalQueryKeys.invoiceDetail(invoiceId),
    queryFn: () => portalApi.invoices.getDetail(invoiceId),
    staleTime: STALE_TIMES.invoices,
    enabled: isPortalAuthenticated() && !!invoiceId,
  });
}

// ============================================================================
// PAYMENT HOOKS
// ============================================================================

/**
 * Hook to confirm a payment
 */
export function usePortalConfirmPayment(options?: {
  onSuccess?: (confirmationId: string) => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: PortalPaymentConfirmRequest) =>
      portalApi.payments.confirmPayment(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.payments() });
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.invoices() });
      toast({
        title: PORTAL_TOAST_MESSAGES.payments.confirmSuccess,
        variant: 'success',
      });
      options?.onSuccess?.(result.confirmation_id);
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.payments.confirmError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

/**
 * Hook to list payment confirmations
 */
export function usePortalPayments(filter?: PortalPaymentFilter) {
  return useQuery({
    queryKey: portalQueryKeys.paymentList(filter),
    queryFn: () => portalApi.payments.list(filter),
    staleTime: STALE_TIMES.payments,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get payment detail
 */
export function usePortalPaymentDetail(confirmationId: string) {
  return useQuery({
    queryKey: portalQueryKeys.paymentDetail(confirmationId),
    queryFn: () => portalApi.payments.getDetail(confirmationId),
    staleTime: STALE_TIMES.payments,
    enabled: isPortalAuthenticated() && !!confirmationId,
  });
}

/**
 * Hook to cancel a payment confirmation
 */
export function usePortalCancelPayment(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (confirmationId: string) =>
      portalApi.payments.cancel(confirmationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.payments() });
      toast({
        title: PORTAL_TOAST_MESSAGES.payments.cancelSuccess,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.payments.cancelError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ============================================================================
// COMPLAINT HOOKS
// ============================================================================

/**
 * Hook to get complaint types
 */
export function usePortalComplaintTypes() {
  return useQuery({
    queryKey: portalQueryKeys.complaintTypes(),
    queryFn: () => portalApi.complaints.getTypes(),
    staleTime: STALE_TIMES.complaintTypes,
  });
}

/**
 * Hook to create a complaint
 */
export function usePortalCreateComplaint(options?: {
  onSuccess?: (complaintId: string, referenceNumber: string) => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: PortalComplaintCreateRequest) =>
      portalApi.complaints.create(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.complaints() });
      toast({
        title: PORTAL_TOAST_MESSAGES.complaints.createSuccess,
        description: `Referenznummer: ${result.reference_number}`,
        variant: 'success',
      });
      options?.onSuccess?.(result.complaint_id, result.reference_number);
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.complaints.createError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

/**
 * Hook to list complaints
 */
export function usePortalComplaints(filter?: PortalComplaintFilter) {
  return useQuery({
    queryKey: portalQueryKeys.complaintList(filter),
    queryFn: () => portalApi.complaints.list(filter),
    staleTime: STALE_TIMES.complaints,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get complaint summary
 */
export function usePortalComplaintSummary() {
  return useQuery({
    queryKey: portalQueryKeys.complaintSummary(),
    queryFn: () => portalApi.complaints.getSummary(),
    staleTime: STALE_TIMES.complaints,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get complaint detail
 */
export function usePortalComplaintDetail(complaintId: string) {
  return useQuery({
    queryKey: portalQueryKeys.complaintDetail(complaintId),
    queryFn: () => portalApi.complaints.getDetail(complaintId),
    staleTime: STALE_TIMES.complaints,
    enabled: isPortalAuthenticated() && !!complaintId,
  });
}

/**
 * Hook to add info to a complaint
 */
export function usePortalAddComplaintInfo(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({
      complaintId,
      data,
    }: {
      complaintId: string;
      data: PortalComplaintAddInfoRequest;
    }) => portalApi.complaints.addInfo(complaintId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: portalQueryKeys.complaintDetail(variables.complaintId),
      });
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.complaints() });
      toast({
        title: PORTAL_TOAST_MESSAGES.complaints.addInfoSuccess,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.complaints.addInfoError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ============================================================================
// DOCUMENT HOOKS
// ============================================================================

/**
 * Hook to get allowed file types
 */
export function usePortalAllowedFileTypes() {
  return useQuery({
    queryKey: portalQueryKeys.documentTypes(),
    queryFn: () => portalApi.documents.getAllowedTypes(),
    staleTime: STALE_TIMES.documentTypes,
  });
}

/**
 * Hook to upload a document
 */
export function usePortalUploadDocument(options?: {
  onSuccess?: (documentId: string) => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({
      file,
      options: uploadOptions,
    }: {
      file: File;
      options?: {
        description?: string;
        document_type?: string;
        complaint_id?: string;
        message_id?: string;
      };
    }) => portalApi.documents.upload(file, uploadOptions),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.documents() });
      toast({
        title: PORTAL_TOAST_MESSAGES.documents.uploadSuccess,
        description: result.filename,
        variant: 'success',
      });
      options?.onSuccess?.(result.document_id);
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.documents.uploadError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

/**
 * Hook to list documents
 */
export function usePortalDocuments(filter?: PortalDocumentFilter) {
  return useQuery({
    queryKey: portalQueryKeys.documentList(filter),
    queryFn: () => portalApi.documents.list(filter),
    staleTime: STALE_TIMES.documents,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get document detail
 */
export function usePortalDocumentDetail(documentId: string) {
  return useQuery({
    queryKey: portalQueryKeys.documentDetail(documentId),
    queryFn: () => portalApi.documents.getDetail(documentId),
    staleTime: STALE_TIMES.documents,
    enabled: isPortalAuthenticated() && !!documentId,
  });
}

/**
 * Hook to delete a document
 */
export function usePortalDeleteDocument(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (documentId: string) => portalApi.documents.delete(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.documents() });
      toast({
        title: PORTAL_TOAST_MESSAGES.documents.deleteSuccess,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.documents.deleteError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ============================================================================
// MESSAGE HOOKS
// ============================================================================

/**
 * Hook to send a message
 */
export function usePortalSendMessage(options?: {
  onSuccess?: (messageId: string) => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: PortalMessageSendRequest) =>
      portalApi.messages.send(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.messages() });
      toast({
        title: PORTAL_TOAST_MESSAGES.messages.sendSuccess,
        variant: 'success',
      });
      options?.onSuccess?.(result.message_id);
    },
    onError: (error: Error) => {
      toast({
        title: PORTAL_TOAST_MESSAGES.messages.sendError,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

/**
 * Hook to list messages
 */
export function usePortalMessages(filter?: PortalMessageFilter) {
  return useQuery({
    queryKey: portalQueryKeys.messageList(filter),
    queryFn: () => portalApi.messages.list(filter),
    staleTime: STALE_TIMES.messages,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get conversation
 */
export function usePortalConversation(complaintId?: string, limit = 100) {
  return useQuery({
    queryKey: portalQueryKeys.messageConversation(complaintId),
    queryFn: () => portalApi.messages.getConversation(complaintId, limit),
    staleTime: STALE_TIMES.messages,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get message summary
 */
export function usePortalMessageSummary() {
  return useQuery({
    queryKey: portalQueryKeys.messageSummary(),
    queryFn: () => portalApi.messages.getSummary(),
    staleTime: STALE_TIMES.messages,
    enabled: isPortalAuthenticated(),
  });
}

/**
 * Hook to get unread count
 */
export function usePortalUnreadCount() {
  return useQuery({
    queryKey: portalQueryKeys.messageUnreadCount(),
    queryFn: () => portalApi.messages.getUnreadCount(),
    staleTime: STALE_TIMES.unreadCount,
    enabled: isPortalAuthenticated(),
    refetchInterval: 60 * 1000, // Refetch every minute
  });
}

/**
 * Hook to mark a message as read
 */
export function usePortalMarkMessageRead(options?: {
  onSuccess?: () => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (messageId: string) => portalApi.messages.markRead(messageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.messages() });
      queryClient.invalidateQueries({
        queryKey: portalQueryKeys.messageUnreadCount(),
      });
      toast({
        title: PORTAL_TOAST_MESSAGES.messages.markReadSuccess,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
  });
}

/**
 * Hook to mark all messages as read
 */
export function usePortalMarkAllMessagesRead(options?: {
  onSuccess?: (count: number) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => portalApi.messages.markAllRead(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: portalQueryKeys.messages() });
      queryClient.invalidateQueries({
        queryKey: portalQueryKeys.messageUnreadCount(),
      });
      toast({
        title: PORTAL_TOAST_MESSAGES.messages.markAllReadSuccess,
        description: `${result.marked_count} Nachrichten`,
        variant: 'success',
      });
      options?.onSuccess?.(result.marked_count);
    },
  });
}

// ============================================================================
// UTILITY HOOKS
// ============================================================================

/**
 * Hook to check if portal user is authenticated
 */
export function usePortalAuth() {
  const user = usePortalUser();

  return {
    isAuthenticated: isPortalAuthenticated(),
    user: user.data,
    isLoading: user.isLoading,
    error: user.error,
  };
}

/**
 * Hook to prefetch portal data for dashboard
 */
export function usePrefetchPortalDashboard() {
  const queryClient = useQueryClient();

  const prefetch = () => {
    if (!isPortalAuthenticated()) return;

    // Prefetch all dashboard data in parallel
    queryClient.prefetchQuery({
      queryKey: portalQueryKeys.invoiceSummary(),
      queryFn: () => portalApi.invoices.getSummary(),
    });

    queryClient.prefetchQuery({
      queryKey: portalQueryKeys.invoiceOpen(),
      queryFn: () => portalApi.invoices.getOpen(),
    });

    queryClient.prefetchQuery({
      queryKey: portalQueryKeys.complaintSummary(),
      queryFn: () => portalApi.complaints.getSummary(),
    });

    queryClient.prefetchQuery({
      queryKey: portalQueryKeys.messageSummary(),
      queryFn: () => portalApi.messages.getSummary(),
    });

    queryClient.prefetchQuery({
      queryKey: portalQueryKeys.messageUnreadCount(),
      queryFn: () => portalApi.messages.getUnreadCount(),
    });
  };

  return { prefetch };
}
