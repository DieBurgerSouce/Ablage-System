/**
 * ML Dashboard Route
 *
 * Dashboard für Machine Learning Performance und Lernfortschritt.
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { MLDashboardPage } from '@/features/ml-dashboard';

export const Route = createFileRoute('/ml-dashboard')({
    // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
    beforeLoad: () => frozenModuleGuard('ai_speculative'),
    component: MLDashboardPage,
});
