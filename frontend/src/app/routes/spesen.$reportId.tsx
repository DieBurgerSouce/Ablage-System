/**
 * Spesenabrechnung Detail Route
 *
 * Detailansicht einer Spesenabrechnung mit allen Positionen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ExpenseReportDetailPage } from '@/features/expenses';

export const Route = createFileRoute('/spesen/$reportId')({
  component: ExpenseReportDetailPage,
});
