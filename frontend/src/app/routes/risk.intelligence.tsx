/**
 * Risk Intelligence Route
 *
 * Erweiterte Risikoanalyse mit Branchen-Benchmarks, Trends und Netzwerk-Analyse.
 */

import { createFileRoute } from '@tanstack/react-router';
import { RiskIntelligenceDashboard } from '@/features/risk-intelligence';

export const Route = createFileRoute('/risk/intelligence')({
  component: RiskIntelligencePage,
});

function RiskIntelligencePage() {
  return <RiskIntelligenceDashboard />;
}
