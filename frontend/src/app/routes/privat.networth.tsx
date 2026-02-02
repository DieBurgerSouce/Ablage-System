/**
 * Privat Net Worth Route
 *
 * Nettovermoegen-Dashboard mit Vermoegensaufstellung,
 * Verbindlichkeiten und historischer Entwicklung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { NetWorthDashboard } from '@/features/privat';

export const Route = createFileRoute('/privat/networth')({
  component: NetWorthDashboard,
});
