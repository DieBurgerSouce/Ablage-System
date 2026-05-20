/**
 * Berichte Builder Route - Visueller Report-Builder
 *
 * Multi-Step-Formular zum Erstellen neuer Berichte.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ReportBuilderPage } from '@/features/reports/components/ReportBuilderPage';

export const Route = createFileRoute('/berichte/builder')({
  component: ReportBuilderPage,
});
