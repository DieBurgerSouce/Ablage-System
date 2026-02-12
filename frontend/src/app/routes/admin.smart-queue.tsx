/**
 * Smart OCR Queue Route
 *
 * Admin-Bereich für intelligente Warteschlangen-Verwaltung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { SmartQueuePage } from '@/features/admin/smart-queue';

export const Route = createFileRoute('/admin/smart-queue')({
  component: SmartQueuePage,
});
