/**
 * Nachlassplanung Route
 *
 * Route: /privat/nachlassplanung
 *
 * Features:
 * - Vermögensverteilung
 * - Erbschaftsteuer-Rechner (Klasse I, II, III)
 * - Freibeträge-Übersicht
 * - Vollmachten-Verwaltung
 * - Nießbrauch-Bewertung
 */

import { createFileRoute } from '@tanstack/react-router';
import { EstatePlanningPage } from '@/features/privat/estate/EstatePlanningPage';

export const Route = createFileRoute('/privat/nachlassplanung')({
  component: EstatePlanningPage,
});
