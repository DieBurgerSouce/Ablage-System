/**
 * Notification Preferences Route
 *
 * Route: /settings/notifications
 *
 * Features:
 * - Kanal-Einstellungen (Email, Slack, SMS, Push, Teams)
 * - Schweregrad-Matrix
 * - Ruhezeiten-Konfiguration
 * - GDPR Opt-in für SMS/WhatsApp
 */

import { createFileRoute } from '@tanstack/react-router';
import { NotificationPreferencesPage } from '@/features/settings/notifications/NotificationPreferencesPage';

export const Route = createFileRoute('/settings/notifications')({
  component: NotificationPreferencesPage,
});
