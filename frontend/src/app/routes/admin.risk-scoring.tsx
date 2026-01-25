/**
 * Risk Scoring Admin Route
 *
 * Route fuer das Risk Scoring Dashboard im Admin-Bereich.
 */

import { createFileRoute } from '@tanstack/react-router';
import { RiskDashboard } from '@/features/risk-scoring';

export const Route = createFileRoute('/admin/risk-scoring')({
  component: RiskDashboard,
});
