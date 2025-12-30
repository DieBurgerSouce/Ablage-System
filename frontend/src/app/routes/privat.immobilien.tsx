/**
 * Privat Immobilien Route
 *
 * Immobilien-Übersicht und -Verwaltung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PropertiesPage } from '@/features/privat';

export const Route = createFileRoute('/privat/immobilien')({
  component: PropertiesPage,
});
