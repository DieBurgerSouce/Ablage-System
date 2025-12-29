/**
 * Kasse Index Route
 *
 * Hauptseite fuer das Kassenbuch mit Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CashDashboard } from '@/features/cash';

export const Route = createFileRoute('/kasse/')({
  component: CashDashboard,
});
