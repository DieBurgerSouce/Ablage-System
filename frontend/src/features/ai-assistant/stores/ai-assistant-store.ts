/**
 * AI Assistant Global Store
 *
 * Zustand store for managing global AI assistant state.
 * Persists session across page navigation.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export type AIAssistantView = 'minimized' | 'expanded' | 'fullscreen';
export type PageContextType =
  | 'dashboard'
  | 'documents'
  | 'document-detail'
  | 'entities'
  | 'entity-detail'
  | 'invoices'
  | 'banking'
  | 'validation'
  | 'reports'
  | 'admin'
  | 'settings'
  | 'unknown';

export interface PageContext {
  type: PageContextType;
  documentId?: string;
  entityId?: string;
  entityName?: string;
  additionalContext?: Record<string, unknown>;
}

export interface AIAssistantState {
  // View state
  view: AIAssistantView;
  isOpen: boolean;

  // Session
  sessionId: string | null;

  // Context
  pageContext: PageContext;

  // Unread
  unreadCount: number;
  lastReadAt: string | null;

  // Quick actions
  showQuickActions: boolean;

  // Actions
  setView: (view: AIAssistantView) => void;
  open: () => void;
  close: () => void;
  toggle: () => void;
  setSessionId: (sessionId: string | null) => void;
  setPageContext: (context: PageContext) => void;
  incrementUnread: () => void;
  markAsRead: () => void;
  toggleQuickActions: () => void;
  reset: () => void;
}

const initialState = {
  view: 'minimized' as AIAssistantView,
  isOpen: false,
  sessionId: null,
  pageContext: { type: 'unknown' as PageContextType },
  unreadCount: 0,
  lastReadAt: null,
  showQuickActions: false,
};

export const useAIAssistantStore = create<AIAssistantState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setView: (view) => set({ view }),

      open: () => set({ isOpen: true, view: 'expanded', unreadCount: 0, lastReadAt: new Date().toISOString() }),

      close: () => set({ isOpen: false, view: 'minimized' }),

      toggle: () => {
        const { isOpen } = get();
        if (isOpen) {
          set({ isOpen: false, view: 'minimized' });
        } else {
          set({ isOpen: true, view: 'expanded', unreadCount: 0, lastReadAt: new Date().toISOString() });
        }
      },

      setSessionId: (sessionId) => set({ sessionId }),

      setPageContext: (pageContext) => set({ pageContext }),

      incrementUnread: () => {
        const { isOpen, unreadCount } = get();
        if (!isOpen) {
          set({ unreadCount: unreadCount + 1 });
        }
      },

      markAsRead: () => set({ unreadCount: 0, lastReadAt: new Date().toISOString() }),

      toggleQuickActions: () => set((state) => ({ showQuickActions: !state.showQuickActions })),

      reset: () => set(initialState),
    }),
    {
      name: 'ai-assistant-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        sessionId: state.sessionId,
        lastReadAt: state.lastReadAt,
      }),
    }
  )
);
