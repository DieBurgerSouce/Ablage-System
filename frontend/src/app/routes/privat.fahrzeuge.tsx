/**
 * Privat Fahrzeuge Route
 *
 * Fahrzeuge-Übersicht und -Verwaltung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { VehiclesPage } from '@/features/privat';

export const Route = createFileRoute('/privat/fahrzeuge')({
  component: VehiclesPage,
});
