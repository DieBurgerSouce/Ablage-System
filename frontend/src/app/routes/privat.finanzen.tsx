/**
 * Privat Finanzen Route
 *
 * Kredite und Geldanlagen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { FinancesPage } from '@/features/privat';

export const Route = createFileRoute('/privat/finanzen')({
  component: FinancesPage,
});
