/**
 * Privat Versicherungen Route
 *
 * Versicherungen-Übersicht und -Verwaltung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { InsurancesPage } from '@/features/privat';

export const Route = createFileRoute('/privat/versicherungen')({
  component: InsurancesPage,
});
