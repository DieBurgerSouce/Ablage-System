/**
 * Document Comparison Route
 *
 * Route für den Dokumentenvergleich.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ComparePage } from '@/features/documents/compare';

export const Route = createFileRoute('/documents/compare')({
  component: ComparePage,
});
