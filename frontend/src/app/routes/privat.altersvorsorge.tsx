/**
 * Altersvorsorge Route
 *
 * Route: /privat/altersvorsorge
 *
 * Features:
 * - Rentenlücken-Rechner
 * - Rentenpunkte-Übersicht
 * - Monte-Carlo-Simulation
 * - Entnahmestrategien (4%-Regel)
 * - Riester/Rürup Optimierung
 */

import { createFileRoute } from '@tanstack/react-router';
import { RetirementPlanningPage } from '@/features/privat/retirement/RetirementPlanningPage';

export const Route = createFileRoute('/privat/altersvorsorge')({
  component: RetirementPlanningPage,
});
