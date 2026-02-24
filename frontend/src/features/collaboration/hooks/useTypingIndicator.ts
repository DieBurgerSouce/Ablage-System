/**
 * useTypingIndicator - Hook fuer Echtzeit-Tipp-Indikatoren
 *
 * Sendet typing_start bei Tastendruck und typing_stop nach 3s Idle.
 * Empfaengt typing_indicator Events von anderen Usern.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useRawMessage, useWebSocketSend } from '@/lib/websocket';

interface TypingUser {
  user_id: string;
}

interface UseTypingIndicatorOptions {
  documentId: string;
  enabled?: boolean;
}

const TYPING_TIMEOUT_MS = 3000;

export function useTypingIndicator({ documentId, enabled = true }: UseTypingIndicatorOptions) {
  const [typingUsers, setTypingUsers] = useState<TypingUser[]>([]);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTypingRef = useRef(false);
  const cleanupTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const sendMessage = useWebSocketSend();

  // Empfange typing_indicator Messages von anderen Usern
  useRawMessage('typing_indicator', useCallback((message) => {
    if (!enabled || !documentId) return;

    const payload = message.payload as {
      user_id?: string;
      document_id?: string;
      is_typing?: boolean;
    };

    if (payload.document_id !== documentId) return;
    const userId = payload.user_id;
    if (!userId) return;

    if (payload.is_typing) {
      setTypingUsers((prev) => {
        if (prev.some((u) => u.user_id === userId)) return prev;
        return [...prev, { user_id: userId }];
      });

      // Auto-Cleanup nach Timeout (falls typing_stop nie kommt)
      const existingTimer = cleanupTimersRef.current.get(userId);
      if (existingTimer) {
        clearTimeout(existingTimer);
      }
      const timer = setTimeout(() => {
        setTypingUsers((prev) => prev.filter((u) => u.user_id !== userId));
        cleanupTimersRef.current.delete(userId);
      }, TYPING_TIMEOUT_MS * 2);
      cleanupTimersRef.current.set(userId, timer);
    } else {
      setTypingUsers((prev) => prev.filter((u) => u.user_id !== userId));
      const existingTimer = cleanupTimersRef.current.get(userId);
      if (existingTimer) {
        clearTimeout(existingTimer);
        cleanupTimersRef.current.delete(userId);
      }
    }
  }, [documentId, enabled]));

  // Sende typing_start/typing_stop
  const notifyTyping = useCallback(() => {
    if (!enabled || !documentId) return;

    if (!isTypingRef.current) {
      isTypingRef.current = true;
      sendMessage({
        type: 'typing_start',
        document_id: documentId,
      });
    }

    // Reset timeout
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }

    typingTimeoutRef.current = setTimeout(() => {
      isTypingRef.current = false;
      sendMessage({
        type: 'typing_stop',
        document_id: documentId,
      });
    }, TYPING_TIMEOUT_MS);
  }, [documentId, enabled, sendMessage]);

  // Cleanup bei Unmount
  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }
      // Cleanup-Timer fuer andere User aufraumen
      cleanupTimersRef.current.forEach((timer) => clearTimeout(timer));
      cleanupTimersRef.current.clear();
    };
  }, []);

  // Sende typing_stop wenn documentId sich aendert oder Component unmountet
  useEffect(() => {
    return () => {
      if (isTypingRef.current) {
        isTypingRef.current = false;
        sendMessage({
          type: 'typing_stop',
          document_id: documentId,
        });
      }
    };
  }, [documentId, sendMessage]);

  return {
    typingUsers,
    notifyTyping,
  };
}
