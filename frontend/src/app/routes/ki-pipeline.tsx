/**
 * KI-Pipeline Route
 * Main KI-Pipeline page at /ki-pipeline
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { KIPipelinePage } from '@/features/ki-pipeline';

export const Route = createFileRoute('/ki-pipeline')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: KIPipelinePage,
});
