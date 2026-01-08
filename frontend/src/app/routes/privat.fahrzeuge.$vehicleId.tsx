/**
 * Privat Fahrzeuge Detail Route
 *
 * Detailansicht eines einzelnen Fahrzeugs.
 */

import { createFileRoute } from '@tanstack/react-router';
import { VehicleDetailPage } from '@/features/privat';

export const Route = createFileRoute('/privat/fahrzeuge/$vehicleId')({
  component: VehicleDetailPage,
});
