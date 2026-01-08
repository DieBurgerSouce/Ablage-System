/**
 * Privat Space Detail Route
 *
 * Zeigt die Detailansicht eines Bereichs mit allen Kategorien.
 */

import { createFileRoute } from '@tanstack/react-router';
import { SpaceDetailPage } from '@/features/privat';

export const Route = createFileRoute('/privat/spaces/$spaceId')({
  component: SpaceDetailPage,
});
