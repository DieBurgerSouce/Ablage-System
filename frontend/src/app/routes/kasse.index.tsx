/**
 * Kasse Index Route
 *
 * Hauptseite für das Kassenbuch mit Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CashDashboard } from '@/features/cash';

export const Route = createFileRoute('/kasse/')({
  component: CashDashboard,
});
