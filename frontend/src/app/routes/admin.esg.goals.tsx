/**
 * ESG Ziele - Goals Page
 *
 * Verwaltet ESG-Ziele und deren Fortschritt.
 */

import { createFileRoute } from '@tanstack/react-router';
import { GoalsPage } from '@/features/esg';

export const Route = createFileRoute('/admin/esg/goals')({
    component: GoalsPage,
});
