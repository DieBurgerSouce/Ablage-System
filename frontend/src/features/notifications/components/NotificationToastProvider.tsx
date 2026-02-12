/**
 * Notification Toast Provider
 *
 * Wird im Root-Layout eingebunden und abonniert Echtzeit-Benachrichtigungen
 * über WebSocket. Rendert keine eigene UI - nur Hook-Aktivierung.
 */

import { useNotificationToast } from '../hooks/useNotificationToast';

export function NotificationToastProvider() {
  useNotificationToast();
  return null; // Keine eigene UI - nur Hooks
}
