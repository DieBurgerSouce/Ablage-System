/**
 * ESG Berichte - Reports Page
 *
 * Generiert und verwaltet ESG-Berichte für Compliance und Stakeholder.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ReportsPage } from '@/features/esg';

export const Route = createFileRoute('/admin/esg/reports')({
    component: ReportsPage,
});
