/**
 * Privat Notfall Route
 *
 * Notfallzugriff und Vertrauenspersonen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { EmergencyPage } from '@/features/privat';

export const Route = createFileRoute('/privat/notfall')({
  component: EmergencyPage,
});
