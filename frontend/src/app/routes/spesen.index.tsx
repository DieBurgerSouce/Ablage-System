/**
 * Spesen Index Route
 *
 * Hauptseite für Spesenabrechnungen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ExpensesPage } from '@/features/expenses';

export const Route = createFileRoute('/spesen/')({
  component: ExpensesPage,
});
