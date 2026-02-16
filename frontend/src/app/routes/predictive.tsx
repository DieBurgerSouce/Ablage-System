// Predictive Dashboard Route
// Route: /predictive (Phase 7.2: KI-Vorhersagen)

import { createFileRoute } from '@tanstack/react-router';
import { PredictiveDashboardPage } from '@/features/predictive';

export const Route = createFileRoute('/predictive')({
  component: PredictiveDashboardPage,
});
