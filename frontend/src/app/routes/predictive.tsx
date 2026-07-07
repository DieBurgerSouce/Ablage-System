// Predictive Dashboard Route
// Route: /predictive (Phase 7.2: KI-Vorhersagen)

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { PredictiveDashboardPage } from '@/features/predictive';

export const Route = createFileRoute('/predictive')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: PredictiveDashboardPage,
});
