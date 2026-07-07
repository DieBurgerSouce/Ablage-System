/**
 * Ad-Hoc Reporting List Route
 * German Enterprise Document Platform
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { ReportListPage } from '@/features/adhoc-reporting';

export const Route = createFileRoute('/adhoc-reporting')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: ReportListPage,
});
