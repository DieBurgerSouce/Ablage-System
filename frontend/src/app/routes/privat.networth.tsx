/**
 * Privat Net Worth Route
 *
 * Nettovermögen-Dashboard mit Vermögensaufstellung,
 * Verbindlichkeiten und historischer Entwicklung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { NetWorthDashboard } from '@/features/privat';

export const Route = createFileRoute('/privat/networth')({
  component: NetWorthDashboard,
});
