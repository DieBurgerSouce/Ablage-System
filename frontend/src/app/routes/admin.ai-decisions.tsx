/**
 * Admin AI Decisions Route
 *
 * Route: /admin/ai-decisions
 *
 * Dashboard für AI/ML Entscheidungen, Drift Detection,
 * A/B Testing und Lernfortschritt.
 */

import { createFileRoute } from '@tanstack/react-router';
import { AIDecisionDashboard } from '@/features/ai-decisions';

export const Route = createFileRoute('/admin/ai-decisions')({
  component: AIDecisionsPage,
});

function AIDecisionsPage() {
  return <AIDecisionDashboard />;
}
