/**
 * Widget Administration Route
 *
 * Verwaltung von Dashboard-Widgets, Berechtigungen und Layout-Vorlagen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { WidgetAdminPage } from '@/features/admin/widgets';

export const Route = createFileRoute('/admin/widgets')({
  component: WidgetAdminPage,
});
