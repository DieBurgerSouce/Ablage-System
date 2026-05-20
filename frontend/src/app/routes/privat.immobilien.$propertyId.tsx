/**
 * Privat Immobilien Detail Route
 *
 * Detailansicht einer einzelnen Immobilie.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PropertyDetailPage } from '@/features/privat';

export const Route = createFileRoute('/privat/immobilien/$propertyId')({
  component: PropertyDetailPage,
});
