/**
 * Berichte Index Route - Reports Dashboard
 *
 * Zeigt die Haupt-Übersicht mit Meine Berichte, Vorlagen und Geplante Exporte.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ReportsPage } from '@/features/reports/components/ReportsPage';

export const Route = createFileRoute('/berichte/')({
  component: ReportsPage,
});
