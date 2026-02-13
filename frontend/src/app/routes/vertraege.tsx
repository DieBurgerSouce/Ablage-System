/**
 * Verträge Route
 *
 * B2B-Vertragsmanagement mit Fristen und Verlängerungsoptionen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ContractsPage } from '@/features/contracts';

export const Route = createFileRoute('/vertraege')({
  component: ContractsPage,
});
