/**
 * Privat Index Route
 *
 * Dashboard für persönliche Dokumentenverwaltung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PrivatPage } from '@/features/privat';

export const Route = createFileRoute('/privat/')({
  component: PrivatPage,
});
