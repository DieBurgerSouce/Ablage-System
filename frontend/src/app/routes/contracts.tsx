/**
 * Contracts Route - Vertragsmanagement Dashboard
 *
 * Route: /contracts
 *
 * Features:
 * - Vertragsübersicht mit KPIs
 * - Fristen-Warnungen
 * - Kalenderansicht für Fristen
 * - iCal-Export
 * - Infinite Scroll für Vertragsliste
 */

import { createFileRoute } from '@tanstack/react-router';
import { ContractsPage } from '@/features/contracts';

export const Route = createFileRoute('/contracts')({
  component: ContractsPage,
});
