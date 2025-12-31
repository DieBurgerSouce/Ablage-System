/**
 * Privat Index Route
 *
 * Dashboard fuer persoenliche Dokumentenverwaltung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PrivatPage } from '@/features/privat';

export const Route = createFileRoute('/privat/')({
  component: PrivatPage,
});
