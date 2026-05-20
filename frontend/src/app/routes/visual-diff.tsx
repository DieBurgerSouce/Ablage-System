/**
 * Visual Diff Route - Dokumenten-Vergleich
 *
 * Seite-an-Seite Vergleich von Dokumentversionen mit Timeline.
 */

import { createFileRoute } from '@tanstack/react-router';
import { VisualDiffPage } from '@/features/visual-diff';

export const Route = createFileRoute('/visual-diff')({
  component: VisualDiffPage,
});
